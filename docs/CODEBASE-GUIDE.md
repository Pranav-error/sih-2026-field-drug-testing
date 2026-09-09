# The codebase, explained

For teammates who need to understand and defend this project. Everything below is
read from the **actual source**, with file and function cited. Where the code does
not do something the documentation or the problem statement implies, it says
**NOT IMPLEMENTED** in bold.

Read §1 and §12 if you have ten minutes. Read all of it before facing judges.

---

## 1. What this project actually is

Three separate programs that share one file format.

| | Language | What it is | Runs where |
|---|---|---|---|
| **`core/ftr`** | Python | The reference implementation and the reference verifier | A laptop |
| **`dart/ftr_verify`** | Dart | A second, independent implementation of the same format, plus the on-device pipeline | Phone, browser, CLI |
| **`app/`** | Flutter | The officer-facing app | Android handset |

**There is no server and no database.** Not "not yet" — there is no server-side
component in the design at all. Records are files. That is deliberate: CCTNS-2.0 is
meant to be the system of record, and building a second evidence store would create
a surveillance surface for no benefit (`ARCHITECTURE.md` §12).

### Entry points

| Entry point | File |
|---|---|
| The app | `app/lib/main.dart` → `main()` → `FieldCompanionApp` → `CaptureFlow` |
| Reference verifier CLI | `core/ftr/cli.py` → `main()` |
| Dart verifier CLI | `dart/ftr_verify/bin/ftrverify.dart` |
| Certificate emitter | `core/ftr/certcli.py` |
| Capture-set tooling | `core/ftr/ingest.py` |
| Card printer | `core/ftr/printable.py` |
| End-to-end demo | `core/demo.py` |

### The actual architecture

```
        OFFICER
           │  taps, moves the phone
           ▼
  ┌───────────────────────────────────────────────┐
  │  Flutter app  ·  app/lib/main.dart            │
  │  screens.dart · viewfinder.dart (camera)      │
  └───────────────────────┬───────────────────────┘
                          │ JPEG bytes
                          ▼
  ┌───────────────────────────────────────────────┐
  │  ON-DEVICE PIPELINE  (pure Dart, no network)  │
  │  detect.dart    fiducials → homography        │
  │  pipeline.dart  light field → CIELAB → gate   │
  │  colorimetry.dart  ΔE2000 → conformal set     │
  └───────────────────────┬───────────────────────┘
                          │ Map<String, Object?>
                          ▼
  ┌───────────────────────────────────────────────┐
  │  seal.dart  →  canonical_cbor.dart  →  SHA-256│
  └───────────────────────┬───────────────────────┘
                          │ 32-byte digest
                          ▼
  ┌───────────────────────────────────────────────┐
  │  ANDROID SECURE ELEMENT                       │
  │  HardwareKeystore.kt  ECDSA P-256 in StrongBox│
  │  returns signature + attestation certificates │
  └───────────────────────┬───────────────────────┘
                          │ SealedRecord
                          ▼
              ⚠ IN MEMORY ONLY — see §6
                          │
        (on a laptop, a record file reaches:)
                          ▼
  ┌───────────────────────────────────────────────┐
  │  VERIFIERS (two, independent)                 │
  │  core/ftr/verifier.py   ·  src/verifier.dart  │
  │  PROVEN / ASSERTED / UNVERIFIABLE             │
  └───────────────────────────────────────────────┘
```

Two boxes are missing versus the diagram in `ARCHITECTURE.md`, and you should know
which: **L3 Corroborate** (GNSS/Wi-Fi/cell agreement) and **L6** (the §63
certificate) exist in Python but are **not wired into the app**.

---

## 2. One test, end to end

### Step 1 — the officer opens the app

**Sees:** a device-posture screen, before any camera.
**Code:** `main.dart` → `CaptureFlow.initState()` → `_openKeystore()` →
`platform_keystore.dart` → `PlatformKeystore.open()` → method channel
`in.gov.ncb.sih26231/keystore` → `HardwareKeystore.prepare()` in Kotlin.

The Kotlin generates a P-256 key **inside StrongBox** on first run
(`HardwareKeystore.generate`, `setIsStrongBoxBacked(true)`), catches
`StrongBoxUnavailableException`, and falls back to the TEE while reporting that it
did.

