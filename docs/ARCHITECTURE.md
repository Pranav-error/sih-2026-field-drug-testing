# Digital Companion for Field Drug Testing — Architecture

**SIH26231** · Ministry of Home Affairs / Narcotics Control Bureau · Software · MedTech/BioTech/HealthTech
Deadline: 30 September 2026

---

## 0. The problem restated

The problem statement asks for an app that photographs a colorimetric field-test strip, classifies
the colour, and produces a tamper-evident record.

**That is two problems wearing one coat, and they are not equally hard.**

- *Stated problem:* classify a colour change. This is an undergraduate computer-vision exercise.
- *Actual problem NCB has:* **a presumptive field test result is not usable as documentary evidence.**
  The PS says so explicitly — "leaves no verifiable record that a test was actually conducted at a
  given place and time. As a result, field test outcomes cannot presently be relied upon as
  documentary evidence."

Every design decision below follows from treating the second sentence as the specification and the
first as a subroutine.

### Design axiom

> The classifier is not the product. The **record** is the product.
> The classifier is one signed input to it, and it must be able to say "I don't know."

---

## 1. Constraints taken from the PS

| Constraint | Source | Consequence for design |
|---|---|---|
| No new hardware | PS text, verbatim | Phone camera is the instrument; a printed card is the only physical artefact |
| Works alongside *existing* kits | PS text | Must be **kit-agnostic** — cannot depend on a vendor's serialised pouch |
| Outcome categories incl. inconclusive | PS text | Abstention is a required output class, not a failure mode |
| Timestamp + GPS + operator ID + image hash | PS text | These are the minimum record fields; we treat them as the floor, not the ceiling |
| Presumptive only, not confirmatory | PS "Note to Participants" | The system must be *legible about its own uncertainty* or it misleads a court |
| No dataset provided | `dataset_link` empty | Data acquisition strategy is part of the deliverable (see §7) |

---

## 2. System overview

