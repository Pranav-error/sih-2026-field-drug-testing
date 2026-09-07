"""Track F tooling — survey a capture set, and calibrate from it.

Data collection is the critical path (ARCHITECTURE.md §11), and the failure mode
is specific: photograph two thousand cards over three weekends, then discover at
the end that a third of them are unusable and the reason is a torch reflection
nobody noticed at the time. Software cannot take the photographs. It can make the
feedback immediate.

Two commands:

    python -m ftr.ingest survey    captures/
    python -m ftr.ingest calibrate captures/ --holdout tungsten

`survey` reports what fraction of a set is usable and *why the rest is not*,
broken down so a capture session can be corrected while the equipment is still
set up.

`calibrate` fits the reference loci and the conformal threshold, and evaluates on
a **held-out illuminant** rather than held-out samples. §7.5 is explicit about
this: reporting accuracy on an illuminant the model never saw is the only
generalisation claim that means anything for field deployment. Random splits
flatter the model and would be a quiet lie in the submission.

Expected layout — the label and the condition both come from the path, so the
capture matrix is recorded by how the files are filed:

    captures/<label>/<illuminant>/<anything>.jpg
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from .card import CARD_V1, CardSpec
from .colorimetry import ConformalClassifier, delta_e_2000
from .pipeline import Measurement, measure

__all__ = ["Capture", "survey", "calibrate", "SurveyReport", "CalibrationReport"]

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}

_NUMBER = re.compile(r"-?\d+\.?\d*")


def refusal_kind(reason: str) -> str:
    """Group refusals by their cause, not by the measurement that triggered them.

    "0.50 stops" and "0.51 stops" are the same problem. Histogramming the raw
    strings shatters one finding into many and buries it — which defeats the point
    of surveying a capture set at all.
    """
    return _NUMBER.sub("#", reason)


@dataclass
class Capture:
    """One photograph, and what the pipeline made of it."""

    path: str
    label: str
    condition: str
    detected: bool
    gate_passed: bool
    lab: list[float] | None
    transform_residual: float | None
    illumination_residual: float | None
    tilt: float | None
    guidance: str
    refusals: list[str]

    @classmethod
    def from_measurement(cls, path: Path, label: str, condition: str, m: Measurement) -> "Capture":
        return cls(
            path=str(path),
            label=label,
            condition=condition,
            detected=m.detected,
            gate_passed=bool(m.quality and m.quality.passed and not m.refusals),
            lab=[float(v) for v in m.lab] if m.lab is not None else None,
            transform_residual=m.transform_residual_delta_e,
            illumination_residual=m.illumination_residual_stops,
            tilt=m.quality.tilt_degrees if m.quality else None,
            guidance=m.guidance(),
            refusals=list(m.refusals),
        )

    @property
    def usable(self) -> bool:
        return self.gate_passed and self.lab is not None


def _walk(root: Path) -> list[tuple[Path, str, str]]:
    """Find images and read label/condition from the directory structure."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in IMAGE_SUFFIXES or not p.is_file():
            continue
        rel = p.relative_to(root).parts
        label = rel[0] if len(rel) > 1 else "unlabelled"
        condition = rel[1] if len(rel) > 2 else "unspecified"
        out.append((p, label, condition))
    return out


def read_captures(root: Path, spec: CardSpec = CARD_V1,
                  classifier: ConformalClassifier | None = None) -> list[Capture]:
    caps = []
    for path, label, condition in _walk(root):
        img = cv2.imread(str(path))
        if img is None:
            caps.append(Capture(str(path), label, condition, False, False, None, None,
                                None, None, "File could not be read as an image.",
                                ["unreadable file"]))
            continue
        caps.append(Capture.from_measurement(path, label, condition,
                                             measure(img, classifier, spec)))
    return caps


# --------------------------------------------------------------------------- #
# survey
# --------------------------------------------------------------------------- #

