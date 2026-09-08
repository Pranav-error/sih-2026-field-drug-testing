"""The L2 ablation again — this time on physically rendered data.

The earlier ablation (core/tools/ablation.py) ran on frames from an RGB-gain
simulator, which cannot produce metamerism. This one renders every measurement
from measured reflectance spectra, measured illuminant spectra and measured camera
sensitivities, so two classes really can converge under one light and separate
under another.

Two generalisation questions, and the second is the one nobody usually asks:

  * **held-out illuminant** — a light the calibration never saw
  * **held-out camera**     — a handset model the calibration never saw

Both matter for issued police phones. A calibration built on the three models a
team owns has to survive the fourth.

    python core/tools/spectral_ablation.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "tools"))

from ablation import Logistic, Mahalanobis, NearestLocus, conformal_threshold, evaluate  # noqa: E402
from ftr.colorimetry import RootPolynomial, xyz_to_lab                  # noqa: E402
from ftr.spectral import (colourchecker_reflectances, illuminant_spd,   # noqa: E402
                          load_cameras, render_rgb)
from spectral_study import cie_xyz                                       # noqa: E402

ILLUMINANTS = ["D65", "D50", "A", "FL2", "FL11", "LED-B3"]
REFERENCE = "D65"

# Four surrogate "reaction" colours, chosen from measured ColorChecker
# reflectances. Two of them sit close together on purpose: a reagent that gave
# well-separated colours for every substance class would not be the problem NCB
# has. These are real measured spectra of real surfaces standing in for real
# measured spectra of a real reaction — the optics are honest, the chemistry
# is still borrowed.
CLASS_PATCHES = {
    "opiate_class": "purple",
    "opiate_related": "purplish blue",
    "amphetamine_class": "moderate red",
    "negative": "neutral 8 (.23 D)",
}

REPLICATES = 12          # frames per class per camera per illuminant
NOISE = 0.004            # sensor noise on linear RGB, roughly 10-bit read noise


def build(cams, refl, spds, rng):
    """Render the whole study: one Lab measurement per frame, via the real L1 path."""
    chart = [n for n in refl if n not in CLASS_PATCHES.values()]
    chart_xyz = np.array([cie_xyz(refl[n], spds[REFERENCE]) for n in chart])

    rows = []
    for cname, cam in cams.items():
        for ill in ILLUMINANTS:
            base_chart = np.array([render_rgb(refl[n], spds[ill], cam) for n in chart])
            for label, patch in CLASS_PATCHES.items():
                base_well = render_rgb(refl[patch], spds[ill], cam)
                for _ in range(REPLICATES):
                    # Exposure jitter and sensor noise: the nuisance an officer
                    # introduces without meaning to. The chart and the well share
                    # the exposure, because they share the frame.
                    k = rng.uniform(0.75, 1.25)
                    ch = base_chart * k + rng.normal(0, NOISE, base_chart.shape)
                    wl = base_well * k + rng.normal(0, NOISE, 3)
                    ch = np.clip(ch, 1e-5, None)

                    t = RootPolynomial.fit(ch, chart_xyz)
                    lab = np.atleast_1d(t.to_lab(np.clip(wl, 1e-5, None)[None, :]))
                    rows.append((cname, cam.kind, ill, label, lab))
    return rows


def run_split(rows, split_key, alpha, classes):
    """Rotate the held-out value of `split_key` and average the results."""
    groups = sorted({r[split_key] for r in rows})
    out = defaultdict(list)
    for held in groups:
        tr = [r for r in rows if r[split_key] != held]
        te = [r for r in rows if r[split_key] == held]
        Xtr = np.array([r[4] for r in tr]); ytr = np.array([r[3] for r in tr])
        Xte = np.array([r[4] for r in te]); yte = np.array([r[3] for r in te])
        fit = np.arange(len(ytr)) % 2 == 0
        for cls in (NearestLocus, Mahalanobis, Logistic):
            s = cls()
            s.fit(Xtr[fit], ytr[fit], classes)
            t = conformal_threshold(s, Xtr[~fit], ytr[~fit], alpha)
            out[s.name].append(evaluate(s, t, Xte, yte, classes))
    return out


def report(title, res, alpha):
    print(f"  {title}")
    print(f"  {'scorer':<36}{'coverage':>10}{'commits':>10}{'errors':>9}")
    for name, r in res.items():
        cov = np.mean([x[0] for x in r]); com = np.mean([x[1] for x in r])
        err = np.mean([x[2] for x in r])
        flag = "" if cov >= 1 - alpha else "  < bound"
        print(f"  {name:<36}{cov:9.1%}{com:10.1%}{err:9.1%}{flag}")
    print()


def main() -> int:
    alpha = 0.05
    rng = np.random.default_rng(2026)
    cams = load_cameras()
    refl = colourchecker_reflectances()
    spds = {n: illuminant_spd(n) for n in ILLUMINANTS}
    classes = sorted(CLASS_PATCHES)

    rows = build(cams, refl, spds, rng)
    print(f"{len(rows)} rendered measurements · {len(cams)} cameras · "
          f"{len(ILLUMINANTS)} illuminants · {len(classes)} classes · alpha={alpha}")
    print("rendered from measured reflectance x measured SPD x measured sensitivity")
    print()

    report("HELD-OUT ILLUMINANT (a light the calibration never saw)",
           run_split(rows, 2, alpha, classes), alpha)
    report("HELD-OUT CAMERA (a handset model the calibration never saw)",
           run_split(rows, 0, alpha, classes), alpha)

    # Mobile handsets are the deployment target, so ask that question directly.
    mobile = [r for r in rows if r[1] in ("mobile", "compact")]
    dslr = [r for r in rows if r[1] == "dslr"]
    if mobile and dslr:
        Xtr = np.array([r[4] for r in dslr]); ytr = np.array([r[3] for r in dslr])
        Xte = np.array([r[4] for r in mobile]); yte = np.array([r[3] for r in mobile])
        fit = np.arange(len(ytr)) % 2 == 0
        print("  CALIBRATE ON DSLRs, DEPLOY ON PHONES (the realistic mistake)")
        print(f"  {'scorer':<36}{'coverage':>10}{'commits':>10}{'errors':>9}")
        for cls in (NearestLocus, Mahalanobis, Logistic):
            s = cls(); s.fit(Xtr[fit], ytr[fit], classes)
            t = conformal_threshold(s, Xtr[~fit], ytr[~fit], alpha)
            cov, com, err = evaluate(s, t, Xte, yte, classes)
            flag = "" if cov >= 1 - alpha else "  < bound"
            print(f"  {s.name:<36}{cov:9.1%}{com:10.1%}{err:9.1%}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