```
                      ┌─────────────────────────────────────────────┐
   physical world     │  existing colorimetric kit  +  printed      │
                      │  reference colour card (matte, free)        │
                      └───────────────────┬─────────────────────────┘
                                          │  single camera frame
┌─────────────────────────────────────────▼─────────────────────────────────────────┐
│ L1  COLORIMETRIC NORMALISATION            (deterministic, no learning)            │
│     card detect → homography → patch sample → INUC → device RGB→CIELAB transform  │
│     out: ΔE-comparable Lab* triple + calibration-quality score                    │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L2  CLASSIFICATION WITH ABSTENTION        (conformal, bounded error)              │
│     Lab* → reagent-specific decision region → {positive, negative, inconclusive}  │
│     out: label + prediction set + calibrated confidence                           │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L3  LOCATION CORROBORATION BUNDLE         (multi-encoding agreement)              │
│     GNSS fix + raw measurements/SNR + Wi-Fi BSSID set + cell ID + motion history  │
│     out: location claim + independent-corroboration score + spoof indicators      │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L4  EVIDENTIARY BINDING                   (hardware root of trust)                │
│     canonical CBOR → SHA-256 → sign in StrongBox/TEE → attach attestation chain   │
│     out: signed Field Test Record (FTR)                                           │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L5  APPEND-ONLY DEVICE LEDGER             (ordering + backdating resistance)      │
│     per-device hash chain, Merkle checkpoints anchored opportunistically          │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L6  STATUTORY OUTPUT                      (the part nobody else builds)           │
│     BSA §63 Schedule Part A certificate, auto-populated with hash + algorithm     │
│     NDPS Rules 2022 linkage fields · eSakshya/CCTNS-2.0 handoff envelope          │
├───────────────────────────────────────────────────────────────────────────────────┤
│ L7  INDEPENDENT OFFLINE VERIFIER          (separate binary, no server needed)     │
│     recompute · verify signature · walk attestation chain · replay hash chain     │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Layers 1–2 answer *what did the test say*. Layers 3–5 answer *can this be trusted*. Layer 6 answers
*is this admissible*. Layer 7 is what makes the whole thing meaningful to somebody who does not
trust us — which, in an adversarial proceeding, is everybody.

---

## 3. L1 — Colorimetric normalisation

The research is unambiguous that naive RGB off a phone camera is not a measurement. Ambient
illuminant, auto-white-balance, auto-exposure, and undisclosed vendor ISP processing all move the
numbers, and device-specific calibration materially changes accuracy.

### Pipeline

1. **Card detection.** Locate the reference card (ArUco/AprilTag fiducials at the corners — robust
   under partial occlusion and steep angles, and gives sub-pixel corner estimates for free).
2. **Homography rectification.** Four corners → planar warp. Removes perspective, fixes patch
   geometry, and lets us sample patches by known coordinates instead of by segmentation.
3. **Intensity non-uniformity correction (INUC).** A neutral grey field on the card gives a
   per-pixel illumination surface; divide it out. This handles the single biggest field problem —
   an officer's shadow falling across half the frame.
4. **Device transform.** Solve a per-device-model RGB→XYZ mapping (least squares over the card's
   known patch reflectances, polynomial or root-polynomial to absorb ISP nonlinearity). Convert to
   **CIELAB**, because ΔE distance in Lab is perceptually and physically meaningful in a way that
   Euclidean RGB distance is not.
5. **Patch extraction.** Sample the reaction region at fixed offsets from the card, with a trimmed
   mean over the region to reject specular highlights and dust.
6. **Calibration-quality score.** Residual error on the card's own patches after transform, plus
   dynamic range, plus blur estimate. **If the calibration is bad, the record says so** — this
   feeds abstention rather than being silently swallowed.

### Why deterministic first, learning second

A least-squares colour transform is auditable, explainable to a court, and cheap to defend. A CNN
that maps pixels to "positive" is none of those things. The learned component is confined to L2,
operating on *already-normalised* Lab values — so the model has ~3 input dimensions per patch, not
3×10⁶, which is also why it can be trained on a small honest dataset instead of a large dishonest one.

---

## 4. L2 — Classification with abstention

Reagent reactions are defined by known colour transitions (e.g. the reference literature describes
Marquis producing characteristic colour developments for different substance classes). So the
decision problem is: *which reference locus is this Lab point nearest, and is it near enough to say
anything at all?*

### Method

- Per-reagent, per-outcome **reference loci** in Lab, with empirical covariance.
- **Conformal prediction** over the distance statistic: calibrate a threshold on held-out data so
  that the prediction set contains the true label with probability ≥ 1−α, with a finite-sample
  guarantee that holds without distributional assumptions.
- Output is a **prediction set**, not an argmax:
  - singleton `{positive}` → report positive
  - singleton `{negative}` → report negative
  - `{positive, negative}` or `{}` → **inconclusive**, with the reason attached

### Why this is the right instrument

The PS demands an `inconclusive` category, and the Note to Participants stresses that this is a
*presumptive* result. Conformal prediction is the only common technique that turns "inconclusive"
from a heuristic softmax cutoff into a **quantity with a stated error bound** — "at the configured
risk level, the reported label is wrong at most α of the time on exchangeable data." That sentence
is defensible under cross-examination. "The model was 87% confident" is not.

It also degrades honestly: poor lighting or a damaged card widens the prediction set and pushes
toward abstention, rather than producing a confident wrong answer in exactly the conditions where a
confident wrong answer is most damaging.

---

## 5. L3 — Location corroboration

The PS asks for "GPS location." A bare GPS coordinate from an Android app is a number the app was
handed; mock-location tooling and rooted devices can supply any number desired.

We therefore capture a **bundle of mutually-constraining signals** and score their agreement:

| Signal | What it independently constrains | Cost to forge |
|---|---|---|
| Fused location fix | The claim itself | Trivial (mock provider) |
| Raw GNSS measurements + per-satellite C/N₀ | Sky view, constellation geometry at that time/place | High — must synthesise a plausible constellation |
| Wi-Fi BSSID neighbourhood | Physical radio environment | High — requires knowing real BSSIDs at target location |
| Serving cell ID / neighbour cells | Tower topology | High |
| Motion history since last record | Kinematic plausibility (no 200 km jumps) | Medium |
| Mock-location flag, root/Magisk indicators, developer settings | Device posture | Medium |

No single one is trusted. The record stores the bundle plus a **corroboration score**, and — this is
the important part — **stores the disagreements**. A record whose GPS says Karwar while its cell ID
says Bengaluru is not rejected; it is *recorded as inconsistent*, so the inconsistency is available
to the defence and the prosecution alike. Suppressing it would make the system a party to the case.

> This is the same structural idea as requiring a forged document to be edited coherently across
> several independent encodings: **no single move escapes all the channels.**

---

## 6. L4/L5 — Evidentiary binding and the device ledger

### The Field Test Record (FTR)

Canonical CBOR (deterministic encoding — byte-identical serialisation for identical content, which
matters because the hash is the legal artefact), containing:

```
ftr:
  schema_version
  record_uuid
  prev_record_hash                 ← chains to the previous FTR on this device
  captured_at                      ← device clock + monotonic uptime + last trusted-time delta
  operator:      { id, credential_ref, biometric_unlock_used }
  kit:           { reagent_type, lot (if legible), kit_photo_hash }
  card:          { card_id, print_batch }
  capture:
    raw_image_sha256               ← the untouched sensor frame
    normalised_image_sha256        ← the rectified/corrected derivative
    exif_subset_hash
  colorimetry:
    lab_values, calibration_residual, blur_metric, dynamic_range
  classification:
    model_id, model_sha256, alpha, prediction_set, label
  location_bundle:
    fix, gnss_raw_digest, wifi_bssid_set_digest, cell_ids,
    corroboration_score, spoof_indicators[]
  device:
    android_id_hash, os_patch_level, bootloader_state, verified_boot_state
