"""
ESGenuine — bootstrap CONFIDENCE INTERVALS (roadmap 6.7)
=========================================================

Every number this project reports is a point estimate computed on 50 claims. None has
ever carried an interval. On n=50 the 95% CI around a rate near 0.90 is roughly ±8
points, which is wide enough to change what the numbers mean:

    "96.1 in-sample vs 89.7 out-of-sample" reads as a 6.4-point generalization gap.
    With intervals attached it may well read as "these two are not distinguishable."

A reviewer will ask. Answering costs seconds of compute — the gold sets are tiny and the
harnesses are offline — so there is no reason not to have it before submission.

WHAT IT COMPUTES
----------------
1. **Per-metric CIs** on every rate in `run_evaluation.py`, for each gold set.
   Nonparametric bootstrap: resample the gold CLAIMS with replacement (the claim is the
   sampling unit), recompute every rate, take the 2.5th/97.5th percentiles.

2. **PAIRED CIs on the ablation deltas** (S1→S5 and any stage pair). This is the one that
   matters for the paper's central claim. Each bootstrap resample scores BOTH stages on
   the SAME resampled claims, so the delta distribution accounts for the fact that the
   stages are measured on identical data. An unpaired comparison would throw away that
   structure and give needlessly wide intervals — the deltas here are large and paired
   testing is what shows it.

   If a delta's CI excludes zero, that stage's contribution is statistically supported at
   this sample size. If it does not, say so — an honest null is far cheaper to defend than
   a claim a reviewer overturns.

WHAT IT DOES NOT FIX
--------------------
An interval quantifies SAMPLING noise. It says nothing about BIAS. Both gold sets are
development sets (the ontology was tuned against each; six labels were rewritten to match
new taxonomy nodes), so a tight CI here means "this development-set number is precisely
estimated", never "this number generalizes". Contamination and sampling error are
independent problems and the bootstrap addresses only the second.

Likewise the composite still has no recall term. A tight interval on a precision-only
metric is a precise measurement of half the picture.

Run:
    python backend/scripts/run_bootstrap.py                    # both gold sets + ablation
    python backend/scripts/run_bootstrap.py -B 10000           # more resamples
    python backend/scripts/run_bootstrap.py --markdown         # paper-ready table
    python backend/scripts/run_bootstrap.py --json out.json
"""
import argparse
import json
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_evaluation as ev                                       # noqa: E402
from run_ablation import CASES as ABL_CASES, STAGES, _load, _run_stage   # noqa: E402

_GOLD = _REPO / "backend" / "tests" / "eval"

SEED = 42
DEFAULT_B = 2000

# The five rates the composite averages, plus pillar accuracy for reference.
RATES = ("candidate_precision", "aspect_node_acc", "aspect_pillar_acc",
         "value_acc", "unit_base_acc", "type_acc")


# ─────────────────────────────────────────── per-claim outcomes -> rates

def _outcomes(gold: dict, claims_json: list) -> list:
    """Score once, then keep the per-claim boolean outcomes.

    Resampling these is exactly equivalent to re-running `evaluate` on a resampled gold
    set, and is ~1000x faster because the extraction is indexed once instead of per
    resample. Presence of a key encodes the denominator condition `evaluate` applied
    (e.g. `value_ok` is absent for ambiguous or non-numeric golds), so the reconstructed
    rates match the harness by construction rather than by a parallel reimplementation.
    """
    return ev.evaluate(gold, claims_json)["per_claim"]


def _rates_from(rows: list) -> dict:
    num = {k: 0 for k in RATES}
    den = {k: 0 for k in RATES}

    for r in rows:
        if not r.get("matched"):
            continue
        den["candidate_precision"] += 1
        if r.get("is_esg_claim"):
            num["candidate_precision"] += 1
        for key, field in (("aspect_node_acc", "node_ok"), ("aspect_pillar_acc", "pillar_ok"),
                           ("value_acc", "value_ok"), ("unit_base_acc", "unit_ok"),
                           ("type_acc", "type_ok")):
            if field in r:
                den[key] += 1
                if r[field]:
                    num[key] += 1

    out = {k: (num[k] / den[k] if den[k] else None) for k in RATES}
    parts = [out[k] for k in ("candidate_precision", "aspect_node_acc", "value_acc",
                              "unit_base_acc", "type_acc") if out[k] is not None]
    out["precision_composite"] = round(100.0 * sum(parts) / len(parts), 1) if parts else None
    out["_den"] = den
    return out


