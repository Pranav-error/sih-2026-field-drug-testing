"""L1 against a synthetic camera.

The property that matters is not "the pipeline is accurate". It is:

    every frame the gate ACCEPTS is accurate, and every frame it accepts wrongly
    would have been a confident wrong answer.

So the headline test measures the worst error across all accepted frames, and the
rest establish that each degradation is caught by the metric meant to catch it.
"""

import numpy as np
import pytest

from ftr.card import CARD_V1, PX_PER_MM
from ftr.colorimetry import RootPolynomial, delta_e_2000, srgb_to_linear, xyz_to_lab
from ftr.detect import (detect_card, estimate_illumination, grade_frame, rectify,
                        sample_patches, sample_well)
from ftr.pipeline import SRGB_TO_XYZ_D65, measure, reference_xyz
from synth import render_card, photograph

WELL_SRGB = (0.28, 0.12, 0.22)
TRUTH_LAB = xyz_to_lab(srgb_to_linear(np.array(WELL_SRGB)) @ SRGB_TO_XYZ_D65.T)


@pytest.fixture(scope="module")
def card():
    return render_card(well_srgb=WELL_SRGB)


def _run(photo):
    det = detect_card(photo)
    assert det is not None and det.complete, "card not detected"
    rect = rectify(photo, det)
    first = sample_patches(rect)
    gain, resid = estimate_illumination(first)
    patches = sample_patches(rect, gain=gain)
    t = RootPolynomial.fit(patches.rgb, reference_xyz())
    well, _ = sample_well(rect, gain=gain)
    lab = t.to_lab(well[None, :])
    return det, grade_frame(rect, det, patches, resid), float(delta_e_2000(lab, TRUTH_LAB))


# --- card geometry --------------------------------------------------------- #

def test_no_element_of_the_card_overlaps_another():
    """A layout bug here is a silent measurement bug everywhere downstream."""
    c = CARD_V1
    half = c.patch_size_mm / 2
    boxes = [(x - half, y - half, x + half, y + half) for x, y in c.patch_centres_mm]

    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes[i + 1:], i + 1):
            assert (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]), \
                f"patch {i} overlaps patch {j}"

    s = c.marker_size_mm
    for i, a in enumerate(boxes):
        for k, (ox, oy) in enumerate(c.marker_origins_mm):
            m = (ox, oy, ox + s, oy + s)
            assert (a[2] <= m[0] or m[2] <= a[0] or a[3] <= m[1] or m[3] <= a[1]), \
                f"patch {i} overlaps marker {k}"

    wx, wy = c.well_centre_mm
    for i, (x, y) in enumerate(c.patch_centres_mm):
        dx, dy = max(abs(x - wx) - half, 0), max(abs(y - wy) - half, 0)
        assert np.hypot(dx, dy) >= c.well_radius_mm, f"patch {i} overlaps the reaction well"

    assert 0 <= wx - c.well_radius_mm and wx + c.well_radius_mm <= c.width_mm
    assert 0 <= wy - c.well_radius_mm and wy + c.well_radius_mm <= c.height_mm


def test_neutrals_span_the_card_in_both_axes():
    """The illumination surface is bi-quadratic in x AND y.

    Neutrals on a single row leave every y term unconstrained, so the fit cannot
    see a shadow above or below that line. Synthetic capture caught a hotspot
    passing the gate at 52 dE when this was violated; the layout must not regress.
    """
    n = CARD_V1.patch_centres_mm[list(CARD_V1.neutral_index)]
    assert len(set(n[:, 0])) >= 3, "neutrals must span at least three columns"
    assert len(set(n[:, 1])) >= 3, "neutrals must span at least three rows"
    assert len(n) >= 6, "a bi-quadratic surface needs six independent points"


# --- detection ------------------------------------------------------------- #

@pytest.mark.parametrize("kw", [
    {}, dict(tilt=10), dict(tilt=20), dict(rotation=25), dict(rotation=-40),
    dict(blur_px=2), dict(noise=4.0), dict(jpeg_quality=60),
    dict(illuminant="tungsten"), dict(illuminant="shade"), dict(exposure=0.5),
    dict(shadow=0.6), dict(tilt=15, rotation=20, jpeg_quality=70, noise=2.0),
])
def test_card_is_found_across_the_capture_matrix(card, kw):
    det = detect_card(photograph(card, **kw))
    assert det is not None and det.complete
    assert det.reprojection_px < 2.0


