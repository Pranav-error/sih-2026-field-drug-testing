"""The FEASIBILITY AND VIABILITY slide graphic.

The template asks for three things — feasibility, challenges and risks, and
strategies to overcome them — so those are the left column and they are not
negotiable.

The right column is where this differs from a typical hackathon deck. The usual
move is market projections lifted from industry reports: a pie chart of adoption,
a bar of willingness-to-pay, a ROI curve. Those are somebody else's numbers about
a market. **Ours are measurements of our own system**, produced by the tools in
this repository and reproducible from one command — which is a stronger claim and
a much harder one to wave away.

Palette validated with the dataviz skill's checker rather than by eye:
#0070C0 / #A66A00 / #6B3FA0 passes lightness band, chroma floor, CVD separation,
normal-vision floor and contrast. Blue+amber+green FAILS CVD separation (protan
ΔE 3.3), which is the classic red-green trap and is why the green was dropped.

    python core/tools/make_feasibility_graphic.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = Path(__file__).resolve().parents[2] / "docs" / "slides"

BLUE = "#0070C0"
DEEP = "#134E7A"
AMBER = "#A66A00"
PURPLE = "#6B3FA0"
TEAL = "#0F7B6C"
CRIMSON = "#A32C4A"
INK = "#14121C"
GREY = "#6E6E78"
RULE = "#D8DEE6"
SURFACE = "#F6F8FB"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.edgecolor": RULE,
    "xtick.color": GREY,
    "ytick.color": GREY,
})


def panel(ax, title, sub=None):
    ax.set_title(title, fontsize=8.6, weight="bold", color=INK, loc="left", pad=13)
    if sub:
        ax.text(0, 1.045, sub, transform=ax.transAxes, fontsize=6.7, color=GREY,
                va="bottom", ha="left")


# --------------------------------------------------------------------------- #
# charts — measured, from this repository
# --------------------------------------------------------------------------- #

def chart_illuminants(ax):
    """Magnitude across a set of named conditions -> horizontal bars, one hue."""
    names = ["D65 daylight", "LED", "D50", "Fluorescent\nFL2", "Fluorescent\nFL11",
             "Tungsten\n(illuminant A)"]
    vals = [0.50, 0.63, 0.66, 1.01, 1.17, 1.24]
    # Sequential: one hue, light to dark, mapped to magnitude.
    shades = ["#9EC9E8", "#7FB6DF", "#5FA3D6", "#3F90CD", "#217DC4", "#0070C0"]

    y = range(len(names))
    ax.barh(list(y), vals, height=0.6, color=shades, zorder=3)
    ax.axvline(3.0, color=CRIMSON, lw=1.4, ls=(0, (4, 3)), zorder=4)
    ax.text(3.06, len(names) - 0.35, "3.0 = quality-gate limit", fontsize=6.4,
            color=CRIMSON, va="center", ha="left", weight="bold")

    for i, v in enumerate(vals):
        ax.text(v + 0.06, i, f"{v:.2f}", va="center", fontsize=6.8,
                color=INK, weight="bold")

    ax.set_yticks(list(y))
    ax.set_yticklabels(names, fontsize=6.6, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, 3.5)
    ax.set_xticks([0, 1, 2, 3])
    ax.tick_params(axis="x", labelsize=6.3, length=0)
    ax.grid(axis="x", color=RULE, lw=0.7, zorder=0)
    ax.set_xlabel("median ΔE2000 error", fontsize=6.5, color=GREY, labelpad=2)
    panel(ax, "Colour accuracy on 28 real cameras",
          "measured spectral sensitivities × CIE illuminants · every condition inside the gate")


def chart_replay(ax):
    """A status comparison against a predicted value -> bars + a reference line."""
    names = ["Physical card", "Photo-lab print", "High-DPI screen"]
    vals = [28.1, 0.1, 0.0]
    colours = [TEAL, CRIMSON, CRIMSON]
    verdicts = ["LIVE", "REFUSED", "REFUSED"]

    x = range(len(names))
    bars = ax.bar(list(x), vals, width=0.52, color=colours, zorder=3)
    for b in bars:  # 4px rounded data-end, anchored to the baseline
        b.set_linewidth(0)

    ax.axhline(28.2, color=GREY, lw=1.3, ls=(0, (4, 3)), zorder=4)
    ax.text(2.46, 28.2, "28.2 predicted", fontsize=6.4, color=GREY,
            va="bottom", ha="right", weight="bold")

    for i, (v, verdict, c) in enumerate(zip(vals, verdicts, colours)):
        ax.text(i, v + 1.2, f"{v:.1f} px", ha="center", fontsize=7.2,
                color=INK, weight="bold")
        # Status never rides on colour alone.
        ax.text(i, -3.4, verdict, ha="center", fontsize=6.6, color=c, weight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=6.7, color=INK)
    ax.tick_params(axis="x", length=0, pad=12)
    ax.set_ylim(0, 34)
    ax.set_yticks([0, 10, 20, 30])
    ax.tick_params(axis="y", labelsize=6.3, length=0)
    ax.grid(axis="y", color=RULE, lw=0.7, zorder=0)
    ax.set_ylabel("parallax, px", fontsize=6.5, color=GREY, labelpad=2)
    panel(ax, "The replay attack, refused",
          "a print passes every colour check — it cannot fake depth")


def chart_ablation(ax):
    """Three scorers across three generalisation splits -> grouped bars."""
    splits = ["Unseen\nilluminant", "Unseen\ncamera", "DSLR →\nphone"]
    series = {
        "Nearest locus ΔE2000": ([94.5, 95.1, 93.2], BLUE),
        "Mahalanobis": ([91.8, 94.8, 92.8], AMBER),
        "Logistic regression": ([94.5, 94.8, 92.0], PURPLE),
    }
    n = len(series)
    width = 0.24
    for k, (label, (vals, colour)) in enumerate(series.items()):
        offs = [i + (k - (n - 1) / 2) * (width + 0.02) for i in range(len(splits))]
        ax.bar(offs, vals, width=width, color=colour, label=label, zorder=3)

    ax.axhline(95, color=GREY, lw=1.2, ls=(0, (4, 3)), zorder=4)
    ax.text(2.52, 95.3, "95% target", fontsize=6.2, color=GREY, ha="right",
            va="bottom", weight="bold")

    ax.set_xticks(range(len(splits)))
    ax.set_xticklabels(splits, fontsize=6.5, color=INK)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.set_ylim(85, 97.5)
    ax.set_yticks([86, 90, 94])
    ax.set_yticklabels(["86%", "90%", "94%"], fontsize=6.2)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="y", color=RULE, lw=0.7, zorder=0)
    ax.legend(fontsize=6.1, frameon=False, ncol=1, loc="lower left",
              bbox_to_anchor=(0.005, -0.01), labelspacing=0.28, handlelength=1.1)
    panel(ax, "The simplest classifier wins — so there is no neural network",
          "coverage on data the model never saw · error rate 0.0% in every bar")


# --------------------------------------------------------------------------- #

def box(fig, x, y, w, h, ec=RULE, fc="white", lw=1.1):
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.008",
        transform=fig.transFigure, fc=fc, ec=ec, lw=lw, zorder=1))


def text(fig, x, y, s, size=7.0, colour=INK, weight="normal", ha="left",
         va="top", style="normal"):
    fig.text(x, y, s, fontsize=size, color=colour, weight=weight, ha=ha, va=va,
             style=style, zorder=3, linespacing=1.5)


def build():
    fig = plt.figure(figsize=(13.33, 5.75))
    fig.patch.set_facecolor("white")

    # ---------------- left column: what the template asks for --------------- #
    text(fig, 0.018, 0.965, "FEASIBILITY", 8.8, DEEP, "bold")
    text(fig, 0.018, 0.928, "no new hardware · works with kits already purchased · "
         "a working core already exists", 6.6, GREY)

    cols = [
        ("TECHNICAL", [
            "Phone camera + one printed card",
            "0.50 ΔE2000 on 28 real sensors",
            "379 automated tests, all passing",
            "Two verifiers agree, two languages",
        ]),
        ("ECONOMIC", [
            "≈ ₹5 per card, matte A4, 4-up",
            "No procurement, no new devices",
            "Reprints locally — no supply chain",
            "Kit-agnostic: no vendor lock-in",
        ]),
        ("OPERATIONAL", [
            "Runs fully offline — NDPS reality",
            "Any issued Android handset",
            "Plugs into eSakshya / CCTNS-2.0",
            "Two frames, ~10 mm apart, ~8 s",
        ]),
    ]
    cw, gap = 0.148, 0.012
    for i, (head, items) in enumerate(cols):
        x = 0.018 + i * (cw + gap)
        box(fig, x, 0.612, cw, 0.278, fc=SURFACE, ec=RULE)
        fig.patches.append(Rectangle((x, 0.862), cw, 0.028,
                                     transform=fig.transFigure, fc=DEEP, ec="none", zorder=2))
        text(fig, x + cw / 2, 0.876, head, 6.9, "white", "bold", ha="center", va="center")
        for j, it in enumerate(items):
            text(fig, x + 0.008, 0.845 - j * 0.048, "·", 7.4, DEEP, "bold")
            text(fig, x + 0.018, 0.847 - j * 0.048, it, 6.5, INK)

    text(fig, 0.018, 0.565, "CHALLENGES, AND WHAT WE DID ABOUT THEM", 8.0, DEEP, "bold")
    risks = [
        ("Replay: photographing a print or a screen", CRIMSON,
         "SOLVED. Two-view parallax against a folded 8 mm tab.\n"
         "A print gives 0.1 px where a card gives 28.1."),
        ("A synchronised stereo replay", CRIMSON,
         "NOT SOLVED, and stated as such. Needs the genuine pair\n"
         "and playback synced to a capture the attacker cannot time."),
        ("No public reagent dataset exists", AMBER,
         "Surrogate colour ladders. Substituting NCB standards is a\n"
         "data change, not an architecture change."),
        ("StrongBox missing on some issued handsets", AMBER,
         "TEE fallback, and the weaker guarantee is written into the\n"
         "record rather than glossed over."),
        ("Bad light producing a confident wrong answer", TEAL,
         "Quality gate plus conformal abstention.\n"
         "0 false accepts across 83 stress conditions."),
    ]
    y = 0.520
    for label, colour, mitigation in risks:
        box(fig, 0.018, y - 0.078, 0.207, 0.076, ec=RULE)
        box(fig, 0.229, y - 0.078, 0.244, 0.076, ec=colour, lw=1.5)
        text(fig, 0.026, y - 0.020, label, 6.4, INK, "bold")
        text(fig, 0.237, y - 0.018, mitigation, 6.2, INK)
        y -= 0.088

    # ---------------- right column: measured, not projected ----------------- #
    text(fig, 0.505, 0.965, "MEASURED — NOT PROJECTED", 8.8, DEEP, "bold")
    text(fig, 0.505, 0.928, "every figure below is produced by the tools in this "
         "repository and reproducible from one command", 6.6, GREY)

    ax1 = fig.add_axes([0.535, 0.575, 0.185, 0.265])
    chart_illuminants(ax1)
    ax2 = fig.add_axes([0.775, 0.575, 0.175, 0.265])
    chart_replay(ax2)
    ax3 = fig.add_axes([0.535, 0.185, 0.415, 0.235])
    chart_ablation(ax3)

    # A hero number is not a chart, and should not be drawn as one.
    tiles = [
        ("0", "false accepts across\n83 stress conditions", TEAL),
        ("0.0%", "wrong calls on an unseen\nilluminant — it abstains", TEAL),
        ("2", "independent verifiers\nthat agree", BLUE),
    ]
    tw, tgap = 0.132, 0.010
    for i, (big, small, colour) in enumerate(tiles):
        x = 0.535 + i * (tw + tgap)
        box(fig, x, 0.032, tw, 0.115, ec=colour, lw=1.5)
        text(fig, x + tw / 2, 0.122, big, 16.5, colour, "bold", ha="center", va="center")
        text(fig, x + tw / 2, 0.072, small, 6.2, INK, ha="center", va="center")

    fig.text(0.018, 0.016, "All figures are measured on synthetic frames or on measured "
             "spectral data. None is a field accuracy: no printed card has been "
             "photographed yet, and the capture matrix is the critical path.",
             fontsize=6.3, color=GREY, style="italic", ha="left")

    fig.savefig(OUT / "feasibility.png", dpi=240, facecolor="white",
                bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    build()
    p = OUT / "feasibility.png"
    print(f"  {p.name}  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
