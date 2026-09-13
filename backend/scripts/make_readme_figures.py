"""
ESGenuine — conclusion-report figures
=====================================

Three plots for `conclusion/README.md`, rendered as PNG (GitHub cannot display PDF).

Every value is COMPUTED FROM THE COMMITTED FIXTURES at render time — nothing is
hardcoded — so a figure cannot drift away from the numbers in the docs. Same
discipline as `make_figures.py`, different audience: this one is read on a phone in a
browser tab, so it is bigger-typed, lighter on annotation, and light-theme only.

  fig_readme_1_ablation   which repair stage earns the gain, per disclosure regime
  fig_readme_2_tradeoff   what precision-oriented repair costs in recall
  fig_readme_3_extractor  matched-input model comparison (the P1 result)

Run:  python backend/scripts/make_readme_figures.py
Out:  docs/images/*.png
"""
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

import run_ablation as ab                                           # noqa: E402
import run_recall as rr                                             # noqa: E402
from extractors.models import ExtractedClaim                        # noqa: E402
from extractors.quality_gate import _value_in_source                # noqa: E402

_FIX = _REPO / "backend" / "tests" / "eval" / "fixtures"
_OUT = _REPO / "conclusion" / "images"

# Colourblind-safe (Okabe-Ito). Series 2 also gets a hatch so greyscale survives.
C_BRSR, C_IR = "#0072B2", "#D55E00"
C_GOOD, C_WARN = "#009E73", "#CC79A7"
GRID = dict(color="#D8D8D8", lw=0.8)


def _rc():
    plt.rcParams.update({
        "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
        "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.facecolor": "white", "figure.facecolor": "white",
        "axes.titleweight": "bold",
    })


def _save(fig, stem):
    _OUT.mkdir(parents=True, exist_ok=True)
    p = _OUT / f"{stem}.png"
    fig.savefig(p)
    plt.close(fig)
    print(f"  wrote {p.relative_to(_REPO)}")


# ───────────────────────────────────────────────────── data

def _ablation():
    res = ab.run()
    (brsr_label, ir_label) = list(res)
    return res[brsr_label]["stages"], res[ir_label]["stages"]


def _load(name):
    p = _FIX / name
    if not p.exists():
        return None
    return [ExtractedClaim.model_validate(json.loads(l))
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _pages(cache):
    return {e["page_number"]: e["markdown"]
            for e in json.loads((_FIX / cache).read_text(encoding="utf-8"))}


def _by_page(claims):
    out = {}
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        pg = c.provenance.page_number
        if pg is None:
            continue
        try:
            out.setdefault(pg, []).append(float(c.metric.value))
        except (TypeError, ValueError):
            pass
    return out


def _recall(claims, pages, only=None):
    got = _by_page(claims)
    tot = hit = 0
    for pg, md in sorted(pages.items()):
        if only is not None and pg not in only:
            continue
        seen = set()
        for cell in rr._candidate_cells(md):
            if cell["is_form"]:
                continue
            key = (cell["row_label"].strip().lower(), cell["value"])
            if key in seen:
                continue
            seen.add(key)
            tot += 1
            if any(rr._close(cell["value"], v) for v in got.get(pg, [])):
                hit += 1
    return hit / tot if tot else 0.0


def _grounding(claims, pages, only=None):
    ok = n = 0
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        pg = c.provenance.page_number
        if only is not None and pg not in only:
            continue
        md = pages.get(pg)
        if md is None:
            continue
        try:
            v = float(c.metric.value)
        except (TypeError, ValueError):
            continue
        n += 1
        ok += bool(_value_in_source(v, md))
    return ok / n if n else 0.0


# ───────────────────────────────────────────────────── figures

def fig1(brsr, ir):
    """Cumulative composite by stage — the regime-dependence result."""
    names = ["S0\nno taxonomy", "S1\n+ontology", "S2\n+FY", "S3\n+value", "S4\n+gate", "S5\n+furniture"]
    b = [s["extraction_score"] for s in brsr]
    i = [s["extraction_score"] for s in ir]
    x = np.arange(len(names))

    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.plot(x, b, "-o", color=C_BRSR, lw=2.6, ms=8, label="BRSR statutory filing")
    ax.plot(x, i, "-s", color=C_IR, lw=2.6, ms=8, ls="--", label="IR narrative report")

    # Annotate the two stages that carry each regime — the actual finding.
    ax.annotate(f"gate: {b[4] - b[3]:+.1f}", xy=(4, b[4]), xytext=(3.05, b[4] + 7),
                color=C_BRSR, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_BRSR, lw=1.6))
    ax.annotate(f"taxonomy: {i[1] - i[0]:+.1f}", xy=(1, i[1]), xytext=(1.15, i[1] - 15),
                color=C_IR, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=C_IR, lw=1.6))

    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("precision composite")
    ax.set_ylim(60, 104)
    ax.set_title("Which repair stage earns the gain depends on the disclosure regime")
    ax.grid(axis="y", **GRID); ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    _save(fig, "fig_readme_1_ablation")