@dataclass
class SurveyReport:
    total: int
    detected: int
    usable: int
    by_label: dict[str, dict[str, int]]
    by_condition: dict[str, dict[str, int]]
    refusal_counts: dict[str, int]
    guidance_counts: dict[str, int]
    worst: list[Capture]

    def text(self) -> str:
        if not self.total:
            return "No images found. Expected captures/<label>/<illuminant>/*.jpg"

        pct = lambda n: f"{100 * n / self.total:5.1f}%"                      # noqa: E731
        lines = [
            f"{self.total} image(s)",
            f"  card found      {self.detected:5d}  {pct(self.detected)}",
            f"  usable          {self.usable:5d}  {pct(self.usable)}",
            "",
        ]

        if self.usable < self.total:
            lines.append("Why the rest were refused")
            lines.append("-" * 25)
            for reason, n in sorted(self.refusal_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {n:4d}  {reason}")
            lines.append("")
            lines.append("What to tell the person holding the phone")
            lines.append("-" * 40)
            for g, n in sorted(self.guidance_counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {n:4d}  {g}")
            lines.append("")

        def table(title: str, data: dict[str, dict[str, int]]) -> None:
            if len(data) <= 1:
                return
            lines.append(title)
            lines.append("-" * len(title))
            width = max(len(k) for k in data)
            for k, v in sorted(data.items()):
                rate = 100 * v["usable"] / v["total"] if v["total"] else 0
                bar = "#" * int(rate / 5)
                lines.append(f"  {k:<{width}}  {v['usable']:4d}/{v['total']:<4d} "
                             f"{rate:5.1f}%  {bar}")
            lines.append("")

        table("Usable by label", self.by_label)
        table("Usable by condition", self.by_condition)

        # A condition that is wholly unusable is a protocol problem, not a data
        # problem, and no amount of extra photographs under it will help.
        dead = [k for k, v in self.by_condition.items() if v["total"] >= 3 and not v["usable"]]
        if dead:
            lines.append("Conditions with nothing usable at all — fix the protocol, "
                         "do not photograph more:")
            for k in dead:
                lines.append(f"  {k}")
            lines.append("")

        if self.worst:
            lines.append("Worst frames")
            lines.append("-" * 12)
            for c in self.worst:
                lines.append(f"  {c.path}")
                lines.append(f"      {c.refusals[0] if c.refusals else 'no card found'}")
        return "\n".join(lines)


def survey(root: Path, spec: CardSpec = CARD_V1) -> tuple[SurveyReport, list[Capture]]:
    caps = read_captures(root, spec)

    by_label: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "usable": 0})
    by_cond: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "usable": 0})
    refusals: Counter[str] = Counter()
    guidance: Counter[str] = Counter()

    for c in caps:
        by_label[c.label]["total"] += 1
        by_cond[c.condition]["total"] += 1
        if c.usable:
            by_label[c.label]["usable"] += 1
            by_cond[c.condition]["usable"] += 1
        else:
            # Count the *first* refusal only: the others are usually consequences
            # of it, and a histogram of consequences hides the cause.
            refusals[refusal_kind(c.refusals[0]) if c.refusals else "card not found"] += 1
            guidance[c.guidance] += 1

    worst = [c for c in caps if not c.usable][:5]
    report = SurveyReport(
        total=len(caps),
        detected=sum(1 for c in caps if c.detected),
        usable=sum(1 for c in caps if c.usable),
        by_label={k: dict(v) for k, v in by_label.items()},
        by_condition={k: dict(v) for k, v in by_cond.items()},
        refusal_counts=dict(refusals),
        guidance_counts=dict(guidance),
        worst=worst,
    )
    return report, caps


# --------------------------------------------------------------------------- #
# calibrate
# --------------------------------------------------------------------------- #

@dataclass
class CalibrationReport:
    loci: dict[str, list[float]]
    threshold: float
    alpha: float
    n_fit: int
    n_calibration: int
    holdout_condition: str | None
    n_evaluated: int
    coverage: float
    singleton_rate: float
    error_rate: float
    confusion: dict[str, dict[str, int]]

    def text(self) -> str:
        lines = [
            f"Reference loci from {self.n_fit} frame(s)",
            "-" * 40,
        ]
        for name, lab in sorted(self.loci.items()):
            lines.append(f"  {name:<24} L* {lab[0]:6.2f}  a* {lab[1]:6.2f}  b* {lab[2]:6.2f}")
        lines += [
            "",
            f"Conformal threshold  {self.threshold:.3f} dE2000 "
            f"at alpha={self.alpha} from {self.n_calibration} point(s)",
            "",
        ]
        if self.holdout_condition:
            lines.append(f"Evaluated on a HELD-OUT CONDITION: {self.holdout_condition}")
            lines.append("  (an illuminant the loci and threshold never saw — §7.5)")
        else:
            lines.append("Evaluated on held-out SAMPLES, not a held-out condition.")
            lines.append("  This flatters the model. Do not quote it as a field accuracy.")
        lines += [
            "-" * 40,
            f"  frames evaluated   {self.n_evaluated}",
            f"  coverage           {self.coverage:6.1%}   (target >= {1 - self.alpha:.0%})",
            f"  singleton rate     {self.singleton_rate:6.1%}   (how often it commits)",
            f"  error rate         {self.error_rate:6.1%}   (committed and wrong)",
            "",
        ]
        if self.coverage < 1 - self.alpha:
            lines.append("  ! Coverage is below the stated bound. The calibration set is not")
            lines.append("    exchangeable with this condition — which is the finding, not a bug.")
        labels = sorted(self.confusion)
        if labels:
            lines.append("Confusion (rows: truth, columns: reported)")
            w = max(len(x) for x in labels)
            header = " " * (w + 2) + "  ".join(f"{x[:8]:>8}" for x in labels + ["abstain"])
            lines.append(header)
            for t in labels:
                row = self.confusion[t]
                cells = "  ".join(f"{row.get(x, 0):8d}" for x in labels + ["abstain"])
                lines.append(f"  {t:<{w}}{cells}")
        return "\n".join(lines)


