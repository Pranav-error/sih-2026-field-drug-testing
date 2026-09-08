"""High-level architecture diagram for SIH26231.

The seven-layer stack in ARCHITECTURE.md reads top-to-bottom as a list of
components. That hides the thing the design is actually about, which is **trust
boundaries**: who is being asked to believe what, and on whose word.

So this diagram is organised by trust, not by component:

    PHYSICAL      what exists before any software runs
    HANDSET       code that a court has no reason to trust
    SECURE ELEMENT hardware that will not export its key
    ANYONE        what a stranger can check with no network and no trust in us

The arrows crossing those boundaries are labelled with what actually crosses,
because that is the claim being made at each step.

    python core/tools/make_architecture_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parents[2] / "docs" / "slides"

BLUE = "#0070C0"
DEEP = "#134E7A"
TEAL = "#0F7B6C"
AMBER = "#A66A00"
CRIMSON = "#A32C4A"
INK = "#14121C"
GREY = "#7A7A85"
FAINT = "#F2F6FA"
BAND = "#F7F8FA"

plt.rcParams.update({"font.family": "DejaVu Sans"})


HEAD = 0.040          # header bar height, in axis units
LINE = 0.0215         # one line of body text, in axis units at this figure size


def body_height(lines: int, pad: float = 0.022) -> float:
    """Box height that actually fits `lines` of body text under the header.

    Sized rather than guessed: the first version of this diagram had four-line
    bodies inside boxes with room for two, and the text ran out of the bottom.
    """
    return HEAD + lines * LINE + pad


def band(ax, y, h, label, sub, fc="#F7F8FA", ec="#DDE3EA"):
    """A trust zone. The label sits in its own row at the top so no node can
    ever cover it."""
    ax.add_patch(Rectangle((0.006, y), 0.988, h, fc=fc, ec=ec, lw=1.0, zorder=0))
    # Above the connectors, on an opaque ground: routing lines pass behind the
    # labels rather than through the words.
    ax.text(0.018, y + h - 0.014, label, fontsize=8.4, weight="bold", color="#5A5A66",
            va="top", ha="left", zorder=10,
            bbox=dict(fc=fc, ec="none", pad=2.0))
    ax.text(0.982, y + h - 0.016, sub, fontsize=6.8, color=GREY, va="top",
            ha="right", style="italic", zorder=10,
            bbox=dict(fc=fc, ec="none", pad=2.0))


def node(ax, x, y, w, h, tag, title, body, ec=BLUE, tagfc=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.004,rounding_size=0.010",
                                fc="white", ec=ec, lw=1.5, zorder=3))
    ax.add_patch(Rectangle((x + 0.002, y + h - HEAD), w - 0.004, HEAD - 0.002,
                           fc=tagfc or ec, ec="none", zorder=4))
    label = f"{tag}   {title}" if tag else title
    ax.text(x + w / 2, y + h - HEAD / 2 - 0.001, label, ha="center", va="center",
            fontsize=7.8, weight="bold", color="white", zorder=5)
    ax.text(x + w / 2, y + (h - HEAD) / 2, body, ha="center", va="center",
            fontsize=6.9, color=INK, linespacing=1.55, zorder=5)


def arrow(ax, p1, p2, label=None, color=DEEP, lw=1.5, dy=0.010, fs=6.5, rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=12,
                                 lw=lw, color=color, zorder=6,
                                 connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + dy, label, fontsize=fs,
                color=color, ha="center", va="bottom", weight="bold", zorder=7,
                bbox=dict(fc="white", ec="none", pad=1.6))


def build():
    fig, ax = plt.subplots(figsize=(13.33, 7.2))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # Vertical budget, top to bottom. Each band is tall enough for its label row
    # plus the tallest node it holds.
    band(ax, 0.828, 0.170, "PHYSICAL WORLD",
         "exists before any software runs  ·  no new hardware")
    band(ax, 0.520, 0.292, "THE HANDSET  —  software a court has no reason to trust",
         "everything here is re-derivable from the raw frame by somebody else")
    band(ax, 0.338, 0.166, "SECURE ELEMENT  —  StrongBox / TEE",
         "key generated inside, non-exportable, attested to a hardware root")
    band(ax, 0.030, 0.292, "ANYONE, LATER  —  no network, no trust in us",
         "the only part that makes the rest worth anything",
         fc="#F3FAF8", ec="#CBE5DF")

    # ---- physical --------------------------------------------------------- #
    h2 = body_height(2)
    node(ax, 0.045, 0.852, 0.29, h2, "", "EXISTING REAGENT KIT",
         "whatever NCB already buys\nno vendor lock-in, reagent is declared",
         ec=GREY, tagfc=GREY)
    node(ax, 0.370, 0.852, 0.29, h2, "", "PRINTED REFERENCE CARD",
         "matte A4  ·  4 fiducials  ·  15 patches\n8 neutrals  ·  reaction well",
         ec=GREY, tagfc=GREY)
    node(ax, 0.700, 0.852, 0.255, h2, "", "ONE FRAME",
         "card and strip together, co-planar,\nunder one light", ec=BLUE)
    arrow(ax, (0.338, 0.852 + h2 / 2), (0.366, 0.852 + h2 / 2), color=GREY)
    arrow(ax, (0.663, 0.852 + h2 / 2), (0.696, 0.852 + h2 / 2), color=BLUE)

    # ---- handset ---------------------------------------------------------- #
    h3 = body_height(3)
    top = 0.640
    node(ax, 0.030, top, 0.215, h3, "L1", "MEASURE",
         "fiducials → homography\n→ divide out the light field\n→ CIELAB, with a residual")
    node(ax, 0.268, top, 0.215, h3, "L2", "DECIDE",
         "conformal prediction set\n{positive} · {a,b} · ∅\nwith a stated error bound α")
    node(ax, 0.506, top, 0.215, h3, "L3", "CORROBORATE",
         "GNSS raw · Wi-Fi · cell · motion\nagreement scored, and every\ndisagreement recorded")
    node(ax, 0.744, top, 0.226, h3, "", "QUALITY GATE",
         "a frame that cannot be measured\nyields an ABSTENTION,\nnever a confident guess",
         ec=AMBER, tagfc=AMBER)
    for x in (0.245, 0.483, 0.721):
        arrow(ax, (x, top + h3 / 2), (x + 0.021, top + h3 / 2), lw=1.2)
    # Routed orthogonally through the gap between the bands. An arc here sweeps
    # back up through the physical boxes and reads as pointing the wrong way.
    gap = 0.820
    ax.plot([0.828, 0.828], [0.852, gap], color=BLUE, lw=1.5, zorder=6,
            solid_capstyle="round")
    ax.plot([0.828, 0.138], [gap, gap], color=BLUE, lw=1.5, zorder=6,
            solid_capstyle="round")
    arrow(ax, (0.138, gap), (0.138, top + h3 + 0.002), color=BLUE)
    ax.text(0.483, gap + 0.008, "the captured frame", fontsize=6.8, color=BLUE,
            ha="center", va="bottom", weight="bold", zorder=7,
            bbox=dict(fc="white", ec="none", pad=1.6))

    ax.text(0.5, 0.570, "canonical CBOR  —  deterministic bytes, no floats, so two "
            "independent implementations reach the same digest, forever",
            ha="center", va="center", fontsize=7.5, color=INK, weight="bold",
            bbox=dict(fc="white", ec=BLUE, lw=1.3, boxstyle="round,pad=0.45"), zorder=6)
    arrow(ax, (0.5, top), (0.5, 0.590), lw=1.4)

    # ---- secure element ---------------------------------------------------- #
    top = 0.362
    node(ax, 0.100, top, 0.35, h2, "L4", "SEAL",
         "SHA-256 → signed inside the secure element\n→ key attestation chain attached",
         ec=DEEP, tagfc=DEEP)
    node(ax, 0.550, top, 0.35, h2, "L5", "CHAIN",
         "prev_record_hash → append-only ledger\nanchoring window stated, never hidden",
         ec=DEEP, tagfc=DEEP)
    arrow(ax, (0.5, 0.552), (0.5, top + h2), "digest", color=DEEP, dy=0.006)
    arrow(ax, (0.453, top + h2 / 2), (0.546, top + h2 / 2), color=DEEP)

    # ---- anyone ------------------------------------------------------------ #
    h5 = body_height(5)
    top = 0.075
    node(ax, 0.030, top, 0.275, h5, "L6", "STATUTORY OUTPUT",
         "BSA 2023 section 63 certificate\nPart A auto-populated:\nhash value + algorithm\n\n"
         "every oath left blank for a human",
         ec=AMBER, tagfc=AMBER)
    node(ax, 0.335, top, 0.275, h5, "", "HANDOFF",
         "eSakshya / CCTNS-2.0 envelope\nrouted by FIR + seizure memo\n\n"
         "CCTNS-2.0 stays the system of\nrecord — no parallel silo built",
         ec=AMBER, tagfc=AMBER)
    node(ax, 0.640, top, 0.330, h5, "L7", "INDEPENDENT VERIFIER",
         "recompute · check signature · walk\nattestation · replay chain · re-run L1/L2\n\n"
         "PROVEN  /  ASSERTED  /  UNVERIFIABLE\ntwo implementations: Python + Dart",
         ec=TEAL, tagfc=TEAL)

    arrow(ax, (0.230, top + h5 + 0.115), (0.168, top + h5), color=AMBER, rad=0.12)
    arrow(ax, (0.500, top + h5 + 0.115), (0.472, top + h5), color=AMBER)
    arrow(ax, (0.770, top + h5 + 0.115), (0.805, top + h5), "the sealed record",
          color=TEAL, rad=-0.12, fs=6.6, dy=-0.036)
    arrow(ax, (0.308, top + h5 / 2), (0.331, top + h5 / 2), color=AMBER, lw=1.2)

    ax.text(0.805, 0.048, "A verified record is not a true result.  It is an unaltered one.",
            ha="center", fontsize=7.4, color=TEAL, style="italic", weight="bold", zorder=7)

    fig.savefig(OUT / "architecture.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / "architecture.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    build()
    for p in sorted(OUT.glob("architecture.*")):
        print(f"  {p.name}  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
