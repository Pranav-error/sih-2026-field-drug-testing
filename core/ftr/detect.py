"""L1 front half — find the card, rectify it, divide out the light, sample.

Order matters and each step earns its place:

    detect       four fiducials, sub-pixel, robust to partial occlusion
    rectify      homography to a fixed mm grid; patch centres become constants
    INUC         divide out the illumination surface — the officer's own shadow
    sample       trimmed mean per patch, rejecting specular hits and dust
    grade        blur, glare, dynamic range, geometry — reported, never swallowed

The quality numbers are not advisory. They are written into the record, and a
frame that fails them produces an abstention rather than a confident answer.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .card import PX_PER_MM, CARD_V1, CardSpec
from .colorimetry import srgb_to_linear

__all__ = ["Detection", "PatchSample", "detect_card", "rectify", "sample_patches",
           "sample_well", "estimate_illumination", "substrate_residual",
           "QualityGate", "grade_frame"]


# --------------------------------------------------------------------------- #
# detection
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Detection:
    """Where the card is, and how well we know it."""

    homography: np.ndarray            # image -> rectified mm grid (in pixels)
    markers_found: tuple[int, ...]
    reprojection_px: float            # RMS of the four fiducials through H
    tilt_degrees: float               # angle of the card plane off the sensor normal

    @property
    def complete(self) -> bool:
        return len(self.markers_found) == 4


def _detector(spec: CardSpec):
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec.marker_dict))
    params = cv2.aruco.DetectorParameters()
    # Sub-pixel corners: the homography is only as good as these four points, and
    # a half-pixel error at the corner is a millimetre at the far patch.
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = 7
    return cv2.aruco.ArucoDetector(d, params)


def _tilt_from_homography(H: np.ndarray) -> float:
    """Angle between the card plane and the sensor plane, in degrees.

    Recovered from the two in-plane basis vectors of the homography. Exact metric
    tilt needs the camera intrinsics; this is the scale-free proxy, which is what
    the operator guidance and the quality gate actually need.
    """
    h1, h2 = H[:, 0], H[:, 1]
    n1, n2 = np.linalg.norm(h1), np.linalg.norm(h2)
    if n1 == 0 or n2 == 0:
        return 90.0
    cos_between = abs(float(np.dot(h1, h2) / (n1 * n2)))
    skew = np.degrees(np.arcsin(np.clip(cos_between, 0, 1)))
    aspect = max(n1, n2) / min(n1, n2)
    foreshorten = np.degrees(np.arccos(np.clip(1.0 / aspect, 0, 1)))
    return float(max(skew, foreshorten))


def detect_card(image_bgr: np.ndarray, spec: CardSpec = CARD_V1) -> Detection | None:
    """Locate the card. Returns None when fewer than four fiducials resolve.

    Three markers are geometrically sufficient for a homography, and we refuse
    anyway: the fourth is the redundancy that makes the reprojection residual
    meaningful. Without it there is no way to tell a good fit from an exact fit
    to bad points.
    """
    corners, ids, _ = _detector(spec).detectMarkers(image_bgr)
    if ids is None:
        return None
    found = {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}

    wanted = spec.marker_ids
    present = tuple(i for i in wanted if i in found)
    if len(present) < 4:
        return Detection(np.eye(3), present, float("inf"), 90.0)

    # One outer corner per marker: TL of the TL marker, TR of the TR marker, etc.
    # ArUco reports corners clockwise from the marker's top-left.
    picks = [found[wanted[0]][0], found[wanted[1]][1],
             found[wanted[2]][2], found[wanted[3]][3]]
    src = np.array(picks, dtype=np.float32)
    dst = (spec.marker_corners_mm * PX_PER_MM).astype(np.float32)

    H = cv2.getPerspectiveTransform(src, dst)
    back = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    rms = float(np.sqrt(np.mean(np.sum((back - dst) ** 2, axis=1))))
    return Detection(H, wanted, rms, _tilt_from_homography(np.linalg.inv(H)))


def rectify(image_bgr: np.ndarray, det: Detection, spec: CardSpec = CARD_V1) -> np.ndarray:
    """Warp the card to the canonical mm grid."""
    return cv2.warpPerspective(image_bgr, det.homography, spec.rectified_size,
                               flags=cv2.INTER_CUBIC)


# --------------------------------------------------------------------------- #
# sampling
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PatchSample:
    rgb: np.ndarray                   # (N, 3) linear, 0..1, illumination-corrected
    raw_rgb: np.ndarray               # (N, 3) linear, before correction
    saturated: np.ndarray             # (N,) fraction of pixels clipped
    spread: np.ndarray                # (N,) within-patch stdev after trimming


def _trimmed_mean(block: np.ndarray, trim: float = 0.25) -> tuple[np.ndarray, float, float]:
    """Mean of a patch after dropping the brightest and darkest quarter.

    A specular highlight from a torch, a dust speck, or the edge of a neighbouring
    patch all land in the tails. Trimming is cheaper and more predictable than
    outlier modelling, and it is trivial to explain to a court.
    """
    flat = block.reshape(-1, 3)
    lum = flat @ np.array([0.2126, 0.7152, 0.0722])
    order = np.argsort(lum)
    k = int(len(order) * trim / 2)
    keep = flat[order[k:len(order) - k]] if len(order) > 4 * k > 0 else flat
    sat = float(np.mean(np.any(flat >= 0.99, axis=1)))
    # Per-channel spread, then averaged. Taking the std over all three channels
    # together would measure the patch's *colour* — a purple patch has R != G != B
    # and would look noisy while being perfectly clean.
    return keep.mean(axis=0), sat, float(keep.std(axis=0).mean())


def sample_patches(rectified_bgr: np.ndarray, spec: CardSpec = CARD_V1,
                   gain: np.ndarray | None = None) -> PatchSample:
    """Trimmed-mean sample of every patch, in linear RGB.

    ``gain`` is the illumination surface from :func:`estimate_illumination`; when
    supplied, each patch is divided by the surface at its own location.
    """
    rgb = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lin = srgb_to_linear(rgb)
    half = int(spec.patch_size_mm * PX_PER_MM * 0.35)   # inner 70%: avoid print edges

    raw, sat, spread = [], [], []
    for cx, cy in spec.patch_centres_px():
        x, y = int(round(cx)), int(round(cy))
        block = lin[max(0, y - half):y + half, max(0, x - half):x + half]
        m, s, sd = _trimmed_mean(block)
        raw.append(m)
        sat.append(s)
        spread.append(sd)

    raw = np.array(raw)
    corrected = raw if gain is None else raw / np.clip(_gain_at(gain, spec.patch_centres_px()), 1e-6, None)
    return PatchSample(rgb=corrected, raw_rgb=raw,
                       saturated=np.array(sat), spread=np.array(spread))


def sample_well(rectified_bgr: np.ndarray, spec: CardSpec = CARD_V1,
                gain: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Sample the reaction region. Returns linear RGB and the saturated fraction."""
    rgb = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lin = srgb_to_linear(rgb)
    cx, cy = spec.well_centre_px()
    r = spec.well_radius_mm * PX_PER_MM * 0.7

    yy, xx = np.mgrid[0:lin.shape[0], 0:lin.shape[1]]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
    px = lin[mask]
    lum = px @ np.array([0.2126, 0.7152, 0.0722])
    order = np.argsort(lum)
    k = int(len(order) * 0.125)
    keep = px[order[k:len(order) - k]] if len(order) > 4 * k > 0 else px
    val = keep.mean(axis=0)
    if gain is not None:
        val = val / np.clip(_gain_at(gain, np.array([[cx, cy]]))[0], 1e-6, None)
    return val, float(np.mean(np.any(px >= 0.99, axis=1)))


