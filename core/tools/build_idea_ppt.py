"""Fill the SIH 2026 idea-submission template.

Rules taken from the template's own instructions slide:

  * maximum SIX slides including the title — slide 7 (instructions) is deleted
  * points, diagrams and infographics, not paragraphs
  * the provided template must be used, and the idea-detail pointers not changed
  * the file is submitted as PDF

So: the section titles and the layout are left exactly as issued, the prompt text
inside each content box is replaced by content that answers that prompt in the same
order, and the load-bearing content on each slide is a diagram.

    python core/tools/build_idea_ppt.py [--template PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[2]
SLIDES = ROOT / "docs" / "slides"

BLUE = RGBColor(0x00, 0x70, 0xC0)
INK = RGBColor(0x1A, 0x17, 0x26)
GREY = RGBColor(0x80, 0x80, 0x80)
CRIMSON = RGBColor(0xA3, 0x2C, 0x4A)

# Fill these in before submitting. Left as visible placeholders on purpose: a
# silently wrong team id is worse than an obviously missing one.
TEAM_ID = "«TEAM ID»"
TEAM_NAME = "«TEAM NAME as registered on the portal»"

PS_ID = "SIH26231"
PS_TITLE = "Digital Companion for Field Drug Testing"
THEME = "MedTech / BioTech / HealthTech"
CATEGORY = "Software"

IDEA_TITLE = "THE RECORD IS THE PRODUCT"


def _no_bullet(p):
    """The template's list styles inject a bullet glyph at some levels and not
    others, which reads as a mistake. Every bullet in this deck is typed, so the
    inherited ones are removed rather than fought with."""
    pPr = p._p.get_or_add_pPr()
    for tag in ("a:buChar", "a:buAutoNum", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def set_text(tf, blocks, base_size=13, colour=INK, space_after=5):
    """Replace a text frame's content with (text, size, bold, colour, indent) items."""
    tf.clear()
    tf.word_wrap = True
    for i, item in enumerate(blocks):
        text, size, bold, col, indent = item
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = indent
        _no_bullet(p)
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = col
        r.font.name = "Arial"
        p.space_after = Pt(space_after)


def find(slide, name_startswith=None, contains=None):
    for sh in slide.shapes:
        if name_startswith and sh.name.startswith(name_startswith):
            return sh
        if contains and sh.has_text_frame and contains.lower() in sh.text_frame.text.lower():
            return sh
    return None


def delete(slide, shape):
    shape._element.getparent().remove(shape._element)


def add_picture(slide, path, left, top, width):
    """Place a picture and return the bottom edge in inches, so the caller can lay
    out beneath it instead of guessing and overlapping."""
    pic = slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(width))
    return Emu(pic.top).inches + Emu(pic.height).inches


def set_team_name(slide, name):
    """The template stamps 'Your Team Name' in an oval on every content slide."""
    for sh in slide.shapes:
        if sh.has_text_frame and "your team name" in sh.text_frame.text.lower():
            for para in sh.text_frame.paragraphs:
                for r in para.runs:
                    r.text = name
                    r.font.size = Pt(9)
            return


