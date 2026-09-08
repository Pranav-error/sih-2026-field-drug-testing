# `ftr` — the evidentiary core

Python reference implementation of layers L1, L2, L4, L5 and L7 of
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

The classifier is not the product. The record is. This package is the record.

```
ftr/
  card.py             the printed reference card: geometry and nominal colour
  printable.py        renders it at print resolution — python -m ftr.printable
  detect.py           L1 front half: fiducials, homography, INUC, sampling, gate
  colorimetry.py      L1 back half + L2: device transform, CIEDE2000, conformal
  pipeline.py         one frame in, one measurement out — the code the verifier re-runs
  ingest.py           track F: survey a capture set, calibrate on a held-out illuminant
  canonical_cbor.py   deterministic encoding — the digest is the legal artefact
  record.py           the Field Test Record, sealing, the envelope
  chain.py            append-only device ledger, anchoring window
  signing.py          keystore abstraction + attestation, honest about its level
  certificate.py      L6: BSA 2023 s.63 certificate, Part A auto-populated
  esakshya.py         L6: CCTNS-2.0 handoff bundle — not a parallel evidence store
  verifier.py         proven / asserted / unverifiable
  cli.py              ftrverify · ftr-printable · ftr-ingest · ftr-certificate
```

## Run it

```sh
python3 -m venv .venv && .venv/bin/pip install -e core[dev]
.venv/bin/python core/demo.py --keep /tmp/ftr-demo    # end-to-end + 4 attacks
.venv/bin/python -m pytest core                        # 199 tests
./check.sh                                             # both implementations
```

`demo.py` photographs three synthetic strips under three different lighting
conditions, runs each through the real L1/L2 pipeline, seals all three into a
chain — including the one the instrument **refuses to read** — verifies the chain,
then runs four rows of the adversary matrix (§10) live: image edit, result
rewrite, mid-chain deletion, and head truncation. The last of these it *fails to
catch*, and says so.

Print a card:

```sh
.venv/bin/python -m ftr.printable --out card.png --serial 0417 --batch B12
```

Verify a chain yourself, offline, trusting nothing:

```sh
.venv/bin/python -m ftr.cli chain /tmp/ftr-demo/chain
.venv/bin/python -m ftr.cli record /tmp/ftr-demo/chain/000000.ftr \
    --image raw_image_sha256=frame.jpg
```

## What L1 actually achieves

Measured on the synthetic capture matrix (`tests/synth.py`), against a known
ground-truth well colour:

| Condition | Error, no INUC | Error, with INUC | Gate |
|---|---|---|---|
| ideal | 0.31 | 0.46 | pass |
| open shade | 0.13 | 0.37 | pass |
| fluorescent | 0.57 | 0.64 | pass |
| underexposed ×0.55 | 0.38 | 0.52 | pass |
| shadow across card, 0.55 | 1.82 | **0.40** | pass |
| hard shadow, 0.75 | 2.95 | **0.53** | pass |
| shadow + shade + JPEG + noise | 1.43 | **0.76** | pass |
| torch hotspot | 22.85 | 18.25 | **reject** |
| very blurry | — | — | **reject** |
| far too dark | — | — | **reject** |
| tilt 32° | — | — | **reject** |

dE2000. The claim is not "the pipeline is accurate" — it is:

> **The worst error on any frame the gate accepted is 0.76 dE2000.** Every frame
> carrying a large error was rejected, with guidance naming what to move.

That is the property `test_frames_the_gate_accepts_are_accurate` enforces, and it
is the only one worth stating in a submission. These are synthetic frames: real
ink, real paper gloss and a real ISP will be worse. The number to quote at the
finale comes from the physical capture matrix, not from here.

## Two things testing changed about the design

**The card had a latent measurement bug.** All six neutral patches sat on one row,
so the bi-quadratic illumination surface was unconstrained in *y* and could not
see a shadow or hotspot above or below that line. A torch hotspot passed the
quality gate carrying a **52 dE** error. The neutrals now ring the colour field at
three rows and five columns, and `test_neutrals_span_the_card_in_both_axes` stops
that regressing. A layout mistake here is a silent measurement error everywhere
downstream — which is exactly the class of bug a colour chart is supposed to
prevent.

**INUC was competing with the device transform.** Fitted naively, the illumination
surface absorbed the *global* illuminant gain, which the root-polynomial transform
already handles properly using all 23 patches instead of 8 neutrals. The surface
is now mean-normalised over the card so it corrects only *spatial* variation.
Conceding the global term costs nothing; competing for it cost ~1.5 dE under a
coloured illuminant.