def test_detection_returns_none_when_there_is_no_card():
    noise = (np.random.default_rng(0).random((600, 800, 3)) * 255).astype(np.uint8)
    assert detect_card(noise) is None


def test_tilt_is_recovered_and_ordered(card):
    angles = [0, 10, 20, 30]
    measured = [detect_card(photograph(card, tilt=a)).tilt_degrees for a in angles]
    assert measured == sorted(measured), "tilt estimate must increase with real tilt"
    assert measured[0] < 5 and measured[-1] > 20


def test_rectification_puts_patches_where_the_spec_says(card):
    """A patch sampled at its nominal coordinate must be its nominal colour."""
    det = detect_card(photograph(card))
    rect = rectify(photograph(card), det)
    patches = sample_patches(rect)
    nominal = srgb_to_linear(CARD_V1.patch_srgb)
    # linear values, so compare in a relative sense; gross mis-registration would
    # sample a neighbour or the paper and blow this out by an order of magnitude.
    assert np.allclose(patches.rgb, nominal, atol=0.06), "patch sampling is mis-registered"


# --- illumination ---------------------------------------------------------- #

def test_inuc_removes_a_shadow_gradient(card):
    _, _, with_shadow = _run(photograph(card, shadow=0.75))
    assert with_shadow < 1.5, "a strong shadow must be corrected, not merely detected"


def test_inuc_beats_no_correction_under_a_shadow(card):
    photo = photograph(card, shadow=0.75)
    det = detect_card(photo)
    rect = rectify(photo, det)
    raw = sample_patches(rect)
    gain, _ = estimate_illumination(raw)
    corrected = sample_patches(rect, gain=gain)

    ref = reference_xyz()
    well_raw, _ = sample_well(rect)
    well_cor, _ = sample_well(rect, gain=gain)
    de_raw = float(delta_e_2000(RootPolynomial.fit(raw.rgb, ref).to_lab(well_raw[None, :]), TRUTH_LAB))
    de_cor = float(delta_e_2000(RootPolynomial.fit(corrected.rgb, ref).to_lab(well_cor[None, :]), TRUTH_LAB))
    assert de_cor < de_raw / 2, f"correction should more than halve the error ({de_raw:.2f} -> {de_cor:.2f})"


def test_the_illumination_surface_corrects_space_not_exposure(card):
    """Global gain is the device transform's job, fitted against 23 patches.

    The surface must therefore be mean-neutral over the card: a uniform change in
    exposure must leave it essentially flat.
    """
    photo = photograph(card, exposure=0.6)
    det = detect_card(photo)
    raw = sample_patches(rectify(photo, det))
    gain, _ = estimate_illumination(raw)
    from ftr.detect import _basis
    w, h = CARD_V1.rectified_size
    yy, xx = np.mgrid[0:h:40, 0:w:40]
    surface = np.exp(_basis(np.stack([xx.ravel(), yy.ravel()], 1).astype(float), w, h) @ gain)
    assert 0.9 < surface.mean() < 1.1, "the surface must not absorb global exposure"


def test_a_hotspot_raises_the_illumination_residual(card):
    _, clean, _ = _run(photograph(card))
    _, hot, _ = _run(photograph(card, illuminant="torch", glare=0.25))
    assert hot.illumination_residual_stops > 10 * clean.illumination_residual_stops


# --- the quality gate ------------------------------------------------------ #

ACCEPTABLE = [
    ("ideal", {}),
    ("shade", dict(illuminant="shade")),
    ("fluorescent", dict(illuminant="fluorescent")),
    ("underexposed", dict(exposure=0.55)),
    ("shadow", dict(shadow=0.55)),
    ("hard shadow", dict(shadow=0.75)),
    ("shadow+shade+jpeg", dict(shadow=0.45, illuminant="shade", jpeg_quality=75, noise=1.5)),
    ("rotated", dict(rotation=22)),
    ("tilted 18", dict(tilt=18)),
]

