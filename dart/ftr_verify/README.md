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
dart test                                        # 44 tests
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

## Not implemented here

The Dart verifier checks encoding, digest, signature, attestation fields and the
chain. It does **not** re-run L1/L2 from the raw frame — that requires the colour
pipeline, which lives in Python and in the Flutter app's native path. Until it
does, a record verified only by this implementation has had its integrity checked
but not its *result* reproduced, and the report says so by omission rather than
claiming otherwise.
