"""A synthetic camera, so the pipeline can be tested without a printer.

This is a *test instrument*, not a data source. It cannot substitute for the
physical capture matrix in ARCHITECTURE.md §7: it reproduces the geometry and the
illumination physics, but it has no ink, no paper gloss, no real ISP, and no
reagent chemistry. It exists to prove the pipeline recovers a known answer from a
known degradation — nothing more.

Every knob corresponds to a row of the capture matrix: illuminant, exposure,
angle, shadow, glare, focus, sensor noise, JPEG.
"""

from __future__ import annotations

import cv2
import numpy as np

from ftr.card import PX_PER_MM, CARD_V1, CardSpec
from ftr.colorimetry import srgb_to_linear

# Illuminants as multiplicative RGB gains, relative to a neutral daylight frame.
#
# ⚠ A PER-CHANNEL GAIN CANNOT PRODUCE METAMERISM. Two surfaces that match under
# one of these "illuminants" match under all of them, because both are scaled
# identically. Real sensors and real light do not behave that way, and metamerism
# is the entire reason colour constancy is hard.
#
# So every CROSS-ILLUMINANT number measured with this module is measured on an
# easier problem than reality. Use it for geometry, exposure, focus, glare and
# noise — the things it models honestly. For anything about colour across
# illuminants, use ftr/spectral.py, which renders from measured reflectance,
# measured SPDs and measured camera sensitivities. See docs/ROBUSTNESS.md §6.
ILLUMINANTS = {
    "daylight":    np.array([1.00, 1.00, 1.00]),
    "shade":       np.array([0.88, 0.95, 1.18]),   # blue cast
    "tungsten":    np.array([1.28, 0.98, 0.66]),   # warm
    "fluorescent": np.array([1.05, 1.10, 0.88]),   # green cast
    "torch":       np.array([1.12, 1.06, 0.95]),   # phone LED, slightly warm
}


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def render_card(spec: CardSpec = CARD_V1, well_srgb=(0.28, 0.12, 0.22)) -> np.ndarray:
    """The card as printed, flat-on, perfectly lit. Returns BGR uint8."""
    w, h = spec.rectified_size
    img = np.full((h, w, 3), 0.93, dtype=np.float64)          # matte paper white

    half = int(spec.patch_size_mm * PX_PER_MM / 2)
    for (cx, cy), srgb in zip(spec.patch_centres_px(), spec.patch_srgb):
        x, y = int(round(cx)), int(round(cy))
        img[y - half:y + half, x - half:x + half] = srgb[::-1]   # to BGR

    wx, wy = spec.well_centre_px()
    cv2.circle(img, (int(wx), int(wy)), int(spec.well_radius_mm * PX_PER_MM),
               tuple(float(c) for c in np.array(well_srgb)[::-1]), -1)

    dct = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec.marker_dict))
    side = int(spec.marker_size_mm * PX_PER_MM)
    for mid, (ox, oy) in zip(spec.marker_ids, spec.marker_origins_mm):
        m = cv2.aruco.generateImageMarker(dct, mid, side)
        x, y = int(ox * PX_PER_MM), int(oy * PX_PER_MM)
        img[y:y + side, x:x + side] = (m[..., None] / 255.0).repeat(3, axis=2)

    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def photograph(
    card_bgr: np.ndarray,
    *,
    illuminant: str = "daylight",
    exposure: float = 1.0,
    tilt: float = 0.0,          # degrees of perspective, roughly
    rotation: float = 0.0,      # in-plane, degrees
    shadow: float = 0.0,        # 0..1, a soft gradient across the card
    glare: float = 0.0,         # 0..1, a specular hotspot
    blur_px: float = 0.0,
    noise: float = 0.0,         # sensor noise sigma, in 8-bit levels
    jpeg_quality: int | None = None,
    margin: float = 0.35,       # empty scene around the card
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Photograph a rendered card under stated conditions. Returns BGR uint8.

    The illumination model is deliberately physical: gains are applied in *linear*
    light, before the sRGB transfer function, because that is where a shadow
    actually acts. Applying them to 8-bit values would produce a degradation the
    correction step could not legitimately undo, and the test would be measuring
    the wrong thing.
    """
    rng = rng or np.random.default_rng(0)
    h, w = card_bgr.shape[:2]

    lin = srgb_to_linear(card_bgr.astype(np.float64)[..., ::-1] / 255.0)   # to linear RGB

    gain = ILLUMINANTS[illuminant] * exposure
    lin = lin * gain

    if shadow > 0:
        yy, xx = np.mgrid[0:h, 0:w]
        ramp = (xx / w) * 0.65 + (yy / h) * 0.35
        lin = lin * (1.0 - shadow * ramp)[..., None]

    if glare > 0:
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy, r = w * 0.30, h * 0.28, min(w, h) * 0.16
        hot = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r ** 2)))
        lin = lin + glare * hot[..., None] * 1.6

    img = (_linear_to_srgb(lin)[..., ::-1] * 255.0)                       # back to BGR

    # geometry: place the card in a larger scene, then warp
    pad_x, pad_y = int(w * margin), int(h * margin)
    scene = np.full((h + 2 * pad_y, w + 2 * pad_x, 3), 28.0)
    scene[pad_y:pad_y + h, pad_x:pad_x + w] = img
    H, W = scene.shape[:2]

    src = np.float32([[pad_x, pad_y], [pad_x + w, pad_y],
                      [pad_x + w, pad_y + h], [pad_x, pad_y + h]])
    t = np.tan(np.radians(tilt))
    dx, dy = t * w * 0.42, t * h * 0.18
    dst = np.float32([[pad_x + dx, pad_y + dy], [pad_x + w, pad_y],
                      [pad_x + w - dx * 0.5, pad_y + h - dy * 0.6], [pad_x, pad_y + h]])
    if rotation:
        c, s = np.cos(np.radians(rotation)), np.sin(np.radians(rotation))
        R = np.array([[c, -s], [s, c]])
        centre = dst.mean(axis=0)
        dst = ((dst - centre) @ R.T + centre).astype(np.float32)

    M = cv2.getPerspectiveTransform(src, dst)
    scene = cv2.warpPerspective(scene, M, (W, H), flags=cv2.INTER_CUBIC,
                                borderValue=(28, 28, 28))

    if blur_px > 0:
        k = int(blur_px) * 2 + 1
        scene = cv2.GaussianBlur(scene, (k, k), blur_px)
    if noise > 0:
        scene = scene + rng.normal(0, noise, scene.shape)

    out = np.clip(scene, 0, 255).astype(np.uint8)
    if jpeg_quality is not None:
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        assert ok
        out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out
