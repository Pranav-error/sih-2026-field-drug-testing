"""Two-view liveness — the defence against replay.

ARCHITECTURE.md §10 row 1 claimed replay was defeated because the card must be
co-planar and co-illuminated with the strip. Testing showed that reasoning is
wrong: a replay reproduces the whole scene, so co-planarity is *preserved*, and a
photo-lab print or a high-DPI screen passes the pipeline reading as an excellent
capture (docs/ROBUSTNESS.md §3).

What a reproduction cannot reproduce is **depth**.

The geometry is exact rather than heuristic. Two views of a plane are related by a
homography. Rectify both frames using the homography fitted to the card's four
corner fiducials — which lie on the card plane — and every point *on* that plane
lands in the same place in both. A point at height h above the plane does not: it
is displaced by

    displacement ≈ b · h / (D − h)          [millimetres on the card]

for camera baseline b and distance D. So residual displacement after rectification
*is* out-of-plane structure, and a flat reproduction yields exactly zero of it, for
every baseline, at every distance, forever. There is no print quality that fixes
that; it is a property of being flat.

The measured sensitivity, and the card change it forces, are in
docs/PARALLAX.md — the strip alone is too thin to rely on.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .card import PX_PER_MM, CARD_V1, CardSpec

__all__ = ["ParallaxResult", "measure_parallax", "check_liveness"]


@dataclass(frozen=True)
class ParallaxResult:
    """What two rectified views say about whether the scene has depth."""

    displacement_px: float          # median shift of the probe region
    displacement_mm: float
    implied_height_mm: float | None  # None when the geometry is unknown
    plane_residual_px: float        # how well the card itself re-aligned
    confidence: float               # 0..1, match quality of the probe region
    baseline_mm: float | None

    @property
    def flat(self) -> bool:
        """True when the scene is indistinguishable from a flat reproduction."""
        return self.displacement_px < 2.0

    def reason(self) -> str:
        if self.confidence < 0.35:
            return ("the two frames could not be matched — hold steadier, or move "
                    "less between them")
        if self.plane_residual_px > 3.0:
            return (f"the card did not re-align between frames "
                    f"({self.plane_residual_px:.1f} px) — it moved or bent")
        if self.flat:
            return (f"the scene is flat: {self.displacement_px:.1f} px of parallax "
                    "where a physical card gives many times that. This is consistent "
                    "with photographing a print or a screen")
        return (f"{self.displacement_px:.1f} px of parallax — the scene has depth "
                "and is not a flat reproduction")


def _rectify(image_bgr: np.ndarray, homography: np.ndarray, spec: CardSpec) -> np.ndarray:
    return cv2.warpPerspective(image_bgr, homography, spec.rectified_size,
                               flags=cv2.INTER_CUBIC)


def _probe_shift(a: np.ndarray, b: np.ndarray, centre_px: tuple[float, float],
                 radius_px: float) -> tuple[np.ndarray, float]:
    """Sub-pixel shift of a patch of `b` relative to `a`, by phase correlation.

    Phase correlation rather than feature matching: the probe region is small,
    low-texture and may be a uniform colour, which is exactly where feature
    detectors return nothing. Correlation needs no features, works to a fraction
    of a pixel, and returns its own confidence.
    """
    cx, cy = centre_px
    r = int(radius_px)
    x0, y0 = max(0, int(cx) - r), max(0, int(cy) - r)
    x1, y1 = min(a.shape[1], int(cx) + r), min(a.shape[0], int(cy) + r)
    if x1 - x0 < 16 or y1 - y0 < 16:
        return np.zeros(2), 0.0

    pa = cv2.cvtColor(a[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float64)
    pb = cv2.cvtColor(b[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float64)
    if pa.std() < 1.0 or pb.std() < 1.0:
        return np.zeros(2), 0.0

    win = cv2.createHanningWindow((pa.shape[1], pa.shape[0]), cv2.CV_64F)
    (dx, dy), response = cv2.phaseCorrelate(pa, pb, win)
    return np.array([dx, dy]), float(response)


def measure_parallax(frame_a: np.ndarray, frame_b: np.ndarray,
                     det_a, det_b, probe_centre_mm: tuple[float, float],
                     probe_radius_mm: float = 9.0,
                     baseline_mm: float | None = None,
                     distance_mm: float | None = None,
                     spec: CardSpec = CARD_V1) -> ParallaxResult:
    """Compare two views rectified onto the card plane.

    ``det_a`` and ``det_b`` are the Detections for each frame, so the caller has
    already established that the card was found in both.
    """
    ra = _rectify(frame_a, det_a.homography, spec)
    rb = _rectify(frame_b, det_b.homography, spec)

    # How well the card itself re-aligned. Any real displacement here means the
    # card moved, bent, or was mis-detected — and the probe reading is then
    # measuring that instead of depth.
    plane_shifts = []
    for cx, cy in spec.patch_centres_px():
        shift, resp = _probe_shift(ra, rb, (cx, cy), spec.patch_size_mm * PX_PER_MM * 0.45)
        if resp > 0.25:
            plane_shifts.append(np.linalg.norm(shift))
    plane_residual = float(np.median(plane_shifts)) if plane_shifts else 0.0

    probe_px = (probe_centre_mm[0] * PX_PER_MM, probe_centre_mm[1] * PX_PER_MM)
    shift, confidence = _probe_shift(ra, rb, probe_px, probe_radius_mm * PX_PER_MM)

    # The probe's motion relative to the plane, not relative to the sensor.
    relative = np.linalg.norm(shift) - plane_residual
    displacement_px = float(max(relative, 0.0))
    displacement_mm = displacement_px / PX_PER_MM

    implied_height = None
    if baseline_mm and distance_mm and baseline_mm > 1e-6:
        # invert d = b*h/(D-h)
        implied_height = float(displacement_mm * distance_mm /
                               (baseline_mm + displacement_mm))

    return ParallaxResult(
        displacement_px=displacement_px,
        displacement_mm=displacement_mm,
        implied_height_mm=implied_height,
        plane_residual_px=plane_residual,
        confidence=confidence,
        baseline_mm=baseline_mm,
    )


def check_liveness(result: ParallaxResult, expected_height_mm: float,
                   baseline_mm: float, distance_mm: float,
                   tolerance: float = 0.4) -> tuple[bool, str]:
    """Does the measured parallax match a known raised feature of known height?

    Stricter than "is it non-zero", and deliberately so. A raised feature of a
    *known* height predicts a *specific* displacement, so an attacker must not
    only introduce depth but introduce the right amount of it. Too little is a
    flat reproduction; far too much is a different object, or the card moved.

    Returns (live, explanation). The explanation is written to be read by someone
    who does not trust us.
    """
    expected_mm = baseline_mm * expected_height_mm / max(distance_mm - expected_height_mm, 1e-6)
    expected_px = expected_mm * PX_PER_MM

    if result.confidence < 0.35:
        return False, ("Not established: the two frames could not be matched well "
                       "enough to measure parallax.")
    if result.plane_residual_px > 3.0:
        return False, (f"Not established: the card did not re-align between the two "
                       f"frames ({result.plane_residual_px:.1f} px). It moved or bent.")

    lo, hi = expected_px * (1 - tolerance), expected_px * (1 + tolerance * 2.5)
    if result.displacement_px < lo:
        return False, (
            f"FLAT. Measured {result.displacement_px:.1f} px of parallax where a "
            f"physical card predicts {expected_px:.1f} px. A print or a screen gives "
            "zero, at any print quality, because it is flat.")
    if result.displacement_px > hi:
        return False, (
            f"Inconsistent: {result.displacement_px:.1f} px against a predicted "
            f"{expected_px:.1f} px. The geometry does not describe this card.")
    return True, (
        f"Depth confirmed: {result.displacement_px:.1f} px of parallax against a "
        f"predicted {expected_px:.1f} px for a {expected_height_mm:.0f} mm feature "
        f"at {distance_mm:.0f} mm over a {baseline_mm:.0f} mm baseline.")
