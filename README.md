# SIH26231 — Digital Companion for Field Drug Testing

Working documents for Smart India Hackathon 2026.

| Field | Value |
|---|---|
| PS ID | **SIH26231** |
| Title | Digital Companion for Field Drug Testing |
| Organisation | Ministry of Home Affairs — **Narcotics Control Bureau** |
| Category | Software |
| Theme | MedTech / BioTech / HealthTech |
| Deadline | 30 September 2026 |

## Documents

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — seven-layer design, threat model, data strategy,
  three-week build plan.
- [`docs/NOVELTY.md`](docs/NOVELTY.md) — prior-art survey, what is *not* novel, the three candidate
  inventive steps, and the §3(k) patentability problem.
- [`docs/DESIGN.md`](docs/DESIGN.md) — interface spec: tokens, the seven rules every screen obeys,
  per-screen behaviour, accessibility.
- [`docs/DETERMINISM.md`](docs/DETERMINISM.md) — what "reproduces bit-for-bit" is allowed to mean,
  measured across the two implementations rather than assumed.
- [`docs/CAPTURE.md`](docs/CAPTURE.md) — the capture protocol for track F, and the only accuracy
  claim worth making.
- [`docs/CERTIFICATE.md`](docs/CERTIFICATE.md) — what the §63 Schedule actually asks for, and the
  record-schema gap transcribing it exposed.
- [`docs/ROBUSTNESS.md`](docs/ROBUSTNESS.md) — the operating envelope, three defects the sweep found,
  the replay attack that **defeats** the pipeline, and why the learned component was dropped.
- [`docs/app-prototype.html`](docs/app-prototype.html) — clickable nine-screen prototype with the
  rationale beside each screen.

## Code

- [`core/`](core/README.md) — `ftr`, the evidentiary core: canonical CBOR, the Field Test Record,
  the append-only ledger, the colorimetry pipeline, the capture tooling, the §63 certificate
  emitter, and the independent verifier. 199 tests.
- [`dart/ftr_verify/`](dart/ftr_verify/README.md) — the **second** verifier, written independently
  in Dart with no shared code or dependencies, plus the sealing path the app uses. 65 tests.
- [`app/`](app/README.md) — the Flutter client. Capture spine implemented and sealing is real;
  camera and StrongBox are not. 21 tests, each asserting a rule from `DESIGN.md`.

```sh
python3 -m venv .venv && .venv/bin/pip install -e core[dev]
.venv/bin/python core/demo.py --keep /tmp/ftr-demo   # end-to-end, then four attacks
.venv/bin/python -m pytest core -q                  # 123 tests
.venv/bin/python -m ftr.printable --out card.png    # print a reference card
.venv/bin/ftr-certificate rec.ftr --bundle out/     # §63 certificate + handoff bundle

./check.sh    # both suites, then asserts the two verifiers reach the same verdict
```

## The one-paragraph version

The problem statement asks for colour classification plus a tamper-evident record. Colour
classification is an undergraduate exercise and the naive whole system already ships commercially
(DetectaChem MobileDetect). The real gap — stated in the PS itself — is that a presumptive field
test **is not usable as documentary evidence**. So the record is the product: a hardware-attested,
append-only, independently re-derivable measurement that emits a Bharatiya Sakshya Adhiniyam §63
certificate and hands off to MHA's existing eSakshya / CCTNS-2.0 evidence pipeline.

No new hardware. A printed colour card and a phone.

## Status

| Track | State |
|---|---|
| C — crypto / provenance | **Implemented, twice.** `core/ftr` in Python and `dart/ftr_verify` in Dart, independently written, cross-checked against shared vectors. |
| A — colour pipeline | **Implemented.** Fiducial detection, homography, illumination correction, patch sampling, quality gate, device transform. Worst error on an accepted frame: 0.76 dE2000 — on synthetic frames only. |
| B — classification | **Implemented, and ablated.** Conformal abstention with the finite-sample correction. Nearest-locus ΔE2000 beat Mahalanobis and logistic regression on held-out illuminants, so L2 stays closed-form — no learned component, no TFLite. |
| D — app | **Capture spine built.** Standby → capture → result → sealed, with real sealing through the shared package; records it produces verify in Python. Camera, native L1 and StrongBox are not wired, and it has never been run on a handset. |
| E — legal / statutory | **Emitter built, Schedule transcribed.** The certificate now carries the Act's real field labels, ticks SHA256 as the Schedule names it, and reports which statutory fields the record cannot supply. Still stamped DRAFT — the transcription is from a bare-Act repository, not the Gazette. Remaining work: one comparison against the eGazette PDF. See `docs/CERTIFICATE.md`. |
| F — data | **Not started, and it is the critical path.** Card is printable and the ingest tooling is built (`ftr.ingest survey` / `calibrate`, see `docs/CAPTURE.md`); no physical card has been photographed yet. |

