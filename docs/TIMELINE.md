# Build log

What was built, in order, and — more usefully — **what testing proved wrong along
the way**. Reconstructed from the commit history.

The pattern worth noticing: almost every entry marked ⚠ was found by *running*
something, not by reasoning about it. Four of them were found only after the code
met a real photograph or a real screen.

---

## Day 1 — the argument

| | |
|---|---|
| **Architecture and novelty docs** | Seven layers, threat model, data strategy. The load-bearing decision: *the classifier is not the product, the record is.* Prior art conceded up front — the naive build already ships as DetectaChem MobileDetect. |
| **Problem-statement dataset** | 233 SIH 2026 statements, pinned by SHA. |
| **Interface design** | Nine-screen clickable prototype plus `DESIGN.md`: seven rules every screen obeys, chief among them *colour never means good or bad*. |

## Day 1 (evening) — the core

| | |
|---|---|
| **The evidentiary core** | Canonical CBOR (hand-rolled, no dependency), the Field Test Record, the append-only ledger, keystore abstraction, conformal abstention, and the reference verifier. 81 tests. |
| ⚠ **A software key must FAIL verification** | Three tests failed on first run — correctly. `SoftwareKeystore` reports `SOFTWARE` and the verifier treats that as disqualifying, not a warning. The simulated-hardware keystore was moved into `tests/`, never the package. |
| **L1 complete** | Fiducials, homography, illumination correction, sampling, quality gate. |
| ⚠ **The card had a latent measurement bug** | All eight neutral patches sat on **one row**, leaving the bi-quadratic illumination surface unconstrained in *y*. A torch hotspot passed the quality gate carrying **52 ΔE** of error. Neutrals now span three rows and five columns. |
| ⚠ **INUC was competing with the device transform** | The illumination fit was absorbing the global illuminant cast, which the transform already handles properly using 23 patches instead of 8. Now mean-normalised: it corrects *spatial* variation only. |

## Day 2 (early) — two implementations

| | |
|---|---|
| **The second verifier** | Dart, independently written. No shared code, no shared dependency: different SHA-256, different ECDSA, different bignum. Cross-checked against committed vectors in both directions. |
| ⚠ **"Bit-for-bit" was not defensible as written** | §9 claimed the verifier reproduces the classification bit-for-bit. Measured across the two implementations: doubles diverge by ~10⁻¹¹. But the **stored `lab_x100` integers agree exactly**, because every measured field is a scaled integer eleven orders of magnitude above the divergence. `DETERMINISM.md` states what may actually be claimed. |
| **Track F tooling** | `survey` and `calibrate`, evaluating on a **held-out illuminant** rather than held-out samples. |

## Day 2 — the statute, and the sweep

| | |
|---|---|
| **L6 certificate emitter** | BSA §63 Part A auto-populated, eSakshya envelope, handoff bundle. |
| ⚠ **The §63 Schedule was transcribed, and the record schema was wrong** | Fetching the real Schedule showed Part A is filled by *"the Party"* not "the person in charge", **Part B also states the hash**, and SHA256 is named in the Schedule itself. It also asks for Make & Model, Serial Number and **IMEI** — none of which the FTR carried. It carried `android_id_hash`, a privacy-preserving identifier, which is exactly the wrong thing for a form asking for an IMEI. |
| ⚠ **Three false accepts found by an 83-condition sweep** | A hard shadow edge accepted at **17.3 ΔE**; JPEG q10 at **11.6 ΔE**; sensor noise entirely invisible because `spread` was computed and never used — and computed wrongly, across all three channels together, so a purple patch looked noisy while being clean. |
| ⚠ **The replay defence was false** | §10 row 1 claimed replay was beaten because the card must be co-planar with the strip. **A replay reproduces the whole scene, so co-planarity is preserved.** A photo-lab print scored **0.48 ΔE** — better than most honest captures. Moved to *not defended*. |
| ⚠ **The camera simulator was measuring an easier problem** | A per-channel RGB gain **cannot produce metamerism**, so every cross-illuminant number was optimistic. Replaced with rendering from measured reflectance × measured SPD × 28 measured camera sensitivities. The ablation verdict survived; the no-learned-component conclusion now rests on physics. |

## Day 2 (evening) — the submission, and the fix

| | |
|---|---|
| **Idea-submission deck and architecture diagram** | Six slides from the official template; a diagram organised by **trust boundary** rather than by component. |
| **Two-view parallax** | The replay hole closed. A flat reproduction gives **exactly zero** parallax by geometry. The measurement forced a card change: a wet strip is ~0.4 mm and yields ~1 px, so the card gained a **fold-up 8 mm liveness tab**. Print 0.1 px, screen 0.0 px, physical card 28.1 px. |
| ⚠ **Two bugs in the test rig itself** | The replay renderer was standing a *real* tab on top of the printed sheet (a print with a physical tab, which *should* pass), and pasting a whole camera frame into the card quad instead of a correctly-sized print. Both made the replay look defeated when it was not. Caught because the first run showed the print passing at 28.1 px — too suspicious to accept. |
| **Liveness bound into the record** | A defence the verifier cannot see is not evidence. `liveness` became a top-level FTR field; a flat capture is a **refusal**, not an error. |

