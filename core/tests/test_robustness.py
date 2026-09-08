"""The operating envelope, and the one attack that defeats it.

Three outcomes, and they are not equally bad:

    accept + accurate   the pipeline worked
    reject              refused, correctly or over-cautiously
    accept + wrong      the dangerous quadrant

Everything here hunts the third. A robustness suite that only proves the pipeline
works under good conditions is marketing.
"""

import numpy as np
import pytest

import failure_modes as fm
from ftr.colorimetry import RootPolynomial, delta_e_2000, srgb_to_linear, xyz_to_lab
from ftr.detect import (detect_card, estimate_illumination, grade_frame, rectify,
                        sample_patches, sample_well, substrate_residual)
from ftr.pipeline import SRGB_TO_XYZ_D65, reference_xyz
from synth import photograph, render_card

WELL = (0.28, 0.12, 0.22)
TRUTH = xyz_to_lab(srgb_to_linear(np.array(WELL)) @ SRGB_TO_XYZ_D65.T)
DANGEROUS_DE = 4.0


@pytest.fixture(scope="module")
def card():
    return render_card(well_srgb=WELL)


def run(image):
    """(accepted, dE, first_failure)."""
    det = detect_card(image)
    if det is None or not det.complete:
        return False, None, "card not found"
    rect = rectify(image, det)
    first = sample_patches(rect)
    gain, resid = estimate_illumination(first)
    patches = sample_patches(rect, gain=gain)
    quality = grade_frame(rect, det, patches, resid, gain=gain)
    transform = RootPolynomial.fit(patches.rgb, reference_xyz())
    well, _ = sample_well(rect, gain=gain)
    de = float(delta_e_2000(transform.to_lab(well[None, :]), TRUTH))
    failures = quality.failures()
    if not transform.passes():
        failures.append("card residual")
    return (not failures), de, (failures[0] if failures else "")


# --- defects the robustness sweep found, now fixed ------------------------- #

@pytest.mark.parametrize("depth", [0.20, 0.35, 0.50, 0.65])
def test_a_hard_shadow_edge_is_refused(card, depth):
    """Was accepted at up to 17 dE of error before substrate probing existed.

    INUC fits a bi-quadratic surface; a step is not bi-quadratic. Fitting it from
    eight neutral patches meant a shadow edge falling between them was invisible.
    196 substrate probes see it.
    """
    accepted, de, why = run(photograph(fm.hard_shadow(card, depth=depth)))
    assert not accepted, f"a hard shadow edge carrying {de:.2f} dE was accepted"
    assert "shadow" in why or "light" in why


def test_a_soft_shadow_is_still_accepted(card):
    """The fix must not reject the condition INUC exists to correct."""
    accepted, de, why = run(photograph(card, shadow=0.55, illuminant="shade"))
    assert accepted, f"a correctable soft shadow was refused: {why}"
    assert de < 2.0


@pytest.mark.parametrize("quality", [25, 10])
def test_heavy_compression_is_refused(card, quality):
    """JPEG q10 was accepted at 11.6 dE. Blocking corrupts colour without
    blurring, so nothing in the original gate noticed."""
    accepted, de, _ = run(photograph(card, jpeg_quality=quality))
    assert not accepted, f"q{quality} was accepted carrying {de:.2f} dE"


@pytest.mark.parametrize("quality", [95, 80, 60, 40])
def test_ordinary_compression_is_still_accepted(card, quality):
    accepted, de, why = run(photograph(card, jpeg_quality=quality))
    assert accepted, f"q{quality} refused: {why}"
    assert de < 2.0


def test_heavy_sensor_noise_is_refused(card):
    accepted, de, _ = run(photograph(card, noise=25))
    assert not accepted, f"heavy noise accepted carrying {de:.2f} dE"


# --- the envelope ---------------------------------------------------------- #

ENVELOPE = [
    ("tilt 20", dict(tilt=20)),
    ("rotation 30", dict(rotation=30)),
    ("shade", dict(illuminant="shade")),
    ("fluorescent", dict(illuminant="fluorescent")),
    ("underexposed", dict(exposure=0.5)),
    ("soft shadow", dict(shadow=0.55)),
    ("mild noise", dict(noise=8)),
    ("jpeg 80", dict(jpeg_quality=80)),
]