**Why first:** the first question a defence lawyer asks is not what colour the strip
was. It is what kind of device produced this.

| Shown | Real? |
|---|---|
| Security level (STRONGBOX / TEE / SOFTWARE) | **Yes** — `KeyInfo.getSecurityLevel()` |
| Verified boot / bootloader | Displays `IN ATTESTATION` — deliberately not asserted by the app; see §5 |
| Mock location | **NOT IMPLEMENTED.** `main.dart:194` hardcodes `mockLocation: false` |
| Records on device / anchor window | **NOT IMPLEMENTED as real state** — derived from an in-memory counter |

### Step 2 — the chemistry

The officer does exactly what they do today with the department's kit. **No code is
involved.** The system is not a new test.

### Step 3 — strip on the card, first photograph

**Sees:** live camera with a framing rectangle and one instruction.
**Code:** `viewfinder.dart` → `_ViewfinderState._start()` opens a
`CameraController`; a `Timer.periodic` (`_grab()`, default 900 ms) calls
`takePicture()` and hands JPEG bytes to `onFrame`.

`main.dart._onFrame` → `measure_bridge.dart` → `OnDeviceMeasurer.measure()` →
`ftr.measureOnDevice()` in `dart/ftr_verify/lib/src/pipeline.dart`.

**The shutter is disabled until the frame is measurable** — `main.dart._shutterArmed`
returns `_live!.detected && _live!.gatePassed`. Not a UI nicety: a bad frame produces
a *confident wrong* answer, which is worse than none.

### Step 4 — second photograph

**Sees:** a green banner, *"First frame captured. Now move a few centimetres…"*, and
a `2/2` counter.
**Code:** `screens.dart` → `SecondViewScreen`; `main.dart._confirmPair()` runs
`compute(_pairInIsolate, …)` → `OnDeviceMeasurer.measurePair()` →
`livenessOnDevice()` in `pipeline.dart`.

An isolate because the two-view search is the heaviest thing the app does.

**The officer may skip this** (`onSkip` → `PrimaryButton.ghost`), and the record then
carries `checked: false` — see §5.

### Step 5 — the result

**Sees:** a prediction **set**, ΔE to each locus, α, and the liveness panel.
**Code:** `screens.dart` → `ResultScreen`; values from `TestResult` and `Liveness`
in `models.dart`, populated by `MeasureBridge._parse` / `_fromDevice`.

### Step 6 — sealing

**Code:** `main.dart._seal()`. Builds the record via `ftr.buildBody(...)`
(`seal.dart`), encodes with `cbor.encode` (`canonical_cbor.dart`), hashes with
`sha256` (`record.dart`), then `PlatformKeystore.signAsync()` → Kotlin
`HardwareKeystore.sign()` → `Signature.getInstance("NONEwithECDSA")`.

`NONEwithECDSA` because **the digest is the artefact** and is signed directly rather
than re-hashed — matching the `Prehashed` path in `core/ftr/signing.py`.

**⚠ The sealed record is never written to storage.** See §6.

### Step 7 — verification, later

**Code:** `core/ftr/verifier.py::verify_record` or `verifyRecord` in
`dart/ftr_verify/lib/src/verifier.dart`. Both sort every claim into PROVEN /
ASSERTED / UNVERIFIABLE and print all three at equal weight.

---

## 3. The image pipeline, line by line

Two implementations. **The app runs the Dart one.**

| Stage | Python | Dart (what the app runs) |
|---|---|---|
| Greyscale | OpenCV | `detect.dart::toGray` — Rec. 709 luma |
| Binarise | `cv2.aruco` internals | `detect.dart::adaptiveThreshold` — local mean via integral image |
| Find markers | `cv2.aruco.ArucoDetector`, sub-pixel | `detect.dart::findFiducials` — connected components |
| Corners | `CORNER_REFINE_SUBPIX` | Blob diagonal extremes (min/max of x+y and x−y) |
| Homography | `cv2.getPerspectiveTransform` | `detect.dart::homographyFrom` — 4-point DLT, Gauss-Jordan |
| Light field | `detect.py::estimate_illumination` | `pipeline.dart::_fitLightField` |
| Colour transform | `colorimetry.py::RootPolynomial.fit` | `colorimetry.dart::RootPolynomial.fit` |
| Sampling | `detect.py::_trimmed_mean` | `pipeline.dart::_samplePatch` |

