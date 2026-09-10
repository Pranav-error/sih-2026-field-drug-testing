"""Can the card be scanned off a phone screen instead of printed?

Asked before a demo, and worth answering with measurements rather than an
opinion, because the two halves of the pipeline give opposite answers.

**Colour: yes, on a decent display.** The device transform is fitted per frame
from the patches on the card itself, and a screen distorts the patches and the
well together — so the fit absorbs the screen. Only a coarse display fails, and
it fails at the quality gate on patch uniformity rather than by measuring the
wrong colour.

**Liveness: no, and never.** A screen is flat. It returns 0.0 px of parallax
against a predicted 28.2 px, and no display improvement changes that: flatness
is the medium, not an artefact of quality. This is the §10 row 1 defence working
exactly as designed, and it is the reason the fold-up tab exists.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from failure_modes import as_screen                      # noqa: E402
from synth import photograph, render_card                # noqa: E402
from synth3d import replay_pair, stereo_pair, tab_texture  # noqa: E402

from ftr.card import CARD_V1                             # noqa: E402
from ftr.colorimetry import ConformalClassifier          # noqa: E402
from ftr.pipeline import measure, measure_pair           # noqa: E402
from ftr.printable import render_printable               # noqa: E402

CFG = json.loads(Path("core/ftr/data/surrogate_loci.json").read_text())


@pytest.fixture(scope="module")
def clf():
    loci = {k: np.array(v, float) for k, v in CFG["loci_lab"].items()}
    rng = np.random.default_rng(2026)
    labs, lbls = [], []
    for k, v in loci.items():
        for _ in range(200):
            labs.append(v + rng.normal(0, CFG["calibration_sigma_lab"], 3))
            lbls.append(k)
    c = ConformalClassifier(loci, alpha=CFG["alpha"])
    c.calibrate(np.array(labs), lbls)
    return c


def _through_a_screen(card, strength, rng):
    shot = photograph(card, rng=rng, illuminant="daylight")
    scr = as_screen(shot, strength=strength) if strength > 0 else shot
    return photograph(scr, rng=rng, margin=0.12, illuminant="daylight")


@pytest.mark.parametrize("label", ["opiate_class", "amphetamine_class"])
def test_colour_survives_a_typical_phone_display(label, clf):
    """A demo without printers is possible, and this is the evidence for it."""
    card = render_printable(dpi=300, serial="T", batch="T", well_label=label)
    m = measure(_through_a_screen(card, 0.10, np.random.default_rng(7)),
                classifier=clf)
    assert m.quality.passed, m.refusals
    assert list(m.prediction.prediction_set) == [label]


def test_a_coarse_display_is_refused_at_the_gate_not_mismeasured(clf):
    """The failure mode matters as much as the failure.

    A coarse screen must be REFUSED, never quietly measured as some other
    colour. Subpixel stripes break patch uniformity, which is the check added
    after the 83-condition sweep found sensor noise passing invisibly.
    """
    card = render_printable(dpi=300, serial="T", batch="T",
                            well_label="opiate_class")
    m = measure(_through_a_screen(card, 0.20, np.random.default_rng(7)),
                classifier=clf)
    assert not m.quality.passed
    assert any("not uniform" in r for r in m.refusals), m.refusals


def test_liveness_can_never_pass_from_a_screen(clf):
    """0.0 px against a predicted 28.2. No display quality changes this."""
    raised = (tab_texture(), CARD_V1.tab_height_mm, np.array(CARD_V1.tab_quad_mm))
    card = render_card(well_srgb=(0.28, 0.12, 0.22))

    live = measure_pair(*stereo_pair(card, raised=raised), clf)
    assert live.record_fields()["liveness"]["live"] is True, (
        "a physical card with a folded tab must pass, or the test proves nothing")

    for medium in ("screen", "print"):
        m = measure_pair(*replay_pair(card, medium=medium, raised=raised), clf)
        lv = m.record_fields()["liveness"]
        assert lv["live"] is False, medium
        assert lv["displacement_px_x100"] <= 100, (
            f"{medium}: {lv['displacement_px_x100'] / 100:.1f}px of parallax "
            "from something flat")


def test_an_unfolded_physical_card_is_also_refused(clf):
    """The commonest demo mistake, and it is not a bug.

    A printed card whose tab was never folded is flat, so it is refused for the
    same reason a screen is. Worth pinning because it will be reported as a
    fault by whoever forgets the fold.
    """
    card = render_card(well_srgb=(0.28, 0.12, 0.22))
    m = measure_pair(*stereo_pair(card), clf)
    assert m.record_fields()["liveness"]["live"] is False
