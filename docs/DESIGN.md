# Interface Design — Field Companion

**SIH26231** · Digital Companion for Field Drug Testing · v0.1, internal round

Interactive prototype: [`app-prototype.html`](app-prototype.html) — nine screens, clickable,
with the design rationale beside each one. This file is the written spec that prototype encodes.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first. Every interface decision below is downstream of its
design axiom: **the classifier is not the product, the record is.**

---

## 0. Who the interface is for, in order

1. **The operator** — gloved, standing in sunlight, possibly at 2 a.m., under time pressure and
   sometimes under observation by the person whose material is being tested.
2. **The advocate** — reading the exported bundle months later, looking for the weakness.
3. **The judge** — reading the certificate and the verifier report, with no technical background and
   no reason to trust anyone in the room.

An interface optimised only for reader 1 produces evidence that fails readers 2 and 3. Every screen
must survive all three. Where their needs conflict, the operator gets the *fast path* and the other
two get the *complete record* — never the reverse.

---

## 1. Rules obeyed on every screen

| # | Rule | Why |
|---|---|---|
| 1 | **Colour never means good or bad.** Crimson = presumptive positive, teal = negative, amber = abstention/caution. None is a success state. | An interface that celebrates a positive pressures the operator toward one. |
| 2 | **Nothing is hidden because it is unflattering.** Location disagreements, weak attestation, wide prediction sets appear on the screen where they occur *and* in the record. | Suppressing them would make the system a party to the case. |
| 3 | **The word *presumptive* is never off-screen** in any post-result state. | There must be no state in which a user forgets what class of claim this is. |
| 4 | **Measured quantities are set in mono.** Anything the verifier can recompute — hashes, ΔE, Lab, coordinates, α — is IBM Plex Mono. Prose is Archivo. | The typeface tells the reader whether a number is evidence. |
| 5 | **Blank human fields stay blank,** marked ▢ in amber. | An auto-filled signature line is a forgery mechanism. |
| 6 | **Every gate can be overridden, and the override is recorded.** | Field conditions are not negotiable with software; but the protest becomes part of the signed record. |
| 7 | **Colour is never load-bearing alone.** Every stripe, chip and state is doubled by a text label. | Accessibility, sunlight, and cheap issued handsets with poor screens. |

---

## 2. Design tokens

Inherited from `team-brief.html` — the project has one visual language and the app is inside it.

```
ground      #F7F6F9   surface   #FFFFFF   surface-2 #F0EEF4
ink         #1A1726   ink-2     #413A55   muted     #6A6478
rule        #DEDAE7   rule-soft #EAE7F0
accent      #6B3FA0   accent-soft #EDE6F6      ← chrome, links, active state
crimson     #A32C4A   crimson-soft #F8E4E9     ← presumptive positive
teal        #0F7B6C   teal-soft   #DFF0EC      ← presumptive negative, verified, proven
amber       #A66A00   amber-soft  #F8EEDC      ← inconclusive, caution, awaiting a human
```

Dark theme redefines the same token names only; no component styles live inside a media query.
Three states are handled: bare `:root` (light), `@media (prefers-color-scheme:dark)` guarded with
`:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`.

**Type**

| Role | Face | Used for |
|---|---|---|
| UI | Archivo 400/500/600/700 | screen chrome, labels, buttons, verdicts |
| Data | IBM Plex Mono 400/500/600 | hashes, ΔE, Lab, α, coordinates, IDs, eyebrows |
| Prose | Source Serif 4 | documentation and annotation only — not in the app itself |

The app uses **no serif**. Documents use serif for running text. That boundary is deliberate: it
keeps the app feeling like an instrument and the exports feeling like documents.

---

## 3. The nine screens

| # | Screen | Purpose | Primary action |
|---|---|---|---|
| 01 | **Standby** | Device states its own trustworthiness before use | Begin field test |
| 02 | **New test** | Reagent, reference card, case linkage — all kit-agnostic | Open camera |
| 03 | **Capture** | Guidance overlay + live quality meters; shutter gated | Capture frame |
| 04 | **Frame accepted** | Normalisation report + location corroboration, *before* any result | Read result |
| 05 | **Result** | Prediction set, ΔE basis, α — with an abstention variant | Seal record |
| 06 | **Record sealed** | Digest, signature, attestation, chain position, anchor window | Generate certificate |
| 07 | **Record log** | Append-only ledger including the unflattering entries | Export |
| 08 | **BSA §63 certificate** | Pre-populated Part A + eSakshya envelope | Run verifier |
| 09 | **Verifier report** | Proven / asserted / unverifiable | Return to standby |

### 01 Standby
Opens on a **posture report**, not a camera. StrongBox availability, verified-boot state, patch
level and mock-location flag are read at launch. Anchoring debt (`4 records · 3 h 12 m`) sits on the
home screen in amber because that window is the honest limit of what the chain proves.

`Offline` is an amber *state* chip, never an error. NDPS fieldwork happens without coverage; the
interface must not imply the officer erred by being out of it.

**Binds:** `operator.id`, `operator.biometric_unlock_used`, `device.verified_boot_state`,
`device.os_patch_level`, `prev_record_hash`

### 02 New test
The reagent is **declared by the operator**, not read from a vendor QR code — this is the screen
where kit-agnosticism, the PS's explicit requirement, is actually implemented. Identity lives on the
reference card (`card_id`, print batch) instead, so a verifier knows which patch reflectances the
colour transform was solved against.

An illegible kit lot is a first-class answer: the operator photographs it and the app hashes the
photo. Case linkage is optional and its absence is recorded as an explicit `orphaned` flag —
demanding an FIR number at 2 a.m. guarantees fabricated ones.

