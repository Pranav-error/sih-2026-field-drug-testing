"""What real cameras and real illuminants do to the L1 assumption.

Two questions the RGB-gain simulator cannot answer:

  1. Does metamerism actually bite? Two surfaces that a camera cannot tell apart
     under one light, and can under another, are the reason colour constancy is
     hard. A per-channel gain model produces exactly zero of it.
  2. What is the colorimetric error of the card-in-frame approach on *measured*
     camera sensitivities under *measured* illuminant spectra?

Question 2 is answered by leave-one-out over the chart: fit the device transform
on 23 patches, predict the 24th, and compare against its true colour under the
reference illuminant. The held-out patch is a surface the transform has never
seen, which is precisely the situation of the reaction well.

    python core/tools/spectral_study.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from ftr.colorimetry import RootPolynomial, delta_e_2000, xyz_to_lab   # noqa: E402
from ftr.spectral import (WAVELENGTHS, colourchecker_reflectances,      # noqa: E402
                          illuminant_spd, load_cameras, render_rgb)

ILLUMINANTS = ["D65", "D50", "A", "FL2", "FL11", "LED-B3"]
REFERENCE = "D65"


def cie_xyz(reflectance: np.ndarray, illuminant: np.ndarray) -> np.ndarray:
    """True CIE XYZ of a surface under a light, per the 1931 2-degree observer."""
    import colour

    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    bar = np.array([[cmfs[w][i] for i in range(3)] for w in WAVELENGTHS])
    k = 100.0 / (illuminant * bar[:, 1]).sum()
    return k * (reflectance[:, None] * illuminant[:, None] * bar).sum(axis=0)


def main() -> int:
    cams = load_cameras()
    refl = colourchecker_reflectances()
    names = list(refl)
    spds = {n: illuminant_spd(n) for n in ILLUMINANTS}

    # Truth: each patch's colour under the reference illuminant. This is what the
    # transform is asked to recover no matter what light the photo was taken in.
    truth_lab = {n: xyz_to_lab(cie_xyz(refl[n], spds[REFERENCE])) for n in names}

    # ---------------------------------------------------------------- 1. metamerism
    print("1. METAMERISM — pairs a camera cannot separate under one light but can under another")
    print("-" * 92)
    cam = cams["Nokia N900"]
    worst = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            d = {}
            for ill in ("D65", "A", "FL11"):
                ra = render_rgb(refl[a], spds[ill], cam)
                rb = render_rgb(refl[b], spds[ill], cam)
                d[ill] = float(np.linalg.norm(ra - rb) / max(np.linalg.norm(ra), 1e-9))
            swing = max(d.values()) - min(d.values())
            worst.append((swing, a, b, d))
    worst.sort(reverse=True)
    print(f"   camera: {cam.name} (the only mobile sensor in the database)")
    print(f"   {'patch A':<18}{'patch B':<18}{'D65':>9}{'A':>9}{'FL11':>9}   swing")
    for swing, a, b, d in worst[:6]:
        print(f"   {a:<18}{b:<18}{d['D65']:9.4f}{d['A']:9.4f}{d['FL11']:9.4f}{swing:9.4f}")
    print()
    print("   A per-channel gain model gives a swing of EXACTLY ZERO for every pair:")
    print("   scaling both surfaces by the same factor cannot change their ratio.")
    print("   Every cross-illuminant number measured on synth.py inherits that.")

    # ------------------------------------------------- 2. leave-one-out on real data
    print()
    print("2. DEVICE TRANSFORM on measured sensitivities — leave-one-patch-out")
    print("-" * 92)
    print(f"   fit the transform on 23 chart patches, predict the 24th, compare to its")
    print(f"   true colour under {REFERENCE}. dE2000, median over 24 held-out patches.")
    print()
    header = f"   {'camera':<26}" + "".join(f"{i:>10}" for i in ILLUMINANTS)
    print(header)
    print("   " + "-" * (26 + 10 * len(ILLUMINANTS)))

    per_illum: dict[str, list[float]] = {i: [] for i in ILLUMINANTS}
    rows = []
    for cname, cam in cams.items():
        cells = []
        for ill in ILLUMINANTS:
            rgb = np.array([render_rgb(refl[n], spds[ill], cam) for n in names])
            xyz = np.array([xyz_to_lab.__self__ if False else cie_xyz(refl[n], spds[REFERENCE])
                            for n in names])
            errs = []
            for k in range(len(names)):
                keep = [m for m in range(len(names)) if m != k]
                t = RootPolynomial.fit(rgb[keep], xyz[keep])
                pred = t.to_lab(rgb[k][None, :])
                errs.append(float(delta_e_2000(pred, truth_lab[names[k]])))
            med = float(np.median(errs))
            cells.append(med)
            per_illum[ill].append(med)
        rows.append((cname, cam.kind, cells))

    for cname, kind, cells in sorted(rows, key=lambda r: np.mean(r[2])):
        marker = "  <- mobile" if kind == "mobile" else ""
        print(f"   {cname[:25]:<26}" + "".join(f"{c:10.2f}" for c in cells) + marker)

    print("   " + "-" * (26 + 10 * len(ILLUMINANTS)))
    print(f"   {'median across cameras':<26}" +
          "".join(f"{np.median(per_illum[i]):10.2f}" for i in ILLUMINANTS))
    print()
    ref_med = np.median(per_illum[REFERENCE])
    worst_ill = max(ILLUMINANTS, key=lambda i: np.median(per_illum[i]))
    print(f"   under the reference illuminant : {ref_med:.2f} dE2000")
    print(f"   worst illuminant ({worst_ill:<7})      : {np.median(per_illum[worst_ill]):.2f} dE2000")
    print(f"   penalty for a non-reference light: x{np.median(per_illum[worst_ill]) / max(ref_med, 1e-9):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