## Day 3 — making it real

| | |
|---|---|
| ⚠ **The app could not compile for web at all** | `verifier.dart` imported `dart:io` and the barrel exported it. Split into a pure verifier that runs anywhere and `verifier_io.dart` for the chain reader. *An in-app verifier that could not run in the app was a strange thing to have built.* |
| ⚠ **The viewfinder was ~2600 px tall on a desktop** | A 3:4 aspect box unconstrained on a wide window pushed the quality meters and the shutter off screen. The app looked frozen when it was merely enormous. |
| ⚠ **The two capture screens were indistinguishable** | Taking the first frame read as going backwards. Now a `1/2` – `2/2` step counter and a banner. A fourth bug — an app-bar overflow — was caught by the responsive test written minutes earlier. |
| **The camera, and then the real pipeline** | The viewfinder had always been a placeholder. Wired a real camera, then a localhost bridge running the actual `ftr.pipeline` so the numbers stopped being simulated. |
| **L1 ported to pure Dart** | So an APK works in a room with no laptop. The detector does **not** decode ArUco: the card is ours, and *a fiducial is a dark square with white inside it, while every colour patch is a dark square that is solid.* |
| ⚠ **A stray ×255 made every frame read as soft** | Found only when the detector met a real photograph. Every synthetic test passed with the bug in place. |
| **StrongBox** | Keys generated in the secure element with an attestation challenge, honest TEE fallback, chain shipped raw. **The verifier reads verified-boot from the certificate, never from the record** — and fails a record that claims more hardware than its certificate attests to. |
| ⚠ **A DER tag parsed wrongly** | `RootOfTrust` sits at context tag `[704]`, encoded `BF 85 40`. The first reader took only the leading byte and treated `0x85` as a length prefix. |

| ⚠ **The seal button did nothing, on a real handset** | The key was generated with `setDigests(SHA256)` and signed with `NONEwithECDSA`, which Android rejects. Two bugs sat behind it: `_seal()` had no error handling, so the exception vanished, and the record being sealed was a hardcoded constant rather than the live measurement. |
| ⚠ **The Dart verifier failed every genuine StrongBox record** | `IN_ATTESTATION` — the app's deliberate refusal to assert verified boot — fell through to the "modified device" branch. The app's honesty was being read as evidence against it. |
| ⚠ **`biometric_unlock_used` was hardcoded `true`** | The key never had `setUserAuthenticationRequired`. A false claim inside a signed body. Set to `false`, and **both verifiers now state it** — silence would read as a pass. |
| ⚠ **The location bundle claimed 4-of-4 channels agreeing** | On a device that had never read a position. Same class of lie as the biometric flag, and the largest remaining mockup. Replaced with a real fix that never invents: every failure path returns a status naming what happened, and the record says `available: false` rather than going quiet. Both verifiers now refuse to describe **one** agreeing channel as "all channels agreed" — true, and deeply misleading. |
| **Offline made enforceable, not promised** | Once L1 ran on-device, the HTTP measure bridge was dead code on every path — so it went, and with it the `INTERNET` permission. "Works offline" became "cannot go online", enforced by Android rather than by our discipline. |
| **Handoff, and what anchoring actually buys** | `exportChain` writes a self-contained bundle to the share sheet — no network client. Exporting is what witnesses the chain: once a bundle is off the handset, rewriting those records is contradicted by a copy the app cannot reach. Weaker than a countersigned timestamp, and labelled as weaker everywhere it appears. |
| **Two devices in one directory** | Records from a second handset, each individually valid and correctly chained, imply an ordering no single device witnessed. Both implementations now check the signing key **across** the chain and report a `foreign_key` break. |

---

## Where it stands

| Track | State |
|---|---|
| **A** — colour pipeline | Done; 83-condition sweep, 0 false accepts |
| **B** — classification | Done and ablated; no learned component earned its place |
| **C** — provenance | Done twice, cross-checked in both directions |
| **D** — app | Standalone APK: on-device pipeline, liveness, StrongBox, persistent ledger, handoff bundle. No `INTERNET` permission. **Tested on a handset; seal path fixed there.** |
| **E** — statutory | Emitter built, Schedule transcribed. Needs one Gazette comparison. |
| **F** — data | **Not started. The critical path.** See [`DATA-NEEDED.md`](DATA-NEEDED.md). |

**398 automated tests.** Every figure quoted anywhere in this repository is measured
on synthetic frames or on measured spectral data. **None is a field accuracy**, because
no printed card has yet been photographed through the full capture matrix.
