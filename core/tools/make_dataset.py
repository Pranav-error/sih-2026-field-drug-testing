"""Generate a synthetic capture set at scale, for calibration and ablation.

This is a *stand-in*, and the honest framing matters: it reproduces the optical
problem — distinguishing nearby colours under uncontrolled illumination — and none
of the chemistry. No accuracy figure from it belongs in a submission without the
sentence that says so. Its job is to prove the training and evaluation machinery
works end to end before the physical capture set exists, so that when the real
frames arrive nothing is being written for the first time.

    python core/tools/make_dataset.py OUTDIR --per-condition 40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "tests"))

from synth import photograph, render_card   # noqa: E402

# Four classes, two of them deliberately close together. A reagent that developed
# well-separated colours for every substance class would be an easy problem and
# not the one NCB has.
CLASSES = {
    "opiate_class":       (0.28, 0.12, 0.22),
    "opiate_related":     (0.31, 0.15, 0.20),   # ~5 dE from opiate_class
    "amphetamine_class":  (0.34, 0.20, 0.14),
    "negative":           (0.80, 0.78, 0.72),
}

CONDITIONS = {
    "daylight":    dict(illuminant="daylight"),
    "shade":       dict(illuminant="shade", shadow=0.3),
    "tungsten":    dict(illuminant="tungsten", exposure=0.85),
    "fluorescent": dict(illuminant="fluorescent"),
    "overcast":    dict(illuminant="daylight", exposure=0.6, shadow=0.2),
    "indoor_led":  dict(illuminant="torch", exposure=0.9),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path)
    ap.add_argument("--per-condition", type=int, default=40)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    total = 0
    for label, well in CLASSES.items():
        card = render_card(well_srgb=well)
        for cond, base in CONDITIONS.items():
            d = a.out / label / cond
            d.mkdir(parents=True, exist_ok=True)
            for i in range(a.per_condition):
                kw = dict(base)
                # Nuisance variation an officer introduces without meaning to.
                kw.update(
                    tilt=float(rng.uniform(0, 18)),
                    rotation=float(rng.uniform(-25, 25)),
                    noise=float(rng.uniform(0.5, 4.0)),
                    jpeg_quality=int(rng.integers(72, 96)),
                    exposure=float(base.get("exposure", 1.0) * rng.uniform(0.88, 1.12)),
                )
                cv2.imwrite(str(d / f"{i:03d}.jpg"), photograph(card, rng=rng, **kw))
                total += 1
        print(f"  {label}: {len(CONDITIONS) * a.per_condition} frames", flush=True)

    print(f"{total} frames -> {a.out}")
    print(f"{len(CLASSES)} classes x {len(CONDITIONS)} conditions x {a.per_condition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