def _ci(samples: list, lo=2.5, hi=97.5):
    vals = sorted(v for v in samples if v is not None)
    if not vals:
        return None, None
    def pick(p):
        idx = min(len(vals) - 1, max(0, int(round(p / 100.0 * (len(vals) - 1)))))
        return vals[idx]
    return pick(lo), pick(hi)


def bootstrap_rates(rows: list, B: int, seed: int = SEED) -> dict:
    rng = random.Random(seed)
    n = len(rows)
    point = _rates_from(rows)

    draws = {k: [] for k in list(RATES) + ["precision_composite"]}
    for _ in range(B):
        resample = [rows[rng.randrange(n)] for _ in range(n)]
        r = _rates_from(resample)
        for k in draws:
            draws[k].append(r[k])

    out = {}
    for k in draws:
        lo, hi = _ci(draws[k])
        out[k] = {"point": point[k], "ci_lo": lo, "ci_hi": hi,
                  "n": point["_den"].get(k) if k in point["_den"] else n}
    return out


# ─────────────────────────────────────────── paired ablation deltas

def bootstrap_ablation(case_label: str, fixture: str, cache: str, gold_file: str,
                       B: int, seed: int = SEED) -> dict:
    """Paired bootstrap on every consecutive stage delta plus S1->S5 and S0->S5."""
    claims, md_by_page = _load(fixture, cache)
    gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))

    # Per-stage outcome rows, aligned by gold claim index so a resample indexes all
    # stages identically — that alignment IS the pairing.
    per_stage = []
    for i in range(len(STAGES)):
        kept = _run_stage(i, claims, md_by_page)
        rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in kept]
        per_stage.append(_outcomes(gold, rows))

    n = len(per_stage[0])
    points = [_rates_from(s)["precision_composite"] for s in per_stage]

    rng = random.Random(seed)
    delta_draws = {}
    pairs = [(i, i + 1) for i in range(len(STAGES) - 1)]
    pairs += [(1, len(STAGES) - 1), (0, len(STAGES) - 1)]
    for p in pairs:
        delta_draws[p] = []

    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        comps = []
        for s in per_stage:
            comps.append(_rates_from([s[i] for i in idx])["precision_composite"])
        for (a, b) in pairs:
            if comps[a] is not None and comps[b] is not None:
                delta_draws[(a, b)].append(comps[b] - comps[a])

    deltas = []
    for (a, b) in pairs:
        lo, hi = _ci(delta_draws[(a, b)])
        point = (points[b] - points[a]) if (points[a] is not None and points[b] is not None) else None
        deltas.append({
            "from": STAGES[a], "to": STAGES[b],
            "point": round(point, 1) if point is not None else None,
            "ci_lo": round(lo, 1) if lo is not None else None,
            "ci_hi": round(hi, 1) if hi is not None else None,
            "excludes_zero": bool(lo is not None and hi is not None and (lo > 0 or hi < 0)),
        })

    return {"case": case_label, "gold": gold_file, "n_gold": n,
            "stage_points": points, "deltas": deltas}


# ─────────────────────────────────────────── reporting

def _fmt(v, pct=True):
    if v is None:
        return "  --  "
    return f"{100 * v:5.1f}%" if pct else f"{v:5.1f}"


