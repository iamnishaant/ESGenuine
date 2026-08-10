"""
ESGenuine — paper figures
=========================

Generates the figures for the ICMLDE submission as **vector PDF** (for the camera-ready)
and PNG (for previewing), from the committed fixtures.

DESIGN CONSTRAINTS, and why each one is here
--------------------------------------------
* **Numbers are computed, never typed.** Every value is pulled from run_ablation /
  run_evaluation / run_baselines / run_bootstrap at render time. A figure that disagrees
  with the results table is the classic late-stage paper bug; making it impossible costs
  ten seconds of compute.
* **Colourblind-safe.** Two-series blue/orange, validated: worst adjacent pair ΔE 24.7
  (protan), 32.7 (tritan), 33.6 (normal) — all well above the ΔE 8 floor.
* **Greyscale-safe.** Procedia may print mono, so colour is never the only encoding:
  series 2 carries a hatch, markers differ in shape, and every series is directly
  labelled. A reader with a B&W printout loses nothing.
* **No dual axes.** Figure 2 shows two different measures (a precision composite and a
  recall rate), so it uses stacked small multiples on a shared x-axis rather than
  twinning y. Dual-axis charts let the author choose the scales and therefore the
  conclusion.
* **Vector out.** PDF, with fonts as text rather than paths, so the figures stay
  searchable and rescale cleanly in the proof.

Run:
    python backend/scripts/make_figures.py                 # -> docs/figures/*.pdf + *.png
    python backend/scripts/make_figures.py --outdir <dir>
    python backend/scripts/make_figures.py -B 2000         # bootstrap resamples
"""
import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import matplotlib                                                   # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                     # noqa: E402
import numpy as np                                                  # noqa: E402

import run_evaluation as ev                                         # noqa: E402
import run_bootstrap as bs                                          # noqa: E402
from run_ablation import CASES, STAGES, _load, _run_stage           # noqa: E402
from run_baselines import _lane_recall                              # noqa: E402

_GOLD = _REPO / "backend" / "tests" / "eval"

# ── palette (validated: scripts/validate_palette.js, all checks PASS) ────────────────
BLUE   = "#2a78d6"     # series 1 — BRSR statutory (form-heavy)
ORANGE = "#eb6834"     # series 2 — IR narrative
INK    = "#1a1a19"
MUTED  = "#6b6a66"
GRID   = "#dcdcd8"

# Short regime labels. The full CASES labels carry provenance warnings that belong in
# prose, not on an axis.
REGIME = ["BRSR statutory (Tata Power)", "IR narrative (Shell)"]
SERIES = [dict(color=BLUE, hatch=None, marker="o", ls="-"),
          dict(color=ORANGE, hatch="///", marker="s", ls="--")]

STAGE_SHORT = ["raw LLM", "+ontology", "+FY repair", "+value-in-table",
               "+gate fixes", "+furniture drop"]


def _rc():
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["DejaVu Serif", "Times New Roman", "Nimbus Roman", "serif"],
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9.5,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.edgecolor": MUTED,
        "axes.linewidth": 0.6,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,      # embed as TrueType -> selectable text, not outlines
        "ps.fonttype": 42,
    })


def _despine(ax, keep=("left", "bottom")):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)
    ax.set_axisbelow(True)


# ── data ────────────────────────────────────────────────────────────────────────────

def collect(B: int) -> dict:
    """Everything the figures need, computed from the committed fixtures."""
    out = {"cases": []}
    for (label, fixture, cache, gold_file), regime in zip(CASES, REGIME):
        claims, md = _load(fixture, cache)
        gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))

        comps, recalls, kept_n = [], [], []
        for i in range(len(STAGES)):
            kept = _run_stage(i, claims, md)
            rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in kept]
            comps.append(ev.evaluate(gold, rows)["metrics"]["precision_composite"])
            recalls.append(_lane_recall(kept, md)["recall"])
            kept_n.append(len(kept))

        abl = bs.bootstrap_ablation(label, fixture, cache, gold_file, B)
        consecutive = {(d["from"], d["to"]): d for d in abl["deltas"]}

        final = _run_stage(len(STAGES) - 1, claims, md)
        rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in final]
        metrics = bs.bootstrap_rates(bs._outcomes(gold, rows), B)

        out["cases"].append({
            "regime": regime, "composites": comps, "recalls": recalls,
            "kept": kept_n, "deltas": consecutive, "metrics": metrics,
        })
    return out


# ── figure 1 — the central claim ────────────────────────────────────────────────────

