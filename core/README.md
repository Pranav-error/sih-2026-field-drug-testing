# `ftr` — the evidentiary core

Python reference implementation of layers L1, L2, L4, L5 and L7 of
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

The classifier is not the product. The record is. This package is the record.

```
ftr/
  canonical_cbor.py   deterministic encoding — the digest is the legal artefact
  record.py           the Field Test Record, sealing, the envelope
  chain.py            append-only device ledger, anchoring window
  signing.py          keystore abstraction + attestation, honest about its level
  colorimetry.py      L1 device transform, L2 conformal abstention
  verifier.py         proven / asserted / unverifiable
  cli.py              ftrverify
```

## Run it

```sh
python3 -m venv .venv && .venv/bin/pip install -e core[dev]
.venv/bin/python core/demo.py --keep /tmp/ftr-demo    # end-to-end + 4 attacks
.venv/bin/python -m pytest core                        # 81 tests
```

`demo.py` builds a three-record chain from synthetic colorimetry, verifies it, then
runs four rows of the adversary matrix (§10) live: image edit, result rewrite,
mid-chain deletion, and head truncation — the last of which it *fails to catch*,
and says so.

Verify a chain yourself, offline, trusting nothing:

```sh
.venv/bin/python -m ftr.cli chain /tmp/ftr-demo/chain
.venv/bin/python -m ftr.cli record /tmp/ftr-demo/chain/000000.ftr \
    --image raw_image_sha256=frame.jpg
```

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
| Fiducial detection / homography | Not implemented — needs OpenCV. The transform math is here and tested; the card *finder* is not. |
| Real attestation chain parsing | `cert_chain` is carried and counted, not walked to a Google root. Next task on this track. |
| BSA §63 certificate emitter | L6 not started; blocked on transcribing the Schedule from the bare Act. |
| Anchoring service | `Chain.anchor()` records a sequence number. The countersignature and the eSakshya receipt are not implemented. |
| Dart implementation | Required — a single implementation agreeing with itself proves nothing. |

## Test suite

81 tests. The ones that matter most:

- `test_canonical_cbor.py` — RFC 8949 vectors, key ordering, and nine classes of
  non-canonical input that must be rejected.
- `test_chain.py` — the adversary matrix as executable cases, including
  `test_software_keys_never_verify_as_evidence` and
  `test_a_location_disagreement_is_recorded_not_suppressed`.
- `test_colorimetry.py` — CIEDE2000 against the Sharma et al. conformance data,
  and the conformal coverage guarantee measured over 800 trials.
