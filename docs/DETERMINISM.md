# What "reproduces bit-for-bit" is allowed to mean

**SIH26231** · supporting note to [`ARCHITECTURE.md`](ARCHITECTURE.md) §9

§9 point 6 says the verifier "re-runs L1/L2 from the raw image and checks the stored
classification reproduces **bit-for-bit**." That sentence needed testing before it
went anywhere near a submission, because as written it is not obviously true: two
implementations, in two languages, with two least-squares algorithms and two libm
implementations, have no general right to agree on a `double`.

So it was measured rather than assumed.

## The measurement

`core/ftr/colorimetry.py` (Python, numpy SVD-based least squares) against
`dart/ftr_verify/lib/src/colorimetry.dart` (Dart, normal equations with partial
pivoting), on the shared vectors in `dart/ftr_verify/test/vectors/colorimetry.json`:

| Quantity | Worst divergence |
|---|---|
| sRGB → CIELAB, per component | 5.5 × 10⁻¹⁴ |
| CIEDE2000 | 1.0 × 10⁻¹⁴ |
| Device transform, per matrix coefficient | 3.1 × 10⁻¹¹ |
| Probe colour through the fitted transform | 1.1 × 10⁻¹¹ dE2000 |
| Conformal threshold | 8.9 × 10⁻¹⁶ |
| **Stored `lab_x100` integers** | **0** |

## What follows

The floating-point values do **not** agree bit-for-bit, and no amount of care will
make them. The *stored* values do, exactly — because every measured quantity in a
Field Test Record is a scaled integer, and the divergence sits eleven orders of
magnitude below the quantum of the coarsest of them.

So the defensible claim is:

> The verifier re-derives the stored measurement from the raw frame and reproduces
> **every recorded value exactly**. The intermediate floating-point computation is
> reproducible to better than 10⁻¹⁰, far inside the precision the record retains.

That is stronger than it sounds and weaker than the original wording. It is
stronger because it holds across two independent implementations rather than one
program run twice. It is weaker because it says nothing about the `double`s, and
should not.

The claim also stops being true if anyone widens a stored field's precision.
`lab_x100` has a quantum of 0.01 against a divergence of ~10⁻¹¹, which leaves nine
orders of headroom; `lab_x1000000` would not. **Precision in the record is a
correctness constraint, not a formatting preference.** `test_record_fields_are_all_integers_or_bools`
and the Dart `scaled integers survive the divergence` test both guard it.

## Why the scaled-integer rule was already right

Canonical CBOR refuses floats outright (`core/ftr/canonical_cbor.py`), which was
justified at the time on the narrower ground that IEEE-754 rounding must not affect
a digest. This measurement is the second, larger justification: it is what makes
cross-implementation re-derivation checkable at all. Had the record stored
`double`s, the verifier's most important check — *"the result in this record is the
result this frame produces"* — would have had to carry a tolerance, and any
tolerance is an argument a defence gets to have.

## A finding worth keeping

While building the agreement test, both implementations disagreed with a published
CIEDE2000 conformance value. The value was wrong: a bound on ΔE₀₀ for that colour
pair (ΔL′ = 0, ΔC′ ≈ 0, so ΔE₀₀ ≈ |ΔH′|/S_H ≤ 4.87) showed the recalled figure of
7.1792 was impossible. It had been written from memory rather than transcribed.

Two consequences, both already applied:

1. The case was dropped, and `core/tools/gen_colorimetry_vectors.py` carries a
   transcription warning: **the conformance table must be copied from the published
   paper or CIE 142-2001 before anything derived from it enters the submission.**
2. It is the reason both implementations are checked against an *external*
   standard and not only against each other. Two implementations can agree on the
   same mistake; only a third party catches that. The same reasoning is why
   `ARCHITECTURE.md` §13 insists the BSA §63 Schedule be read from the bare Act.

## An unrelated property the same work exposed

Two reference loci closer together than the calibrated conformal threshold can
**never** yield a singleton prediction set. The classifier will always return both,
and report inconclusive.

This is correct, and it is a statement about the reagent rather than the software:
if a reagent develops colours for two substance classes that sit 5 dE apart, and
honest calibration puts the threshold at 5.5 dE, then that reagent cannot
distinguish those classes at that risk level and no classifier should claim
otherwise. The right responses are a different reagent, a tighter capture
protocol, or a frank statement of what the test cannot separate — never a lower
threshold chosen to make the output look decisive.
