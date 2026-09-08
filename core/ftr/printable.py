"""Generate a print-ready reference card.

This is the one physical artefact in the system, and it is the thing standing
between the project and its critical path: no printed cards means no capture
matrix, and no capture matrix means no calibration, no held-out illuminant, and
no accuracy claim worth stating.

    python -m ftr.printable --out card.png --dpi 600 --serial 0417

Print matte, not gloss. Gloss puts a specular highlight on the patches, which is
the one degradation the pipeline rejects outright rather than corrects. Do not
let a printer driver "enhance" the output: colour management, auto-contrast and
photo modes all move the patches away from the nominal values the transform is
solved against.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from .card import CARD_V1, CardSpec

__all__ = ["render_printable"]


def render_printable(spec: CardSpec = CARD_V1, dpi: int = 600, serial: str = "0000",
                     batch: str = "B00") -> np.ndarray:
    """Render the card at print resolution, with a quiet zone and its identity."""
    ppmm = dpi / 25.4
    quiet_mm = 5.0                      # white margin: ArUco needs one to detect
    tab_extent = 0.0
    if spec.tab_height_mm > 0:
        q = np.array(spec.tab_quad_mm, dtype=float)
        tab_extent = spec.tab_height_mm + float(q[:, 1].max() - q[:, 1].min()) + 8.0
    w = int(round((spec.width_mm + 2 * quiet_mm) * ppmm))
    h = int(round((spec.height_mm + tab_extent + 2 * quiet_mm) * ppmm))
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    off = quiet_mm * ppmm

    def px(mm_x, mm_y):
        return int(round(off + mm_x * ppmm)), int(round(off + mm_y * ppmm))

    # card body, very slightly off-white so the trim edge is visible when cut
    cv2.rectangle(img, px(0, 0), px(spec.width_mm, spec.height_mm), (247, 247, 247), -1)

    half = spec.patch_size_mm / 2
    for (cx, cy), srgb in zip(spec.patch_centres_mm, spec.patch_srgb):
        bgr = tuple(int(round(c * 255)) for c in srgb[::-1])
        cv2.rectangle(img, px(cx - half, cy - half), px(cx + half, cy + half), bgr, -1)

    # reaction well: an outline, not a fill. The strip sits here, and anything
    # printed under it would contaminate the sample the pipeline reads.
    wx, wy = spec.well_centre_mm
    cv2.circle(img, px(wx, wy), int(round(spec.well_radius_mm * ppmm)), (170, 170, 170),
               max(1, int(round(0.3 * ppmm))))
    cv2.circle(img, px(wx, wy), int(round((spec.well_radius_mm + 1.2) * ppmm)), (210, 210, 210),
               max(1, int(round(0.2 * ppmm))))

    dct = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, spec.marker_dict))
    side = int(round(spec.marker_size_mm * ppmm))
    for mid, (ox, oy) in zip(spec.marker_ids, spec.marker_origins_mm):
        m = cv2.aruco.generateImageMarker(dct, mid, side)
        x, y = px(ox, oy)
        img[y:y + side, x:x + side] = m[..., None].repeat(3, axis=2)

    card_id = f"{spec.card_id_prefix}-{serial}"
    scale = ppmm / 12.0
    cv2.putText(img, card_id, px(21, 68), cv2.FONT_HERSHEY_SIMPLEX, scale, (90, 90, 90),
                max(1, int(round(0.18 * ppmm))), cv2.LINE_AA)
    cv2.putText(img, f"batch {batch}  /  matte  /  no colour management",
                px(21, 74), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.62, (140, 140, 140),
                max(1, int(round(0.12 * ppmm))), cv2.LINE_AA)

    # The liveness flap, printed below the card and folded up and back over it.
    if spec.tab_height_mm > 0:
        q = np.array(spec.tab_quad_mm, dtype=float)
        tab_w = float(q[:, 0].max() - q[:, 0].min())
        tab_l = float(q[:, 1].max() - q[:, 1].min())
        x0 = float(q[:, 0].min())
        riser_y0 = spec.height_mm
        tab_y0 = riser_y0 + spec.tab_height_mm

        cv2.rectangle(img, px(x0, riser_y0), px(x0 + tab_w, tab_y0 + tab_l),
                      (250, 250, 250), -1)
        for y, label in ((riser_y0, "fold up"), (tab_y0, "fold over")):
            xa, ya = px(x0, y)
            xb, _ = px(x0 + tab_w, y)
            for x in range(xa, xb, int(2.0 * ppmm)):
                cv2.line(img, (x, ya), (min(x + int(1.1 * ppmm), xb), ya),
                         (150, 150, 150), max(1, int(0.25 * ppmm)))
            cv2.putText(img, label, px(x0 + tab_w + 1.5, y + 1.0),
                        cv2.FONT_HERSHEY_SIMPLEX, scale * 0.5, (150, 150, 150),
                        max(1, int(0.1 * ppmm)), cv2.LINE_AA)

        m = cv2.aruco.generateImageMarker(dct, spec.tab_marker_id,
                                          int(min(tab_w, tab_l) * 0.72 * ppmm))
        mh = m.shape[0]
        mx, my = px(x0 + tab_w / 2, tab_y0 + tab_l / 2)
        img[my - mh // 2:my - mh // 2 + mh, mx - mh // 2:mx - mh // 2 + mh] = \
            m[..., None].repeat(3, axis=2)
        cv2.putText(img, f"liveness tab - fold to {spec.tab_height_mm:.0f} mm",
                    px(x0, tab_y0 + tab_l + 3.5), cv2.FONT_HERSHEY_SIMPLEX,
                    scale * 0.55, (140, 140, 140), max(1, int(0.11 * ppmm)), cv2.LINE_AA)

    # trim marks at the card corners
    t = int(round(3 * ppmm))
    for mx, my in [(0, 0), (spec.width_mm, 0), (0, spec.height_mm), (spec.width_mm, spec.height_mm)]:
        x, y = px(mx, my)
        cv2.line(img, (x - t, y), (x + t, y), (150, 150, 150), 1, cv2.LINE_AA)
        cv2.line(img, (x, y - t), (x, y + t), (150, 150, 150), 1, cv2.LINE_AA)
    return img


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ftr-printable", description=__doc__)
    p.add_argument("--out", type=Path, default=Path("card.png"))
    p.add_argument("--dpi", type=int, default=600)
    p.add_argument("--serial", default="0000", help="per-card serial, printed on the card")
    p.add_argument("--batch", default="B00", help="print batch id — goes in every record")
    a = p.parse_args(argv)

    img = render_printable(dpi=a.dpi, serial=a.serial, batch=a.batch)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(a.out), img)
    h, w = img.shape[:2]
    print(f"{a.out}  {w}x{h}px at {a.dpi} dpi  "
          f"({w / a.dpi * 25.4:.0f} x {h / a.dpi * 25.4:.0f} mm including quiet zone)")
    print(f"card id {CARD_V1.card_id_prefix}-{a.serial}, batch {a.batch}")
    print("Print at 100% scale, matte stock, colour management OFF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
