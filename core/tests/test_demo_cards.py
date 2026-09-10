"""The demonstration cards must read as the class they are printed with.

A demo that prints a card and gets an unexpected answer in front of a panel is
worse than no demo. The first version of these cards printed a banner across the
card body at y=52..60mm, which covered 30 of the 196 substrate probe points and
3 of the colour patches: the illumination surface and the device transform were
both solved against a red rectangle, every filled card came back with a Lab of
roughly (337, -153, -6), and the gate refused all of them. Nothing in the
pipeline was wrong — the card was.

So the property is: **a demonstration card differs from an ordinary one in the
well, and nowhere else.**
"""

import json

import numpy as np
import pytest

from ftr.card import CARD_V1
from ftr.colorimetry import ConformalClassifier, delta_e_2000
from ftr.pipeline import measure
from ftr.printable import identity_band, load_loci, render_printable

CFG = json.loads((__import__("pathlib").Path("core/ftr/data/surrogate_loci.json")).read_text())


@pytest.fixture(scope="module")
def classifier():
    loci = {k: np.array(v, float) for k, v in CFG["loci_lab"].items()}
    rng = np.random.default_rng(2026)
    labs, labels = [], []
    for k, v in loci.items():
        for _ in range(200):
            labs.append(v + rng.normal(0, CFG["calibration_sigma_lab"], 3))
            labels.append(k)
    c = ConformalClassifier(loci, alpha=CFG["alpha"])
    c.calibrate(np.array(labs), labels)
    return c


@pytest.mark.parametrize("label", sorted(CFG["loci_lab"]))
def test_a_demo_card_reads_as_its_own_class(label, classifier):
    m = measure(render_printable(dpi=300, serial="T", batch="T", well_label=label),
                classifier=classifier)
    assert m.quality.passed, m.refusals
    assert m.prediction is not None
    assert list(m.prediction.prediction_set) == [label], (
        f"printed {label}, measured Lab {m.lab}")


def test_a_blank_card_reads_negative(classifier):
    """An empty well is a real result, and a successful one."""
    m = measure(render_printable(dpi=300, serial="0417", batch="T"),
                classifier=classifier)
    assert m.quality.passed, m.refusals
    assert list(m.prediction.prediction_set) == ["negative"]


def test_the_banner_never_touches_the_card_body():
    """The regression that made every demo card unmeasurable.

    Checked geometrically as well as end-to-end: an end-to-end test would also
    pass if the banner merely happened to miss the probes at one dpi.
    """
    plain = render_printable(dpi=300, serial="T", batch="T")
    demo = render_printable(dpi=300, serial="T", batch="T", well_label="opiate_class")
    assert demo.shape[0] > plain.shape[0], "the banner must add its own strip"
    assert demo.shape[1] == plain.shape[1]

    # Compare the two card bodies. The banner strip is 14 mm and a pixel grid
    # is not, so the two renders can sit a pixel apart; align on the best offset
    # rather than assume they do not, or a rounding shift reads as the whole
    # card having changed.
    ppmm = 300 / 25.4
    banner = demo.shape[0] - plain.shape[0]
    h = int(CARD_V1.height_mm * ppmm)
    top = int(5 * ppmm)

    # Exactly aligned, not approximately: the banner is a whole number of
    # pixels added to an already-rounded offset, so the card body is
    # bit-identical apart from the well. If that ever stops being true this
    # comparison lights up across the entire card, which is the point — a
    # fractional offset hides a real overlap inside one-pixel antialiasing
    # noise, and that is how the first version of these cards shipped broken.
    a = plain[top:top + h].astype(int)
    b = demo[top + banner:top + banner + h].astype(int)
    assert a.shape == b.shape
    diff = np.abs(a - b).sum(axis=2) > 24

    ys, xs = np.nonzero(diff)
    wx, wy = CARD_V1.well_centre_mm
    r = (CARD_V1.well_radius_mm + 1.5) * ppmm
    dist = np.hypot(xs - (5 + wx) * ppmm, ys - wy * ppmm)
    outside = int((dist > r).sum())
    assert outside == 0, (
        f"{outside} pixels differ outside the well — the demonstration marking "
        "is touching the measured surface")
    assert len(ys) > 0, "the well fill did not draw at all"


