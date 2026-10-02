"""Draws the architecture and dialogue-loop diagrams used in the report."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "figures"
INK, ACCENT, PRUSSIAN, FILL, FILL2 = "#1f2a36", "#a33b2b", "#2b4a6f", "#f7f1e6", "#e9eff6"
plt.rcParams.update({"font.family": "serif", "figure.dpi": 220})


def box(ax, x, y, w, h, title, body="", fc=FILL, ec=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=1.1))
    ax.text(x + w / 2, y + h - 0.13, title, ha="center", va="top", fontsize=9.2, weight="bold", color=INK)
    if body:
        ax.text(x + w / 2, y + h - 0.42, body, ha="center", va="top", fontsize=7.6, color="#3b4552", linespacing=1.35)


def arrow(ax, a, b, color=INK, style="-|>", ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=11, color=color, lw=1.1, ls=ls))


def architecture():
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.text(0.1, 5.85, "OFFLINE  (runs once at start-up)", fontsize=8, color=ACCENT, weight="bold", va="top")
    box(ax, 0.1, 4.0, 2.2, 1.55, "Knowledge base", "Kaggle disease–symptom\ndata: 4,920 rows,\n41 diseases, 132 symptoms")
    box(ax, 2.75, 4.0, 2.2, 1.55, "Leakage audit", "de-duplicate to 304\nunique profiles; group\nsplit by profile")
    box(ax, 5.4, 4.0, 2.2, 1.55, "Evidence model", "smoothed P(symptom|disease)\n+ 3% report-slip noise\n(41 × 132 table)")
    box(ax, 7.85, 4.0, 2.05, 1.55, "Side tables", "descriptions,\nprecautions,\nseverity weights")
    arrow(ax, (2.3, 4.78), (2.75, 4.78))
    arrow(ax, (4.95, 4.78), (5.4, 4.78))

    ax.text(0.1, 3.6, "ONLINE  (every chat turn)", fontsize=8, color=ACCENT, weight="bold", va="top")
    box(ax, 0.1, 1.55, 2.2, 1.75, "Symptom NLU", "lay lexicon + char\nn-gram fuzzy match\n+ negation scope", fc=FILL2, ec=PRUSSIAN)
    box(ax, 2.75, 1.55, 2.2, 1.75, "Evidence state", "each symptom:\npresent / absent /\nunknown", fc=FILL2, ec=PRUSSIAN)
    box(ax, 5.4, 1.55, 2.2, 1.75, "Bayesian posterior", "condition only on\nknown symptoms;\nunknowns marginalised", fc=FILL2, ec=PRUSSIAN)
    box(ax, 7.85, 1.55, 2.05, 1.75, "Policy", "red flag?  → alert\np ≥ 0.90 → conclude\nelse → ask max-EIG\nsymptom", fc=FILL2, ec=PRUSSIAN)
    arrow(ax, (2.3, 2.42), (2.75, 2.42))
    arrow(ax, (4.95, 2.42), (5.4, 2.42))
    arrow(ax, (7.6, 2.42), (7.85, 2.42))
    arrow(ax, (6.5, 4.0), (6.5, 3.3), color=ACCENT)
    arrow(ax, (8.88, 4.0), (8.88, 3.3), color=ACCENT)

    box(ax, 0.1, 0.05, 4.85, 1.1, "Web chat (FastAPI + HTML/JS)", "user text in  ·  question / result / alert out")
    box(ax, 5.4, 0.05, 4.5, 1.1, "Live differential panel", "top-5 posterior · entropy · evidence · triage")
    arrow(ax, (1.2, 1.15), (1.2, 1.55))
    arrow(ax, (8.88, 1.55), (8.88, 1.15))
    arrow(ax, (5.4, 0.6), (4.95, 0.6))
    ax.annotate("answer to the question\nupdates the evidence state", xy=(3.85, 1.55), xytext=(3.85, 1.25),
                fontsize=6.8, ha="center", color="#5b6470")
    fig.tight_layout()
    fig.savefig(OUT / "fig_architecture.png", bbox_inches="tight")
    plt.close(fig)


def loop():
    fig, ax = plt.subplots(figsize=(8.6, 3.3))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3.6)
    ax.axis("off")
    steps = [
        ("1. Patient speaks", "\"fever and chills,\nno cough\""),
        ("2. Extract", "high fever +, chills +\ncough −"),
        ("3. Posterior", "p(d | evidence)\nover 41 diseases"),
        ("4. Score questions", "EIG(s) for every\nunasked symptom"),
        ("5. Ask best one", "\"Do you also have\nloss of appetite?\""),
    ]
    for i, (t, b) in enumerate(steps):
        box(ax, 0.1 + i * 1.98, 1.6, 1.78, 1.6, t, b, fc=FILL2 if i in (2, 3) else FILL,
            ec=PRUSSIAN if i in (2, 3) else INK)
        if i < 4:
            arrow(ax, (1.88 + i * 1.98, 2.4), (2.08 + i * 1.98, 2.4))
    arrow(ax, (9.0, 1.6), (1.0, 1.6), color=ACCENT, style="-|>", ls="--")
    ax.text(5.0, 1.25, "yes / no answer joins the evidence — repeat until p ≥ 0.90, EIG < 0.02 bits, or 8 questions",
            ha="center", fontsize=8, color=ACCENT)
    ax.text(5.0, 0.55, r"EIG(s) = H(D) $-$ [ P(yes) H(D | s = yes) + P(no) H(D | s = no) ],   "
            r"P(yes) = $\Sigma_d$ p(d) $\theta_{ds}$", ha="center", fontsize=9.5, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_loop.png", bbox_inches="tight")
    plt.close(fig)


architecture()
loop()