```

Then:

```
digest      = SHA-256( canonical_cbor(ftr) )
signature   = Sign_StrongBox( digest )        ← key non-exportable, generated in secure element
attestation = KeyAttestationCertChain          ← chains to Google hardware root of trust
```

Key attestation is what converts "an app claims it signed this" into "**this device's secure
hardware signed this, and here is a certificate chain to a root the verifier already trusts, stating
the key was generated in a TEE or StrongBox and cannot be exported.**" The attestation record also
carries verified-boot state, so a record produced on a rooted or unlocked device is *detectable as
such at verification time*, years later, without needing the device in hand.

### Why a hash chain and not just per-record signatures

A signature proves authorship and integrity. It does **not** prove *when*, and it does not prevent
an operator from producing a record later and dating it earlier. `prev_record_hash` makes each
record depend on all previous records on that device, so:

- records cannot be reordered,
- records cannot be silently deleted from the middle,
- a backdated record cannot be inserted without forking the chain, which is visible.

When connectivity is available, the current chain head is **anchored** — pushed to a server (and/or
into the eSakshya/CCTNS upload) with a countersignature and timestamp. Anchoring is what bounds
backdating: a record can only be fabricated within the window since the last anchor, and that window
is itself recorded. Offline operation is fully supported, which matters because NDPS field work
happens in places without connectivity; the honest statement is *"this record was created no later
than the next anchor and no earlier than the previous one,"* and the app prints exactly that rather
than pretending to certified time it does not have.

---

## 7. Data strategy (the honest part)

Real NDPS presumptive kits use controlled reagents against controlled substances. A student team
cannot lawfully obtain either, and should not try. The design therefore separates the *optical*
problem from the *chemical* one and validates only what it can:

1. **Surrogate colorimetric ladders.** pH indicator strips across a buffer series, dye dilution
   series, and printed Munsell/Pantone patches. These reproduce the actual engineering difficulty —
   distinguishing nearby colours under uncontrolled illumination — without any controlled substance.
2. **Physical capture matrix.** Every target photographed across: 5+ illuminants (daylight, shade,
   tungsten, fluorescent, phone torch), 3 exposure biases, 4 angles, 3+ device models, wet/dry
   surfaces, and deliberately degraded cards (creased, faded, partially occluded).
3. **Synthetic augmentation** on top: illuminant shifts, shadow gradients, JPEG recompression,
   motion blur, sensor noise — used for robustness, never for the conformal calibration set.
4. **Conformal calibration** on a held-out physical split only.
5. **Held-out condition, not just held-out samples.** Report accuracy on an illuminant the model
   never saw. This is the generalisation claim that matters for field deployment.

**Stated in the submission, slide two, unprompted:**

> The classifier is trained and calibrated on surrogate colorimetric targets. Substituting NCB
> reagent colour standards is a *data change, not an architecture change*: L1 and L3–L7 are
> substance-independent by construction, and L2 requires only new reference loci and a
> recalibration pass.

Pre-empting this is worth more than hiding it. A judge who finds the gap themselves concludes the
team didn't think about chemistry; a team that names the gap and bounds it demonstrates exactly the
scientific caution that forensic work requires.

---

## 8. L6 — Statutory output

This layer is the differentiator and it is nearly free to build once L4/L5 exist.

### 8.1 BSA §63 certificate

Under the **Bharatiya Sakshya Adhiniyam, 2023**, §63 governs admissibility of electronic records and
replaced §65B of the Indian Evidence Act with effect from 1 July 2024. The accompanying certificate
follows a **Schedule format in two parts** — Part A completed by the person in charge of the device,
Part B by an expert — and it must **state the hash value of the record and the algorithm used**.

The app already computes exactly that hash. So it can emit a **pre-populated Part A** at the moment
of capture: device particulars, operator, time, the SHA-256 digest, and the algorithm name — leaving
only signature and the expert's Part B to be completed by humans.

> Verify the current Schedule wording and part-numbering against the bare Act before printing it in
> the submission. The requirement (two parts, two signatories, hash value + algorithm stated) is well
> established; exact field labels should be transcribed from the statute, not from a blog.

### 8.2 NDPS Rules 2022 linkage

The **NDPS (Seizure, Storage, Sampling and Disposal) Rules, 2022** (GSR 899(E), 23-12-2022)
consolidated and replaced the earlier standing orders, and govern inventory, photography and
representative sampling of seized material — carried out so far as possible in the presence of the
accused, with the §52A application typically moved within about 72 hours.

The FTR therefore carries fields to **link the presumptive field test to the formal seizure record**:
seizure memo reference, sample IDs drawn, witnesses present, and the time delta between field test
and sampling. This is what makes the artefact useful downstream instead of being an orphan file.

### 8.3 eSakshya / CCTNS-2.0 handoff — *do not build a parallel silo*

MHA already runs **eSakshya** (NCRB), a cloud application for audio-video recording of search and
seizure, built for BNSS's recording mandate and being integrated into CCTNS-2.0. Recordings carry
GPS and timestamps, upload into encrypted "Sakshya Locker" vaults on the National Government Cloud,
and — notably — when connectivity fails, the officer records locally, **generates a hash value**, and
uploads later.

That is the *same trust model this system uses*, run by the *same ministry that owns this problem
statement*. So the correct architectural posture is emphatically **not** to invent a competing
evidence store. It is to emit an FTR envelope that:

- carries its own hash in the form eSakshya's offline flow already expects,
- references the FIR / seizure memo so it lands in the right locker,
- and treats CCTNS-2.0 as the system of record.

Framing the deliverable as *"a presumptive-test evidence module that plugs into eSakshya"* rather
than *"our app"* is, on its own, likely worth more at the finale than any accuracy number.

---

## 9. L7 — The independent verifier

A separate, dependency-light binary (and a web build) that takes an FTR bundle and, **with no
network and no trust in the app**:

1. recomputes the canonical encoding and the digest,
2. verifies the signature,
3. walks the key attestation chain to the hardware root and reports the security level and
   verified-boot state,
4. replays the hash chain and reports gaps or forks,
5. recomputes image hashes against the supplied images,
6. re-runs L1/L2 from the raw image and checks the stored classification reproduces bit-for-bit,
7. prints a plain-language report: what is proven, what is merely asserted, and what is unverifiable.

Point 7 is the ethical core of the system. **The verifier must be as loud about what it cannot prove
as about what it can.** A tool that only ever says "VALID ✓" teaches courts to over-trust it, which
is a worse outcome than the subjective status quo.

---

## 10. Threat model — the adversary matrix

Present this instead of a confusion matrix. Each row is a live demo.

| # | Adversary move | Defeated by | Residual risk |
|---|---|---|---|
| 1 | Photograph a photo of a positive strip (replay) | **Two-view parallax.** Rectify both frames on the card plane; a folded 8 mm liveness tab must show the displacement the geometry predicts. A flat reproduction gives exactly zero, at any print quality. Print 0.1 px and screen 0.0 px against 28.2 px predicted — both refused. See [`PARALLAX.md`](PARALLAX.md) | **A synchronised stereo replay.** Parallax proves the scene *had* depth, not that it is there *now*. Needs the genuine stereo pair plus playback synchronised to a capture the attacker does not control — much harder than printing a photo, and still not defended |
| 2 | Edit the image after capture | `raw_image_sha256` bound into the signed record | None if verifier is run |
| 3 | Alter the stored result | Signature over canonical CBOR | None |
| 4 | Backdate a record | Hash chain + anchoring window | Fabrication *within* the unanchored window |
| 5 | Delete an unfavourable test | Chain gap is visible at verification | Chain truncation at the head (detected only by anchor mismatch) |
| 6 | Spoof GPS | Corroboration bundle; disagreements recorded, not hidden | Coordinated multi-channel spoof (very high cost) |
| 7 | Run on a rooted device to bypass checks | Verified-boot state inside the attestation record | Device compromise below the TEE |
| 8 | Substitute the model to bias results | `model_sha256` bound into the record; verifier re-runs it | None if verifier is run |
| 9 | Another officer signs as this operator | Biometric-gated key use; credential reference in record | Shared credentials — a policy failure, not a technical one |
| 10 | Poor lighting produces a wrong "positive" | Conformal abstention + calibration-quality gate | Bounded by α, and the bound is stated |

Rows 4, 5 and 9 are **acknowledged residual risks**, and row 1 retains a narrower one. Saying so out
loud is the difference between a forensic tool and a demo.

> Row 1 has been through both halves of that. It was claimed as defended on reasoning that did not
> survive contact with a simulated attacker; it was then moved to *not defended*; and it is now
> defended by two-view parallax — with the **synchronised stereo replay** that remains stated in the
> residual column rather than quietly dropped. A threat model that overstates its defences is worth
> less than no threat model at all.

---

## 11. Build plan (six people, ~3 weeks to internal round)

| Track | Owner | Week 1 | Week 2 | Week 3 |
|---|---|---|---|---|
| A — Colour pipeline | CV lead | Card + fiducials, homography, INUC | Device transform, Lab, quality score | Held-out-illuminant eval |
| B — Classification | ML | Reference loci, distance stat | Conformal calibration | Abstention tuning, ablation |
| C — Crypto/provenance | **Pranav** | CBOR schema, StrongBox keygen, attestation | Hash chain, anchoring, FTR v1 | Verifier binary |
| D — App | Flutter dev | Capture UX, card guidance overlay | Log, search, export | Offline queue, polish |
| E — Legal/statutory | 1 member | Read BSA §63 Schedule + NDPS Rules 2022 | Part A template, linkage fields | eSakshya envelope spec |
| F — Data | 2 members | Build surrogate ladders, print cards | Capture matrix (target ≥2,000 images) | Degraded-condition set |

**Critical path is F, not C.** Data collection is the only track that cannot be compressed by working
harder in the last 48 hours. Start it in week 1, before the pipeline exists.

### Stack

Flutter (Android-first) · OpenCV via FFI for L1 · ~~TFLite for L2 if a learned component survives
ablation~~ — **it did not: see [`ROBUSTNESS.md`](ROBUSTNESS.md) §4.** Nearest-locus ΔE2000 beats both
Mahalanobis and logistic regression on a held-out illuminant, and is the only one a defence expert
can recompute on paper. **L2 stays closed-form; there is no learned component and no TFLite
dependency.** · Android Keystore/StrongBox for L4 · CBOR + SHA-256 · verifier in Python (reference)
and Dart (in-app) — two independent implementations, because a single implementation that agrees with
itself proves nothing.

---

## 12. What we are deliberately not building

- **A confirmatory test.** The PS forbids it and the chemistry forbids it. Every screen says
  *presumptive*.
- **A conviction-support scoring system.** The tool reports a measurement and its uncertainty. It
  does not opine on guilt, and it must never rank suspects or persons.
- **A national database of test results.** CCTNS-2.0 is the system of record. Building a second one
  would create a new surveillance surface and a new liability with no benefit.
- **Anything that reduces the accused's ability to challenge the evidence.** Every disagreement and
  quality failure is *in* the record precisely so it can be used by the other side. A forensic tool
  that only helps one party is not a forensic tool.

---

## 13. Open questions to resolve before the finale

1. ~~Exact current wording and field labels of the BSA Schedule certificate (read the bare Act).~~
   **Transcribed** — see [`CERTIFICATE.md`](CERTIFICATE.md). Two parts confirmed (Part A by *the
   Party*, Part B by *the Expert*); **both** state the hash; SHA256 is named in the Schedule itself.
   Transcription is from a bare-Act repository, not the Gazette, so certificates remain stamped
   DRAFT. **Remaining: one comparison against the eGazette PDF.** Transcribing it also exposed that
   the FTR carried no make/model/serial/IMEI, which the certificate requires — now added.
2. Whether eSakshya exposes any documented ingest interface, or whether the handoff must be a file
   envelope plus manual upload.
3. Whether NCB will state the reagent set in scope — this changes the number of reference loci.
4. Which Android API levels and StrongBox availability are realistic on issued police handsets.
   StrongBox is not universal; the TEE fallback must be explicit and its weaker guarantee recorded
   in the FTR rather than glossed over.
5. Whether the reference card should be printed, or issued as a durable card with a registered
   `card_id` — the latter is stronger, but edges toward "new hardware."
