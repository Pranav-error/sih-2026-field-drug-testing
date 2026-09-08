"""A two-view camera with real depth, for testing the parallax defence.

`synth.py` warps a flat card by a homography, which is fine for everything except
the one question that matters here: it has no notion of height, so it cannot
produce parallax and cannot distinguish a physical scene from a reproduction of
one.

This module places the card in a world at Z = 0, optionally puts a raised element
at Z = h, and projects both through a pinhole camera at a chosen position. Two
calls with different camera positions give two views with correct parallax —
which is what makes the test meaningful rather than circular. Nothing here fakes
a displacement; it falls out of the projection.

A **replay** is modelled honestly: render one view, then treat that image as a
flat printed surface at Z = 0 and photograph *it* from two positions. Everything
in a reproduction is coplanar by construction, so the parallax is exactly zero —
not approximately, exactly.
"""

from __future__ import annotations

import cv2
import numpy as np

from ftr.card import PX_PER_MM, CARD_V1, CardSpec

from synth import render_card


def project(points_mm_z: np.ndarray, camera_xy: tuple[float, float],
            distance_mm: float, focal_px: float,
            image_size: tuple[int, int]) -> np.ndarray:
    """Pinhole projection of world points onto a downward-looking sensor.

    ``points_mm_z`` is (N, 3): millimetres on the card plane, plus height.
    """
    cx, cy = camera_xy
    w, h = image_size
    p = np.asarray(points_mm_z, dtype=float)
    depth = distance_mm - p[:, 2]
    if np.any(depth <= 1.0):
        raise ValueError("a point is at or behind the camera")
    x = focal_px * (p[:, 0] - cx) / depth + w / 2
    y = focal_px * (p[:, 1] - cy) / depth + h / 2
    return np.stack([x, y], axis=1).astype(np.float32)


def _paste(scene: np.ndarray, texture: np.ndarray, quad_img: np.ndarray) -> None:
    """Warp `texture` into the quadrilateral `quad_img` and composite it in."""
    th, tw = texture.shape[:2]
    src = np.float32([[0, 0], [tw, 0], [tw, th], [0, th]])
    M = cv2.getPerspectiveTransform(src, quad_img.astype(np.float32))
    warped = cv2.warpPerspective(texture, M, (scene.shape[1], scene.shape[0]),
                                 flags=cv2.INTER_CUBIC)
    mask = cv2.warpPerspective(np.full((th, tw), 255, np.uint8), M,
                               (scene.shape[1], scene.shape[0]), flags=cv2.INTER_NEAREST)
    scene[mask > 127] = warped[mask > 127]


def view(card_bgr: np.ndarray, camera_xy=(50.0, 40.0), distance_mm=150.0,
         focal_px=1400.0, image_size=(1400, 1050),
         raised: tuple[np.ndarray, float, np.ndarray] | None = None,
         spec: CardSpec = CARD_V1, rng=None, noise: float = 1.2) -> np.ndarray:
    """One photograph of a physical card, optionally with a raised element.

    ``raised`` is (texture, height_mm, corners_mm) — a flat patch standing at a
    constant height above the card plane.
    """
    rng = rng or np.random.default_rng(0)
    scene = np.full((image_size[1], image_size[0], 3), 34, np.uint8)

    corners = np.array([[0, 0, 0], [spec.width_mm, 0, 0],
                        [spec.width_mm, spec.height_mm, 0], [0, spec.height_mm, 0]])
    _paste(scene, card_bgr, project(corners, camera_xy, distance_mm, focal_px, image_size))

    if raised is not None:
        texture, h, quad_mm = raised
        pts = np.column_stack([quad_mm, np.full(len(quad_mm), float(h))])
        _paste(scene, texture, project(pts, camera_xy, distance_mm, focal_px, image_size))

    if noise:
        scene = np.clip(scene + rng.normal(0, noise, scene.shape), 0, 255).astype(np.uint8)
    return scene


def stereo_pair(card_bgr: np.ndarray, baseline_mm: float = 50.0,
                distance_mm: float = 150.0, **kw) -> tuple[np.ndarray, np.ndarray]:
    """Two views of a physical scene, separated by `baseline_mm`."""
    a = view(card_bgr, camera_xy=(50.0 - baseline_mm / 2, 40.0),
             distance_mm=distance_mm, **kw)
    b = view(card_bgr, camera_xy=(50.0 + baseline_mm / 2, 40.0),
             distance_mm=distance_mm, **kw)
    return a, b


def replay_pair(card_bgr: np.ndarray, baseline_mm: float = 50.0,
                distance_mm: float = 150.0, medium: str = "print",
                raised=None, spec: CardSpec = CARD_V1,
                **kw) -> tuple[np.ndarray, np.ndarray]:
    """Two views of a REPRODUCTION of the scene.

    The attacker photographs the real thing once — including any raised feature,
    which appears correctly in that single image — then prints or displays it and
    photographs the reproduction twice. The reproduction is one flat surface, so
    the raised feature's *depth* is gone even though its *appearance* survives.
    """
    import failure_modes as fm
    from ftr.detect import detect_card, rectify

    # The raised feature is applied ONLY to the original capture. It appears in the
    # attacker's photograph, correctly, from that one angle — and then it is
    # printed onto a sheet and its depth is gone. Passing `raised` through to the
    # reproduction views would stand a real tab on top of the print, which is not
    # a replay: it is a print with a physical tab, and it should pass.
    single = view(card_bgr, camera_xy=(50.0, 40.0), distance_mm=distance_mm,
                  raised=raised, spec=spec, **kw)

    # A competent attacker prints the card at its true size, not a snapshot of a
    # scene. Rectifying the capture is exactly that: a flat sheet carrying the
    # card, including whatever the raised feature looked like from that one angle.
    det = detect_card(single, spec)
    if det is None or not det.complete:
        raise RuntimeError("the frame being reproduced does not itself contain a card")
    sheet = rectify(single, det, spec)
    reproduced = fm.as_print(sheet) if medium == "print" else fm.as_screen(sheet)

    # The reproduction is now the flat "card": a printed sheet on a table. Nothing
    # on it stands proud of anything else, because it is a sheet. No `raised`.
    return stereo_pair(reproduced, baseline_mm=baseline_mm, distance_mm=distance_mm,
                       spec=spec, **kw)


def tab_texture(width_mm: float = 26.0, height_mm: float = 14.0,
                marker_id: int = 7, spec: CardSpec = CARD_V1) -> np.ndarray:
    """A fold-up tab carrying its own fiducial, printed on the same sheet."""
    w, h = int(width_mm * PX_PER_MM), int(height_mm * PX_PER_MM)
    img = np.full((h, w, 3), 244, np.uint8)
    dct = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec.marker_dict))
    side = int(min(w, h) * 0.78)
    m = cv2.aruco.generateImageMarker(dct, marker_id, side)
    y0, x0 = (h - side) // 2, (w - side) // 2
    img[y0:y0 + side, x0:x0 + side] = m[..., None].repeat(3, axis=2)
    return img