### How the card is found (Dart, the shipped path)

`findFiducials` does **not decode ArUco bit patterns.** The discriminator is
simpler and more robust: a fiducial is *a dark square with white inside it*, while
every colour patch is *a dark square that is solid*. Filters, in order:

1. Area between 0.04% and 6% of the frame
2. Bounding-box aspect ratio 0.6–1.65
3. Fill ratio ≥ 0.5
4. **Interior ink fraction between 0.25 and 0.92** — the actual discriminator

Then `orderMarkers` assigns TL/TR/BR/BL by position relative to the group centre.

### Perspective correction — YES, implemented

`homographyFrom(dst, src)` maps the card's millimetre grid to image pixels. Patch
centres become **constants**, so nothing is hunted for by segmentation.

### Lighting correction — YES

`_fitLightField` fits a **bi-quadratic surface in log space** from the 8 neutral
patches, then **mean-normalises it over the card** so it corrects *spatial*
variation only. The global illuminant cast is left to the device transform, which
has 23 patches to constrain it instead of 8.

### The 196 probe points — real, but **Python only**

`card.py::substrate_points_mm()` returns exactly **196** points on bare card, used
by `detect.py::substrate_residual` to *test* the light field. **NOT IMPLEMENTED in
Dart**, so the app does not have this check. It uses the fit residual instead
(`Quality.lightFieldStops`), which is weaker — it was the fit residual missing a
shadow edge that let a 17 ΔE error through in the first place.

### Colour space

- Sample in **linear RGB** (`srgbToLinear`)
- Transform to **CIEXYZ** via root-polynomial least squares
- Convert to **CIELAB** (`xyzToLab`)
- Compare with **CIEDE2000** (`deltaE2000`)

HSV is not used anywhere.

### Glare and noise

`_samplePatch` sorts the 49 samples by luma and **drops the brightest and darkest
eighth** before averaging. Clipping is counted separately (`raw.r >= 252`).

### Thresholds — `pipeline.dart::Quality`

