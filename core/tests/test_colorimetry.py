"""L1 and L2. The conformal coverage test is the one that has to hold."""

import numpy as np
import pytest

from ftr.colorimetry import (
    ConformalClassifier, D65, RootPolynomial, delta_e_2000, srgb_to_linear, xyz_to_lab,
)

# Sharma, Wu & Dalal (2005) CIEDE2000 test data — the standard conformance set.
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize("lab1,lab2,expected", SHARMA)
def test_ciede2000_matches_the_conformance_data(lab1, lab2, expected):
    got = float(delta_e_2000(np.array(lab1), np.array(lab2)))
    assert got == pytest.approx(expected, abs=1e-4)


def test_delta_e_is_symmetric_and_zero_on_itself():
    a, b = np.array([44.7, 5.2, -3.1]), np.array([28.4, 12.1, -9.6])
    assert float(delta_e_2000(a, a)) == pytest.approx(0.0, abs=1e-9)
    assert float(delta_e_2000(a, b)) == pytest.approx(float(delta_e_2000(b, a)), abs=1e-9)


def test_white_point_maps_to_L100():
    assert xyz_to_lab(D65) == pytest.approx([100.0, 0.0, 0.0], abs=1e-6)


def test_srgb_transfer_function_endpoints():
    assert srgb_to_linear(np.array([0.0, 1.0])) == pytest.approx([0.0, 1.0], abs=1e-9)
    assert float(srgb_to_linear(np.array([0.5]))[0]) == pytest.approx(0.2140, abs=1e-4)


# --- L1 -------------------------------------------------------------------- #

def _synthetic_card(rng, n=24):
    """A card of known patches, and what a device with a plausible ISP reports."""
    ref_xyz = rng.uniform(5, 95, size=(n, 3))
    true_M = np.array([[0.41, 0.21, 0.02], [0.36, 0.72, 0.12], [0.18, 0.07, 0.95],
                       [0.02, 0.01, 0.00], [0.01, 0.02, 0.03], [0.03, 0.00, 0.01]]) * 100
    return ref_xyz, true_M


def test_transform_recovers_a_known_device_response(rng=np.random.default_rng(7)):
    ref_xyz, true_M = _synthetic_card(rng)
    # invert approximately: generate device RGB, then the XYZ that device implies
    dev_rgb = rng.uniform(0.05, 0.95, size=(24, 3))
    from ftr.colorimetry import _root_poly
    implied_xyz = _root_poly(dev_rgb) @ true_M

    t = RootPolynomial.fit(dev_rgb, implied_xyz)
    assert t.residual_delta_e < 0.01, "a noiseless fit must be near-exact"
    assert t.passes(limit_delta_e=3.0)


def test_a_noisy_card_raises_the_residual_and_can_fail_the_gate():
    rng = np.random.default_rng(11)
    from ftr.colorimetry import _root_poly
    _, true_M = _synthetic_card(rng)
    dev_rgb = rng.uniform(0.05, 0.95, size=(24, 3))
    implied = _root_poly(dev_rgb) @ true_M
    noisy = implied + rng.normal(0, 9.0, size=implied.shape)

    t = RootPolynomial.fit(dev_rgb, noisy)
    assert t.residual_delta_e > 0.5
    assert t.max_delta_e >= t.residual_delta_e


def test_the_fitted_transform_is_exposure_invariant():
    """Every root-polynomial term carries the units of intensity, so scaling the
    illumination scales all terms equally and the solved matrix does not move.

    This is what stops the transform drifting when the officer steps into shade.
    It does *not* mean a brighter patch reads as the same colour — it reads as
    brighter, correctly; exposure is normalised by the card's grey field in L1,
    not by the polynomial.
    """
    rng = np.random.default_rng(3)
    from ftr.colorimetry import _root_poly
    _, true_M = _synthetic_card(rng)
    dev_rgb = rng.uniform(0.1, 0.9, size=(24, 3))
    xyz = _root_poly(dev_rgb) @ true_M

    dim = RootPolynomial.fit(dev_rgb * 0.4, xyz * 0.4)
    bright = RootPolynomial.fit(dev_rgb * 1.6, xyz * 1.6)
    assert np.allclose(dim.matrix, bright.matrix, atol=1e-9)

    # and the same physical patch, measured under either exposure, lands in the
    # same place once its own illumination is divided out
    probe = np.array([[0.4, 0.3, 0.25]])
    a = dim.to_lab(probe * 0.4 / 0.4)
    b = bright.to_lab(probe * 1.6 / 1.6)
    assert float(delta_e_2000(a, b)) < 1e-6


def test_fit_refuses_an_underdetermined_card():
    with pytest.raises(ValueError, match="at least 6 patches"):
        RootPolynomial.fit(np.zeros((4, 3)), np.zeros((4, 3)))
    with pytest.raises(ValueError, match="one reference XYZ per"):
        RootPolynomial.fit(np.zeros((8, 3)), np.zeros((6, 3)))


# --- L2 -------------------------------------------------------------------- #

LOCI = {
    "positive": np.array([28.4, 12.1, -9.6]),    # marquis purple-black
    "negative": np.array([78.2, -1.4, 6.3]),     # unreacted strip
}


def _draw(rng, label, sigma, n):
    return np.array([LOCI[label] + rng.normal(0, sigma, 3) for _ in range(n)]), [label] * n


