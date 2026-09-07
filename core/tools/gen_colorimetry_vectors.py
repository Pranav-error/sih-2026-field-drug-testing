"""Colorimetry vectors for the cross-implementation agreement test.

ARCHITECTURE.md §9 says the verifier "re-runs L1/L2 from the raw image and checks
the stored classification reproduces bit-for-bit." Two implementations in two
languages with different least-squares algorithms will *not* agree bit-for-bit on
floating point, and pretending otherwise would put an undefendable sentence in the
submission.

So this emits full-precision inputs and outputs, the Dart suite reproduces them,
and the divergence is measured rather than assumed. What the record may claim
follows from that measurement — see docs/DETERMINISM.md.

    python core/tools/gen_colorimetry_vectors.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from ftr.card import CARD_V1                                          # noqa: E402
from ftr.colorimetry import (ConformalClassifier, RootPolynomial,      # noqa: E402
                             delta_e_2000, srgb_to_linear, xyz_to_lab)
from ftr.pipeline import SRGB_TO_XYZ_D65, reference_xyz               # noqa: E402

OUT = ROOT / "dart" / "ftr_verify" / "test" / "vectors"

# Sharma, Wu & Dalal (2005) conformance data. Both implementations are checked
# against the standard, not merely against each other — two implementations can
# agree on the same mistake, and only an external reference catches that.
#
# ⚠ TRANSCRIPTION WARNING. These rows were written from memory and then checked
# numerically; every one below reproduces to 1e-4 in both implementations. A
# fifteenth row was dropped after both implementations disagreed with the value
# recalled for it, and a bound on dE00 for that pair showed the recalled value was
# impossible — the pairing had been misremembered, not the arithmetic.
#
# Before anything derived from this set goes into the submission, transcribe the
# full table from the published paper or CIE 142-2001. Same rule the project
# applies to the BSA Schedule: read the source, not a recollection of it. A test
# that agrees with a wrong reference is worse than no test.
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
]


def main() -> int:
    rng = np.random.default_rng(20260907)

    # 1. sRGB -> linear -> XYZ -> Lab, over the whole range including the knee.
    srgb_cases = [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.04045, 0.04045, 0.04045],
                  [0.5, 0.5, 0.5], [0.28, 0.12, 0.22], [0.003, 0.9, 0.41]]
    srgb_cases += rng.uniform(0, 1, size=(24, 3)).tolist()
    lab_from_srgb = [
        {"srgb": c, "lab": xyz_to_lab(srgb_to_linear(np.array(c)) @ SRGB_TO_XYZ_D65.T).tolist()}
        for c in srgb_cases
    ]

    # 2. CIEDE2000 against the published conformance data.
    sharma = [{"lab1": list(a), "lab2": list(b), "expected": e,
               "ours": float(delta_e_2000(np.array(a), np.array(b)))}
              for a, b, e in SHARMA]

    # 3. A real transform fit on the card's own patches.
    ref = reference_xyz()
    device_rgb = np.clip(
        srgb_to_linear(CARD_V1.patch_srgb) * np.array([1.06, 0.98, 0.91])
        + rng.normal(0, 0.004, CARD_V1.patch_srgb.shape), 1e-4, 1.0)
    t = RootPolynomial.fit(device_rgb, ref)
    probes = rng.uniform(0.02, 0.95, size=(12, 3))
    transform = {
        "device_rgb": device_rgb.tolist(),
        "reference_xyz": ref.tolist(),
        "matrix": t.matrix.tolist(),
        "residual_delta_e": t.residual_delta_e,
        "max_delta_e": t.max_delta_e,
        "probes": [{"rgb": p.tolist(), "lab": t.to_lab(p[None, :]).tolist()} for p in probes],
    }

    # 4. Conformal calibration and prediction, including both abstention modes.
    # Four loci, including two that sit close together. That is not a contrivance
    # to exercise the test: Marquis develops similar dark colours for related
    # compounds, and the interesting abstention is between two *positive* classes,
    # never between a positive and a blank strip.
    loci = {
        "opiate_class": [18.4, 23.2, -7.5],
        "opiate_class_related": [22.1, 20.4, -4.8],
        "amphetamine_class": [40.3, 14.3, 26.4],
        "negative": [80.1, -1.2, 5.9],
    }
    cal_labs, cal_lbls = [], []
    for name, locus in loci.items():
        for _ in range(200):
            cal_labs.append((np.array(locus) + rng.normal(0, 2.4, 3)).tolist())
            cal_lbls.append(name)
    clf = ConformalClassifier({k: np.array(v) for k, v in loci.items()}, alpha=0.05)
    threshold = clf.calibrate(np.array(cal_labs), cal_lbls)

    queries = [
        list(loci["opiate_class"]),                       # confident singleton
        [(a + b) / 2 for a, b in                          # ambiguous: two labels
         zip(loci["opiate_class"], loci["opiate_class_related"])],
        [55.0, -60.0, 70.0],                              # empty set: resembles nothing
        list(loci["negative"]),                           # the other confident call
    ]
    conformal = {
        "loci": loci,
        "alpha": 0.05,
        "calibration_labs": cal_labs,
        "calibration_labels": cal_lbls,
        "threshold": threshold,
        "queries": [],
    }
    for q in queries:
        p = clf.predict(np.array(q))
        conformal["queries"].append({
            "lab": q,
            "prediction_set": list(p.prediction_set),
            "label": p.label,
            "scores": {k: float(v) for k, v in p.scores.items()},
        })

    (OUT / "colorimetry.json").write_text(json.dumps({
        "note": "Generated by core/tools/gen_colorimetry_vectors.py. Full precision. "
                "Dart must reproduce these; the agreement test measures how closely "
                "and asserts the bound recorded in docs/DETERMINISM.md.",
        "lab_from_srgb": lab_from_srgb,
        "ciede2000_sharma": sharma,
        "transform": transform,
        "conformal": conformal,
    }, indent=2) + "\n")

    print(f"wrote {len(lab_from_srgb)} Lab cases, {len(sharma)} CIEDE2000 conformance "
          f"cases,\n  a {len(device_rgb)}-patch transform fit with {len(probes)} probes, "
          f"and {len(queries)} conformal queries")
    print(f"  -> {OUT / 'colorimetry.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
