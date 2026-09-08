# SIH26231 — Digital Companion for Field Drug Testing

Smart India Hackathon 2026. Ministry of Home Affairs / **Narcotics Control Bureau**.

| Field | Value |
|---|---|
| PS ID | **SIH26231** · Software · MedTech/BioTech/HealthTech |
| Deadline | 30 September 2026 |
| Repository | working documents, a runnable core, and an app |

## The one-paragraph version

The problem statement asks for colour classification plus a tamper-evident record.
Colour classification is an undergraduate exercise, and the naive whole system already
ships commercially (DetectaChem MobileDetect). The real gap — stated in the PS itself —
is that a presumptive field test **is not usable as documentary evidence**. So the
record is the product: a hardware-attested, append-only, independently re-derivable
measurement that emits a Bharatiya Sakshya Adhiniyam §63 certificate and hands off to
MHA's existing eSakshya / CCTNS-2.0 pipeline.

No new hardware. A printed colour card and a phone.

> **The classifier is not the product. The record is.**
> It is one signed input, and it must be able to say "I don't know."

---

## What is built

```sh
python3 -m venv .venv && .venv/bin/pip install -e core[dev]
.venv/bin/python core/tools/fetch_spectral_data.py   # measured camera sensitivities
./check.sh                                           # everything, both languages
```

`./check.sh` runs 278 Python tests, 68 Dart tests, 33 Flutter tests, then asserts the
**two independent verifiers reach the same verdict** on the same chain.

| Command | What it does |
|---|---|
| `core/demo.py --keep DIR` | Photograph three strips, seal them, verify, then run five attacks |
| `ftrverify chain DIR` | The reference verifier — offline, trusting nothing |
| `ftr-printable --out card.png` | The reference card, with the liveness tab fold lines |
| `ftr-ingest survey captures/` | Is a capture set usable, and why is the rest not |
| `ftr-ingest calibrate captures/ --holdout tungsten` | Fit and evaluate on a held-out illuminant |
| `ftr-certificate rec.ftr --bundle out/` | §63 certificate + eSakshya handoff bundle |
| `core/tools/robustness.py` | Sweep 83 failure conditions hunting false accepts |
| `core/tools/parallax_study.py` | The replay defence, and how much depth it needs |
| `core/tools/ablation.py` | Does a learned classifier earn its place (it does not) |

### Numbers that are measured, not claimed

| | |
|---|---|
| **0** | false accepts across an 83-condition stress sweep |
| **0.50 ΔE2000** | median colour error on 28 *real* camera sensitivities under D65 (1.24 under tungsten) |
| **0.0%** | wrong calls under an unseen illuminant — the system abstains instead |
| **0.1 px** | parallax from a photo-lab print, against 28.2 px predicted for a physical card |
| **2** | independently written verifiers that agree, in two languages |
| **379** | automated tests |

**Every one of these is measured on synthetic frames or on measured spectral data.
None is a field accuracy.** No printed card has been photographed. See
[`docs/CAPTURE.md`](docs/CAPTURE.md).

---

## Track status

| Track | State |
|---|---|
| **A** — colour pipeline | **Done and stress-tested.** Fiducials, homography, illumination correction, sampling, quality gate, device transform. Envelope swept over 83 conditions with 0 false accepts after three fixes. |
| **B** — classification | **Done and ablated.** Conformal abstention with the finite-sample correction. Nearest-locus ΔE2000 beat Mahalanobis and logistic regression on held-out illuminants *and* held-out cameras, so L2 stays closed-form — no learned component, no TFLite. |
| **C** — crypto / provenance | **Done twice.** Python and Dart, independently written, cross-checked against shared vectors in both directions. |
| **D** — app | **Spine built, including the two-frame capture.** Standby → capture → second view → result → sealed, with real sealing through the shared package and the liveness block in the record. Camera, native L1 and StrongBox are not wired, and it has never run on a handset. |
| **E** — legal / statutory | **Emitter built, Schedule transcribed.** Certificates carry the Act's real field labels and tick SHA256 as the Schedule names it. Still stamped DRAFT: the transcription is from a bare-Act repository, not the Gazette. **Remaining: one comparison against the eGazette PDF.** |
| **F** — data | **Not started, and it is the critical path.** Card is printable, ingest tooling and protocol are built. It needs a person, a printer and a weekend. |

Two tasks now gate the submission and **neither is code**: compare the §63 Schedule
against the Gazette, and run the capture matrix.

---

