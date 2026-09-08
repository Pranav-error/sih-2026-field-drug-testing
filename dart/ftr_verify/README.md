# `ftr_verify` — the second verifier

An independent Dart implementation of the Field Test Record verifier, and the
in-app verifier for the Flutter client.

It exists because of one line in [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) §11:

> two independent implementations, because a single implementation that agrees
> with itself proves nothing.

## What "independent" means here

| | Python (`core/ftr`) | Dart (this package) |
|---|---|---|
| CBOR | hand-written, no dependency | hand-written, no dependency |
| SHA-256 | `hashlib` (CPython/OpenSSL) | `package:crypto` (pure Dart) |
| ECDSA P-256 | `cryptography` (Rust/OpenSSL) | `pointycastle` (pure Dart) |
| Report wording | its own | its own |

No shared code, no shared dependency, different bignum implementations. The
report *prose* is deliberately not copied between them — a reader comparing the
two is comparing two readings of the record, not one text printed twice. What must
match exactly is the verdict and the digest.

## Run it

```sh
dart pub get
dart test                                        # 65 tests
dart run bin/ftrverify.dart chain  /path/to/chain
dart run bin/ftrverify.dart record /path/to/000000.ftr --image raw_image_sha256=frame.jpg
```

From the repository root, `./check.sh` runs both suites and then asserts the two
verifiers reach the *same verdict* on the same chain.

## The contract

`test/vectors/` is written by `core/tools/gen_vectors.py` and read by **both**
suites:

- `encoding.json` — 22 structures that must round-trip identically, and 13
  non-canonical encodings that must be refused. Every reject case is a way a
  challenger could try to smuggle a second encoding of the same content past a
  verifier: indefinite lengths, non-shortest integers, out-of-order keys,
  duplicate keys, floats, tags, trailing bytes.
- `chain/` — three records sealed by Python with a simulated hardware key. Dart
  must verify the signatures, replay the chain, and surface the location
  disagreement on record #2 without failing it.
- `tampered/` — the same chain under three attacks. All must fail in both.

Regenerate deliberately, never to make a test pass:

```sh
python core/tools/gen_vectors.py
```

If a change to either encoder makes the committed bytes stop matching, that is the
contract working. The digest is what a §63 certificate has to state; it is worth
stating only because two separately written encoders reach it.

## Colorimetry, and what agreement bought

`lib/src/colorimetry.dart` is the second implementation of L1's device transform
and L2's conformal abstention — written from the specification, and deliberately
solving least squares by the normal equations rather than numpy's SVD, so the
verifier does not inherit the other implementation's numerics.

Measured divergence on the shared vectors:

| Quantity | Worst |
|---|---|
| sRGB → CIELAB | 5.5 × 10⁻¹⁴ |
| CIEDE2000 | 1.0 × 10⁻¹⁴ |
| Transform matrix coefficient | 3.1 × 10⁻¹¹ |
| Conformal threshold | 8.9 × 10⁻¹⁶ |
| **Stored `lab_x100` integers** | **0** |

The doubles do not agree bit-for-bit and never will. The *stored* values agree
exactly, because every measured field is a scaled integer and the divergence sits
eleven orders of magnitude below the coarsest quantum. That is what the record is
allowed to claim, and [`../../docs/DETERMINISM.md`](../../docs/DETERMINISM.md)
works through why the stronger-sounding original wording was not defensible.

## Sealing, and why the app writes through this package

`lib/src/seal.dart` builds and seals records, which is what the app does on a
handset. Two directions are now tested, and the second is the one that matters:

| Direction | Where |
|---|---|
| Python seals → Dart verifies | `test/cross_implementation_test.dart` |
| **Dart seals → Python verifies** | `core/tests/test_dart_interop.py` |

A format only one implementation can *write* is not a format, and the app is the
writer. The interop fixture is deterministic (fixed keystore seed) so it can be
committed and a diff means something:

```sh
dart run bin/gen_dart_chain.dart ../../core/tests/vectors/dart_sealed
```

Signatures PointyCastle produces are accepted by OpenSSL through Python's
`cryptography`, and the bytes Dart encodes re-encode identically in Python. A
software-keyed record still fails verification in both, regardless of which side
sealed it.

## Not implemented here

This package cannot **find the card in a photograph** — fiducial detection,
homography and illumination correction need OpenCV, which lives in Python and in
the Flutter app's native path. So it reproduces a measurement from sampled patch
values, not from a raw frame. A record verified only here has had its integrity
checked and its classification re-derived, but not its *image* re-read.