| Metric | Limit |
|---|---|
| Fiducials | must be 4 |
| Tilt | ≤ 25° |
| Reprojection | ≤ 6.0 px (**looser than Python's 2.0** — coarser corners) |
| Sharpness | ≥ 0.004 |
| Clipped | ≤ 3% |
| Dynamic range | ≥ 0.30 |
| Light field | ≤ 0.30 stops |
| Card residual | ≤ 3.0 ΔE (`RootPolynomial.passes`) |

---

## 4. The "ML" — and there deliberately isn't any

**There is no neural network, no TFLite, no trained model file, and no training
code.** That is a result, not an omission.

`core/tools/ablation.py` and `spectral_ablation.py` compared three scorers on 8,064
measurements rendered from 28 measured camera sensitivities, each wrapped in the
*same* conformal layer:

| Scorer | Unseen illuminant | Unseen camera | DSLR→phone |
|---|---|---|---|
| **Nearest locus ΔE2000** | **94.5%** | **95.1%** | **93.2%** |
| Mahalanobis | 91.8% | 94.8% | 92.8% |
| Logistic regression | 94.5% | 94.8% | 92.0% |

The simplest won, and it is the only one a defence expert can recompute on paper.

### Conformal prediction — YES, genuinely implemented

`colorimetry.dart::ConformalClassifier`, mirrored in `colorimetry.py`.

```
score(lab, label) = CIEDE2000(lab, locus[label])
threshold         = the ceil((n+1)(1−α))-th smallest calibration score
prediction set    = { label : score ≤ threshold }
```

The `ceil((n+1)(1−α))` is the **finite-sample correction** — verified at
`colorimetry.py:229` and `colorimetry.dart:297`. Using the plain empirical quantile
would lose the guarantee silently. `calibrate()` also *refuses* when there are too
few points for the stated α.

**Inconclusive** is `predictionSet.length != 1` — both `{a,b}` and `{}` (`models.dart::Outcome.fromPredictionSet`).

Calibration in the app is **synthetic**: `measure_bridge.dart::_buildClassifier`
jitters 200 points around each of four hardcoded loci. **NOT calibrated on real
reagent data** — no such dataset exists (`DATA-NEEDED.md` §2).

### Worked example

```
JPEG → decodeImage → toGray → adaptiveThreshold
     → findFiducials  → 4 quads
     → homographyFrom → 3×3 matrix
     → _samplePatch × 23 → linear RGB
     → _fitLightField → divide out
     → RootPolynomial.fit → XYZ → Lab = [18.4, 23.6, −8.2]
     → ΔE2000 to each locus → {opiate 3.8, related 5.9, amph 24.1, negative 62.0}
     → threshold 5.53 → set = {opiate_class}
     → label = "opiate_class"
```

---

## 5. The forensic layer

### What is hashed

`sha256(canonical_cbor(body))`, where `body` is built by `seal.dart::buildBody`:
schema version, record UUID, **sequence**, `prev_record_hash`, captured_at, operator,
kit, card, capture (image hashes), colorimetry, **liveness**, classification,
location bundle, device, NDPS fields, omitted list, and `pipeline`.

**Canonical CBOR** (`canonical_cbor.dart`) is deterministic: definite lengths,
shortest-form integers, map keys sorted bytewise on their *encoded* bytes, **floats
refused outright**. Every measured value is a scaled integer with the scale in the
field name (`lab_x100`). That is why two independently written encoders reach the
same digest.

### What is signed

The 32-byte digest, directly, with ECDSA P-256 inside StrongBox.

### The chain — what modifying record #48 does

```
#47  digest A          #48 body contains prev_record_hash = A
#48  digest B          #49 body contains prev_record_hash = B
#49  digest C
```

Change one byte in #48 → its digest is no longer B →

1. **#48's own signature fails.** The signature covers B; the body now hashes to B′.
   `verifier.py` reports *"the signature does not verify over the recomputed digest."*
2. **#49 breaks too.** It still carries `prev_record_hash = B`, but replaying finds
   B′. `chain.py::Chain.status` emits a `gap`.

To hide it you must re-sign #48 — impossible without the key, which is inside the
secure element — *and* re-sign every later record. **Deleting** #48 leaves the same
gap; `sequence` is inside the signed body, so records cannot be silently relocated.

### The three buckets — `verifier.py::verify_record`

**PROVEN** — canonical encoding reproduces; SHA-256 recomputes; signature verifies;
the attestation certificate states the security level (read from the certificate,
not the record); verified boot GREEN and bootloader locked *per the certificate*;
supplied images hash to the recorded values; the chain replays with no gap or fork.

**ASSERTED** — wall-clock capture time (device clock); that the named operator was
behind the biometric (it binds the device, not the person); the operator-declared
reagent; unanchored records; the liveness verdict when frames are not supplied; that
the attestation chain is not walked to a Google root.

**UNVERIFIABLE** — *whether the substance photographed is the substance seized*;
whether the reaction had fully developed; the correctness of the result itself.

> *A verified record is not a true result. It is an unaltered one.*

### The certificate outranks the record

`verifier.py` parses the attestation extension itself
(`attestation.py::parse_attestation`, OID 1.3.6.1.4.1.11129.2.1.17) and **fails a
record that claims more hardware than its certificate attests to**:

> *"The record claims a STRONGBOX key; the attestation certificate says SOFTWARE.
> The record overstates its own hardware."*

---

## 6. Storage — read this carefully

**There is no database. Anywhere. In any component.** No SQLite, no sqflite, no
shared_preferences, no server. Verified by grep across `core`, `app/lib` and `dart`.

| | |
|---|---|
| A record | one file, `NNNNNN.ftr`, canonical CBOR |
| A chain | a **directory** of those files plus an `ANCHOR` text file |
| Reader/writer | `core/ftr/chain.py::Chain` |

A directory rather than one file, deliberately: appending must never rewrite an
existing byte, so a partial write can lose at most the record being made.

### The app persists records

`app/lib/src/store.dart::RecordStore` writes each sealed record as `NNNNNN.ftr`
into the app's documents directory, mirroring `chain.py::Chain` — including both
guards: it refuses to overwrite an existing slot, and refuses a record that does not
chain to the current head. `RecordStore.status()` replays the chain and reports
every defect rather than the first.

**Anchoring is still not implemented on either side** — see below.

### Anchoring — barely implemented

`chain.py::Chain.anchor(sequence)` writes a sequence number to a text file. There is
**no countersignature, no timestamp authority, no upload**. The docstring says so.
The *honest statement* it supports — "created no earlier than #47 and no later than
the next anchor" — is real; the external witnessing is not.

---

## 7. APIs

**There is no production API.** One development-only HTTP server exists:

| Method | Endpoint | Purpose | Input | Output | File |
|---|---|---|---|---|---|
| `GET` | `/` | Health/info | — | `{ok, card, classes, note}` | `core/tools/measure_server.py::Handler.do_GET` |
| `POST` | `/` | Measure one frame | `{frame: base64 JPEG}` | quality, Lab, prediction | `Handler.do_POST` |
| `POST` | `/` | Measure a pair | `{frame, frame_b}` | the above **+ liveness** | same |
| `OPTIONS` | `/` | CORS preflight | — | 204 | `do_OPTIONS` |

Binds `0.0.0.0:8824`, **no authentication**, and the docstring calls it a demo rig.
The APK does **not** use it — it measures on-device. It exists only for the web
build, which has no OpenCV and no Dart-side camera pipeline equivalent in browsers.

---

## 8. The screens

`app/lib/src/screens.dart`, driven by `enum Step` in `main.dart`.

| # | Screen | Officer does | Validation | Then |
|---|---|---|---|---|
| 1 | **Standby** | reads posture, taps *Begin field test* | none | → capture |
| 2 | **Frame the card `1/2`** | frames the card | shutter blocked until `detected && gatePassed` | → second view |
| 3 | **Second view `2/2`** | moves a few cm, shoots again — or skips | blocked until `SecondView.ready` (≥10 mm) | runs liveness in an isolate → result |
| 4 | **Result** | reads the set, taps *Seal record* | none — an abstention seals too | → sealed |
| 5 | **Record sealed** | reads the digest, taps *Done* | — | → standby |

All nine screens from `DESIGN.md` are built:

| # | Screen | File |
|---|---|---|
| 1 | Standby | `screens.dart::StandbyScreen` |
| 2 | Setup — reagent declared, case linked | `screens_extra.dart::SetupScreen` |
| 3 | Capture `1/2` | `screens.dart::CaptureScreen` |
| 3b | Second view `2/2` | `screens.dart::SecondViewScreen` |
| 4 | Quality gate, reported **before** the result | `screens_extra.dart::GateScreen` |
| 5 | Result | `screens.dart::ResultScreen` |
| 6 | Record sealed | `screens.dart::SealedScreen` |
| 7 | Record log | `screens_extra.dart::LogScreen` |
| 8 | §63 certificate + eSakshya envelope | `screens_extra.dart::CertificateScreen` |
| 9 | Verifier report | `screens_extra.dart::VerifierScreen` |

---

## 9. File map

```
core/ftr/                        Python reference implementation
├── card.py            card geometry, 196 substrate probes, the liveness tab
├── printable.py       renders the card for printing
├── detect.py          ArUco, homography, INUC, sampling, quality gate
├── colorimetry.py     sRGB→Lab, CIEDE2000, root-polynomial, ConformalClassifier
├── spectral.py        physically-based rendering from 28 measured cameras
├── parallax.py        two-view liveness
├── pipeline.py        one frame in, one measurement out
├── canonical_cbor.py  deterministic encoder, floats refused
├── record.py          the FTR, sealing, the envelope
├── chain.py           append-only ledger (files, not a database)
├── signing.py         keystore interface; SOFTWARE fails verification
├── attestation.py     parses the Android attestation extension
├── verifier.py        PROVEN / ASSERTED / UNVERIFIABLE
├── certificate.py     BSA §63 Part A   ⚠ not in the app
├── esakshya.py        CCTNS-2.0 envelope   ⚠ not in the app
└── ingest.py          survey and calibrate a capture set

dart/ftr_verify/lib/src/         second implementation + on-device pipeline
├── canonical_cbor.dart   written independently of the Python
├── card.dart             mirrors card.py
├── detect.dart           pure-Dart fiducial detection      ← the app uses this
├── colorimetry.dart      ΔE2000, transform, conformal
├── pipeline.dart         measureOnDevice, livenessOnDevice ← the app uses this
├── seal.dart             buildBody, seal, keystore interface
├── record.dart           envelope parsing, ECDSA verify
├── verifier.dart         pure — runs in a browser
└── verifier_io.dart      chain verifier (needs a filesystem)

app/lib/
├── main.dart              CaptureFlow: the state machine
├── src/viewfinder.dart    real camera + frame loop
├── src/measure_bridge.dart OnDeviceMeasurer + the dev HTTP bridge
├── src/platform_keystore.dart  StrongBox over a method channel
├── src/screens.dart       the five screens
├── src/screens_extra.dart setup, quality gate, log, certificate, verifier report
├── src/store.dart         RecordStore — the on-device append-only ledger
├── src/certificate.dart   BSA §63 Part A and the CCTNS-2.0 envelope, in Dart
├── src/models.dart        CaptureQuality, TestResult, Liveness, Outcome
└── src/tokens.dart        design tokens; there is no "success" colour

app/android/.../kotlin/
├── HardwareKeystore.kt    StrongBox keygen, attestation, signing
└── MainActivity.kt        the method channel
```

---

## 10. Gap table — do not claim these

| Feature | Claimed | Implemented? | Evidence |
|---|---|---|---|
| Calibration card | ✔ | **YES** | `card.py`, `printable.py`, card in repo |
| Fiducial detection | ✔ | **YES**, both languages | `detect.py`, `detect.dart::findFiducials` |
| Homography | ✔ | **YES** | `detect.dart::homographyFrom` |
| Lighting correction | ✔ | **YES** | `_fitLightField`, `estimate_illumination` |
| **196 probe points** | ✔ | **Python only** | `substrate_residual` — **not in the app** |
| Trimmed mean | ✔ | **YES** | `_samplePatch`, `_trimmed_mean` |
| CIEDE2000 | ✔ | **YES**, matched to Sharma et al. | `colorimetry.*::deltaE2000` |
| Conformal prediction | ✔ | **YES**, with the finite-sample correction | `colorimetry.py:229` |
| Prediction sets | ✔ | **YES** | `Prediction.predictionSet` |
| Canonical CBOR | ✔ | **YES**, twice, cross-checked | `canonical_cbor.*` |
| SHA-256 | ✔ | **YES** | `record.py`, `record.dart` |
| Digital signature | ✔ | **YES**, ECDSA P-256 | `signing.py`, `HardwareKeystore.kt` |
| **StrongBox** | ✔ | **YES**, TEE fallback | `HardwareKeystore.kt` — ⚠ never run on a handset |
| **Verified boot** | ✔ | **Read from the certificate by the verifier** | `attestation.py` — the app does **not** assert it |
| Hash chain | ✔ | **Python only** | `chain.py` — **the app does not persist records** |
| **External anchoring** | ✔ | **NO** — writes a sequence number, no countersignature | `chain.py::anchor` |
| Offline verification | ✔ | **YES** | `cli.py`, `ftrverify.dart` |
| **Print/photo attack detection** | ✔ | **YES** | `parallax.py`, `livenessOnDevice` |
| **Mock-location detection** | ✔ | **NOT IMPLEMENTED** | `main.dart:194` hardcodes `false` |
| **GPS / L3 corroboration** | ✔ | **NOT IMPLEMENTED** | `main.dart:282` hardcodes the bundle |
| **§63 certificate in the app** | ✔ | **YES** | `app/lib/src/certificate.dart::buildCertificate`, `CertificateScreen` |
| **eSakshya handoff in the app** | ✔ | **YES** | `certificate.dart::buildEnvelope`, shown on the certificate screen |
| Record log / persistence | ✔ | **YES** | `app/lib/src/store.dart::RecordStore` — records written to app storage |
| In-app verifier report | ✔ | **YES** | `VerifierScreen` runs `ftr.verifyRecord` on-device |
| Trained ML model | — | **Deliberately none** | ablation: the closed-form scorer won |
| Real reagent calibration | ✔ | **NO** — synthetic loci | `_buildClassifier` |

---

## 11. Explaining it

### 30 seconds
> A field drug test today is a note in a diary — it cannot be used as evidence. We
> photograph the test strip next to a printed colour card, which turns the phone into
> a colour instrument. The measurement is sealed with a key inside the phone's secure
> chip, and anyone can re-check it later without trusting us or our app.

### One minute
> Add: the result is a *set*, not a percentage — it can say "I don't know" with a
> stated error rate. We take two photographs, because a photograph of a card is flat
> and cannot fake depth, which is how we refuse someone re-photographing a printed
> result. And the verifier reports what it *cannot* prove as loudly as what it can.

### Three minutes — technical
> L1: four fiducials give a homography onto a millimetre grid, so patches are sampled
> at known coordinates. The grey ladder gives a light field we divide out. Then a
> root-polynomial least-squares transform maps the phone's RGB to CIEXYZ using the
> card's own patches — solved in the same frame, under the same light. That is the
> whole reason for the card.
>
> L2: CIEDE2000 to reference loci in CIELAB, wrapped in conformal prediction with the
> finite-sample correction, so "inconclusive" carries a stated bound.
>
> L4/L5: canonical CBOR — deterministic, floats refused — hashed with SHA-256 and
> signed in StrongBox. `prev_record_hash` chains records so tampering forks the chain.
>
> L7: two independently written verifiers, no shared code, cross-checked in both
> directions. A single implementation agreeing with itself proves nothing.

### Why each technology
| Choice | Why |
|---|---|
| CIELAB + CIEDE2000 | distance is perceptually meaningful; RGB distance is not |
| Root-polynomial | every term carries the units of intensity, so it is exposure-invariant |
| Conformal prediction | turns "inconclusive" into a quantity with a bound a court can test |
| Canonical CBOR, no floats | the digest is the legal artefact; IEEE-754 rounding must not touch it |
| StrongBox | converts *the app claims* into *this device's hardware signed this* |
| Two implementations | one agreeing with itself proves nothing |
| Pure Dart on-device | an APK that needs a laptop is not a field tool |

### What makes it different
The naive build — photograph, classify, log GPS, export PDF — **already ships
commercially as DetectaChem MobileDetect**. We concede that on slide two. What does
not exist is a field record a court can independently re-derive: kit-agnostic, with a
stated abstention bound, hardware-attested, and verifiable by someone who trusts
neither the app nor us.

### Limitations — say these before you are asked
1. **Never run on a handset.** Everything is measured on synthetic frames or measured
   spectral data.
2. **No reagent calibration.** Loci are surrogates; no such dataset is public.
3. **Anchoring is not real** on either side — a sequence number, no countersignature.
4. **A synchronised stereo replay defeats the liveness check** — replaying the genuine
   pair reproduces the real parallax.
5. **The attestation chain is not walked to a Google root.**
6. **No GPS or mock-location detection in the app** — the location bundle is constant.
7. **The 196 substrate probes are Python-only**, so the app runs a weaker light-field
   check.

---

## 12. Judge questions

**Why the calibration card?**
Because a phone's auto white balance and auto exposure make raw RGB meaningless. The
card puts 23 known colours in the same frame under the same light, so we can solve
what the camera did to *those* and apply the same correction to the strip.

**Why not just RGB?**
Euclidean distance in RGB does not correspond to visible difference. Two pairs the
same distance apart in RGB can look identical or obviously different. CIELAB is built
so distance is meaningful, and CIEDE2000 corrects it further where it is worst —
which is near neutral and in the blues, exactly where reagent colours live.

**What is ΔE?**
A number for how different two colours are. Roughly, 1.0 is the smallest difference a
person can see. Our card residual is 0.27 ΔE on a real photograph.

**Why two photographs?**
One frame cannot tell a real card from a photograph of one. We measured it: a
photo-lab print scores 0.48 ΔE — *better* than most honest captures. Depth is the one
thing a reproduction cannot copy, and depth needs two viewpoints. The card's folded
tab shifts 28.1 px between frames; a print shifts 0.1 px.

**How do you detect a fake card?**
Rectify both frames onto the card's own fiducials. Everything flat lands identically;
the 8 mm tab does not. A flat reproduction gives *exactly* zero — that is geometry,
not a tuned threshold.

**Why can the AI say "inconclusive"?**
Because there is no AI, and that is the point. It is conformal prediction: we
calibrate a threshold so the true label is in the returned set at least 1−α of the
time. When the set has two labels, or none, it reports inconclusive. *"At α = 0.05
the reported label is wrong at most 5% of the time on exchangeable data"* survives
cross-examination. *"87% confident"* does not.

**What does SHA-256 do?**
Turns the record into a 32-byte fingerprint. Change one byte and the fingerprint
changes completely. §63 requires the certificate to state it.

**What does signing do?**
Proves the fingerprint was produced by a specific key. **StrongBox** proves that key
was generated inside a tamper-resistant chip and cannot leave it — so the signature
proves *this device*, not merely *someone with a file*.

**Can you prove the officer performed the test?**
**No.** Biometric unlock binds the record to the *enrolled device*, not to a person.
The verifier says so under ASSERTED.

**Can you prove the photographed substance is the seized substance?**
**No, and nothing based on a camera ever could.** It is the first line under
UNVERIFIABLE. It rests on the seizure procedure and the witnesses.

**What happens without internet?**
Everything works. Detection, classification, sealing and signing are all on-device.
Only anchoring needs a network, and its absence is *stated* — the record says how
wide the unanchored window is rather than implying certified time.

**Can someone modify the database?**
There is no database. Records are files. Modify one and its signature fails and the
chain forks. Delete one and replay shows the gap. **The honest gap: truncating the
*head* of the chain is undetectable from the files alone**, and the verifier says so.

**What if the phone is rooted?**
The attestation certificate carries verified-boot state. The verifier reads it *from
the certificate*, not from the record, and fails a record created on a modified
device — detectable years later without the handset.

**Where does it fall short?**
Read §11 limitations aloud. A judge who finds a gap themselves concludes we never
looked; a team that names it first demonstrates the caution forensic work requires.

---

# THE PROJECT IN ONE SIMPLE STORY

An officer stops a car at midnight and finds a packet of powder. They use the drug-test
kit they already carry — a chemical that changes colour. Today that is where it ends:
they write "turned purple" in a diary, and a court cannot do anything with that.

We give them one extra thing: **a printed piece of paper**, costing about ₹5.

It has 23 colour squares we know exactly, four black markers at the corners, and a
small flap folded up so it stands 8 mm above the page.

The officer puts the test strip on the paper and photographs both together. That
matters: the phone's camera adjusts colours automatically and unpredictably, so a
photo of the strip alone means nothing. But photographed *beside colours we already
know*, we can work out what the camera did — and undo it. **The paper turns the phone
into a measuring instrument.**

Then the officer moves a few centimetres and takes a second photo. This is the clever
bit. Someone could photograph a positive result once, print it, and re-photograph that
print forever — and every fake record would look perfect. But **a photograph is flat**.
The folded flap on our paper stands up, so it shifts between the two photos. A print
has nothing standing up, so nothing shifts. Real card: 28 pixels. Print: 0.1 pixels.

The phone then compares the measured colour to known reagent colours. If it is clearly
one of them, it says so. If it sits between two, it says **inconclusive** — and that is
a feature. It is better to say "I don't know" than to be confidently wrong about
something that puts a person in jail.

Everything — both photos, the colour, the quality checks, the depth result — is packed
into a file in a format so precise that two different programs written separately
produce byte-identical output. That file gets a fingerprint (SHA-256), and the
fingerprint is signed by **a key locked inside the phone's security chip** that cannot
be copied out. Each record also carries the previous record's fingerprint, so they form
a chain: change one and everything after it breaks visibly.

Months later, a defence lawyer runs our verifier on their own laptop, offline, trusting
nothing. It re-does the whole calculation and prints three lists: what it **proved**,
what is merely **claimed**, and what **nothing could ever prove** — including whether
the substance in the photo is the substance that was seized.

That last list is the point. A tool that only ever says "VALID ✓" teaches courts to
trust it too much. Ours ends:

> **A verified record is not a true result. It is an unaltered one.**
