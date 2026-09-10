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
import json
from pathlib import Path

import cv2
import numpy as np

from .card import CARD_V1, CardSpec
from .colorimetry import lab_to_srgb

__all__ = ["render_printable"]


SURROGATE_LOCI = Path(__file__).with_name("data") / "surrogate_loci.json"


def load_loci() -> dict[str, list[float]]:
    """The surrogate ladder, from the one file Python and Dart both read."""
    return json.loads(SURROGATE_LOCI.read_text())["loci_lab"]


def identity_band(spec: CardSpec = CARD_V1) -> tuple[float, float]:
    """The horizontal span, in mm, where the card id may be printed.

    Exposed rather than inlined because the first version of this calculation
    was duplicated into its own test, and the copy got it wrong in a way the
    original did not — which is the failure mode the whole one-source-of-truth
    rule exists to stop, reproduced inside the test meant to enforce it.
    """
    x0 = spec.well_centre_mm[0] + spec.well_radius_mm + 2.5
    # The first marker to the RIGHT of x0. Taking the minimum over all markers
    # picks the bottom-left one at x=3 and yields a negative width.
    rights = [ox for ox, _ in spec.marker_origins_mm if ox > x0]
    x1 = (min(rights) if rights else spec.width_mm) - 1.5
    return x0, x1