def fig_ablation(data, outdir: Path):
    """(a) cumulative score by stage; (b) per-stage delta with 95% CI, by regime.

    Panel (b) is the paper's thesis in one image: the tallest bar is a DIFFERENT stage
    for each regime, and the intervals do not overlap.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.9, 2.9),
                                   gridspec_kw={"width_ratios": [1, 1.25]})

    # (a) cumulative
    x = np.arange(len(STAGES))
    for case, s in zip(data["cases"], SERIES):
        ax1.plot(x, case["composites"], color=s["color"], ls=s["ls"], lw=1.6,
                 marker=s["marker"], ms=4.5, mfc="white", mew=1.4, label=case["regime"],
                 clip_on=False, zorder=3)
        ax1.annotate(f"{case['composites'][-1]:.1f}",
                     (x[-1], case["composites"][-1]), textcoords="offset points",
                     xytext=(4, -1), fontsize=8, color=s["color"], weight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"S{i}" for i in x])
    ax1.set_xlabel("cumulative repair stage")
    ax1.set_ylabel("precision composite")
    ax1.set_ylim(60, 102)
    ax1.set_xlim(-0.2, len(STAGES) - 0.55)
    ax1.grid(axis="x", visible=False)
    ax1.set_title("(a) cumulative", loc="left", color=MUTED)
    _despine(ax1)

    # (b) per-stage deltas with CIs
    pairs = [(STAGES[i], STAGES[i + 1]) for i in range(len(STAGES) - 1)]
    y = np.arange(len(pairs))
    h = 0.36
    for k, (case, s) in enumerate(zip(data["cases"], SERIES)):
        ds = [case["deltas"][p] for p in pairs]
        pts = [d["point"] for d in ds]
        lo = [d["point"] - d["ci_lo"] for d in ds]
        hi = [d["ci_hi"] - d["point"] for d in ds]
        off = (h / 2 + 0.01) * (1 if k else -1)
        ax2.barh(y + off, pts, height=h, color=s["color"], hatch=s["hatch"],
                 edgecolor="white", linewidth=0.8, label=case["regime"], zorder=2)
        ax2.errorbar(pts, y + off, xerr=[lo, hi], fmt="none", ecolor=INK,
                     elinewidth=0.8, capsize=2, capthick=0.8, zorder=4)

        for yi, d in zip(y + off, ds):
            # A stage measured at exactly zero draws no bar, which reads as MISSING DATA
            # rather than as the finding it is. Mark it so the null is visible.
            if abs(d["point"]) < 0.05:
                ax2.plot([0], [yi], marker="|", ms=6, mew=1.2, color=MUTED, zorder=5)
            # Label clear of the CI whisker, not at the bar end — at the bar end the
            # upper cap strikes through the text.
            label = f"{d['point']:+.1f}" + ("" if d["excludes_zero"] else "  n.s.")
            ax2.annotate(label, (max(d["point"], d["ci_hi"]), yi),
                         textcoords="offset points", xytext=(5, -2.6),
                         fontsize=7.5, color=INK if d["excludes_zero"] else MUTED)

    ax2.set_yticks(y)
    ax2.set_yticklabels([STAGE_SHORT[i + 1] for i in range(len(pairs))])
    ax2.invert_yaxis()
    ax2.set_xlabel("Δ precision composite (95% CI)")
    ax2.axvline(0, color=MUTED, lw=0.8, zorder=1)
    ax2.grid(axis="y", visible=False)
    ax2.set_xlim(-1.5, 34)
    ax2.set_title("(b) marginal contribution per stage", loc="left", color=MUTED)
    _despine(ax2)

    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.10))
    fig.tight_layout()
    _save(fig, outdir, "fig1_ablation_by_regime")


# ── figure 2 — the trade-off ────────────────────────────────────────────────────────

def fig_tradeoff(data, outdir: Path):
    """Precision composite and table-fact recall across the same stages.

    Stacked small multiples on a shared x-axis, NOT a twinned y-axis: the two panels
    measure different things, and a dual axis would let the scaling choose the story.
    Tata only — Shell's recall is flat at 9.2% because that fixture is text-dominant
    (13 table claims of 247) with partial page coverage, so its recall describes the
    fixture rather than the pipeline.
    """
    case = data["cases"][0]
    x = np.arange(len(STAGES))

    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(4.4, 3.6), sharex=True,
                                         gridspec_kw={"hspace": 0.18})

    ax_top.plot(x, case["composites"], color=BLUE, lw=1.7, marker="o", ms=4.5,
                mfc="white", mew=1.4, clip_on=False, zorder=3)
    ax_top.set_ylabel("precision composite")
    # headroom for the end label, which sits ABOVE the final point — the line runs
    # up-and-right through the space to its left, so a left-side label gets struck through
    ax_top.set_ylim(60, 108)
    ax_top.grid(axis="x", visible=False)
    ax_top.annotate(f"{case['composites'][0]:.1f}", (0, case["composites"][0]),
                    textcoords="offset points", xytext=(2, -11), fontsize=8, color=BLUE)
    ax_top.annotate(f"{case['composites'][-1]:.1f}  (+{case['composites'][-1]-case['composites'][0]:.1f})",
                    (x[-1], case["composites"][-1]), textcoords="offset points",
                    xytext=(2, 9), fontsize=8, color=BLUE, weight="bold", ha="right")
    _despine(ax_top)

    rec = [100 * r for r in case["recalls"]]
    ax_bot.plot(x, rec, color=ORANGE, lw=1.7, ls="--", marker="s", ms=4.5,
                mfc="white", mew=1.4, clip_on=False, zorder=3)
    ax_bot.set_ylabel("table-fact recall (%)")
    ax_bot.set_ylim(50, 63)
    ax_bot.grid(axis="x", visible=False)
    ax_bot.annotate(f"{rec[0]:.1f}%", (0, rec[0]), textcoords="offset points",
                    xytext=(2, 5), fontsize=8, color=ORANGE)
    # below the final point: the line falls steeply into it, so the space to its
    # upper-left (the previous label position) is exactly where the line runs
    ax_bot.annotate(f"{rec[-1]:.1f}%  ({rec[-1]-rec[0]:+.1f} pp)", (x[-1], rec[-1]),
                    textcoords="offset points", xytext=(2, -14), fontsize=8,
                    color=ORANGE, weight="bold", ha="right")
    _despine(ax_bot)

    # mark the two stages that actually cost recall
    for ax in (ax_top, ax_bot):
        for i in (2, 5):
            ax.axvline(i, color=MUTED, lw=0.6, ls=":", zorder=1)

    ax_bot.set_xticks(x)
    ax_bot.set_xticklabels(STAGE_SHORT, rotation=30, ha="right")
    ax_bot.set_xlabel("cumulative repair stage")
    fig.align_ylabels([ax_top, ax_bot])
    _save(fig, outdir, "fig2_precision_recall_tradeoff")


# ── figure 3 — where the regimes differ ─────────────────────────────────────────────

def fig_metrics(data, outdir: Path):
    """Per-field rates for the shipped configuration, both regimes, with 95% CIs.

    Shows WHERE the harder document is harder — node accuracy and unit canonicalisation
    — rather than collapsing it into one composite.
    """
    keys = ["candidate_precision", "aspect_node_acc", "aspect_pillar_acc",
            "value_acc", "unit_base_acc", "type_acc"]
    nice = ["candidate\nprecision", "aspect node", "aspect pillar",
            "value", "unit family", "claim type"]

    fig, ax = plt.subplots(figsize=(6.9, 2.5))
    x = np.arange(len(keys))
    w = 0.36
    for k, (case, s) in enumerate(zip(data["cases"], SERIES)):
        pts, lo, hi = [], [], []
        for key in keys:
            m = case["metrics"][key]
            p = 100 * m["point"] if m["point"] is not None else 0.0
            pts.append(p)
            lo.append(p - 100 * m["ci_lo"] if m["ci_lo"] is not None else 0)
            hi.append(100 * m["ci_hi"] - p if m["ci_hi"] is not None else 0)
        off = (w / 2 + 0.01) * (1 if k else -1)
        ax.bar(x + off, pts, width=w, color=s["color"], hatch=s["hatch"],
               edgecolor="white", linewidth=0.8, label=case["regime"], zorder=2)
        ax.errorbar(x + off, pts, yerr=[lo, hi], fmt="none", ecolor=INK,
                    elinewidth=0.8, capsize=2, capthick=0.8, zorder=4)

        # CEILING MARKER. A rate with no observed errors bootstraps to a degenerate
        # [100, 100] interval, so its bar renders with a vanishing whisker and reads as
        # "measured with certainty". It is not: it is a boundary artifact on n<=37. Mark
        # those bars with a dagger and disclose the real bound in the caption.
        for xi, p in zip(x + off, pts):
            if p >= 99.95:
                ax.annotate("†", (xi, 100), textcoords="offset points", xytext=(0, 3),
                            ha="center", fontsize=8, color=INK)

    ax.set_xticks(x)
    ax.set_xticklabels(nice)
    ax.set_ylabel("accuracy (%)")
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(axis="x", visible=False)
    ax.legend(loc="lower left", frameon=False, ncol=2, bbox_to_anchor=(0.0, -0.42))
    _despine(ax)
    fig.tight_layout()
    _save(fig, outdir, "fig3_per_metric_by_regime")


def _save(fig, outdir: Path, stem: str):
    outdir.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        p = outdir / f"{stem}.{ext}"
        fig.savefig(p)
        print(f"  wrote {p.relative_to(_REPO)}")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Render the paper figures from committed fixtures.")
    ap.add_argument("--outdir", default=str(_REPO / "docs" / "figures"))
    ap.add_argument("-B", type=int, default=2000, help="bootstrap resamples")
    a = ap.parse_args()

    _rc()
    print(f"computing (B={a.B} bootstrap resamples)...")
    data = collect(a.B)
    out = Path(a.outdir)
    fig_ablation(data, out)
    fig_tradeoff(data, out)
    fig_metrics(data, out)
    print("\ndone. PDF for the camera-ready, PNG for previewing.")