def fig2(brsr):
    """Precision rises while recall falls — the honesty figure."""
    claims, md = ab._load("tata_docling_full.jsonl", "docling_tata.json")
    stages = [0, 1, 2, 3, 4, 5]
    prec = [s["extraction_score"] for s in brsr]
    rec = [100 * _recall(ab._run_stage(s, claims, md), md) for s in stages]
    names = ["S0", "S1", "S2", "S3", "S4", "S5"]
    x = np.arange(len(names))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.6), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1], "hspace": 0.18})
    a1.plot(x, prec, "-o", color=C_GOOD, lw=2.6, ms=7)
    a1.set_ylabel("precision composite")
    a1.set_title("Precision-oriented repair is a trade, not a free win")
    a1.grid(axis="y", **GRID); a1.set_axisbelow(True)
    a1.annotate(f"{prec[0]:.1f} → {prec[-1]:.1f}  ({prec[-1]-prec[0]:+.1f})",
                xy=(0.02, 0.82), xycoords="axes fraction", color=C_GOOD, fontweight="bold")

    a2.plot(x, rec, "-s", color=C_WARN, lw=2.6, ms=7, ls="--")
    a2.set_ylabel("table-fact recall (%)")
    a2.grid(axis="y", **GRID); a2.set_axisbelow(True)
    a2.annotate(f"{rec[0]:.1f}% → {rec[-1]:.1f}%  ({rec[-1]-rec[0]:+.1f}pp)",
                xy=(0.02, 0.12), xycoords="axes fraction", color=C_WARN, fontweight="bold")
    a2.set_xticks(x); a2.set_xticklabels(names)
    a2.set_xlabel("cumulative repair stage (statutory filing)")
    fig.tight_layout()
    _save(fig, "fig_readme_2_tradeoff")


def fig3():
    """Matched-input extractor comparison — the P1 result."""
    cases = [("BRSR statutory", "docling_tata.json", "tata"),
             ("IR narrative", "docling_shell2022.json", "shell")]
    labels, inc_r, fro_r, inc_g, fro_g = [], [], [], [], []
    for label, cache, key in cases:
        inc, fro = _load(f"baseline_incumbent_{key}.jsonl"), _load(f"baseline_frontier_{key}.jsonl")
        if inc is None or fro is None:
            continue
        pages = _pages(cache)
        both = set(_by_page(inc)) & set(_by_page(fro))     # page-matched: fair to both
        labels.append(label)
        inc_r.append(100 * _recall(inc, pages, both)); fro_r.append(100 * _recall(fro, pages, both))
        inc_g.append(100 * _grounding(inc, pages, both)); fro_g.append(100 * _grounding(fro, pages, both))

    if not labels:
        print("  [skip] fig3 — matched arms not generated")
        return

    x = np.arange(len(labels)); w = 0.36
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.4))
    for ax, (lo, hi, title) in zip((a1, a2), [
            (inc_r, fro_r, "Table-fact recall"), (inc_g, fro_g, "Grounding precision")]):
        ax.bar(x - w / 2, lo, w, color="#999999", label="llama-3.3-70b", edgecolor="white")
        ax.bar(x + w / 2, hi, w, color=C_BRSR, label="gpt-oss-120b", edgecolor="white", hatch="//")
        for xi, (a, b) in enumerate(zip(lo, hi)):
            ax.text(xi - w / 2, a + 2, f"{a:.1f}", ha="center", fontsize=9.5)
            ax.text(xi + w / 2, b + 2, f"{b:.1f}", ha="center", fontsize=9.5, fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylim(0, 118); ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_title(title); ax.grid(axis="y", **GRID); ax.set_axisbelow(True)
    a1.set_ylabel("%")
    # Legend above both panels: inside either axes it lands on a bar (they reach 97-100%).
    handles, names = a1.get_legend_handles_labels()
    fig.legend(handles, names, frameon=False, loc="upper center", ncol=2, fontsize=10,
               bbox_to_anchor=(0.5, 0.965))
    fig.suptitle("Extractor choice dominates the tabular surface (identical input, page-matched)",
                 fontweight="bold", y=1.02)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    _save(fig, "fig_readme_3_extractor")


if __name__ == "__main__":
    _rc()
    print("computing from committed fixtures...")
    brsr, ir = _ablation()
    fig1(brsr, ir)
    fig2(brsr)
    fig3()
    print("done.")