MUST_REJECT = [
    ("torch hotspot", dict(illuminant="torch", glare=0.25)),
    ("very blurry", dict(blur_px=9)),
    ("far too dark", dict(exposure=0.15)),
    ("extreme tilt", dict(tilt=32)),
    ("blown out", dict(exposure=1.9)),
]


@pytest.mark.parametrize("name,kw", ACCEPTABLE, ids=[n for n, _ in ACCEPTABLE])
def test_frames_the_gate_accepts_are_accurate(card, name, kw):
    """The headline property. An accepted frame must carry a usable measurement."""
    _, gate, de = _run(photograph(card, **kw))
    assert gate.passed, f"{name} should be usable but was rejected: {gate.failures()}"
    assert de < 2.0, f"{name} passed the gate carrying {de:.2f} dE of error"


@pytest.mark.parametrize("name,kw", MUST_REJECT, ids=[n for n, _ in MUST_REJECT])
def test_frames_that_would_mislead_are_rejected(card, name, kw):
    _, gate, _ = _run(photograph(card, **kw))
    assert not gate.passed, f"{name} was accepted; it should not have been"
    assert gate.guidance() != "Hold steady.", f"{name} gave no actionable guidance"


def test_guidance_names_the_fix_not_the_failure(card):
    """Copy rule from DESIGN.md: tell the operator what to move."""
    _, gate, _ = _run(photograph(card, tilt=32))
    assert "flatter" in gate.guidance().lower()
    _, gate, _ = _run(photograph(card, blur_px=9))
    assert "steady" in gate.guidance().lower() or "focus" in gate.guidance().lower()


# --- the pipeline ---------------------------------------------------------- #

def test_measure_abstains_rather_than_guessing(card):
    from ftr.colorimetry import ConformalClassifier
    loci = {"positive": TRUTH_LAB, "negative": np.array([78.2, -1.4, 6.3])}
    rng = np.random.default_rng(1)
    labs, lbls = [], []
    for k, v in loci.items():
        labs += [v + rng.normal(0, 2.0, 3) for _ in range(150)]
        lbls += [k] * 150
    clf = ConformalClassifier(loci, alpha=0.05)
    clf.calibrate(np.array(labs), lbls)

    good = measure(photograph(card), clf)
    assert good.usable and good.prediction.label == "positive"

    bad = measure(photograph(card, illuminant="torch", glare=0.25), clf)
    assert not bad.usable and bad.prediction is None
    assert bad.refusals, "a refusal must carry its reason"


def test_measure_reports_missing_card_without_crashing():
    noise = (np.random.default_rng(2).random((600, 800, 3)) * 255).astype(np.uint8)
    m = measure(noise)
    assert not m.detected and not m.usable
    assert "fiducials" in m.refusals[0]
    assert m.record_fields()["colorimetry"]["measured"] is False


def test_record_fields_are_all_integers_or_bools(card):
    """Canonical CBOR refuses floats. Catch a stray one here, not at sealing."""
    from ftr.canonical_cbor import dumps
    m = measure(photograph(card))
    dumps(m.record_fields())      # raises CborError on any float


def test_the_same_frame_measures_identically_twice(card):
    """The verifier re-runs this and demands the stored Lab back, bit for bit."""
    photo = photograph(card, shadow=0.4, jpeg_quality=80)
    a, b = measure(photo), measure(photo)
    assert a.record_fields() == b.record_fields()


# --- the printed artefact -------------------------------------------------- #

def test_the_printable_card_is_detectable_after_a_camera_round_trip():
    """The physical artefact and the detector must not drift apart.

    render_printable() is what gets printed and handed to an officer; the synthetic
    camera in synth.py is what the rest of this file tests against. If they ever
    diverge — a marker id, a quiet zone, a patch coordinate — every test above
    keeps passing while the real card stops working. This is the only test that
    closes that loop.
    """
    import cv2
    from ftr.printable import render_printable

    printed = render_printable(dpi=300, serial="0417", batch="B12")
    # photographed at a realistic capture resolution, not at print resolution
    scale = 1400 / printed.shape[1]
    shot = cv2.resize(printed, (1400, int(printed.shape[0] * scale)), interpolation=cv2.INTER_AREA)

    det = detect_card(shot)
    assert det is not None and det.complete, "the card we print must be the card we detect"
    assert det.reprojection_px < 2.0