# --------------------------------------------------------------------------- #
# illumination non-uniformity correction
# --------------------------------------------------------------------------- #

def _basis(xy: np.ndarray, w: float, h: float) -> np.ndarray:
    """Bi-quadratic basis in normalised card coordinates."""
    x = xy[:, 0] / w
    y = xy[:, 1] / h
    return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=1)


def _gain_at(coeffs: np.ndarray, xy_px: np.ndarray, spec: CardSpec = CARD_V1) -> np.ndarray:
    w, h = spec.rectified_size
    return np.exp(_basis(np.asarray(xy_px, dtype=float), w, h) @ coeffs)


def estimate_illumination(sample: PatchSample, spec: CardSpec = CARD_V1) -> tuple[np.ndarray, float]:
    """Fit a smooth multiplicative illumination surface from the grey ladder.

    Only the neutrals are used. They are the one set of patches whose *relative*
    reflectance survives a print batch, and restricting the fit to them is what
    keeps this step from quietly absorbing the device's colour response — which
    is the next step's job, and must stay separable from it.

    The surface is bi-quadratic in card coordinates and fitted in log space, so it
    is multiplicative: a shadow that halves the light over one corner is a
    constant offset in log space, not a shape the fit has to chase.

    Returns the per-channel coefficients and the residual, in stops, that remains
    after correction. A large residual means the light was not smooth — a hard
    shadow edge, a torch hotspot — and that goes in the record.
    """
    idx = np.array(spec.neutral_index)

    # A clipped patch has lost the very ratio this fit depends on: its observed
    # value is pinned at the sensor ceiling, not proportional to the light. Fitting
    # through it drags the whole surface. Drop them, and refuse to fit rather than
    # extrapolate if too few survive — a bi-quadratic needs six independent points.
    clean = idx[sample.saturated[idx] <= 0.02]
    if len(clean) >= 6:
        idx = clean

    xy = spec.patch_centres_px()[idx]
    w, h = spec.rectified_size
    A = _basis(xy, w, h)

    obs = np.clip(sample.raw_rgb[idx], 1e-6, None)
    expected = np.clip(srgb_to_linear(spec.patch_srgb[idx]), 1e-6, None)
    ratio = np.log(obs / expected)

    coeffs, *_ = np.linalg.lstsq(A, ratio, rcond=None)
    residual = float(np.sqrt(np.mean((ratio - A @ coeffs) ** 2)) / np.log(2))

    # Remove the surface's own mean over the card, so the correction is purely
    # *spatial*. The global term — overall exposure and the illuminant's colour
    # cast — is left alone deliberately: the device transform in L1's second half
    # is fitted against known reflectances and absorbs it properly, with all 24
    # patches constraining it instead of the 6 neutrals here. Measured on
    # synthetic frames, competing for that global term costs ~1.5 dE under a
    # coloured illuminant; conceding it costs nothing and still removes a shadow
    # gradient almost entirely.
    w, h = spec.rectified_size
    yy, xx = np.mgrid[0:h:32, 0:w:32]
    card_xy = np.stack([xx.ravel(), yy.ravel()], axis=1).astype(float)
    coeffs = coeffs.copy()
    coeffs[0] -= (_basis(card_xy, w, h) @ coeffs).mean(axis=0)
    return coeffs, residual


