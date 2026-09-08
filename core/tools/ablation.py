"""Does a learned component earn its place in L2?

ARCHITECTURE.md §11 says TFLite is used for L2 **"if a learned component survives
ablation"**. This is the ablation. It compares, under a *held-out illuminant*:

  A. nearest-locus (median) + conformal        — the current design
  B. Mahalanobis to per-class covariance + conformal
  C. multinomial logistic regression + conformal

All three are wrapped in the same conformal layer, so what is being compared is
the *score function*, not whether abstention exists. That matters: a comparison
where one arm has calibrated abstention and another does not is not a comparison.

The bar a learned component has to clear is not "higher accuracy". It is:

  * materially better under an illuminant it never saw, and
  * still explainable to a court, and
  * worth the loss of a closed-form transform that a defence expert can re-derive
    on paper.

A 1% gain does not clear that bar.

    python core/tools/ablation.py DATASET
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))
sys.path.insert(0, str(ROOT / "core" / "tests"))

from ftr.colorimetry import delta_e_2000        # noqa: E402
from ftr.ingest import read_captures            # noqa: E402


# --------------------------------------------------------------------------- #
# scorers. each returns a nonconformity score per class: lower = more conforming
# --------------------------------------------------------------------------- #

class NearestLocus:
    """The current design: CIEDE2000 distance to the per-class median Lab."""

    name = "A. nearest locus (dE2000)"
    explainable = "closed form; a defence expert can recompute it on paper"

    def fit(self, X, y, classes):
        self.loci = {c: np.median(X[y == c], axis=0) for c in classes}

    def scores(self, x):
        return {c: float(delta_e_2000(x, locus)) for c, locus in self.loci.items()}


class Mahalanobis:
    """Distance in units of each class's own scatter."""

    name = "B. Mahalanobis to class covariance"
    explainable = "closed form, but the metric differs per class"

    def fit(self, X, y, classes):
        self.mu, self.inv = {}, {}
        for c in classes:
            pts = X[y == c]
            self.mu[c] = pts.mean(axis=0)
            cov = np.cov(pts.T) + np.eye(3) * 1e-3   # ridge: classes can be tight
            self.inv[c] = np.linalg.inv(cov)

    def scores(self, x):
        out = {}
        for c in self.mu:
            d = x - self.mu[c]
            out[c] = float(np.sqrt(d @ self.inv[c] @ d))
        return out


class Logistic:
    """A learned score: multinomial logistic regression on the Lab triple."""

    name = "C. logistic regression on Lab"
    explainable = "12 coefficients; explainable, but not derivable on paper"

    def fit(self, X, y, classes):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        self.classes = list(classes)
        self.scaler = StandardScaler().fit(X)
        self.model = LogisticRegression(max_iter=2000)  # multinomial by default in sklearn >= 1.5
        self.model.fit(self.scaler.transform(X), y)

    def scores(self, x):
        p = self.model.predict_proba(self.scaler.transform(x[None, :]))[0]
        # Nonconformity = 1 - probability, so lower is still more conforming and
        # the conformal layer above is identical across all three arms.
        return {c: float(1.0 - p[list(self.model.classes_).index(c)])
                for c in self.classes}


# --------------------------------------------------------------------------- #

def conformal_threshold(scorer, X, y, alpha):
    """Finite-sample conformal threshold: the ceil((n+1)(1-alpha))-th smallest."""
    s = np.array([scorer.scores(X[i])[y[i]] for i in range(len(y))])
    n = len(s)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return float(np.sort(s)[min(k, n) - 1])


def evaluate(scorer, threshold, X, y, classes):
    covered = committed = wrong = 0
    for i in range(len(y)):
        sc = scorer.scores(X[i])
        pset = [c for c in classes if sc[c] <= threshold]
        if y[i] in pset:
            covered += 1
        if len(pset) == 1:
            committed += 1
            if pset[0] != y[i]:
                wrong += 1
    n = len(y)
    return covered / n, committed / n, wrong / n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--alpha", type=float, default=0.05)
    a = ap.parse_args()

    caps = [c for c in read_captures(a.dataset) if c.usable]
    if not caps:
        print("no usable frames")
        return 2

    X = np.array([c.lab for c in caps])
    y = np.array([c.label for c in caps])
    cond = np.array([c.condition for c in caps])
    classes = sorted(set(y))
    conditions = sorted(set(cond))

    print(f"{len(caps)} usable frames · {len(classes)} classes · "
          f"{len(conditions)} conditions · alpha={a.alpha}")
    print(f"classes: {', '.join(classes)}")
    print()

    results: dict[str, list[tuple[float, float, float]]] = defaultdict(list)

    for holdout in conditions:
        train = cond != holdout
        test = ~train
        Xtr, ytr = X[train], y[train]
        # Half the training frames define the model, half calibrate the threshold.
        # Calibrating on the points that defined it would make the scores
        # optimistic and silently break the coverage guarantee.
        fit_idx = np.arange(len(ytr)) % 2 == 0
        for scorer_cls in (NearestLocus, Mahalanobis, Logistic):
            s = scorer_cls()
            s.fit(Xtr[fit_idx], ytr[fit_idx], classes)
            t = conformal_threshold(s, Xtr[~fit_idx], ytr[~fit_idx], a.alpha)
            results[s.name].append(evaluate(s, t, X[test], y[test], classes))

    print("Held-out illuminant, averaged over every choice of holdout")
    print("-" * 78)
    print(f"{'scorer':<36}{'coverage':>10}{'commits':>10}{'errors':>9}")
    for name, rows in results.items():
        cov = np.mean([r[0] for r in rows])
        com = np.mean([r[1] for r in rows])
        err = np.mean([r[2] for r in rows])
        flag = "" if cov >= 1 - a.alpha else "   < bound"
        print(f"{name:<36}{cov:9.1%}{com:10.1%}{err:9.1%}{flag}")

    print()
    print("Per-holdout coverage")
    print("-" * 78)
    header = f"{'scorer':<36}" + "".join(f"{c[:9]:>10}" for c in conditions)
    print(header)
    for name, rows in results.items():
        cells = "".join(f"{r[0]:9.1%} " for r in rows)
        print(f"{name:<36}{cells}")

    print()
    base = np.mean([r[1] for r in results["A. nearest locus (dE2000)"]])
    print("Verdict")
    print("-" * 78)
    for name, rows in results.items():
        com = np.mean([r[1] for r in rows])
        err = np.mean([r[2] for r in rows])
        delta = com - base
        print(f"  {name}")
        print(f"      commits {com:.1%} ({delta:+.1%} vs A), errors {err:.1%}")
    print()
    print("  A learned component earns its place only by being materially better")
    print("  under an unseen illuminant. Marginal gains do not pay for the loss of")
    print("  a closed-form score a defence expert can recompute on paper.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
