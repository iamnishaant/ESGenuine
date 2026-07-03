"""
ESGenuine - Extraction Quality Evaluation Harness
==================================================

Gives extraction a NUMBER (previously there was none - quality was assessed by
inspection only). Compares the extractor's output against a hand-labeled gold set
and reports precision/accuracy per field, so a change to the parser (e.g. the
Docling table-parse swap) can be measured, not eyeballed.

Metrics reported
----------------
  candidate_precision : of the claims the extractor emitted, how many are real
                        ESG claims (not page furniture / form questions /
                        hallucinated-value fragments). This is the single biggest
                        lever - a false claim poisons every downstream module.
  aspect_node_acc     : on real claims, exact normalized-aspect-node match
  aspect_pillar_acc   : on real claims, pillar match (emissions/social/water/...)
                        - a looser bar that ignores sub-node quibbles
  value_acc           : on real, non-ambiguous, numeric claims, |x-gold|/gold <= tol
  unit_base_acc       : on real, numeric claims, unit canonicalizes to the same family
  type_acc            : on real claims, performance/target/narrative match
  extraction_score    : composite 0-100 = 100 * mean(precision, node_acc, value_acc,
                        unit_acc, type_acc). One headline number to track.

Usage
-----
  python backend/scripts/run_evaluation.py                      # default paths
  python backend/scripts/run_evaluation.py --extraction <jsonl> --gold <json>
  python backend/scripts/run_evaluation.py --report            # per-claim table
  python backend/scripts/run_evaluation.py --json out.json     # machine-readable dump

Matching: gold <-> extraction by claim_id (falls back to normalized source_sentence,
so the same gold survives a re-extraction that changes claim_ids as long as the
sentence text is stable).
"""

import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACTION = _REPO / "backend" / "test_results" / "incremental_claims_backup.jsonl"
DEFAULT_GOLD = _REPO / "backend" / "tests" / "eval" / "gold_set.json"

VALUE_TOL = 0.05  # 5% relative tolerance for value accuracy


# ---------------------------------------------------------------- unit families

# Map a free-text unit string onto a coarse canonical family. Kept deliberately
# small + self-contained (no import of the extractor stack) so the harness runs
# anywhere. Mirrors the gold set's `unit_base` vocabulary.
def unit_to_base(unit):
    if unit is None:
        return None
    u = str(unit).strip().lower()
    if u in ("", "unspecified", "none", "na", "n/a"):
        return None
    u = re.sub(r"\s*/\s*", "/", u)  # "tonnes / kWh" == "tonnes/kwh"
    if "%" in u or "percent" in u:
        return "percent"
    if "co2" in u or "coe" in u or "co2e" in u:  # tonnes CO2e, gCO2e, milliontonnescoe
        return "co2e_mass"
    if any(k in u for k in ("/inr", "/turnover", "per rupee", "/mwh", "/kwh", "kcal/kwh", "intensity", "/mj")):
        return "rate"
    if any(k in u for k in ("mwp", "mw", "gw", "kw")) and "kwh" not in u and "mwh" not in u and "gwh" not in u:
        return "power_capacity"
    if any(k in u for k in ("litre", "liter", "gallon", "m3", "cubic", "kilo litre", "kl")):
        return "volume"
    if any(k in u for k in ("kwh", "mwh", "gwh", "joule", "gj", "tj", "pj", "kcal")):
        return "energy"
    if any(k in u for k in ("tonne", "ton", "mt", "kg", "metric tonne")):
        return "mass"
    if any(k in u for k in ("gbp", "usd", "inr", "eur", "rs", "rupee", "$", "cr", "crore", "million gbp")):
        return "currency"
    if any(k in u for k in ("employee", "worker", "count", "number", "no.", "connection",
                            "case", "complaint", "incident")):
        return "count"
    return "other"


def pillar_of(aspect):
    if not aspect:
        return None
    return aspect.split(".")[0]