def substrate_residual(rectified_bgr: np.ndarray, gain: np.ndarray,
                       spec: CardSpec = CARD_V1) -> float:
    """How well the fitted light field explains the bare card, in stops.

    The eight neutral patches are enough to *fit* a smooth surface and far too few
    to *test* one: a shadow edge falling between them is invisible to the fit
    residual, and a synthetic hard shadow was accepted at 17 dE of error before
    this existed.

    The card substrate is uniform paper, so after dividing out the fitted gain
    every probe point should read the same value — the paper's reflectance. The
    spread of what remains is illumination the model failed to capture. A smooth
    gradient leaves almost nothing; a step leaves a bimodal residual and a large
    spread.
    """
    rgb = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    lin = srgb_to_linear(rgb)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])

    pts = spec.substrate_points_px()
    if len(pts) < 16:
        return 0.0
    xs = np.clip(pts[:, 0].astype(int), 0, lum.shape[1] - 1)
    ys = np.clip(pts[:, 1].astype(int), 0, lum.shape[0] - 1)

    # Small median patch per probe, so a dust speck does not become a finding.
    vals = []
    for x, y in zip(xs, ys):
        block = lum[max(0, y - 4):y + 5, max(0, x - 4):x + 5]
        vals.append(np.median(block) if block.size else 0.0)
    vals = np.asarray(vals)

    g = _gain_at(gain, np.stack([xs, ys], axis=1).astype(float), spec)
    gl = g @ np.array([0.2126, 0.7152, 0.0722])

    ratio = np.clip(vals, 1e-6, None) / np.clip(gl, 1e-6, None)
    logs = np.log2(ratio)
    # Robust spread: a few clipped or occluded probes must not dominate.
    return float((np.percentile(logs, 90) - np.percentile(logs, 10)) / 2.0)


