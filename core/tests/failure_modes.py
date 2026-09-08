"""Degradations the first synthetic camera did not model.

`synth.py` covers the capture matrix from ARCHITECTURE.md §7.2 — illuminant,
exposure, angle, focus, noise, JPEG. Those are the conditions an *honest* officer
produces. This module covers the rest of reality:

  * a card that is not flat, which breaks the planarity the homography assumes
  * a finger over a fiducial
  * a hard shadow edge, which is not the smooth surface INUC fits
  * two light sources of different colour in one frame
  * directional motion blur, not the isotropic kind
  * distance, and therefore resolution
  * **replay**: photographing a print or a screen showing a card and a strip

The last one is the point. §10 row 1 claims replay is "defeated by" the card being
co-planar and co-illuminated with the strip. That claim has never been tested, and
testing it is the whole reason this file exists.
"""

from __future__ import annotations

import cv2
import numpy as np

from ftr.card import PX_PER_MM, CARD_V1, CardSpec
from ftr.colorimetry import srgb_to_linear

from synth import ILLUMINANTS, _linear_to_srgb, photograph, render_card


# --------------------------------------------------------------------------- #
# geometry the homography cannot represent
# --------------------------------------------------------------------------- #

def crease(card_bgr: np.ndarray, depth: float = 0.5, position: float = 0.5,
           axis: str = "v") -> np.ndarray:
    """Fold the card along a line, so it is no longer planar.

    A homography maps one *plane* to another. A creased card is two planes, so no
    single homography fits it: patches on the far side of the fold land in the
    wrong place, and the fiducial reprojection residual is the only thing that can
    notice. Cards in a pocket get creased, so this is a routine condition rather
    than an exotic one.
    """
    h, w = card_bgr.shape[:2]
    out = np.zeros_like(card_bgr)
    if axis == "v":
        fold = int(w * position)
        for x in range(w):
            # perspective foreshortening away from the fold line
            d = abs(x - fold) / max(fold, w - fold)
            squeeze = 1.0 - depth * d
            src_y = (np.arange(h) - h / 2) / max(squeeze, 1e-3) + h / 2
            src_y = np.clip(src_y, 0, h - 1).astype(np.int32)
            out[:, x] = card_bgr[src_y, x]
    else:
        fold = int(h * position)
        for y in range(h):
            d = abs(y - fold) / max(fold, h - fold)
            squeeze = 1.0 - depth * d
            src_x = (np.arange(w) - w / 2) / max(squeeze, 1e-3) + w / 2
            src_x = np.clip(src_x, 0, w - 1).astype(np.int32)
            out[y] = card_bgr[y, src_x]
    return out


def occlude_fiducial(scene_bgr: np.ndarray, which: int = 0, coverage: float = 0.6,
                     spec: CardSpec = CARD_V1) -> np.ndarray:
    """Put a thumb over one corner marker."""
    out = scene_bgr.copy()
    h, w = out.shape[:2]
    ox, oy = spec.marker_origins_mm[which]
    s = spec.marker_size_mm
    # card occupies the middle of the scene; synth pads by `margin`
    pad_x = int(w * 0.35 / 1.7)
    pad_y = int(h * 0.35 / 1.7)
    scale = (w - 2 * pad_x) / (spec.width_mm * PX_PER_MM)
    x0 = int(pad_x + ox * PX_PER_MM * scale)
    y0 = int(pad_y + oy * PX_PER_MM * scale)
    side = int(s * PX_PER_MM * scale * coverage)
    cv2.rectangle(out, (x0, y0), (x0 + side, y0 + side), (58, 62, 96), -1)
    return out


def hard_shadow(card_bgr: np.ndarray, position: float = 0.45, depth: float = 0.55,
                softness: float = 0.02) -> np.ndarray:
    """A shadow with an edge, not a gradient.

    INUC fits a bi-quadratic surface. A step is not bi-quadratic, so the fit
    cannot remove it — the residual should rise and the gate should refuse. If it
    does not, a doorway or a vehicle edge across the card produces a silently
    wrong measurement.
    """
    h, w = card_bgr.shape[:2]
    lin = srgb_to_linear(card_bgr.astype(np.float64)[..., ::-1] / 255.0)
    xx = np.arange(w)[None, :] / w
    edge = 1.0 / (1.0 + np.exp(-(xx - position) / max(softness, 1e-4)))
    mask = 1.0 - depth * (1.0 - edge)
    lin = lin * np.repeat(mask, h, axis=0)[..., None]
    return (_linear_to_srgb(lin)[..., ::-1] * 255).astype(np.uint8)