def norm_sentence(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ---------------------------------------------------------------- load + match

def load_extraction(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def index_extraction(rows):
    by_id, by_sent = {}, {}
    for r in rows:
        cid = r.get("claim_id")
        if cid:
            by_id[cid] = r
        sent = norm_sentence((r.get("provenance") or {}).get("source_sentence"))
        if sent:
            by_sent.setdefault(sent, r)
    return by_id, by_sent


def match(gold_rec, by_id, by_sent):
    r = by_id.get(gold_rec["claim_id"])
    if r is not None:
        return r, "claim_id"
    r = by_sent.get(norm_sentence(gold_rec.get("source_sentence")))
    if r is not None:
        return r, "source_sentence"
    return None, None


# ---------------------------------------------------------------- scoring

def extracted_fields(r):
    m = r.get("metric") or {}
    return {
        "aspect": r.get("normalized_aspect"),
        "value": m.get("value"),
        "unit": m.get("unit"),
        "type": r.get("claim_type"),
    }


def within_tol(pred, gold):
    if pred is None or gold is None:
        return False
    try:
        pred, gold = float(pred), float(gold)
    except (TypeError, ValueError):
        return False
    if gold == 0.0:
        return abs(pred) < 1e-9
    return abs(pred - gold) / abs(gold) <= VALUE_TOL


def evaluate(gold, extraction, want_report=False):
    by_id, by_sent = index_extraction(extraction)

    tallies = {
        "gold_total": 0, "matched": 0, "unmatched": 0,
        "prec_num": 0, "prec_den": 0,
        "node_num": 0, "node_den": 0,
        "pillar_num": 0, "pillar_den": 0,
        "value_num": 0, "value_den": 0,
        "unit_num": 0, "unit_den": 0,
        "type_num": 0, "type_den": 0,
    }
    per_claim = []

    for g in gold["claims"]:
        tallies["gold_total"] += 1
        r, how = match(g, by_id, by_sent)
        if r is None:
            tallies["unmatched"] += 1
            per_claim.append({"claim_id": g["claim_id"], "matched": False})
            continue
        tallies["matched"] += 1
        ex = extracted_fields(r)

        # candidate precision: extractor emitted this claim; gold says is it real?
        tallies["prec_den"] += 1
        is_real = bool(g["is_esg_claim"])
        if is_real:
            tallies["prec_num"] += 1

        row = {"claim_id": g["claim_id"], "matched": True, "how": how,
               "is_esg_claim": is_real}

        # remaining fields only meaningful on genuine claims
        if is_real:
            # aspect node + pillar
            tallies["node_den"] += 1
            node_ok = (ex["aspect"] == g["aspect"])
            if node_ok:
                tallies["node_num"] += 1
            tallies["pillar_den"] += 1
            pillar_ok = (pillar_of(ex["aspect"]) == pillar_of(g["aspect"]))
            if pillar_ok:
                tallies["pillar_num"] += 1
            row.update(aspect_gold=g["aspect"], aspect_pred=ex["aspect"],
                       node_ok=node_ok, pillar_ok=pillar_ok)

            # value (skip ambiguous multi-value rows and non-numeric golds)
            if not g.get("value_ambiguous") and g.get("value") is not None:
                tallies["value_den"] += 1
                v_ok = within_tol(ex["value"], g["value"])
                if v_ok:
                    tallies["value_num"] += 1
                row.update(value_gold=g["value"], value_pred=ex["value"], value_ok=v_ok)

            # unit base (only where gold has a unit family)
            if g.get("unit_base") is not None:
                tallies["unit_den"] += 1
                u_ok = (unit_to_base(ex["unit"]) == g["unit_base"])
                if u_ok:
                    tallies["unit_num"] += 1
                row.update(unit_gold=g["unit_base"], unit_pred=unit_to_base(ex["unit"]), unit_ok=u_ok)

            # claim type
            if g.get("claim_type") is not None:
                tallies["type_den"] += 1
                t_ok = (ex["type"] == g["claim_type"])
                if t_ok:
                    tallies["type_num"] += 1
                row.update(type_gold=g["claim_type"], type_pred=ex["type"], type_ok=t_ok)

        per_claim.append(row)

    def rate(num, den):
        return (num / den) if den else None

    metrics = {
        "candidate_precision": rate(tallies["prec_num"], tallies["prec_den"]),
        "aspect_node_acc": rate(tallies["node_num"], tallies["node_den"]),
        "aspect_pillar_acc": rate(tallies["pillar_num"], tallies["pillar_den"]),
        "value_acc": rate(tallies["value_num"], tallies["value_den"]),
        "unit_base_acc": rate(tallies["unit_num"], tallies["unit_den"]),
        "type_acc": rate(tallies["type_num"], tallies["type_den"]),
    }
    # composite: mean of the five load-bearing rates that exist
    parts = [metrics["candidate_precision"], metrics["aspect_node_acc"],
             metrics["value_acc"], metrics["unit_base_acc"], metrics["type_acc"]]
    parts = [p for p in parts if p is not None]
    metrics["extraction_score"] = round(100.0 * sum(parts) / len(parts), 1) if parts else None

    return {"tallies": tallies, "metrics": metrics, "per_claim": per_claim}


# ---------------------------------------------------------------- reporting

def pct(x):
    return "  n/a" if x is None else f"{100 * x:5.1f}%"


def print_summary(result, gold_meta):
    t, m = result["tallies"], result["metrics"]
    print("=" * 60)
    print("ESGenuine - Extraction Quality Evaluation")
    print("=" * 60)
    print(f"gold set        : v{gold_meta.get('version', '?')}  ({t['gold_total']} claims)")
    print(f"matched         : {t['matched']}   unmatched: {t['unmatched']}")
    print("-" * 60)
    print(f"candidate_precision  {pct(m['candidate_precision'])}   ({t['prec_num']}/{t['prec_den']} emitted claims are real)")
    print(f"aspect_node_acc      {pct(m['aspect_node_acc'])}   ({t['node_num']}/{t['node_den']})")
    print(f"aspect_pillar_acc    {pct(m['aspect_pillar_acc'])}   ({t['pillar_num']}/{t['pillar_den']})")
    print(f"value_acc            {pct(m['value_acc'])}   ({t['value_num']}/{t['value_den']}, +-{int(VALUE_TOL*100)}% tol, unambiguous only)")
    print(f"unit_base_acc        {pct(m['unit_base_acc'])}   ({t['unit_num']}/{t['unit_den']})")
    print(f"type_acc             {pct(m['type_acc'])}   ({t['type_num']}/{t['type_den']})")
    print("-" * 60)
    print(f"EXTRACTION_SCORE     {m['extraction_score']}/100")
    print("=" * 60)


def print_report(result):
    print("\nPer-claim detail (real claims with any error):")
    for row in result["per_claim"]:
        if not row.get("matched"):
            print(f"  [UNMATCHED] {row['claim_id']}")
            continue
        if not row.get("is_esg_claim"):
            print(f"  [NOT-A-CLAIM] {row['claim_id']}  (extractor emitted it anyway)")
            continue
        errs = []
        if row.get("node_ok") is False:
            errs.append(f"aspect {row['aspect_pred']}->{row['aspect_gold']}")
        if row.get("value_ok") is False:
            errs.append(f"value {row['value_pred']}->{row['value_gold']}")
        if row.get("unit_ok") is False:
            errs.append(f"unit {row['unit_pred']}->{row['unit_gold']}")
        if row.get("type_ok") is False:
            errs.append(f"type {row['type_pred']}->{row['type_gold']}")
        if errs:
            print(f"  [ERR] {row['claim_id']}: " + "; ".join(errs))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure extraction quality against the gold set.")
    ap.add_argument("--extraction", default=str(DEFAULT_EXTRACTION), help="claims JSONL to score")
    ap.add_argument("--gold", default=str(DEFAULT_GOLD), help="gold_set.json")
    ap.add_argument("--report", action="store_true", help="print per-claim error detail")
    ap.add_argument("--json", dest="json_out", help="write machine-readable metrics to this path")
    args = ap.parse_args(argv)

    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    extraction = load_extraction(args.extraction)
    result = evaluate(gold, extraction, want_report=args.report)

    print_summary(result, gold.get("_meta", {}))
    if args.report:
        print_report(result)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n[wrote] {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