def _print(res):
    for case, d in res["rates"].items():
        print(f"\n{'=' * 84}\n{case}   [n={d['n_gold']} gold claims, B={res['B']} resamples]\n{'=' * 84}")
        print(f"{'metric':<24}{'point':>9}{'95% CI':>22}{'width':>9}   n")
        print("-" * 84)
        for k in list(RATES) + ["precision_composite"]:
            m = d["metrics"][k]
            is_comp = k == "precision_composite"
            p, lo, hi = m["point"], m["ci_lo"], m["ci_hi"]
            if p is None:
                continue
            width = (hi - lo) if (lo is not None and hi is not None) else None
            if is_comp:
                print("-" * 84)
                print(f"{k:<24}{p:>9.1f}{f'[{lo:.1f}, {hi:.1f}]':>22}"
                      f"{width:>9.1f}   {m['n']}")
            else:
                print(f"{k:<24}{_fmt(p):>9}{f'[{100 * lo:.1f}%, {100 * hi:.1f}%]':>22}"
                      f"{100 * width:>8.1f}pp   {m['n']}")

    print(f"\n\n{'=' * 84}\nPAIRED ablation deltas — same resampled claims scored at both stages\n{'=' * 84}")
    for ab in res["ablation"]:
        print(f"\n{ab['case']}  (n={ab['n_gold']})")
        print(f"  {'delta':<44}{'point':>8}{'95% CI':>20}   verdict")
        print("  " + "-" * 82)
        for d in ab["deltas"]:
            label = f"{d['from']} -> {d['to']}"
            verdict = "SUPPORTED (excludes 0)" if d["excludes_zero"] else "not distinguishable from 0"
            ci = f"[{d['ci_lo']:+.1f}, {d['ci_hi']:+.1f}]"
            print(f"  {label:<44}{d['point']:>+8.1f}{ci:>20}   {verdict}")

    print("\n" + "=" * 84)
    print("READ THIS BEFORE QUOTING ANY INTERVAL")
    print("  An interval quantifies SAMPLING noise only. Both gold sets are DEVELOPMENT")
    print("  sets — the ontology was tuned against each and 6 labels were rewritten to")
    print("  match new taxonomy nodes — so a tight CI means the development-set number is")
    print("  precisely estimated, NOT that it generalizes. Bias and variance are separate")
    print("  problems; this script addresses only variance.")
    print("  The composite also has no recall term (see run_recall.py).")
    print()
    print("  CEILING EFFECT: a rate where every scored claim is correct yields the")
    print("  degenerate interval [100%, 100%] — every resample of all-correct data is")
    print("  all-correct. That is an artifact of the percentile bootstrap at the boundary,")
    print("  NOT evidence of zero uncertainty. On n=37 the true upper bound is fine but the")
    print("  lower bound is not 100%: report a one-sided Clopper-Pearson/rule-of-three")
    print("  bound instead (~92% lower bound at n=37), or state 'no errors observed in N'.")
    print("=" * 84)


def _print_markdown(res):
    print("\n<!-- generated by backend/scripts/run_bootstrap.py — do not hand-edit -->")
    for case, d in res["rates"].items():
        print(f"\n**{case}** — n={d['n_gold']} gold claims, {res['B']} bootstrap resamples\n")
        print("| metric | point | 95% CI | n |")
        print("|---|--:|:--:|--:|")
        for k in list(RATES) + ["precision_composite"]:
            m = d["metrics"][k]
            if m["point"] is None:
                continue
            if k == "precision_composite":
                print(f"| **{k}** | **{m['point']:.1f}** | [{m['ci_lo']:.1f}, {m['ci_hi']:.1f}] | {m['n']} |")
            else:
                print(f"| {k} | {100 * m['point']:.1f}% | "
                      f"[{100 * m['ci_lo']:.1f}%, {100 * m['ci_hi']:.1f}%] | {m['n']} |")
    print("\n**Paired ablation deltas** (same resampled claims scored at both stages)\n")
    print("| document | delta | point | 95% CI | excludes 0 |")
    print("|---|---|--:|:--:|:--:|")
    for ab in res["ablation"]:
        for d in ab["deltas"]:
            print(f"| {ab['case']} | {d['from']} → {d['to']} | {d['point']:+.1f} | "
                  f"[{d['ci_lo']:+.1f}, {d['ci_hi']:+.1f}] | {'yes' if d['excludes_zero'] else '**no**'} |")
    print("\n> Intervals quantify sampling noise only. Both gold sets are development sets, "
          "so a tight interval means the development-set estimate is precise — not that it "
          "generalizes.")


def run(B: int = DEFAULT_B, seed: int = SEED) -> dict:
    rates = {}
    ablation = []
    for label, fixture, cache, gold_file in ABL_CASES:
        gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))
        claims, md_by_page = _load(fixture, cache)
        shipped = _run_stage(len(STAGES) - 1, claims, md_by_page)
        rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in shipped]
        outcomes = _outcomes(gold, rows)
        rates[label] = {"gold": gold_file, "n_gold": len(outcomes),
                        "metrics": bootstrap_rates(outcomes, B, seed)}
        ablation.append(bootstrap_ablation(label, fixture, cache, gold_file, B, seed))
    return {"B": B, "seed": seed, "rates": rates, "ablation": ablation}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Bootstrap CIs for the gold metrics and paired ablation deltas.")
    ap.add_argument("-B", type=int, default=DEFAULT_B, help=f"resamples (default {DEFAULT_B})")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()

    res = run(a.B, a.seed)
    _print_markdown(res) if a.markdown else _print(res)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {a.json_out}")
