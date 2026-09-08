"""Diagrams for the SIH idea presentation, in the template's own palette.

The template asks for points, diagrams and infographics rather than paragraphs, so
the load-bearing content on each slide is a picture. Everything drawn here is a
real number or a real design element from the repository — nothing is decorative
filler, and nothing claims more than the work supports.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parents[2] / "docs" / "slides"

BLUE = "#0070C0"
GREY = "#808080"
INK = "#1A1726"
CRIMSON = "#A32C4A"
TEAL = "#0F7B6C"
AMBER = "#A66A00"
LIGHT = "#EAF3FB"
FONT = "DejaVu Sans"

plt.rcParams.update({"font.family": FONT, "figure.dpi": 220})


def box(ax, x, y, w, h, text, fc=LIGHT, ec=BLUE, tc=INK, size=7.2, weight="normal", lw=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size,
            color=tc, zorder=3, weight=weight, linespacing=1.35)


def arrow(ax, x1, y1, x2, y2, color=BLUE):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9,
                                 lw=1.1, color=color, zorder=1))


def canvas(w=12.6, h=4.3):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


# --------------------------------------------------------------------------- #

def pipeline():
    """L1-L7, what each layer does, and what it is built with."""
    fig, ax = canvas(12.6, 4.6)
    stages = [
        ("L1  MEASURE", "printed card + strip\nin one frame\nfiducials → homography\n→ light field → CIELAB",
         "OpenCV / ArUco", BLUE),
        ("L2  DECIDE", "conformal prediction set\n{positive} · {a,b} · ∅\nstated error bound α",
         "closed form, no ML", BLUE),
        ("L4  SEAL", "canonical CBOR\n→ SHA-256\n→ StrongBox signature",
         "Android Keystore", BLUE),
        ("L5  CHAIN", "prev_record_hash\nappend-only ledger\nanchoring window", "on-device", BLUE),
        ("L6  CERTIFY", "BSA §63 Part A\nauto-populated\n+ eSakshya envelope", "CCTNS-2.0", BLUE),
        ("L7  VERIFY", "re-derives everything\noffline, trusting nothing\nPython + Dart",
         "two implementations", TEAL),
    ]
    n = len(stages)
    w, gap = 0.146, 0.024
    x = 0.012
    for title, body, tech, col in stages:
        box(ax, x, 0.42, w, 0.32, body, fc="white", ec=col, size=6.6)
        box(ax, x, 0.755, w, 0.11, title, fc=col, ec=col, tc="white", size=8.0, weight="bold")
        ax.text(x + w / 2, 0.375, tech, ha="center", va="top", fontsize=6.2, color=GREY, style="italic")
        if x > 0.02:
            arrow(ax, x - gap + 0.004, 0.58, x - 0.004, 0.58)
        x += w + gap

    ax.text(0.5, 0.19, "No new hardware.  A printed colour card and the phone already issued.",
            ha="center", fontsize=8.6, color=INK, weight="bold")
    ax.text(0.5, 0.075,
            "Measured on 28 real camera sensitivities × CIE illuminants:  0.50 ΔE2000 under D65,"
            "  1.24 under tungsten   ·   83-condition sweep: 0 false accepts",
            ha="center", fontsize=7.0, color=GREY)
    fig.savefig(OUT / "pipeline.png", bbox_inches="tight", transparent=False, facecolor="white")
    plt.close(fig)


def risks():
    """Risk against mitigation, including the one we have not solved."""
    fig, ax = canvas(12.6, 4.0)
    rows = [
        ("Replay: photographing a\nquality print or screen",
         "NOT SOLVED — declared a residual risk.\nNeeds multi-frame parallax.", CRIMSON),
        ("No reagent dataset exists\npublicly", "Surrogate colour ladders. Substituting NCB\n"
         "standards is a data change, not architecture.", AMBER),
        ("StrongBox absent on some\nissued handsets",
         "TEE fallback; the weaker guarantee is\nwritten into the record, not hidden.", AMBER),
        ("Backdating inside the\nunanchored window",
         "Hash chain + anchoring. The open window is\nstated on screen and in the record.", TEAL),
        ("Bad light producing a\nconfident wrong answer",
         "Quality gate + conformal abstention.\n0 false accepts across 83 conditions.", TEAL),
    ]
    y = 0.845
    h = 0.155
    box(ax, 0.012, y + 0.055, 0.30, 0.085, "RISK", fc=BLUE, ec=BLUE, tc="white", size=8.4, weight="bold")
    box(ax, 0.335, y + 0.055, 0.653, 0.085, "MITIGATION  /  HONEST STATUS", fc=BLUE, ec=BLUE,
        tc="white", size=8.4, weight="bold")
    for risk, mit, col in rows:
        box(ax, 0.012, y - h + 0.03, 0.30, h - 0.03, risk, fc="white", ec=GREY, size=7.0)
        box(ax, 0.335, y - h + 0.03, 0.653, h - 0.03, mit, fc="white", ec=col, size=7.0, lw=1.6)
        y -= h
    fig.savefig(OUT / "risks.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def evidence():
    """What has been built and measured, as numbers rather than adjectives."""
    fig, ax = canvas(12.6, 2.5)
    cards = [
        ("0", "false accepts\nacross 83 stress conditions", TEAL),
        ("0.50", "ΔE2000 median, 28 real cameras\n(1.24 under tungsten)", BLUE),
        ("0.0%", "wrong calls under an unseen\nilluminant — it abstains instead", TEAL),
        ("2", "independent verifiers that\nagree, in two languages", BLUE),
        ("341", "automated tests\nacross the whole system", GREY),
    ]
    w, gap = 0.183, 0.021
    x = 0.008
    for big, small, col in cards:
        box(ax, x, 0.12, w, 0.78, "", fc="white", ec=col, lw=1.6)
        ax.text(x + w / 2, 0.66, big, ha="center", va="center", fontsize=21, color=col, weight="bold")
        ax.text(x + w / 2, 0.33, small, ha="center", va="center", fontsize=7.0, color=INK,
                linespacing=1.45)
        x += w + gap
    fig.savefig(OUT / "evidence.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def impact():
    """Who benefits, and how."""
    fig, ax = canvas(12.6, 3.5)
    cols = [
        ("NCB / POLICE", BLUE, [
            "A field test becomes documentary evidence",
            "§63 Part A auto-filled at capture",
            "Plugs into eSakshya / CCTNS-2.0 — no new silo",
            "Works with kits already purchased",
            "Offline queue — no coverage required",
        ]),
        ("COURTS & THE ACCUSED", TEAL, [
            "Anyone can verify offline, trusting no one",
            "Disagreements recorded, not suppressed",
            "'Inconclusive' has a stated error bound",
            "Verifier says what it CANNOT prove",
            "Same tool serves defence and prosecution",
            "Records cannot be deleted or reordered",
        ]),
        ("COST & REACH", AMBER, [
            "One printed card ≈ ₹5, matte A4",
            "No new hardware, no new procurement",
            "Runs fully offline — NDPS field reality",
            "Any Android handset already issued",
            "Kit-agnostic: not tied to one vendor",
            "Card reprints locally, no supply chain",
        ]),
    ]
    w, gap = 0.318, 0.023
    x = 0.008
    for title, col, items in cols:
        box(ax, x, 0.86, w, 0.12, title, fc=col, ec=col, tc="white", size=9.0, weight="bold")
        box(ax, x, 0.05, w, 0.79, "", fc="white", ec=col, lw=1.4)
        yy = 0.76
        for it in items:
            ax.text(x + 0.014, yy, "•" if not it.startswith("   ") else " ", fontsize=7.5, color=col,
                    va="top")
            ax.text(x + 0.036, yy, it.strip(), fontsize=7.4, color=INK, va="top", linespacing=1.4)
            yy -= 0.125
        x += w + gap
    fig.savefig(OUT / "impact.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pipeline(); risks(); evidence(); impact()
    for p in sorted(OUT.glob("*.png")):
        print(f"  {p.name}  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