def test_every_pair_of_loci_is_separable(classifier):
    """Two rungs closer than the threshold make a single label impossible."""
    loci = load_loci()
    ks = sorted(loci)
    worst, pair = 1e9, ""
    for i, a in enumerate(ks):
        for b in ks[i + 1:]:
            d = float(delta_e_2000(np.array(loci[a]), np.array(loci[b])))
            if d < worst:
                worst, pair = d, f"{a} <-> {b}"
    assert worst > 2 * classifier.threshold, (
        f"closest pair {pair} is {worst:.2f} apart, threshold "
        f"{classifier.threshold:.2f}")


def test_no_second_copy_of_the_ladder_in_the_package():
    """The values that decide what a field test reports live in ONE file.

    They were duplicated across four modules, one of which (measure_server.py)
    was stale and deleted. A second copy of a locus is a second opinion about
    what a colour means, and it surfaces as a wrong classification rather than
    as a crash.

    Scoped to ``core/ftr`` — the package — on purpose. ``test_colorimetry.py``
    and ``gen_colorimetry_vectors.py`` also contain loci a few dE apart, and
    those are *deliberately contrived*: they exist to prove that the classifier
    abstains when two classes are not separable, which is the behaviour the real
    ladder must avoid needing. Flagging them would be flagging a test for
    testing the thing it is named after.
    """
    import pathlib, re
    root = pathlib.Path("core/ftr")
    offenders = []
    for f in root.rglob("*.py"):
        if f.name == "printable.py":
            continue
        text = f.read_text()
        for lab in load_loci().values():
            # the distinctive first component of each locus, as written
            if re.search(rf"\b{lab[0]}\s*,\s*{lab[1]}\b", text):
                offenders.append(f"{f}: {lab}")
    assert not offenders, (
        "loci are hardcoded outside core/ftr/data/surrogate_loci.json:\n  "
        + "\n  ".join(offenders))


def test_the_identity_block_clears_the_markers_the_well_and_the_tab():
    """Three keep-outs the text has been through twice.

    It started at x=21mm, which the folded liveness tab covers. Moved left, it
    landed on the bottom-left ArUco marker — and a fiducial with lettering
    across it may not decode, which would take the whole frame down rather than
    degrade it. This pins the band it now occupies.
    """
    import cv2
    c = CARD_V1
    x0, x1 = identity_band(c)
    assert x1 > x0, f"the identity band is {x1 - x0:.1f}mm wide"

    # clear of the well
    assert x0 > c.well_centre_mm[0] + c.well_radius_mm
    # clear of the tab's landing area
    tab = np.array(c.tab_quad_mm, dtype=float)
    assert x0 >= tab[:, 0].max()
    # clear of every marker
    for ox, oy in c.marker_origins_mm:
        overlaps_x = not (x1 <= ox or x0 >= ox + c.marker_size_mm)
        overlaps_y = not (77.0 <= oy or 66.0 >= oy + c.marker_size_mm)
        assert not (overlaps_x and overlaps_y), f"marker at {ox},{oy}"

    # and the longest serial we produce still fits inside it
    longest = f"{c.card_id_prefix}-DEMO-" + max(
        (k[:6].upper() for k in load_loci()), key=len)
    ppmm = 600 / 25.4
    sc = 600 / 25.4 / 12.0
    while sc > 0.05:
        (tw, _), _ = cv2.getTextSize(longest, cv2.FONT_HERSHEY_SIMPLEX, sc,
                                     max(1, int(round(0.18 * ppmm))))
        if tw <= (x1 - x0) * ppmm:
            break
        sc *= 0.94
    assert sc > 0.05, f"{longest!r} cannot be fitted into {x1 - x0:.1f}mm"