def render_printable(spec: CardSpec = CARD_V1, dpi: int = 600, serial: str = "0000",
                     batch: str = "B00", well_label: str | None = None) -> np.ndarray:
    """Render the card at print resolution, with a quiet zone and its identity.

    ``well_label`` fills the reaction well with a locus colour, producing a
    **demonstration card**: the pipeline reads a printed patch and reports the
    matching class, so a rehearsal can show a positive without reagents and
    without a controlled substance.

    Every such card is marked, twice. A demonstration card that could pass for
    an ordinary one is a route to a fabricated positive in a real record, so the
    well fill comes with a printed band naming the class, and the card id
    carries DEMO — which reaches the record, because the operator types it in.
    """
    ppmm = dpi / 25.4
    quiet_mm = 5.0                      # white margin: ArUco needs one to detect
    tab_extent = 0.0
    if spec.tab_height_mm > 0:
        q = np.array(spec.tab_quad_mm, dtype=float)
        tab_extent = spec.tab_height_mm + float(q[:, 1].max() - q[:, 1].min()) + 8.0
    # A demonstration card gets a banner strip ABOVE the quiet zone, never on
    # the card body. The first attempt printed the band across the card at
    # y=52..60mm, which covered 30 of the 196 substrate probe points and 3 of
    # the colour patches — the illumination fit and the device transform were
    # both solved against a red rectangle, and every filled card came back with
    # a Lab of about (337, -153, -6) and a failed gate. A demonstration card
    # must differ from an ordinary one in the well and nowhere else.
    banner_mm = 14.0 if well_label is not None else 0.0
    # A WHOLE number of pixels, and added to the offset already rounded. If the
    # strip were 14 mm of fractional pixels, every element on the card would
    # round to a different subpixel position than on a plain card, and the two
    # would differ by antialiasing everywhere — which is both an unprovable
    # claim ("the marking does not touch the measured surface") and a real risk,
    # because it hides an overlap in a haze of one-pixel noise. With an integer
    # offset the card body is bit-identical to a plain card except for the well,
    # and test_demo_cards.py asserts exactly that.
    banner_px = int(round(banner_mm * ppmm))

    w = int(round((spec.width_mm + 2 * quiet_mm) * ppmm))
    h = int(round((spec.height_mm + tab_extent + 2 * quiet_mm) * ppmm)) + banner_px
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    off_x = quiet_mm * ppmm
    off_y = quiet_mm * ppmm

    def px(mm_x, mm_y):
        return (int(round(off_x + mm_x * ppmm)),
                int(round(off_y + mm_y * ppmm)) + banner_px)

    # card body, very slightly off-white so the trim edge is visible when cut
    cv2.rectangle(img, px(0, 0), px(spec.width_mm, spec.height_mm), (247, 247, 247), -1)

    half = spec.patch_size_mm / 2
    for (cx, cy), srgb in zip(spec.patch_centres_mm, spec.patch_srgb):
        bgr = tuple(int(round(c * 255)) for c in srgb[::-1])
        cv2.rectangle(img, px(cx - half, cy - half), px(cx + half, cy + half), bgr, -1)

    # reaction well: an outline, not a fill. The strip sits here, and anything
    # printed under it would contaminate the sample the pipeline reads. The one
    # exception is a demonstration card, which is labelled as such on its face.
    wx, wy = spec.well_centre_mm
    if well_label is not None:
        loci = load_loci()
        if well_label not in loci:
            raise SystemExit(f"unknown class {well_label!r}; "
                             f"choose from {', '.join(sorted(loci))}")
        rgb = lab_to_srgb(np.array(loci[well_label], dtype=float))
        bgr = tuple(int(round(c * 255)) for c in rgb[::-1])
        cv2.circle(img, px(wx, wy),
                   int(round((spec.well_radius_mm - 0.4) * ppmm)), bgr, -1)
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

    scale = ppmm / 12.0
    card_id = f"{spec.card_id_prefix}-{serial}"
    if well_label is not None:
        cv2.rectangle(img, px(0, -banner_mm + 1.0), px(spec.width_mm, -2.0),
                      (60, 60, 200), -1)
        cv2.putText(img, "DEMONSTRATION CARD - PRINTED WELL, NO REAGENT",
                    px(2.0, -banner_mm + 5.6), cv2.FONT_HERSHEY_SIMPLEX,
                    scale * 0.62, (255, 255, 255),
                    max(1, int(round(0.15 * ppmm))), cv2.LINE_AA)
        cv2.putText(img, f"expected result: {well_label}   -   enter card id "
                    f"{card_id} in the app",
                    px(2.0, -banner_mm + 9.6), cv2.FONT_HERSHEY_SIMPLEX,
                    scale * 0.46, (235, 235, 255),
                    max(1, int(round(0.10 * ppmm))), cv2.LINE_AA)
    # The identity block goes to the RIGHT of the well, between it and the
    # corner marker. Three constraints, and the original position violated two:
    #
    #   x < 40.8   the folded liveness tab lands on (21..40, 66..80), so text
    #              there is hidden the moment the card is used as intended
    #   x < 17     the bottom-left ArUco marker occupies (3..17, 63..77), and a
    #              fiducial with lettering across it may not decode at all
    #   40.8..59.2 the well
    #
    # That leaves 59.2..83. Auto-fit rather than assume: a demonstration card's
    # serial is longer than a plain one's, which is how the text ended up over
    # the marker in the first place.
    id_x0, id_x1 = identity_band(spec)

    def fitted(text: str, base: float, thick_mm: float) -> float:
        """Largest scale at or below ``base`` that keeps ``text`` inside."""
        avail = (id_x1 - id_x0) * ppmm
        sc = base
        while sc > 0.05:
            (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, sc,
                                         max(1, int(round(thick_mm * ppmm))))
            if tw <= avail:
                return sc
            sc *= 0.94
        return sc

    cv2.putText(img, card_id, px(id_x0, 69), cv2.FONT_HERSHEY_SIMPLEX,
                fitted(card_id, scale, 0.18), (90, 90, 90),
                max(1, int(round(0.18 * ppmm))), cv2.LINE_AA)
    sub = f"batch {batch}  /  matte  /  no colour management"
    cv2.putText(img, sub, px(id_x0, 74), cv2.FONT_HERSHEY_SIMPLEX,
                fitted(sub, scale * 0.62, 0.12), (140, 140, 140),
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
    p.add_argument("--well", default=None,
                   help="fill the well with this class colour, making a "
                        "DEMONSTRATION card (no reagent). "
                        f"one of: {', '.join(sorted(load_loci()))}")
    p.add_argument("--demo-set", type=Path, default=None,
                   help="write one demonstration card per class into this "
                        "directory, plus a blank one, and a printing guide")
    a = p.parse_args(argv)

    if a.demo_set is not None:
        return _write_demo_set(a.demo_set, a.dpi, a.batch)

    serial = a.serial if a.well is None else f"DEMO-{a.well[:6].upper()}"
    img = render_printable(dpi=a.dpi, serial=serial, batch=a.batch,
                           well_label=a.well)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(a.out), img)
    h, w = img.shape[:2]
    print(f"{a.out}  {w}x{h}px at {a.dpi} dpi  "
          f"({w / a.dpi * 25.4:.0f} x {h / a.dpi * 25.4:.0f} mm including quiet zone)")
    print(f"card id {CARD_V1.card_id_prefix}-{serial}, batch {a.batch}")
    if a.well is not None:
        print(f"DEMONSTRATION card: the well is printed {a.well}, not reacted.")
    print("Print at 100% scale, matte stock, colour management OFF.")
    return 0


