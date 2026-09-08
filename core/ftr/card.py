"""The reference card — geometry, nominal colours, and what they are worth.

The card is the only physical artefact in the system and it does three jobs at
once:

  1. **Fiducials** give a homography, so patches are sampled at known coordinates
     instead of being hunted for by segmentation.
  2. **Colour patches** of known reflectance let the device transform be solved
     in the same frame, under the same light, as the measurement itself.
  3. **Being co-planar with the strip** is what makes the illumination correction
     valid — and is simultaneously the defence against photographing a photograph.

Everything is specified in millimetres on the printed card. The rectified image
is a fixed pixel grid over those millimetres, so a patch centre is a constant, not
a search result.

Nominal patch colours below are the values the card is *printed to*. They are not
the values it *is*: offset printing, paper stock and ink batch all shift colour by
several dE. The authoritative reference for a print batch must come from a
spectrophotometer reading of that batch, keyed by ``print_batch`` in the record.
Until that measurement exists, every result carries the nominal-values caveat, and
the verifier says so rather than implying a precision the card does not have.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["CardSpec", "CARD_V1", "PX_PER_MM"]

# Rectified resolution. 10 px/mm puts ~90 px across a 9 mm patch, which leaves
# plenty after the trimmed mean discards edges, specular hits and dust.
PX_PER_MM = 10


@dataclass(frozen=True)
class CardSpec:
    """Printed geometry and nominal colorimetry for one card design."""

    card_id_prefix: str
    width_mm: float
    height_mm: float
    marker_dict: str
    marker_ids: tuple[int, int, int, int]      # TL, TR, BR, BL
    marker_size_mm: float
    marker_origins_mm: tuple[tuple[float, float], ...]
    patch_size_mm: float
    patch_centres_mm: np.ndarray               # (N, 2)
    patch_srgb: np.ndarray                     # (N, 3) in [0, 1], nominal
    neutral_index: tuple[int, ...]             # which patches are the grey ladder
    well_centre_mm: tuple[float, float]
    well_radius_mm: float

    # The liveness tab: a flap on the same printed sheet, scored and folded so it
    # stands a known height above the card plane. It is the only thing on the card
    # that a photograph of the card cannot reproduce, because a photograph is flat.
    # See docs/PARALLAX.md.
    tab_height_mm: float = 0.0
    tab_marker_id: int = 7
    tab_quad_mm: tuple[tuple[float, float], ...] = ()

    # -- derived geometry --------------------------------------------------- #

    @property
    def rectified_size(self) -> tuple[int, int]:
        return (int(self.width_mm * PX_PER_MM), int(self.height_mm * PX_PER_MM))

    @property
    def marker_corners_mm(self) -> np.ndarray:
        """Outer corner of each marker, in the order the detector reports them.

        ArUco gives corners clockwise from the marker's own top-left. We take the
        one outer corner per marker that lies at the card's extremity, which is
        what makes the four points a well-conditioned quad spanning the card.
        """
        s = self.marker_size_mm
        (tlx, tly), (trx, try_), (brx, bry), (blx, bly) = self.marker_origins_mm
        return np.array([
            [tlx, tly],                 # top-left marker, its top-left corner
            [trx + s, try_],            # top-right marker, its top-right corner
            [brx + s, bry + s],         # bottom-right marker, bottom-right corner
            [blx, bly + s],             # bottom-left marker, bottom-left corner
        ], dtype=np.float32)

    def patch_centres_px(self) -> np.ndarray:
        return self.patch_centres_mm * PX_PER_MM

    def substrate_points_mm(self, pitch: float = 4.0, margin: float = 2.5) -> np.ndarray:
        """Bare-paper probe points: a dense grid avoiding every printed element.

        The substrate has uniform reflectance by construction, so ANY structure
        measured across it is illumination and nothing else. That makes it a far
        better probe of the light field than the eight neutral patches, which are
        too few and too far apart to notice a shadow edge falling between them.
        """
        pts = []
        half = self.patch_size_mm / 2 + 1.0
        wx, wy = self.well_centre_mm
        s = self.marker_size_mm
        x = margin
        while x <= self.width_mm - margin:
            y = margin
            while y <= self.height_mm - margin:
                ok = True
                for px_, py_ in self.patch_centres_mm:
                    if abs(x - px_) < half and abs(y - py_) < half:
                        ok = False
                        break
                if ok:
                    for ox, oy in self.marker_origins_mm:
                        if ox - 1.5 <= x <= ox + s + 1.5 and oy - 1.5 <= y <= oy + s + 1.5:
                            ok = False
                            break
                if ok and (x - wx) ** 2 + (y - wy) ** 2 < (self.well_radius_mm + 2.0) ** 2:
                    ok = False
                if ok:
                    pts.append((x, y))
                y += pitch
            x += pitch
        return np.array(pts, dtype=float)

    def substrate_points_px(self, **kw) -> np.ndarray:
        return self.substrate_points_mm(**kw) * PX_PER_MM

    def well_centre_px(self) -> tuple[float, float]:
        return (self.well_centre_mm[0] * PX_PER_MM, self.well_centre_mm[1] * PX_PER_MM)

    @property
    def n_patches(self) -> int:
        return len(self.patch_centres_mm)


def _grid(x0: float, y0: float, cols: int, rows: int, pitch: float) -> list[tuple[float, float]]:
    return [(x0 + c * pitch, y0 + r * pitch) for r in range(rows) for c in range(cols)]


# --------------------------------------------------------------------------- #
# CARD-IN-2026 revision 1
# --------------------------------------------------------------------------- #
# 100 x 80 mm, A4-printable four to a sheet, matte stock. Markers are 14 mm at
# the corners; 18 colour patches sit in the upper field and 6 neutrals form a
# grey ladder below them. The strip's reaction region sits in the well at the
# bottom centre, inside the marker quad so it shares the card's illumination.

_MARKER_ORIGINS = ((3.0, 3.0), (83.0, 3.0), (83.0, 63.0), (3.0, 63.0))

# Colour patches: 5 x 3 in the middle field.
_COLOUR_CENTRES = _grid(x0=26.0, y0=22.0, cols=5, rows=3, pitch=10.0)

# Neutrals ring the colour field at THREE distinct rows and FIVE distinct columns.
# This is not decoration. The illumination surface is bi-quadratic in (x, y) and is
# fitted from the neutrals alone; putting them all on one row leaves every y term
# unconstrained, so the fit cannot see a shadow or a torch hotspot above or below
# that line. Synthetic capture caught exactly that: a specular hotspot sitting off
# the neutral row passed the quality gate while carrying a 52 dE error.
_NEUTRAL_CENTRES = [
    (26.0, 10.0), (50.0, 10.0), (74.0, 10.0),      # top
    (8.0, 34.0),                (92.0, 34.0),      # flanks, mid-height
    (26.0, 56.0), (50.0, 56.0), (74.0, 56.0),      # bottom
]

# Nominal sRGB. The colour patches span the region reagent reactions occupy —
# purples, browns, blue-blacks, oranges — rather than a general-purpose chart,
# because transform accuracy matters most where the decision boundary sits.
_COLOUR_SRGB = [
    (0.42, 0.19, 0.38), (0.24, 0.14, 0.31), (0.16, 0.10, 0.17), (0.55, 0.30, 0.20), (0.36, 0.20, 0.13),
    (0.20, 0.13, 0.10), (0.13, 0.16, 0.30), (0.10, 0.11, 0.19), (0.08, 0.08, 0.11), (0.79, 0.64, 0.16),
    (0.62, 0.41, 0.12), (0.17, 0.43, 0.36), (0.12, 0.29, 0.25), (0.70, 0.24, 0.28), (0.44, 0.15, 0.19),
]
# Grey ladder. These carry the illumination surface: they are the only patches
# whose *relative* reflectance can be trusted across a print batch.
_NEUTRAL_SRGB = [
    (0.09, 0.09, 0.09), (0.30, 0.30, 0.30), (0.52, 0.52, 0.52),
    (0.20, 0.20, 0.20),                     (0.66, 0.66, 0.66),
    (0.40, 0.40, 0.40), (0.78, 0.78, 0.78), (0.91, 0.91, 0.91),
]

CARD_V1 = CardSpec(
    card_id_prefix="CARD-IN-2026",
    width_mm=100.0,
    height_mm=80.0,
    marker_dict="DICT_4X4_50",
    marker_ids=(0, 1, 2, 3),
    marker_size_mm=14.0,
    marker_origins_mm=_MARKER_ORIGINS,
    patch_size_mm=9.0,
    patch_centres_mm=np.array(_COLOUR_CENTRES + _NEUTRAL_CENTRES, dtype=float),
    patch_srgb=np.array(_COLOUR_SRGB + _NEUTRAL_SRGB, dtype=float),
    neutral_index=tuple(range(len(_COLOUR_SRGB), len(_COLOUR_SRGB) + len(_NEUTRAL_SRGB))),
    well_centre_mm=(50.0, 70.0),
    well_radius_mm=8.0,
    # Folds up from the bottom edge and back over the card: an 8 mm riser, then a
    # 14 mm tab lying parallel to the card. Two score lines, no glue, no die-cut.
    # It occupies the clear strip between the bottom-left fiducial (ends x=17) and
    # the reaction well (starts x=42), so it obscures nothing that is measured.
    tab_height_mm=8.0,
    tab_marker_id=7,
    tab_quad_mm=((21.0, 66.0), (40.0, 66.0), (40.0, 80.0), (21.0, 80.0)),
)


def tab_centre_mm(spec: CardSpec) -> tuple[float, float]:
    q = np.array(spec.tab_quad_mm, dtype=float)
    return (float(q[:, 0].mean()), float(q[:, 1].mean()))