def test_conformal_coverage_holds_on_held_out_data():
    """The guarantee: the true label is in the set at least 1-alpha of the time.

    This is the property that makes the abstention defensible in court, so it is
    tested empirically rather than assumed from the construction.
    """
    rng = np.random.default_rng(42)
    alpha = 0.05
    cal_labs, cal_lbls = [], []
    for lbl in LOCI:
        x, y = _draw(rng, lbl, 4.0, 200)
        cal_labs.append(x)
        cal_lbls += y
    clf = ConformalClassifier(LOCI, alpha=alpha)
    clf.calibrate(np.vstack(cal_labs), cal_lbls)

    hits = 0
    trials = 800
    for _ in range(trials):
        lbl = "positive" if rng.random() < 0.5 else "negative"
        x = LOCI[lbl] + rng.normal(0, 4.0, 3)
        if lbl in clf.predict(x).prediction_set:
            hits += 1
    coverage = hits / trials
    assert coverage >= 1 - alpha - 0.03, f"coverage {coverage:.3f} below the stated bound"


def test_a_clean_measurement_yields_a_singleton():
    rng = np.random.default_rng(1)
    labs, lbls = [], []
    for lbl in LOCI:
        x, y = _draw(rng, lbl, 2.0, 150)
        labs.append(x)
        lbls += y
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.vstack(labs), lbls)

    p = clf.predict(LOCI["positive"])
    assert p.prediction_set == ("positive",)
    assert p.label == "positive" and not p.inconclusive


def test_an_ambiguous_measurement_abstains_rather_than_guessing():
    """A point midway between loci must widen the set, not pick the nearer one."""
    rng = np.random.default_rng(2)
    labs, lbls = [], []
    for lbl in LOCI:
        x, y = _draw(rng, lbl, 12.0, 300)   # a sloppy, realistic calibration set
        labs.append(x)
        lbls += y
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.vstack(labs), lbls)

    midpoint = (LOCI["positive"] + LOCI["negative"]) / 2
    p = clf.predict(midpoint)
    assert p.inconclusive and p.label is None
    assert set(p.prediction_set) == {"positive", "negative"}
    assert "does not separate" in p.reason


def test_a_measurement_near_nothing_returns_the_empty_set():
    rng = np.random.default_rng(4)
    labs, lbls = [], []
    for lbl in LOCI:
        x, y = _draw(rng, lbl, 1.5, 120)
        labs.append(x)
        lbls += y
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.vstack(labs), lbls)

    p = clf.predict(np.array([55.0, -60.0, 70.0]))   # vivid green: no locus is close
    assert p.prediction_set == () and p.inconclusive
    assert "resembles nothing" in p.reason


def test_certainty_never_increases_as_the_measurement_drifts_away():
    """Honest degradation: moving away from a locus must never buy confidence.

    The nonconformity score for a label must be non-decreasing as the
    measurement walks away from that label\'s locus, and the label must be
    dropped from the set before the walk reaches the other locus.
    """
    rng = np.random.default_rng(5)
    labs, lbls = [], []
    for lbl in LOCI:
        x, y = _draw(rng, lbl, 6.0, 250)
        labs.append(x)
        lbls += y
    clf = ConformalClassifier(LOCI, alpha=0.05)
    clf.calibrate(np.vstack(labs), lbls)

    direction = LOCI["negative"] - LOCI["positive"]
    direction = direction / np.linalg.norm(direction)

    scores, sets = [], []
    for drift in (0, 5, 10, 15, 20, 30):
        p = clf.predict(LOCI["positive"] + direction * drift)
        scores.append(p.scores["positive"])
        sets.append(p.prediction_set)

    assert scores == sorted(scores), "score for 'positive' must not fall as we leave it"
    assert sets[0] == ("positive",), "a clean point is a singleton"
    assert "positive" not in sets[-1], "the far end must not still be called positive"
    assert any(len(s) != 1 for s in sets), "somewhere in between, the call must be given up"


def test_calibration_refuses_too_few_points_for_the_stated_alpha():
    clf = ConformalClassifier(LOCI, alpha=0.01)
    with pytest.raises(ValueError, match="finite-sample guarantee"):
        clf.calibrate(np.array([LOCI["positive"]] * 5), ["positive"] * 5)


def test_predicting_before_calibrating_is_an_error():
    with pytest.raises(RuntimeError, match="not calibrated"):
        ConformalClassifier(LOCI).predict(np.array([50.0, 0.0, 0.0]))


def test_loci_closer_than_the_threshold_can_never_yield_a_singleton():
    """A statement about the reagent, not about the software.

    If two substance classes develop colours closer together than the calibrated
    threshold, the classifier must always return both and report inconclusive.
    Lowering the threshold to make the output look decisive would be discarding
    the coverage guarantee — the one thing that makes the result defensible.
    See docs/DETERMINISM.md.
    """
    near = {
        "class_a": np.array([18.4, 23.2, -7.5]),
        "class_b": np.array([22.1, 20.4, -4.8]),   # about 5 dE away
    }
    separation = float(delta_e_2000(near["class_a"], near["class_b"]))

    rng = np.random.default_rng(17)
    labs, lbls = [], []
    for lbl, locus in near.items():
        labs += [locus + rng.normal(0, 2.4, 3) for _ in range(300)]
        lbls += [lbl] * 300
    clf = ConformalClassifier(near, alpha=0.05)
    threshold = clf.calibrate(np.array(labs), lbls)

    assert threshold > separation, (
        "this test is only meaningful when the loci are closer than the threshold"
    )
    for locus in near.values():
        p = clf.predict(locus)
        assert p.inconclusive, "sitting exactly on a locus must still abstain"
        assert set(p.prediction_set) == set(near), "both classes remain admissible"