## Five decisions worth defending

**1. Canonical CBOR, hand-rolled, no dependency.**
The digest is what §63 requires the certificate to state, so serialisation must be
byte-identical for identical content on every implementation, forever. The profile
is RFC 8949 §4.2.1 core rules: definite lengths, shortest-form integers, map keys
sorted bytewise on their *encoded* bytes. `is_canonical()` rejects anything a
canonical encoder could not have produced, which is what stops a challenger
smuggling in a second encoding of the same content.

**2. Floats are refused outright.**
`dumps({"delta_e": 3.81})` raises. Every measured quantity is a scaled integer with
the scale in the field name — `delta_e_x1000`, `lab_x100`, `alpha_x1000`. IEEE-754
rounding differences between a Dart implementation and a Python one are not worth
defending under cross-examination.

**3. A software key fails verification, loudly.**
`SoftwareKeystore` reports `security_level = "SOFTWARE"` and the verifier treats
that as a *failure*, not a warning:

> Signing key security level is SOFTWARE. The key is not hardware-backed, so the
> signature proves only that whoever held the key file made this record.
> Development records must never be presented as evidence.

The simulated-hardware keystore lives in `tests/`, never in the package. A class
that lets software claim StrongBox would destroy the only thing the record is for.

**4. The verifier has three buckets, and the last two are the point.**
`PROVEN` is re-derived from the bytes here. `ASSERTED` is in the record but nothing
supports it — wall-clock time, operator identity behind the biometric,
operator-declared reagent. `UNVERIFIABLE` is outside what any bundle of bytes could
establish: whether the substance photographed is the substance seized. The report
ends with *"A verified record is not a true result. It is an unaltered one."*

**5. Conformal abstention, with the finite-sample correction.**
`ConformalClassifier.calibrate()` takes the `ceil((n+1)(1-α))`-th smallest score,
not the empirical `1-α` quantile. Getting that wrong loses the guarantee quietly.
`test_conformal_coverage_holds_on_held_out_data` checks the coverage empirically
rather than trusting the construction.

## Known gaps

| Gap | Status |
|---|---|
| Head truncation | Undetectable from files alone. Reported as unverifiable, by design. |
| Real card, real ink | Everything above is synthetic. No printed card has been photographed. **This is the critical path** — see `docs/CAPTURE.md`. |
| Real attestation chain parsing | `cert_chain` is carried and counted, not walked to a Google root. Next task on this track. |
| BSA §63 certificate emitter | **Built, and deliberately stamped DRAFT.** The statutory field *labels* are unverified paraphrases; every computed value is real. Track E transcribes the Schedule into `ftr/data/bsa63_schedule.json` and flips one flag. |
| eSakshya ingest interface | Envelope is well-formed and marked PROVISIONAL. Nobody has yet established whether a documented ingest interface exists (§13 q2). |
| Anchoring service | `Chain.anchor()` records a sequence number. The countersignature and the eSakshya receipt are not implemented. |
| Dart implementation | **Done** — `dart/ftr_verify`, including L1's colour transform and L2. It cannot yet find the card in a photograph (ArUco is native), so it reproduces a *measurement* but not yet a *frame*. |

## Test suite

199 Python tests, plus 65 in Dart. The ones that matter most:

- `test_canonical_cbor.py` — RFC 8949 vectors, key ordering, and nine classes of
  non-canonical input that must be rejected.
- `test_chain.py` — the adversary matrix as executable cases, including
  `test_software_keys_never_verify_as_evidence` and
  `test_a_location_disagreement_is_recorded_not_suppressed`.
- `test_colorimetry.py` — CIEDE2000 against the Sharma et al. conformance data,
  and the conformal coverage guarantee measured over 800 trials.
- `test_cross_implementation.py` — the committed vectors both languages read. If a
  change to either encoder makes these bytes stop matching, the contract is working.
- `test_certificate.py` — the three rules L6 will not bend: the app never fills a
  field a human must attest, nothing is asserted that the record does not carry,
  and an unverified Schedule can only produce a DRAFT.
- `test_detect.py` — the capture matrix: what the gate accepts must be accurate,
  what would mislead must be rejected, and
  `test_the_printable_card_is_detectable_after_a_camera_round_trip` closes the
  loop between the card we print and the card we detect.