def _write_demo_set(out_dir: Path, dpi: int, batch: str) -> int:
    """One card per class, plus a blank, plus the guide that goes with them."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    blank = out_dir / "card-blank.png"
    cv2.imwrite(str(blank), render_printable(dpi=dpi, serial="0417", batch=batch))
    written.append((blank, "an ordinary card — an empty well reads negative"))

    for label in sorted(load_loci()):
        f = out_dir / f"card-{label.replace('_', '-')}.png"
        cv2.imwrite(str(f), render_printable(
            dpi=dpi, serial=f"DEMO-{label[:6].upper()}", batch=batch,
            well_label=label))
        written.append((f, f"demonstration card, well printed {label}"))

    (out_dir / "PRINTING.txt").write_text(_PRINTING_GUIDE)
    written.append((out_dir / "PRINTING.txt", "how to print and shoot these"))

    for f, note in written:
        print(f"  {f.name:34s} {note}")
    print(f"\n{len(written)} files in {out_dir}")
    print("Read PRINTING.txt before printing — scale and colour management "
          "matter more than the printer does.")
    return 0


_PRINTING_GUIDE = """\
Demonstration cards — printing and shooting
===========================================

WHAT THESE ARE
  card-blank.png        an ordinary reference card. An empty well reads
                        NEGATIVE, which is a real, successful result.
  card-*.png            demonstration cards. The well is PRINTED with a class
                        colour. No reagent, no controlled substance. Each one
                        says so across its face and carries DEMO in its card id.

  A demonstration card produces a record that looks like a positive field test.
  That is the point, and it is also the risk: type the printed DEMO card id into
  the app's New test screen so the record itself names the card it read. A
  record that does not say it came from a demonstration card is the one thing
  here that could actually mislead somebody.

NO PRINTER? A SCREEN SOMETIMES WORKS — DO NOT COUNT ON IT
  Photographing the card off a screen often gives a correct colour result. The
  device transform is fitted per frame from the patches on the card itself, so
  the fit absorbs a good deal of what a display does to the colours.

  But it is not dependable. A tester shooting a laptop panel got a refusal at
  11.01 dE, and no simulated display defect we tried reproduces that — a real
  panel evidently does something our tests do not model. The good news is the
  failure mode: it REFUSES rather than reporting the wrong drug class.

  On a refusal the app now prints "likely cause: ..." beneath it. Read that
  line. It distinguishes a reflection on the glass from the room lighting from
  a display colour problem, so you change the right thing.

  And a screen can never pass the liveness check: it is flat, so it gives 0.0px
  of parallax against a predicted 28.2px. That is the anti-replay defence doing
  its job, not a fault. From a screen, take one frame and tap "Continue with one
  frame only" — the record then states plainly that no liveness check was
  performed, which is a demo you can defend.