**Binds:** `kit.reagent_type`, `kit.kit_photo_hash`, `card.card_id`, `card.print_batch`,
`ndps.seizure_memo_ref`, `ndps.sample_ids`

### 03 Capture
The overlay is a measurement instrument. Card and reaction well must be **co-planar and
co-illuminated in one frame** — this is what makes the illumination correction and the device
transform valid, and simultaneously the defence against re-photographing a photograph.

Four fiducials must lock before the shutter arms. Live meters are the same quantities later written
to the record. Hints name the *fix*, not the failure: "Tilt back slightly" beats "poor image
quality" for someone wearing gloves in the sun.

**A disabled shutter is a rude interaction and the correct one.** A bad frame yields a confident
wrong answer in exactly the conditions where that does the most damage.

**Binds:** `capture.raw_image_sha256`, `colorimetry.blur_metric`, `colorimetry.dynamic_range`,
`card.fiducial_lock`

### 04 Frame accepted
Both gates report **before the result is revealed**. Order matters: an operator who has already seen
"positive" will rationalise a poor calibration score.

The location panel is a bundle and reports **agreement between channels**, not a fused number that
hides which channel dissented. A disagreement renders in amber and is stored, never dropped.
Corrective steps (shadow removal) are disclosed on screen — correction is not concealment.

Retake is offered at equal visual weight. No dark pattern pushes toward proceeding.

**Binds:** `colorimetry.calibration_residual`, `location_bundle.*`, `corroboration_score`,
`spoof_indicators[]`

### 05 Result — two designed states, no error state
```
CONFIDENT              ABSTENTION
prediction set         prediction set
  = { positive }         = { positive, negative }
verdict: crimson       verdict: amber
ΔE nearest    3.81     ΔE nearest      9.61
ΔE next      14.20     ΔE next        11.24
separation   10.39     separation      1.63  (needs 4.00)
```
Both carry α and coverage. Both are sealable. **Inconclusive is a result, not a prompt to retry
until the answer improves** — the copy says exactly that, because the retry loop is the single most
likely way this system gets abused in the field.

`model_sha256` appears on the result screen: a result is meaningless without knowing which model
produced it, and the verifier re-runs precisely that one.

**Binds:** `classification.prediction_set`, `.label`, `.alpha`, `.model_sha256`,
`colorimetry.lab_values`

### 06 Record sealed
Canonical CBOR → SHA-256 → StrongBox signature → attestation chain. The screen states the limit of
its own proof verbatim:

> This record proves it was created **no earlier** than record #47 and **no later** than the next
> anchor. It does not prove the wall-clock time, and it does not claim to.

Sealing is irreversible and the copy says so. No draft state, no edit-after-seal — the mere
*possibility* of revision is all a defence needs. On handsets without StrongBox the security level
row reads `TEE`, and that weaker guarantee goes into the signed record.

### 07 Record log
Append-only. The prototype deliberately shows a positive **carrying a location disagreement**, an
inconclusive, and an orphaned record — the entries a vendor demo would omit.

Outcome is a 3px severity stripe at the left edge, scannable at arm's length, always doubled by the
text label. `Withdraw` exists; `delete` does not — annotation is the honest primitive for an
append-only store.

### 08 BSA §63 certificate
§63 replaced §65B in July 2024 and its certificate must state the **hash value and the algorithm**.
The app computed both at capture, so Part A is pre-populated the moment the record seals. Part B and
both signature lines stay blank and amber.

The eSakshya/CCTNS-2.0 envelope routes by FIR. **No parallel evidence store is built** — the
deliverable is a presumptive-test module that plugs into the ministry's existing pipeline.

> ⚠ Transcribe exact Schedule field labels and part numbering from the bare Act before printing this
> in the submission. The prototype's labels are placeholders.

### 09 Verifier report
Three sections, equal visual weight, none collapsed behind a disclosure triangle:

- **Proven** (teal) — digest recomputes, signature valid, attestation chains to hardware root,
  raw frame unedited, L1–L2 re-run reproduces the stored result bit-for-bit, chain replays with no
  fork.
- **Asserted, not proven** (amber) — wall-clock time, operator identity behind the biometric,
  operator-declared reagent.
- **Unverifiable** (grey) — whether the substance photographed is the substance seized; whether the
  reaction had fully developed; the result itself, which is presumptive.

> A verifier that only ever prints VALID ✓ teaches courts to over-trust it.

---

## 4. Interaction and accessibility

- **Touch targets** ≥ 48 dp. Primary actions live in a fixed footer, reachable one-handed.
- **Gloves and sunlight**: no hover-dependent affordance, no gesture-only action, minimum body size
  0.79 rem at device scale, high-contrast tokens in both themes.
- **`prefers-reduced-motion`**: the capture animation resolves immediately to its locked state; all
  transitions disabled.
- **Focus**: 2px accent outline with offset on every interactive element; rail is keyboard
  navigable; ← / → move between screens in the prototype.
- **State is never colour-only** — every stripe and chip has a text label.

## 5. What the prototype does not yet cover

1. Onboarding and device enrolment (key generation, card registration).
2. Multi-sample sessions — several strips from one seizure under one memo.
3. Anchor-reconnect flow and its conflict states.
4. Withdrawal/annotation UI for record 07.
5. Settings, including the α risk level — likely a policy-locked value, not an operator control.
6. Hindi and regional-language strings. Every string in the prototype is written to be translatable;
   none is assembled from fragments.

## 6. Handoff

Build order matches `ARCHITECTURE.md` §11 track D. Screens 03 → 05 → 06 are the demo spine and
should be built first; 01, 02, 07 are conventional and can follow. 08 and 09 need track E's statute
work before their labels are final.
