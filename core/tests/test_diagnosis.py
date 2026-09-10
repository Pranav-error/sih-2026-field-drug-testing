"""A refusal must say what to change, not only that something is wrong.

From a real report: a tester photographed the card off a laptop screen and got
"the card's own patches did not reproduce (11.01 dE)". That number is correct
and completely unactionable — the tester retakes the same frame in the same
conditions and gets the same number. Three separate people then guessed at the
cause (low-CRI lighting, wide-gamut display, a print colour-management setting)
and none of the three could be reproduced in simulation.

The card spans dark to light and neutral to saturated on purpose, so the *shape*
of the error across it carries the answer. These tests inject a known cause and
require the diagnosis to name it — or, where the signal genuinely is not there,
to say so rather than guess.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from ftr.card import CARD_V1                              # noqa: E402
from ftr.colorimetry import RootPolynomial, xyz_to_lab    # noqa: E402
from ftr.pipeline import reference_xyz                    # noqa: E402


@pytest.fixture
def reference():
    return reference_xyz(CARD_V1)


def _fit_with(reference, error):
    """A transform whose per-patch error is exactly ``error``.

    Constructed rather than photographed: these tests are about the reasoning
    over the residuals, and driving it through a renderer would make a failure
    ambiguous between the diagnosis and the simulation.
    """
    t = RootPolynomial.fit(np.eye(3)[[0, 1, 2, 0, 1, 2]] * 0.5 + 0.25,
                           reference[:6])
    return RootPolynomial(matrix=t.matrix, residual_delta_e=float(np.mean(error)),
                          max_delta_e=float(np.max(error)),
                          per_patch_delta_e=np.asarray(error, dtype=float))


def test_a_few_wild_patches_read_as_something_on_the_card(reference):
    n = len(reference)
    err = np.full(n, 2.0)
    err[[3, 7, 11]] = [46.0, 40.0, 47.0]          # a glare spot's footprint
    d = _fit_with(reference, err).diagnose(reference)
    assert "something on the card" in d
    assert "glare" in d
    assert "3 of" in d


def test_error_rising_as_patches_darken_reads_as_added_light(reference):
    lab = xyz_to_lab(reference)
    err = 14.0 - 0.14 * lab[:, 0]                 # darkest worst
    d = _fit_with(reference, err).diagnose(reference)
    assert "darker" in d
    assert "black level" in d or "reflection" in d


def test_error_rising_with_saturation_reads_as_a_stretched_gamut(reference):
    lab = xyz_to_lab(reference)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    err = 2.0 + 0.22 * chroma
    d = _fit_with(reference, err).diagnose(reference)
    assert "saturated" in d
    assert "gamut" in d or "vivid" in d


def test_flat_error_reads_as_the_illuminant(reference):
    rng = np.random.default_rng(3)
    err = 9.0 + rng.normal(0, 0.25, len(reference))
    d = _fit_with(reference, err).diagnose(reference)
    assert "same amount" in d
    assert "spectrum" in d and "CRI" in d


def test_an_unreadable_pattern_admits_it_rather_than_guessing(reference):
    """The honest branch, and the one that matters most.

    A confident wrong cause is worse than no cause: it sends somebody to change
    their lighting when the problem is their printer. This fires on the real
    veiling-glare-through-a-screen case, where the lightness correlation is only
    -0.18 and no story is supportable.
    """
    rng = np.random.default_rng(5)
    err = rng.uniform(0.5, 10.0, len(reference))
    d = _fit_with(reference, err).diagnose(reference)
    assert "no clear pattern" in d


def test_the_diagnosis_never_reaches_a_record():
    """A guess about somebody's lighting is not evidence.

    It is a refusal string for the screen. Refusals are recorded, so the wording
    stays hedged — 'likely cause' — and nothing in record.py promotes it to a
    field of its own.
    """
    src = Path("core/ftr/record.py").read_text()
    assert "diagnose" not in src