## Things we got wrong, and fixed

The project's own record of being wrong is worth more than a list of features.

**The threat model claimed a replay defence that did not exist.** §10 row 1 said replay
was beaten because the card must be co-planar and co-illuminated with the strip. A
replay reproduces the *whole scene*, so both are preserved. A photo-lab print and a
high-DPI screen passed every colour check reading as **excellent** captures. Now closed
by two-view parallax against a folded 8 mm liveness tab — print 0.1 px, screen 0.0 px,
both refused. A **synchronised stereo replay** still works and is stated as such.
→ [`PARALLAX.md`](docs/PARALLAX.md)

**The reference card had a latent measurement bug.** All eight neutral patches sat on
one row, leaving the illumination surface unconstrained in *y*. A torch hotspot passed
the quality gate carrying **52 ΔE** of error. Neutrals now span three rows and five
columns, and a test enforces it. → [`ROBUSTNESS.md`](docs/ROBUSTNESS.md)

**The camera simulator was measuring an easier problem.** A per-channel RGB gain cannot
produce metamerism, so every cross-illuminant number taken from it was optimistic.
Replaced with rendering from measured reflectance × measured SPD × measured camera
sensitivity. → [`ROBUSTNESS.md §6`](docs/ROBUSTNESS.md)

**The record schema was incomplete for its own statutory purpose.** Transcribing the
§63 Schedule revealed it asks for Make & Model, Serial Number and IMEI — none of which
the FTR carried. It carried `android_id_hash`, a privacy-preserving identifier, which
is exactly the wrong thing for a form asking for an IMEI. → [`CERTIFICATE.md`](docs/CERTIFICATE.md)

**A reference value was written from memory and was impossible.** A CIEDE2000
conformance figure disagreed with both implementations; a bound on ΔE₀₀ for that colour
pair proved the recalled value could not occur. Reference data is now transcribed or
flagged, never recalled. → [`DETERMINISM.md`](docs/DETERMINISM.md)

---

## Documents

**Design and argument**
- [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) — seven layers, the threat model, data strategy, build plan
- [`NOVELTY.md`](docs/NOVELTY.md) — prior art conceded, what survives it, the §3(k) problem
- [`DESIGN.md`](docs/DESIGN.md) — interface spec: tokens, the seven rules every screen obeys
- [`app-prototype.html`](docs/app-prototype.html) — clickable nine-screen prototype

**What was measured**
- [`ROBUSTNESS.md`](docs/ROBUSTNESS.md) — the operating envelope, three defects found, the ablation, and what changed under measured physics
- [`PARALLAX.md`](docs/PARALLAX.md) — the two-view liveness check, the card change it forced, the replay that still works
- [`DETERMINISM.md`](docs/DETERMINISM.md) — what "reproduces bit-for-bit" may actually claim
- [`CERTIFICATE.md`](docs/CERTIFICATE.md) — what the §63 Schedule asks for, and the schema gap it exposed
- [`CAPTURE.md`](docs/CAPTURE.md) — the track F protocol, and the only accuracy claim worth making

**Submission**
- [`SIH26231-idea-submission.pptx`](docs/SIH26231-idea-submission.pptx) / [`.pdf`](docs/SIH26231-idea-submission.pdf) — six slides from the official template
- [`architecture-diagram-brief.md`](docs/architecture-diagram-brief.md) — design brief for the architecture diagram
- [`slides/`](docs/slides) — architecture, pipeline, risk table, impact and evidence graphics

## Code

- [`core/`](core/README.md) — `ftr`: canonical CBOR, the Field Test Record, the append-only
  ledger, the colour pipeline, the parallax defence, the §63 emitter, the capture tooling
  and the reference verifier. **278 tests.**
- [`dart/ftr_verify/`](dart/ftr_verify/README.md) — the **second** verifier and the app's
  sealing path, written independently with no shared code or dependency. **68 tests.**
- [`app/`](app/README.md) — the Flutter client. Capture spine and real sealing; camera and
  StrongBox not wired. **33 tests.**
- [`data/spectral/`](data/spectral/README.md) — measured spectral data: sources, licence,
  and what is still missing (all of the chemistry).

## What we are deliberately not building

A confirmatory test. A conviction-support score. A national database of results —
CCTNS-2.0 stays the system of record, and a parallel silo would add a surveillance
surface and a liability for no benefit. Anything that reduces the accused's ability to
challenge the evidence: every disagreement and quality failure is *in* the record
precisely so the other side can use it.