@pytest.mark.parametrize("name,kw", ENVELOPE, ids=[n for n, _ in ENVELOPE])
def test_the_envelope_holds(card, name, kw):
    accepted, de, why = run(photograph(card, **kw))
    assert accepted, f"{name} should be inside the envelope: {why}"
    assert de < DANGEROUS_DE, f"{name} accepted carrying {de:.2f} dE"


OUTSIDE = [
    ("extreme tilt", lambda c: photograph(c, tilt=35)),
    ("creased card", lambda c: photograph(fm.crease(c, depth=0.3))),
    ("occluded fiducial", lambda c: fm.occlude_fiducial(photograph(c), coverage=0.5)),
    ("far too dark", lambda c: photograph(c, exposure=0.1)),
    ("blown out", lambda c: photograph(c, exposure=2.2)),
    ("defocused", lambda c: photograph(c, blur_px=7)),
    ("motion blur", lambda c: fm.motion_blur(photograph(c), length=21)),
    ("torch hotspot", lambda c: photograph(c, illuminant="torch", glare=0.25)),
    ("too far away", lambda c: fm.at_distance(photograph(c), 0.15)),
]


@pytest.mark.parametrize("name,make", OUTSIDE, ids=[n for n, _ in OUTSIDE])
def test_conditions_outside_the_envelope_are_refused(card, name, make):
    accepted, de, _ = run(make(card))
    assert not accepted, f"{name} was accepted carrying {de:.2f} dE"


def test_a_creased_card_is_caught_by_the_geometry(card):
    """A homography maps one plane to another. A creased card is two planes, and
    no single homography fits it — which the tilt estimate notices."""
    accepted, _, why = run(photograph(fm.crease(card, depth=0.3)))
    assert not accepted
    assert "tilt" in why.lower()


# --- the attack that still works ------------------------------------------- #

def test_a_cheap_replay_is_caught(card):
    """Low-quality reproductions leave artefacts the gate notices."""
    accepted, _, _ = run(fm.replay(card, medium="print"))
    assert not accepted
    accepted, _, _ = run(fm.replay(card, medium="screen"))
    assert not accepted


@pytest.mark.parametrize("medium,kw", [
    ("print", dict(dot_gain=0.02, gamut=0.97, blur_px=0.4)),
    ("screen", dict(pitch=2, strength=0.06)),
])
def test_a_QUALITY_replay_defeats_the_pipeline(card, medium, kw):
    """**This test asserts a vulnerability, and it is meant to.**

    ARCHITECTURE.md §10 row 1 claimed replay was defeated because "the card must
    be co-planar and co-illuminated with the strip". That reasoning is wrong: a
    replay reproduces the *whole scene*, so co-planarity and co-illumination are
    preserved, not broken.

    What actually catches a cheap replay is reproduction artefacts — print blur,
    screen subpixel structure — and better equipment removes them. A photo-lab
    print and a high-DPI screen both pass the gate reading as near-perfect
    captures.

    If this test ever starts failing, someone has built a real defence and this
    test should be inverted, the §10 row updated, and docs/ROBUSTNESS.md revised.
    Until then it stands as the honest statement of a residual risk.
    """
    original = photograph(card, illuminant="daylight")
    reproduced = (fm.as_print(original, **kw) if medium == "print"
                  else fm.as_screen(original, **kw))
    accepted, de, why = run(photograph(reproduced, margin=0.12))

    assert accepted, (
        f"a quality {medium} replay was refused ({why}) — if this is a real "
        "defence rather than an artefact of the simulation, invert this test"
    )
    assert de < 1.0, "and it reads as an excellent capture, which is the problem"


def test_the_substrate_probe_separates_smooth_light_from_edges(card):
    """The metric that made the shadow fix possible, tested directly."""
    def residual(img):
        det = detect_card(img)
        rect = rectify(img, det)
        gain, _ = estimate_illumination(sample_patches(rect))
        return substrate_residual(rect, gain)

    ideal = residual(photograph(card))
    smooth = residual(photograph(card, shadow=0.55))
    edge = residual(photograph(fm.hard_shadow(card, depth=0.35)))

    assert ideal < 0.08 and smooth < 0.10, "smooth light must leave little residual"
    assert edge > 5 * smooth, "an edge must be unmistakable next to a gradient"