# --------------------------------------------------------------------------- #
# quality
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class QualityGate:
    """Everything the record needs to say about how good the frame was."""

    markers_found: int
    reprojection_px: float
    tilt_degrees: float
    blur: float                       # normalised Laplacian variance; higher is sharper
    clipped_fraction: float
    dynamic_range: float
    illumination_residual_stops: float
    light_field_residual_stops: float
    patch_spread: float

    # Thresholds are policy, not physics. They live here so a change is one edit
    # and shows up in review, rather than being scattered through the pipeline.
    MIN_MARKERS = 4
    MAX_REPROJECTION_PX = 2.0
    MAX_TILT_DEG = 25.0
    MIN_BLUR = 0.010
    MAX_CLIPPED = 0.02
    MIN_DYNAMIC_RANGE = 0.35
    MAX_ILLUM_RESIDUAL = 0.35
    # Measured across 196 substrate probes, not 8 patches. On synthetic frames an
    # ideal capture leaves 0.04 and a legitimate soft shadow 0.06, while a hard
    # shadow edge leaves 0.36 and up. 0.12 sits in that gap.
    #
    # ⚠ This threshold is calibrated on SYNTHETIC frames. Real paper texture,
    # print non-uniformity and lens vignetting will all raise the floor. Re-derive
    # it from the physical capture set (docs/CAPTURE.md) before quoting any
    # rejection rate — a threshold tuned on simulations is a guess about reality.
    MAX_LIGHT_FIELD_RESIDUAL = 0.12
    # Within-patch spread, per channel, relative to patch brightness. Rises with
    # sensor noise, which corrupts colour without blurring the frame — so nothing
    # else in this gate notices it. Same synthetic-calibration caveat applies.
    MAX_PATCH_SPREAD = 0.30

    def failures(self) -> list[str]:
        f = []
        if self.markers_found < self.MIN_MARKERS:
            f.append(f"only {self.markers_found} of 4 fiducials resolved")
        if self.reprojection_px > self.MAX_REPROJECTION_PX:
            f.append(f"fiducial reprojection {self.reprojection_px:.2f} px "
                     f"exceeds {self.MAX_REPROJECTION_PX:.2f}")
        if self.tilt_degrees > self.MAX_TILT_DEG:
            f.append(f"card tilted {self.tilt_degrees:.0f}deg, limit {self.MAX_TILT_DEG:.0f}")
        if self.blur < self.MIN_BLUR:
            f.append(f"frame is soft (sharpness {self.blur:.4f} below {self.MIN_BLUR})")
        if self.clipped_fraction > self.MAX_CLIPPED:
            f.append(f"{self.clipped_fraction * 100:.1f}% of the card is clipped — "
                     "the brightest patches carry no information")
        if self.dynamic_range < self.MIN_DYNAMIC_RANGE:
            f.append(f"dynamic range {self.dynamic_range:.2f} below {self.MIN_DYNAMIC_RANGE}")
        if self.illumination_residual_stops > self.MAX_ILLUM_RESIDUAL:
            f.append(f"light is not smooth across the card "
                     f"({self.illumination_residual_stops:.2f} stops after correction)")
        if self.light_field_residual_stops > self.MAX_LIGHT_FIELD_RESIDUAL:
            f.append(f"a shadow or highlight edge crosses the card "
                     f"({self.light_field_residual_stops:.2f} stops unexplained)")
        if self.patch_spread > self.MAX_PATCH_SPREAD:
            f.append(f"patch colour is not uniform ({self.patch_spread:.3f}) — "
                     "heavy compression or sensor noise")
        return f

    @property
    def passed(self) -> bool:
        return not self.failures()

    def guidance(self) -> str:
        """One instruction for the operator: what to move, not what went wrong."""
        if self.markers_found < 4:
            return "Move back until all four corner markers are in frame."
        if self.tilt_degrees > self.MAX_TILT_DEG:
            return "Hold the phone flatter, parallel to the card."
        if self.clipped_fraction > self.MAX_CLIPPED:
            return "Too bright. Move out of direct light, or shade the card with your hand."
        if self.blur < self.MIN_BLUR:
            return "Hold steady, or move slightly further away to focus."
        if self.light_field_residual_stops > self.MAX_LIGHT_FIELD_RESIDUAL:
            return "A shadow edge crosses the card. Move so the light is even across all of it."
        if self.illumination_residual_stops > self.MAX_ILLUM_RESIDUAL:
            return "The light is uneven — move your shadow, or the reflection, off the card."
        if self.patch_spread > self.MAX_PATCH_SPREAD:
            return "The image is too grainy. Find more light and hold steady."
        if self.dynamic_range < self.MIN_DYNAMIC_RANGE:
            return "Find more light."
        return "Hold steady."


def grade_frame(rectified_bgr: np.ndarray, det: Detection, sample: PatchSample,
                illum_residual: float, spec: CardSpec = CARD_V1,
                gain: np.ndarray | None = None) -> QualityGate:
    grey = cv2.cvtColor(rectified_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
    lap = cv2.Laplacian(grey, cv2.CV_64F)
    # Normalised by contrast so a low-contrast-but-sharp frame is not called soft.
    blur = float(lap.var() / max(grey.var(), 1e-6))

    lum = sample.raw_rgb @ np.array([0.2126, 0.7152, 0.0722])
    field = 0.0 if gain is None else substrate_residual(rectified_bgr, gain, spec)
    # Relative, so a dark patch and a bright one are judged on the same scale.
    rel_spread = float(np.mean(sample.spread / np.clip(lum, 1e-3, None)))
    return QualityGate(
        markers_found=len(det.markers_found),
        reprojection_px=det.reprojection_px,
        tilt_degrees=det.tilt_degrees,
        blur=blur,
        clipped_fraction=float(sample.saturated.mean()),
        dynamic_range=float(lum.max() - lum.min()),
        illumination_residual_stops=illum_residual,
        light_field_residual_stops=field,
        patch_spread=rel_spread,
    )
