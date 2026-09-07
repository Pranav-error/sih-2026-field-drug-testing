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
- [`docs/app-prototype.html`](docs/app-prototype.html) — clickable nine-screen prototype with the
  rationale beside each screen.

## Code

- [`core/`](core/README.md) — `ftr`, the evidentiary core: canonical CBOR, the Field Test Record,
  the append-only ledger, the colorimetry pipeline, and the independent verifier. 81 tests.

```sh
python3 -m venv .venv && .venv/bin/pip install -e core[dev]
.venv/bin/python core/demo.py --keep /tmp/ftr-demo   # end-to-end, then four attacks
.venv/bin/python -m pytest core -q                  # 123 tests
.venv/bin/python -m ftr.printable --out card.png    # print a reference card
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
| C — crypto / provenance | **Implemented.** `core/ftr`: canonical CBOR, FTR, hash chain, verifier, `ftrverify` CLI. |
| A — colour pipeline | **Implemented.** Fiducial detection, homography, illumination correction, patch sampling, quality gate, device transform. Worst error on an accepted frame: 0.76 dE2000 — on synthetic frames only. |
| B — classification | **Implemented.** Conformal abstention with the finite-sample correction; coverage tested empirically. |
| D — app | **Designed, not built.** See `docs/DESIGN.md` and the prototype. |
| E — legal / statutory | Not started. Blocked on transcribing the BSA §63 Schedule from the bare Act. |
| F — data | **Not started, and it is the critical path.** The reference card is now printable (`python -m ftr.printable`); no physical card has been photographed yet. |

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
