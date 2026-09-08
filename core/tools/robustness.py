"""Map the operating envelope: where the pipeline works, and where it lies.

Three outcomes matter, and they are not equally bad:

  ACCEPT + accurate    the pipeline worked
  REJECT               the pipeline refused, correctly or over-cautiously
  ACCEPT + wrong       **the dangerous quadrant** — a confident wrong answer

A robustness report that counts only the first two is marketing. This one hunts
the third, because a false accept in the field is a wrong presumptive result
attached to a signed, hardware-attested record that looks trustworthy.

    python core/tools/robustness.py [--quick]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "tests"))

import failure_modes as fm                                            # noqa: E402
from ftr.card import CARD_V1                                          # noqa: E402
from ftr.colorimetry import delta_e_2000, srgb_to_linear, xyz_to_lab  # noqa: E402
from ftr.detect import (detect_card, estimate_illumination, grade_frame,  # noqa: E402
                        rectify, sample_patches, sample_well)
from ftr.colorimetry import RootPolynomial                            # noqa: E402
from ftr.pipeline import SRGB_TO_XYZ_D65, reference_xyz               # noqa: E402
from synth import photograph, render_card                             # noqa: E402

WELL = (0.28, 0.12, 0.22)
TRUTH = xyz_to_lab(srgb_to_linear(np.array(WELL)) @ SRGB_TO_XYZ_D65.T)

# The error at which a presumptive call could flip between reagent classes.
# Reference loci for related compounds sit ~5-9 dE apart, so anything above this
# is capable of changing the reported answer.
DANGEROUS_DE = 4.0


def evaluate(image) -> tuple[str, float | None, str]:
    """Returns (verdict, dE, note). verdict in {no-detect, reject, accept}."""
    det = detect_card(image)
    if det is None or not det.complete:
        found = 0 if det is None else len(det.markers_found)
        return "no-detect", None, f"{found}/4 fiducials"
    rect = rectify(image, det)
    first = sample_patches(rect)
    gain, resid = estimate_illumination(first)
    patches = sample_patches(rect, gain=gain)
    quality = grade_frame(rect, det, patches, resid, gain=gain)

    transform = RootPolynomial.fit(patches.rgb, reference_xyz())
    well, _ = sample_well(rect, gain=gain)
    de = float(delta_e_2000(transform.to_lab(well[None, :]), TRUTH))

    failures = list(quality.failures())
    if not transform.passes():
        failures.append(f"card residual {transform.residual_delta_e:.2f} dE")
    if failures:
        return "reject", de, failures[0][:58]
    return "accept", de, f"reproj {det.reprojection_px:.2f}px"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="fewer points per sweep")
    a = ap.parse_args()
    rng = np.random.default_rng(11)
    card = render_card(well_srgb=WELL)
    step = 2 if a.quick else 1

    cases: list[tuple[str, str, object]] = []

    def add(group, name, img):
        cases.append((group, name, img))

    # --- geometry ---------------------------------------------------------- #
    for t in range(0, 51, 5 * step):
        add("tilt", f"{t}deg", photograph(card, tilt=t, rng=rng))
    for f in [1.0, 0.7, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1]:
        add("distance", f"scale {f:.2f}", fm.at_distance(photograph(card, rng=rng), f))
    for d in [0.0, 0.15, 0.3, 0.45, 0.6, 0.8]:
        add("crease", f"depth {d:.2f}",
            photograph(fm.crease(card, depth=d), rng=rng))
    for c in [0.0, 0.3, 0.5, 0.7, 1.0]:
        add("occluded fiducial", f"{c:.0%} covered",
            fm.occlude_fiducial(photograph(card, rng=rng), coverage=c))

    # --- light ------------------------------------------------------------- #
    for d in [0.0, 0.2, 0.35, 0.5, 0.65, 0.8]:
        add("hard shadow edge", f"depth {d:.2f}",
            photograph(fm.hard_shadow(card, depth=d), rng=rng))
    for b in [1.0, 0.5, 0.25, 0.12, 0.05]:
        add("mixed illuminants", f"blend {b:.2f}",
            photograph(fm.mixed_illuminants(card, blend=b), rng=rng))
    for g in [0.0, 0.1, 0.2, 0.3, 0.45]:
        add("glare", f"{g:.2f}", photograph(card, glare=g, illuminant="torch", rng=rng))
    for e in [0.1, 0.25, 0.5, 0.8, 1.0, 1.3, 1.7, 2.2]:
        add("exposure", f"x{e:.2f}", photograph(card, exposure=e, rng=rng))

    # --- optics ------------------------------------------------------------ #
    for b in [0, 2, 4, 7, 11, 15]:
        add("defocus", f"{b}px", photograph(card, blur_px=b, rng=rng))
    for L in [1, 7, 13, 21, 31]:
        add("motion blur", f"{L}px", fm.motion_blur(photograph(card, rng=rng), length=L))
    for q in [95, 80, 60, 40, 25, 10]:
        add("jpeg", f"q{q}", photograph(card, jpeg_quality=q, rng=rng))
    for n in [0, 3, 8, 15, 25]:
        add("sensor noise", f"sigma {n}", photograph(card, noise=n, rng=rng))

    # --- replay: §10 row 1 ------------------------------------------------- #
    for medium in ("print", "screen"):
        for tilt in (0, 8, 16):
            add("REPLAY", f"{medium}, tilt {tilt}",
                fm.replay(card, medium=medium, tilt=tilt, rng=rng))

    # --- run --------------------------------------------------------------- #
    rows = []
    for group, name, img in cases:
        verdict, de, note = evaluate(img)
        rows.append((group, name, verdict, de, note))

    width = max(len(g) for g, *_ in rows)
    print(f"{'condition':<{width}}  {'setting':<18} {'verdict':<10} {'dE2000':>8}  note")
    print("-" * (width + 62))
    last = None
    false_accepts, correct_rejects, good = [], [], []
    for group, name, verdict, de, note in rows:
        if group != last:
            print()
            last = group
        dangerous = verdict == "accept" and de is not None and de > DANGEROUS_DE
        flag = "  <-- FALSE ACCEPT" if dangerous else ""
        des = "     —" if de is None else f"{de:8.2f}"
        print(f"{group:<{width}}  {name:<18} {verdict:<10} {des}  {note}{flag}")
        if dangerous:
            false_accepts.append((group, name, de))
        elif verdict == "accept":
            good.append((group, name, de))
        elif verdict in ("reject", "no-detect"):
            correct_rejects.append((group, name, de))

    print()
    print("=" * (width + 62))
    print(f"{len(rows)} conditions:  {len(good)} accepted and accurate, "
          f"{len(correct_rejects)} refused, {len(false_accepts)} FALSE ACCEPTS")
    if good:
        print(f"worst error among ACCEPTED frames: "
              f"{max(d for *_, d in good if d is not None):.2f} dE2000")
    if false_accepts:
        print()
        print("FALSE ACCEPTS — the pipeline returned a measurement it should not have:")
        for group, name, de in sorted(false_accepts, key=lambda r: -r[2]):
            print(f"  {de:7.2f} dE   {group} / {name}")
        return 1
    print("\nNo false accepts in this sweep.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
