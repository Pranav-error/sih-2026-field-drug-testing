"""Physically-based rendering, and the property the RGB-gain model cannot have."""

import numpy as np
import pytest

from ftr.colorimetry import RootPolynomial, delta_e_2000, xyz_to_lab
from ftr.spectral import (WAVELENGTHS, CAMSPEC_PATH, colourchecker_reflectances,
                          illuminant_spd, load_cameras, render_rgb)

pytestmark = pytest.mark.skipif(
    not CAMSPEC_PATH.exists(),
    reason="spectral data not fetched; run python core/tools/fetch_spectral_data.py",
)


@pytest.fixture(scope="module")
def cams():
    return load_cameras()


@pytest.fixture(scope="module")
def refl():
    return colourchecker_reflectances()


def test_the_camera_database_parses_completely(cams):
    assert len(cams) == 28, "the Jiang database has 28 cameras"
    for cam in cams.values():
        assert cam.sensitivities.shape == (len(WAVELENGTHS), 3)
        assert np.all(cam.sensitivities >= 0), "a sensitivity cannot be negative"
        assert cam.sensitivities.max() > 0.5, "channels are normalised to a peak near 1"


def test_the_database_contains_a_mobile_sensor(cams):
    """The deployment target is a phone. Exactly one of the 28 is one, which is a
    limitation of this analysis and is recorded as such in data/spectral/README.md."""
    mobiles = [n for n, c in cams.items() if c.kind == "mobile"]
    assert mobiles == ["Nokia N900"]


def test_illuminants_differ_in_shape_not_just_brightness():
    a, d65 = illuminant_spd("A"), illuminant_spd("D65")
    assert np.isclose(a.mean(), 1.0) and np.isclose(d65.mean(), 1.0), "energy-normalised"
    # Illuminant A is a tungsten black body: red-heavy, blue-poor.
    assert a[-1] / a[0] > 3 * (d65[-1] / d65[0])


def test_metamerism_exists_in_rendered_data(cams, refl):
    """The property that makes cross-illuminant results meaningful.

    Two surfaces whose camera response is close under one light and far apart
    under another. A per-channel gain model produces a swing of exactly zero for
    every pair, because scaling both surfaces identically cannot change their
    ratio — so every cross-illuminant number taken from tests/synth.py is measured
    on an easier problem than reality. This test asserts the physical renderer does
    not share that flaw.
    """
    cam = cams["Nokia N900"]
    names = list(refl)
    swings = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = []
            for ill in ("D65", "A", "FL11"):
                spd = illuminant_spd(ill)
                ra = render_rgb(refl[names[i]], spd, cam)
                rb = render_rgb(refl[names[j]], spd, cam)
                d.append(float(np.linalg.norm(ra - rb) / max(np.linalg.norm(ra), 1e-9)))
            swings.append(max(d) - min(d))
    assert max(swings) > 1.0, "no metameric divergence: the renderer is not physical"


def test_the_device_transform_recovers_a_held_out_surface(cams, refl):
    """Leave-one-patch-out: fit on 23, predict the 24th, on measured sensitivities.

    The held-out patch is a surface the transform has never seen, which is exactly
    the situation of the reaction well.
    """
    from ftr.spectral import WAVELENGTHS as W
    import colour

    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    bar = np.array([[cmfs[w][i] for i in range(3)] for w in W])

    def xyz(r, ill):
        k = 100.0 / (ill * bar[:, 1]).sum()
        return k * (r[:, None] * ill[:, None] * bar).sum(axis=0)

    names = list(refl)
    d65 = illuminant_spd("D65")
    truth = {n: xyz_to_lab(xyz(refl[n], d65)) for n in names}

    for cam_name in ("Nokia N900", "Canon 5DMarkII"):
        cam = cams[cam_name]
        for ill_name, limit in (("D65", 1.5), ("A", 3.0)):
            spd = illuminant_spd(ill_name)
            rgb = np.array([render_rgb(refl[n], spd, cam) for n in names])
            tgt = np.array([xyz(refl[n], d65) for n in names])
            errs = []
            for k in range(len(names)):
                keep = [m for m in range(len(names)) if m != k]
                t = RootPolynomial.fit(rgb[keep], tgt[keep])
                errs.append(float(delta_e_2000(t.to_lab(rgb[k][None, :]), truth[names[k]])))
            median = float(np.median(errs))
            assert median < limit, (
                f"{cam_name} under {ill_name}: median {median:.2f} dE exceeds {limit}"
            )


def test_a_non_reference_illuminant_costs_accuracy(cams, refl):
    """Tungsten is measurably harder than daylight, and the design should not
    pretend otherwise. If this ever stops being true, the renderer has broken."""
    import colour
    from ftr.spectral import WAVELENGTHS as W

    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    bar = np.array([[cmfs[w][i] for i in range(3)] for w in W])

    def xyz(r, ill):
        k = 100.0 / (ill * bar[:, 1]).sum()
        return k * (r[:, None] * ill[:, None] * bar).sum(axis=0)

    names = list(refl)
    d65 = illuminant_spd("D65")
    truth = {n: xyz_to_lab(xyz(refl[n], d65)) for n in names}
    cam = cams["Canon 5DMarkII"]

    def median_error(ill_name):
        spd = illuminant_spd(ill_name)
        rgb = np.array([render_rgb(refl[n], spd, cam) for n in names])
        tgt = np.array([xyz(refl[n], d65) for n in names])
        errs = []
        for k in range(len(names)):
            keep = [m for m in range(len(names)) if m != k]
            t = RootPolynomial.fit(rgb[keep], tgt[keep])
            errs.append(float(delta_e_2000(t.to_lab(rgb[k][None, :]), truth[names[k]])))
        return float(np.median(errs))

    assert median_error("A") > median_error("D65"), "tungsten must cost something"