Track F cannot be compressed by working harder in the last 48 hours. It is the one to start next.

Open questions are listed at the end of `ARCHITECTURE.md`.

## Sources

**Legal**
- Section 63, Bharatiya Sakshya Adhiniyam 2023 — https://indiankanoon.org/doc/125020475/
- BSA §63 admissibility and hash value — https://corpotechlegal.com/admissibility-electronic-evidence-sec-63-bsa/
- Electronic evidence under the BSA — https://blog.ipleaders.in/electronic-evidence-under-the-bsa-2023/
- Admissibility requirements under BSA (LiveLaw) — https://www.livelaw.in/articles/electronic-evidence-admissibility-section-63-bhartiya-saksha-adhiniyam-2023-261511
- NDPS §52A principles, Supreme Court summary — https://www.livelaw.in/supreme-court/s52a-ndps-act-samples-be-drawn-in-presence-of-accused-as-far-as-possible-though-not-at-spot-of-seizure-281502
- NDPS quantity determination and procedural safeguards — https://www.livelaw.in/lawschool/articles/quantity-determination-ndps-act-mixture-theory-procedural-safeguards-scientific-challenges-537649

**Government systems**
- eSakshya (NIC Informatics) — https://informatics.nic.in/files/websites/october-2024/eSakshya.php
- MHA SOP, audio-video recording of scene of crime (BPRD) — https://bprd.nic.in/uploads/pdf/SOP%20of%20Audio-Video%20Recording%20for%20Scene%20of%20Crime%20(1).pdf

**Prior art — commercial**
- DetectaChem MobileDetect release — https://www.police1.com/police-products/fentanyl-protection/press-releases/detectachem-releases-mobiledetect-for-drug-detection-on-smartphones-zJqAlULpj5skoXCU/
- MobileDetect pouches — https://tritechforensics.com/mobiledetect-test-pouches/
- MobileDetect training deck (2018) — http://www.protechsales.com/wp-content/uploads/2019/01/PTS-DetectaChem_MobileDetect-Training-2018.pdf
- Next generation field drug testing — https://www.police1.com/police-products/fentanyl-protection/articles/next-generation-field-drug-testing-AIpmOfxaPeApN9Ox/

**Prior art — patents**
- US20100241451A1 electronic chain of custody for drug testing — https://patents.google.com/patent/US20100241451
- US10244198B2 monitored mobile personal substance testing — https://patents.google.com/patent/US10244198B2/en
- US20060106718A1 electronic chain of custody — https://patents.google.com/patent/US20060106718A1/en

**Colorimetry**
- Device-specific calibration for smartphone colorimetry — https://discovery.ucl.ac.uk/id/eprint/10086021/1/CIC_Final.pdf
- Device-independent colorimetric measurement using smartphones (PLOS One) — https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0230561
- RGB vs HSV vs CIELAB accuracy comparison — https://www.tandfonline.com/doi/full/10.1080/20548923.2024.2444168
- HueDx colour-correction system — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11451979/
- Smartphone colorimetric detection via machine learning — https://arxiv.org/pdf/1703.10217
- Objective presumptive field-testing, centrifugal microdevices + smartphone — https://pubmed.ncbi.nlm.nih.gov/27525468/
- Presumptive tests for xylazine, computer vision — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11961553/
- Portable testing techniques for drug materials (review) — https://wires.onlinelibrary.wiley.com/doi/10.1002/wfs2.1461

**Security**
- Android key attestation — https://developer.android.com/privacy-and-security/security-key-attestation
- Hardware-backed Keystore (AOSP) — https://source.android.com/docs/security/features/keystore
- Key and ID attestation (AOSP) — https://source.android.com/docs/security/features/keystore/attestation
- Geo-spoofing defences — https://www.guardsquare.com/blog/securing-location-trust-to-prevent-geo-spoofing