PRINTING
  Paper size            A4 is fine. Each card is 110 x 134 mm, so it sits on
                        A4 with room to spare. One card per sheet.

  Scale                 100%. Not "fit to page", not "borderless" — both rescale
                        silently. The geometry is metric and the parallax check
                        is in millimetres, so a card printed at 97% is a card
                        whose liveness prediction is wrong.

  Finish                MATTE. Never glossy, never satin, never "photo paper"
                        unless the box says matte. Gloss reflects the room back
                        at the lens as a specular highlight, which is the exact
                        failure that made screen capture unusable: light added
                        on top of the card, which the colour transform cannot
                        remove because it has no constant term.

  Weight                180-250 gsm matte photo paper or card stock. This is
                        not fussiness — plain 80 gsm copier paper curls, will
                        not lie flat under the phone, and the liveness tab will
                        not hold an 8 mm fold. It flops, the parallax reads
                        short, and the check fails for a reason that has nothing
                        to do with the system. If 80 gsm is all you have, print
                        it and glue it to a cereal box.

  Whiteness             bright white. NOT cream, ivory, off-white or recycled.
                        The negative locus is L* 95.5, measured from the card's
                        own substrate; cream paper sits several dE away and a
                        blank card then reads as something other than negative.

  Printer               any consumer inkjet or laser. The device transform is
                        fitted per frame from the printed patches, so a
                        printer's own colour bias is corrected rather than
                        assumed away. Inkjet on matte stock is the most diffuse
                        and therefore the best; laser toner has a slight sheen
                        but works.

  Colour management     OFF. "No colour correction" / "Application manages
                        colour" / printer profile None. The card IS the colour
                        reference; letting a driver "improve" it defeats the
                        purpose, and a perceptual rendering intent bends each
                        hue by a different amount, which is exactly what the
                        transform cannot absorb.

WHAT TO TELL A PRINT SHOP
  Copy the block between the lines and send it with the files. The two things a
  shop gets wrong unprompted are fit-to-page, which silently shrinks the card by
  a few percent and breaks the millimetre geometry, and auto colour enhancement,
  which defeats the entire point — the card IS the colour reference.

  ------------------------------------------------------------------
  Please print these files:

    - Actual size / 100% scale. Do NOT use "fit to page", "scale to
      fit" or borderless. The size must be exact.
    - One file per A4 sheet, portrait.
    - Matte paper, around 200 gsm (matte photo paper or card stock).
      Not glossy.
    - Bright white paper, not cream or recycled.
    - Colour correction OFF / "no colour adjustment" / printer
      profile None. Please do not auto-enhance the colours.
    - Do not cut or trim anything. Leave the full A4 sheet as
      printed.
  ------------------------------------------------------------------

  If asked what it is: a colour calibration test chart. That is accurate.

  DO NOT CUT, and here is why:
    - the white margin around the card is a quiet zone the corner markers need
      in order to be detected;
    - the strip below the card is the liveness tab and must stay attached;
    - the small corner crosses are trim marks for reference, not an instruction.

  For a demo, two sheets is enough: card-amphetamine-class.png for a clear
  positive and card-blank.png for a negative.

THE LIVENESS TAB — READ THIS
  Fold the tab up along the first dashed line and over along the second, so it
  stands about 8 mm above the card face.

  If you do not fold it, the card is flat, and the two-view check will correctly
  report NOT LIVE — "scene was flat". That is not a bug. A flat reproduction
  gives exactly zero parallax at any print quality, which is the whole reason
  the tab exists. An unfolded demonstration card is indistinguishable from a
  photograph of a card, and the app is supposed to say so.

SHOOTING
  1. Lay the card flat under even light. Avoid a single hard lamp or a torch
     held close — the illumination gate measures non-uniformity and will refuse.
  2. Frame the whole card, all four corner markers visible.
  3. Take the first frame.
  4. Move the phone sideways by about a centimetre. Not up, not closer —
     sideways. Take the second frame.
  5. The app reports the parallax it measured against the parallax the geometry
     predicts for an 8 mm tab.

WHAT TO EXPECT
  card-blank            negative        single label
  card-negative         negative        single label
  card-opiate-class     opiate_class    single label
  card-opiate-related   opiate_related  single label
  card-amphetamine-class amphetamine_class  single label

  Every pair of classes is more than twice the abstention threshold apart, so a
  clean frame of any of these returns one label. If you get two labels, the
  frame is the problem, not the card — check the light.
"""


if __name__ == "__main__":
    raise SystemExit(main())