def build(template: Path, out: Path) -> None:
    prs = Presentation(str(template))
    s1, s2, s3, s4, s5, s6, s7 = prs.slides

    # ---------------------------------------------------------------- slide 1
    box = find(s1, contains="Problem Statement ID")
    set_text(box.text_frame, [
        (f"Problem Statement ID  –  {PS_ID}", 17, True, BLUE, 0),
        (f"Problem Statement Title  –  {PS_TITLE}", 15, False, INK, 0),
        (f"Theme  –  {THEME}", 14, False, INK, 0),
        (f"PS Category  –  {CATEGORY}", 14, False, INK, 0),
        (f"Team ID  –  {TEAM_ID}", 14, False, GREY, 0),
        (f"Team Name  –  {TEAM_NAME}", 14, False, GREY, 0),
    ], space_after=9)

    # ---------------------------------------------------------------- slide 2
    title = find(s2, contains="IDEA TITLE")
    # Between the team-name oval on the left and the SIH logo on the right.
    title.left, title.top = Inches(1.85), Inches(0.10)
    title.width, title.height = Inches(8.6), Inches(1.0)
    set_text(title.text_frame, [(IDEA_TITLE, 30, True, BLUE, 0)])
    sub = s2.shapes.add_textbox(Inches(1.85), Inches(0.86), Inches(8.6), Inches(0.34))
    set_text(sub.text_frame, [
        ("not the colour reading — that part is an undergraduate exercise",
         12.5, False, GREY, 0)])

    body = find(s2, contains="Proposed Solution")
    body.left, body.top = Inches(0.45), Inches(1.32)
    body.width, body.height = Inches(12.4), Inches(2.25)
    set_text(body.text_frame, [
        ("THE PROBLEM IS NOT THE COLOUR.  The problem statement says it plainly: a field "
         "test \"leaves no verifiable record… outcomes cannot presently be relied upon as "
         "documentary evidence.\"  Reading a colour is an undergraduate exercise — and the "
         "naive app already ships commercially (DetectaChem MobileDetect).", 12, False, INK, 0),
        ("OUR SOLUTION.  The measurement is bound, at the instant of capture, into a "
         "hardware-attested, append-only record that anyone can re-derive offline — and that "
         "emits a Bharatiya Sakshya Adhiniyam Section 63 certificate and hands off to "
         "eSakshya / CCTNS-2.0.", 12, False, INK, 0),
        ("WHAT IS ACTUALLY NEW:", 12, True, BLUE, 0),
        ("Kit-agnostic — reagent is declared, not read from a vendor's serialised pouch, "
         "as the PS requires", 11.5, False, INK, 1),
        ("\"Inconclusive\" carries a stated error bound (conformal prediction), not a "
         "softmax confidence a court cannot cross-examine", 11.5, False, INK, 1),
        ("Two independently written verifiers that agree — a single implementation "
         "agreeing with itself proves nothing", 11.5, False, INK, 1),
        ("The statutory certificate is emitted, not left as an exercise", 11.5, False, INK, 1),
    ], space_after=6)
    tb = s2.shapes.add_textbox(Inches(0.45), Inches(3.66), Inches(12.4), Inches(0.42))
    set_text(tb.text_frame, [
        ("No new hardware: a printed colour card and the phone already issued.",
         13, True, INK, 0)])
    add_picture(s2, SLIDES / "evidence.png", 0.75, 4.16, 11.8)

    # ---------------------------------------------------------------- slide 3
    body = find(s3, contains="Technologies to be used")
    body.left, body.top = Inches(0.45), Inches(1.12)
    body.width, body.height = Inches(12.4), Inches(1.0)
    set_text(body.text_frame, [
        ("Flutter (Android) · OpenCV/ArUco · CIELAB + CIEDE2000 · conformal prediction · "
         "canonical CBOR + SHA-256 · ECDSA P-256 in StrongBox/TEE · verifiers in Python and Dart",
         12, False, INK, 0),
    ])
    bottom = add_picture(s3, SLIDES / "pipeline.png", 0.35, 1.72, 12.6)
    tb = s3.shapes.add_textbox(Inches(0.45), Inches(bottom + 0.06), Inches(12.4), Inches(0.80))
    set_text(tb.text_frame, [
        ("WHY DETERMINISTIC, NOT A NEURAL NETWORK:  a least-squares colour transform is "
         "auditable and defensible in court. We ablated a learned classifier against it on "
         "8,064 measurements rendered from 28 measured camera sensitivities — the closed-form "
         "score won on every split, so there is no learned component and no TFLite dependency.",
         10.5, False, INK, 0)])

    # ---------------------------------------------------------------- slide 4
    body = find(s4, contains="Analysis of the feasibility")
    body.left, body.top = Inches(0.45), Inches(1.12)
    body.width, body.height = Inches(12.4), Inches(0.9)
    set_text(body.text_frame, [
        ("FEASIBLE TODAY: no new hardware, works with kits already purchased, runs fully "
         "offline, and a working core already exists — 341 automated tests, both verifiers "
         "agreeing on every record.", 12, False, INK, 0),
    ])
    bottom = add_picture(s4, SLIDES / "risks.png", 1.15, 2.02, 11.0)
    tb = s4.shapes.add_textbox(Inches(0.45), Inches(bottom + 0.05), Inches(12.4), Inches(0.7))
    set_text(tb.text_frame, [
        ("We list the attack we have NOT solved. A threat model that overstates its defences "
         "is worth less than none — a judge who finds the gap first concludes we never looked.",
         11, True, CRIMSON, 0)])

    # ---------------------------------------------------------------- slide 5
    body = find(s5, contains="Potential impact")
    body.left, body.top = Inches(0.45), Inches(1.12)
    body.width, body.height = Inches(12.4), Inches(0.8)
    set_text(body.text_frame, [
        ("Turns a presumptive field test from an unusable note into an artefact a court can "
         "test — without building a second evidence store for the State to maintain.",
         12, False, INK, 0),
    ])
    bottom = add_picture(s5, SLIDES / "impact.png", 0.75, 1.92, 11.8)
    tb = s5.shapes.add_textbox(Inches(0.45), Inches(bottom + 0.06), Inches(12.4), Inches(0.8))
    set_text(tb.text_frame, [
        ("Deliberately NOT built: a confirmatory test, a national database of results, or any "
         "scoring of persons. CCTNS-2.0 stays the system of record; a parallel silo would add "
         "a surveillance surface and a liability for no benefit.", 10.5, False, GREY, 0)])

    # ---------------------------------------------------------------- slide 6
    body = find(s6, contains="Details / Links")
    body.left, body.top = Inches(0.45), Inches(1.18)
    body.width, body.height = Inches(8.15), Inches(5.5)
    set_text(body.text_frame, [
        ("STATUTE & GOVERNMENT SYSTEMS", 12.5, True, BLUE, 0),
        ("Bharatiya Sakshya Adhiniyam 2023, Section 63 + the Schedule (certificate, Parts A "
         "and B; hash value and algorithm required)  ·  indiankanoon.org/doc/125020475",
         10.5, False, INK, 1),
        ("NDPS (Seizure, Storage, Sampling and Disposal) Rules 2022 — GSR 899(E)  ·  "
         "eSakshya, NCRB / CCTNS-2.0  ·  informatics.nic.in", 10.5, False, INK, 1),
        ("PRIOR ART — CONCEDED, NOT IGNORED", 12.5, True, BLUE, 0),
        ("DetectaChem MobileDetect: smartphone + colorimetric pouches, GPS-tagged PDF "
         "reports. The naive solution is a shipping product; our claim is narrower and sits "
         "in the binding, the abstention bound and the verifiability.", 10.5, False, INK, 1),
        ("METHOD", 12.5, True, BLUE, 0),
        ("Finlayson et al., root-polynomial colour correction (exposure-invariant)  ·  "
         "Sharma, Wu & Dalal (2005), CIEDE2000 conformance data  ·  Vovk et al., conformal "
         "prediction  ·  Android key attestation & StrongBox (AOSP)", 10.5, False, INK, 1),
        ("MEASURED DATA USED IN OUR EVALUATION", 12.5, True, BLUE, 0),
        ("Jiang, Liu, Gu & Süsstrunk (2013) camera spectral sensitivity database, 28 cameras "
         "— Zenodo 3245883, CC BY-NC-SA 4.0  ·  CIE illuminant SPDs, 1931 observer and "
         "ColorChecker reflectances via colour-science (BSD-3)", 10.5, False, INK, 1),
        ("STATED LIMITATION", 12.5, True, CRIMSON, 0),
        ("No public dataset of colorimetric drug-test images exists, and no spectral library "
         "of NDPS reagent developments. Our classifier is calibrated on surrogate colour "
         "targets. Substituting NCB reagent standards is a DATA change, not an architecture "
         "change: L1 and L3–L7 are substance-independent by construction.",
         10.5, False, INK, 1),
    ], space_after=4)

    for sl in (s2, s3, s4, s5, s6):
        set_team_name(sl, TEAM_NAME)

    # Right column: the physical artefact, then what makes the work checkable.
    card = ROOT / "docs" / "reference-card.png"
    y = 1.30
    if card.is_file():
        y = add_picture(s6, card, 9.05, y, 3.55) + 0.06
        cap = s6.shapes.add_textbox(Inches(9.05), Inches(y), Inches(3.75), Inches(0.6))
        set_text(cap.text_frame, [
            ("The only physical artefact: a matte A4 print — fiducials, 15 reagent-gamut "
             "patches, 8 neutrals, reaction well.", 8.5, False, GREY, 0)])
        y += 0.62
    note = s6.shapes.add_textbox(Inches(9.05), Inches(y), Inches(3.75), Inches(1.9))
    set_text(note.text_frame, [
        ("REPRODUCIBILITY", 11.5, True, BLUE, 0),
        ("Working code, 341 automated tests, and every figure on these slides "
         "regenerable from one command.", 9, False, INK, 0),
        ("Every number here is measured on synthetic frames or measured spectral "
         "data — none is a field accuracy. The physical capture set is the critical "
         "path, and we say so.", 9, False, INK, 0),
    ], space_after=3)

    # instructions slide — the template says to delete it before uploading
    xml_slides = prs.slides._sldIdLst
    xml_slides.remove(list(xml_slides)[6])

    prs.save(str(out))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", type=Path,
                    default=Path.home() / "Downloads" / "SIH2026-IDEA-Presentation-Format.pptx")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "SIH26231-idea-submission.pptx")
    a = ap.parse_args()
    if not a.template.is_file():
        print(f"template not found: {a.template}")
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    build(a.template, a.out)

    prs = Presentation(str(a.out))
    print(f"{a.out}  ·  {len(prs.slides)} slides")
    for i, s in enumerate(prs.slides, 1):
        title = next((sh.text_frame.text.splitlines()[0] for sh in s.shapes
                      if sh.has_text_frame and sh.text_frame.text.strip()), "")
        pics = sum(1 for sh in s.shapes if sh.shape_type == 13)
        print(f"  {i}. {title[:58]:<58} {pics} image(s)")
    print("\nRemaining: set TEAM_ID and TEAM_NAME, then export to PDF (portal takes PDF only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