def calibrate(root: Path, holdout: str | None = None, alpha: float = 0.05,
              spec: CardSpec = CARD_V1) -> CalibrationReport:
    """Fit loci and threshold, then evaluate — by default on a held-out illuminant."""
    caps = [c for c in read_captures(root, spec) if c.usable]
    if not caps:
        raise ValueError("no usable frames; run `survey` first and fix the captures")

    labels = sorted({c.label for c in caps})
    if len(labels) < 2:
        raise ValueError(f"need at least two labels to calibrate, found {labels}")

    conditions = sorted({c.condition for c in caps})
    if holdout is not None and holdout not in conditions:
        raise ValueError(f"holdout condition {holdout!r} not in the set: {conditions}")

    train = [c for c in caps if c.condition != holdout]
    test = [c for c in caps if c.condition == holdout] if holdout else []

    if holdout is None:
        # Held-out samples: an honest fallback, clearly labelled as the weaker claim.
        train = caps[::2]
        test = caps[1::2]

    if not train or not test:
        raise ValueError("the split left nothing to fit or nothing to evaluate")

    # Loci are the per-label median, which shrugs off a single bad frame in a way
    # the mean does not. Half the fit set defines them; the other half calibrates
    # the threshold, because calibrating on the points that defined the loci would
    # make the scores optimistic and silently break the coverage guarantee.
    fit_half, cal_half = train[::2], train[1::2]
    loci: dict[str, np.ndarray] = {}
    for lbl in labels:
        pts = np.array([c.lab for c in fit_half if c.label == lbl])
        if len(pts) == 0:
            raise ValueError(f"label {lbl!r} has no frames in the fitting split")
        loci[lbl] = np.median(pts, axis=0)

    cal_pts = [c for c in cal_half if c.label in loci]
    if not cal_pts:
        raise ValueError("no frames left to calibrate the threshold")

    clf = ConformalClassifier(loci, alpha=alpha)
    try:
        threshold = clf.calibrate(np.array([c.lab for c in cal_pts]),
                                  [c.label for c in cal_pts])
    except ValueError as e:
        # The conformal guarantee is finite-sample: below a minimum count there is
        # no threshold that honours alpha. Say what to go and do about it, in
        # frames, because the person reading this is holding a camera.
        need = int(np.ceil(1 / alpha)) - 1
        shortfall = need - len(cal_pts)
        total_needed = 2 * need
        raise ValueError(
            f"{e}\n"
            f"  The calibration split gets about half the non-held-out usable frames, "
            f"so this needs roughly {total_needed} usable frames outside "
            f"'{holdout or 'the evaluation half'}' and has {len(train)}.\n"
            f"  Capture about {max(1, 2 * shortfall)} more usable frames, or raise "
            f"--alpha (a weaker guarantee, honestly stated) to "
            f"{1 / (len(cal_pts) + 1):.2f} or above."
        ) from e

    covered = committed = wrong = 0
    confusion: dict[str, dict[str, int]] = {l: defaultdict(int) for l in labels}
    for c in test:
        p = clf.predict(np.array(c.lab))
        if c.label in p.prediction_set:
            covered += 1
        if p.label is not None:
            committed += 1
            if p.label != c.label:
                wrong += 1
            confusion[c.label][p.label] += 1
        else:
            confusion[c.label]["abstain"] += 1

    n = len(test)
    return CalibrationReport(
        loci={k: [float(x) for x in v] for k, v in loci.items()},
        threshold=float(threshold),
        alpha=alpha,
        n_fit=len(fit_half),
        n_calibration=len(cal_pts),
        holdout_condition=holdout,
        n_evaluated=n,
        coverage=covered / n if n else 0.0,
        singleton_rate=committed / n if n else 0.0,
        error_rate=wrong / n if n else 0.0,
        confusion={k: dict(v) for k, v in confusion.items()},
    )


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ftr-ingest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("survey", help="report what fraction of a capture set is usable")
    ps.add_argument("root", type=Path)
    ps.add_argument("--json", type=Path, help="also write the per-frame manifest here")

    pc = sub.add_parser("calibrate", help="fit loci and threshold, evaluate on a held-out condition")
    pc.add_argument("root", type=Path)
    pc.add_argument("--holdout", help="illuminant to hold out; omit for a weaker sample split")
    pc.add_argument("--alpha", type=float, default=0.05)
    pc.add_argument("--json", type=Path)

    a = p.parse_args(argv)
    if not a.root.is_dir():
        print(f"ftr-ingest: not a directory: {a.root}")
        return 2

    if a.cmd == "survey":
        report, caps = survey(a.root)
        print(report.text())
        if a.json:
            a.json.write_text(json.dumps(
                {"summary": {k: v for k, v in asdict(report).items() if k != "worst"},
                 "captures": [asdict(c) for c in caps]}, indent=2) + "\n")
            print(f"\nmanifest -> {a.json}")
        return 0 if report.usable else 1

    try:
        report = calibrate(a.root, holdout=a.holdout, alpha=a.alpha)
    except ValueError as e:
        print(f"ftr-ingest: {e}")
        return 2
    print(report.text())
    if a.json:
        a.json.write_text(json.dumps(asdict(report), indent=2) + "\n")
        print(f"\nreport -> {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
