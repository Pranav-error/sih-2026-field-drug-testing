"""How much depth does the replay defence actually need?

The geometry says a flat reproduction gives exactly zero parallax. That is a
guarantee. What it does not say is whether a *real* scene gives enough parallax to
measure through noise, blur and compression — which is an empirical question, and
the answer decides whether the reference card needs redesigning.

    python core/tools/parallax_study.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "tests"))

from ftr.card import PX_PER_MM, CARD_V1                      # noqa: E402
from ftr.detect import detect_card                            # noqa: E402
from ftr.parallax import check_liveness, measure_parallax     # noqa: E402
from synth import render_card                                 # noqa: E402
from synth3d import replay_pair, stereo_pair, tab_texture     # noqa: E402

# A clear region of the card: right of the bottom-left fiducial, left of the well.
TAB_QUAD = np.array([[21.0, 63.0], [40.0, 63.0], [40.0, 77.0], [21.0, 77.0]])
TAB_CENTRE = (30.5, 70.0)
TAB_RADIUS = 9.0


def run(card, height_mm, baseline_mm, distance_mm, replay=None, **kw):
    raised = None if height_mm <= 0 else (tab_texture(), height_mm, TAB_QUAD)
    if replay:
        a, b = replay_pair(card, baseline_mm=baseline_mm, distance_mm=distance_mm,
                           medium=replay, raised=raised, **kw)
    else:
        a, b = stereo_pair(card, baseline_mm=baseline_mm, distance_mm=distance_mm,
                           raised=raised, **kw)
    da, db = detect_card(a), detect_card(b)
    if da is None or db is None or not (da.complete and db.complete):
        return None
    return measure_parallax(a, b, da, db, TAB_CENTRE, TAB_RADIUS,
                            baseline_mm=baseline_mm, distance_mm=distance_mm)


def main() -> int:
    card = render_card()
    D, B = 150.0, 50.0

    print("1. PARALLAX vs FEATURE HEIGHT   (distance 150 mm, baseline 50 mm)")
    print("-" * 78)
    print(f"   {'height mm':>10}{'predicted px':>15}{'measured px':>14}{'implied h':>12}"
          f"{'confidence':>12}")
    for h in (0.0, 0.4, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0):
        r = run(card, h, B, D)
        if r is None:
            print(f"   {h:10.1f}   card not detected")
            continue
        pred = B * h / max(D - h, 1e-6) * PX_PER_MM
        ih = "—" if r.implied_height_mm is None else f"{r.implied_height_mm:.1f} mm"
        print(f"   {h:10.1f}{pred:15.1f}{r.displacement_px:14.1f}{ih:>12}"
              f"{r.confidence:12.2f}")

    print()
    print("2. THE ATTACK   (an 8 mm tab, so the honest capture is easy to measure)")
    print("-" * 78)
    h = 8.0
    for label, kwargs in [
        ("physical card", dict()),
        ("photo-lab print of it", dict(replay="print")),
        ("high-DPI screen of it", dict(replay="screen")),
    ]:
        r = run(card, h, B, D, **kwargs)
        if r is None:
            print(f"   {label:<26}   card not detected in the pair\n")
            continue
        live, why = check_liveness(r, h, B, D)
        verdict = "LIVE" if live else "REFUSED"
        print(f"   {label:<26}{r.displacement_px:7.1f} px   {verdict}")
        print(f"   {'':<26}{why}")
        print()

    print("3. HOW LITTLE MOVEMENT IS ENOUGH   (8 mm tab at 150 mm)")
    print("-" * 78)
    print(f"   {'baseline mm':>12}{'measured px':>14}   verdict")
    for b in (5, 10, 20, 30, 50, 80):
        r = run(card, h, float(b), D)
        if r is None:
            print(f"   {b:12.0f}   card not detected"); continue
        live, _ = check_liveness(r, h, float(b), D)
        print(f"   {b:12.0f}{r.displacement_px:14.1f}   {'LIVE' if live else 'refused'}")

    print()
    print("4. DEGRADED CAPTURE   (does the check survive a bad frame pair?)")
    print("-" * 78)
    for label, kw in [("clean", dict(noise=1.2)),
                      ("noisy sensor", dict(noise=9.0)),
                      ("very noisy", dict(noise=20.0))]:
        r = run(card, h, B, D, **kw)
        if r is None:
            print(f"   {label:<16}   card not detected"); continue
        live, why = check_liveness(r, h, B, D)
        print(f"   {label:<16}{r.displacement_px:7.1f} px  conf {r.confidence:.2f}   "
              f"{'LIVE' if live else 'refused'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