def mixed_illuminants(card_bgr: np.ndarray, left: str = "tungsten",
                      right: str = "shade", blend: float = 0.25) -> np.ndarray:
    """Two light sources of different colour across one card.

    A single global white balance cannot be right for both halves, and the device
    transform solves for one. Standing in a doorway at dusk with the interior
    lights on is exactly this.
    """
    h, w = card_bgr.shape[:2]
    lin = srgb_to_linear(card_bgr.astype(np.float64)[..., ::-1] / 255.0)
    t = np.clip((np.arange(w) / w - 0.5) / max(blend, 1e-3) + 0.5, 0, 1)[None, :, None]
    gain = ILLUMINANTS[left][None, None, :] * (1 - t) + ILLUMINANTS[right][None, None, :] * t
    lin = lin * gain
    return (_linear_to_srgb(lin)[..., ::-1] * 255).astype(np.uint8)


def motion_blur(scene_bgr: np.ndarray, length: int = 15, angle_deg: float = 20) -> np.ndarray:
    """Directional blur from a moving hand — not the isotropic kind."""
    k = np.zeros((length, length), dtype=np.float64)
    k[length // 2, :] = 1.0
    m = cv2.getRotationMatrix2D((length / 2 - 0.5, length / 2 - 0.5), angle_deg, 1.0)
    k = cv2.warpAffine(k, m, (length, length))
    k /= max(k.sum(), 1e-9)
    return cv2.filter2D(scene_bgr, -1, k)


def at_distance(scene_bgr: np.ndarray, factor: float = 0.35) -> np.ndarray:
    """Photograph from further away: fewer pixels on the card, then upsampled.

    Fiducial detection has a floor in pixels per marker. Finding it matters,
    because "stand back so the whole card is in frame" is the first thing the
    guidance tells an officer to do.
    """
    h, w = scene_bgr.shape[:2]
    small = cv2.resize(scene_bgr, (max(int(w * factor), 8), max(int(h * factor), 8)),
                       interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


# --------------------------------------------------------------------------- #
# replay — the attack §10 row 1 claims is defeated
# --------------------------------------------------------------------------- #

def as_print(scene_bgr: np.ndarray, dot_gain: float = 0.06,
             gamut: float = 0.88, blur_px: float = 1.4) -> np.ndarray:
    """Simulate printing a photograph, before it is re-photographed.

    Three effects a printer reliably imposes: ink spread darkens midtones (dot
    gain), the printable gamut is smaller than the display gamut, and the print
    is softer than the original.
    """
    lin = srgb_to_linear(scene_bgr.astype(np.float64)[..., ::-1] / 255.0)
    grey = lin.mean(axis=2, keepdims=True)
    lin = grey + (lin - grey) * gamut          # desaturate toward the print gamut
    lin = np.clip(lin - dot_gain * lin * (1 - lin) * 4, 0, 1)   # dot gain
    out = (_linear_to_srgb(lin)[..., ::-1] * 255).astype(np.uint8)
    return cv2.GaussianBlur(out, (0, 0), blur_px)


def as_screen(scene_bgr: np.ndarray, pitch: int = 3, strength: float = 0.20) -> np.ndarray:
    """Simulate an LCD showing the photograph: RGB subpixel stripes and scanlines.

    Re-photographing a screen is the cheapest replay attack. Whether it survives
    the pipeline is an empirical question, and this is how it gets asked.
    """
    out = scene_bgr.astype(np.float64)
    h, w = out.shape[:2]
    cols = np.arange(w)
    for c in range(3):
        stripe = ((cols % pitch) == c).astype(np.float64)
        out[..., c] *= (1 - strength) + strength * pitch * stripe[None, :]
    rows = np.arange(h)
    out *= (1 - strength * 0.4 * ((rows % 2)[:, None, None]))
    return np.clip(out, 0, 255).astype(np.uint8)


def replay(card_bgr: np.ndarray, medium: str = "print", *, rng=None, **capture) -> np.ndarray:
    """Photograph a reproduction of a card-and-strip photograph.

    The whole scene — card, fiducials, reaction well — is reproduced together, so
    it stays co-planar and co-illuminated. That is precisely why the §10 row 1
    defence deserves testing rather than assertion.
    """
    original = photograph(card_bgr, rng=rng, illuminant="daylight")
    reproduced = as_print(original) if medium == "print" else as_screen(original)
    return photograph(reproduced, rng=rng, margin=0.12, **capture)
