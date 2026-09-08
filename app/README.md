# Field Companion — the app

Flutter client for SIH26231. Implements the capture spine from
[`../docs/DESIGN.md`](../docs/DESIGN.md): standby → capture → result → sealed.

```sh
flutter pub get
flutter test        # 21 tests, each asserting a rule from DESIGN.md
flutter run
```

## What is real, and what is not

| | State |
|---|---|
| **Sealing** | Real. Goes through `ftr_verify`, the same package the reference verifier reads. Records this app produces verify in Python. |
| **Canonical CBOR, hash chain, envelope** | Real, shared — the app does **not** carry its own copy. |
| Screens, gating, guidance copy | Real, and tested. |
| Camera | **Not implemented.** A button stands in for the frame settling. |
| L1 colour pipeline | **Not wired.** Card detection needs OpenCV over a platform channel; the Dart colour maths is in `ftr_verify`. |
| StrongBox keystore | **Not implemented.** Development builds sign with a software key. |
| Archivo / IBM Plex Mono | **Not bundled.** Flutter falls back silently on an unknown family, so each is paired with a real fallback stack — `monospace` first for the mono face. Bundle the real faces before the finale; the fallback keeps the *rule* true, not the look. |

The app has been analysed, unit-tested and compiled. **It has not been run on a
handset.** Nothing here has seen a real camera frame.

## The one thing to understand before changing it

The app does not carry its own encoder. `pubspec.yaml` depends on `ftr_verify` by
path, and sealing goes through `ftr.seal()`. A second implementation of canonical
CBOR living inside the app is exactly the divergence the two-implementation rule
exists to prevent — if the app encoded records its own way, the reference verifier
agreeing with itself would prove nothing about what the handset actually wrote.

Records this app seals are verified by the Python suite in
`core/tests/test_dart_interop.py`, which is the direction that matters: **the app
is the writer.**

## Why a development build refuses to look trustworthy

`SoftwareKeystore` reports `securityLevel = "SOFTWARE"`. Both verifiers treat that
as a **failure**, not a warning, and the standby screen says so on its face:

> This build signs with a software key. Records it produces are for development
> only and will fail verification. They must never be presented as evidence.

There is deliberately no way to make a software key claim StrongBox. A demo that
looked like real evidence would be the worst possible artefact to build.

## Rules the widgets enforce

`test/design_rules_test.dart` tests the rules rather than the pixels — padding is
free to change, these are not:

- **Colour never means good or bad.** `Outcome` has three cases and none is
  `success`; there is no such token to reach for. Positive and negative are
  different colours and neither is the accent.
- **The word *presumptive* is never off-screen** on any screen that shows or seals
  a result, for every outcome including both abstentions.
- **An abstention is a result, not an error.** No "Error", no "Try again", no
  "Failed" — and it can be sealed like any other outcome, because an inconclusive
  result is evidence too.
- **A non-singleton prediction set is always an abstention**, whatever it contains.
- **The shutter is gated on measurability.** A bad frame cannot be captured, and
  the guidance names what to move rather than what went wrong.
- **The device is honest about itself.** Evidence grade requires hardware backing
  *and* verified boot *and* a locked bootloader.
- **The sealed screen states the limits of its own proof** — including that it does
  not prove wall-clock time.
- **Touch targets are ≥ 48dp and state is never colour-only.** Gloves, sunlight,
  and an issued handset.

## Next

1. Platform channel for the camera and the native L1 pipeline (OpenCV/ArUco).
2. `StrongBoxKeystore` over a platform channel — `KeyGenParameterSpec.Builder`
   with `setIsStrongBoxBacked(true)` and `setAttestationChallenge(digest)`, with an
   explicit TEE fallback whose weaker guarantee is recorded rather than glossed.
3. On-device chain storage and the record log screen.
4. The remaining screens from `DESIGN.md`: setup, quality gate, log, certificate,
   verifier report.
