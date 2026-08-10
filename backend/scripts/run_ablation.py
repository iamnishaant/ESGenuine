"""
ESGenuine — deterministic-stack ABLATION harness (roadmap Phase 6.2)
===================================================================

Answers the question a reviewer asks first: **which part of the system earns the
63.6 -> 96.1 extraction score?**

The pipeline is `LLM extraction -> deterministic post-correction`. The deterministic
half is the project's actual contribution (the LLM half is standard practice), so it
has to be isolated and measured rather than asserted. This harness re-runs the FROZEN
raw LLM extractions in `tests/eval/fixtures/` through progressively more of that
deterministic stack and scores each stage against the committed gold sets.

**Costs nothing.** No LLM calls, no network, no model downloads — the raw extractions
and their Docling page-markdown caches are already committed. Runs in seconds, so an
ablation can be regenerated on every gate/ontology change.

Stages (cumulative — each adds to the previous):

    S0  raw LLM            no deterministic layer at all. `normalized_aspect` is reset
                           to the LLM's free-text `aspect`, which is the honest "what
                           did the model alone produce" condition. THE BASELINE.
    S1  + ontology         ESGOntology.normalize_aspect -> taxonomy node, then
                           _refresh_keys -> canonical metric_family/metric_key.
    S2  + FY-column repair fix_fy_column: the extractor often reads the FY24 cell when
                           the row label says FY23. Needs the Docling markdown.
    S3  + value-in-table   flags table claims whose value does not appear in the source
                           table markdown (the fabrication class).
    S4  + gate corrections apply_gate: aspect/type repairs + suspicion flags
                           (scope-from-row-text, gender!=biodiversity, waste<->water, ...).
    S5  + furniture drop   is_furniture: drop form questions / bare labels with invented
                           numbers. This is the precision lever. == SHIPPING PIPELINE.

HONESTY NOTE — read before quoting the headline number.
`aspect_node_acc` is 0.0% at S0 **by construction**: the LLM emits free text ("GHG
emissions", "water withdrawal") and the gold set records taxonomy nodes
("emissions.scope1.co2e"), so exact match cannot score above zero without a mapping
layer. The S0->S5 total therefore flatters the deterministic stack. Report BOTH:

  * S0 -> S5  = the full "LLM alone vs shipped system" delta, but its node term is
                partly an artifact of comparing free text against a controlled vocabulary.
  * S1 -> S5  = the DEFENSIBLE number. S1 is the minimum sane system (an LLM plus a
                vocabulary mapping); everything after it is the repair layer this
                project actually contributes. Quote this one in a paper.

Both are printed. S1->S5 is the conservative claim; use it when a reviewer is watching.

SECOND HONESTY NOTE — added by the 2026-08-10 audit, and it outranks the first.
BOTH gold sets are DEVELOPMENT sets. Shell v0.3 is described elsewhere as "out-of-sample";
it is not. It was built in `dd63093` (scoring 81.1) and the ontology was tuned against the
errors it revealed in `48555ea` the same day, reaching 89.7 — a commit that also rewrote 2
of its gold labels to match the taxonomy nodes it introduced. `95e1f20` did the same to 4
Tata labels. So S1->S5 is defensible as *an ablation of the repair layer* (the stages are
paired on identical claims, which the contamination does not disturb) but the ABSOLUTE
endpoints are development scores. Never present 96.1 or 89.7 as generalization.

Third: this composite has no recall term, and the repair layer's gain is not free —
`run_baselines.py` measures it costing 5.5pp of table-fact recall on Tata. Report the
trade, not just the gain.

See `backend/tests/eval/README.md` and `docs/ANNOTATION_PROTOCOL.md`.

Run:
    python backend/scripts/run_ablation.py              # table to stdout
    python backend/scripts/run_ablation.py --json out.json
    python backend/scripts/run_ablation.py --markdown   # paper-ready table
"""
import argparse
import copy
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_evaluation as ev                                        # noqa: E402
from extractors.models import ExtractedClaim                       # noqa: E402
from extractors.ontology import ESGOntology                        # noqa: E402
from extractors.quality_gate import (                              # noqa: E402
    apply_gate, is_furniture, fix_fy_column, _value_in_source, _refresh_keys)

_FIX = _REPO / "backend" / "tests" / "eval" / "fixtures"
_GOLD = _REPO / "backend" / "tests" / "eval"

# (label, fixture jsonl, docling cache, gold set)
CASES = [
    ("Tata Power BRSR FY24 (DEV set — gate tuned on it)",
     "tata_docling_full.jsonl", "docling_tata.json", "gold_set_docling_tata.json"),
    ("Shell SR2022 (DEV set — ontology r2 tuned on it, 48555ea)",
     "shell_2022_raw.jsonl", "docling_shell2022.json", "gold_set_shell_v03.json"),
]

STAGES = ["S0 raw LLM", "S1 +ontology", "S2 +FY repair",
          "S3 +value-in-table", "S4 +gate fixes", "S5 +furniture drop"]


def _load(fixture: str, cache: str):
    md_by_page = {e["page_number"]: e["markdown"]
                  for e in json.loads((_FIX / cache).read_text(encoding="utf-8"))}
    claims = []
    with open(_FIX / fixture, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                claims.append(ExtractedClaim.model_validate(json.loads(line)))
    return claims, md_by_page


def _run_stage(stage: int, claims, md_by_page):
    """Apply the deterministic stack up to `stage` (0..5). Returns kept claims.

    Works on a deep copy so stages stay independent — the gate mutates claims in
    place, so sharing objects between stages would silently contaminate results.
    """
    cs = copy.deepcopy(claims)

    for c in cs:
        c.quality_flags = []
        c.framework_tags = []
        # S0 baseline: strip the deterministic taxonomy mapping the fixture was
        # stored with, leaving the LLM's own free-text aspect.
        c.normalized_aspect = c.aspect

    if stage >= 1:
        for c in cs:
            c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
            _refresh_keys(c)

    if stage >= 2:
        for c in cs:
            md = md_by_page.get(c.provenance.page_number if c.provenance else None)
            if md and c.metric is not None and c.metric.value is not None:
                fix_fy_column(c, md)

    if stage >= 3:
        for c in cs:
            md = md_by_page.get(c.provenance.page_number if c.provenance else None)
            if md and c.metric is not None and c.metric.value is not None:
                if c.source_type == "table" and not _value_in_source(float(c.metric.value), md):
                    c.quality_flags.append("value_not_in_table")

    if stage >= 4:
        for c in cs:
            apply_gate(c)

    if stage >= 5:
        cs = [c for c in cs if not is_furniture(c)]

    return cs


def _score(kept, gold):
    rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in kept]
    return ev.evaluate(gold, rows)["metrics"]


def run():
    out = {}
    for label, fixture, cache, gold_file in CASES:
        claims, md_by_page = _load(fixture, cache)
        gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))
        stages = []
        for i, name in enumerate(STAGES):
            kept = _run_stage(i, claims, md_by_page)
            m = _score(kept, gold)
            stages.append({
                "stage": name,
                "claims_kept": len(kept),
                "extraction_score": m["extraction_score"],
                "candidate_precision": m["candidate_precision"],
                "aspect_node_acc": m["aspect_node_acc"],
                "value_acc": m["value_acc"],
                "unit_base_acc": m["unit_base_acc"],
                "type_acc": m["type_acc"],
            })
        out[label] = {"fixture": fixture, "gold": gold_file,
                      "raw_claims": len(claims), "stages": stages}
    return out


def _pct(v):
    return "  --  " if v is None else f"{100 * v:5.1f}%"


def _print_table(res):
    for label, data in res.items():
        print(f"\n{'=' * 96}\n{label}   [{data['raw_claims']} raw claims -> {data['gold']}]\n{'=' * 96}")
        print(f"{'stage':<22}{'kept':>6}{'SCORE':>9}{'prec':>8}{'node':>8}{'value':>8}{'unit':>8}{'type':>8}   delta")
        print("-" * 96)
        prev = None
        for s in data["stages"]:
            sc = s["extraction_score"]
            delta = "" if prev is None else f"{sc - prev:+.1f}"
            print(f"{s['stage']:<22}{s['claims_kept']:>6}{sc:>9.1f}"
                  f"{_pct(s['candidate_precision']):>8}{_pct(s['aspect_node_acc']):>8}"
                  f"{_pct(s['value_acc']):>8}{_pct(s['unit_base_acc']):>8}"
                  f"{_pct(s['type_acc']):>8}   {delta}")
            prev = sc
        s0, s1, last = data["stages"][0], data["stages"][1], data["stages"][-1]
        print("-" * 96)
        print(f"{'S0->S5 (headline)':<22}{'':>6}"
              f"{last['extraction_score'] - s0['extraction_score']:>+9.1f}"
              f"   ({s0['extraction_score']} -> {last['extraction_score']})"
              f"  <- node term inflated: S0 node=0% by construction")
        print(f"{'S1->S5 (DEFENSIBLE)':<22}{'':>6}"
              f"{last['extraction_score'] - s1['extraction_score']:>+9.1f}"
              f"   ({s1['extraction_score']} -> {last['extraction_score']})"
              f"  <- repair layer alone, zero LLM cost.")
    print("\n  QUOTING GUIDANCE (audit 2026-08-10)")
    print("    The DELTA is quotable: stages are paired on identical claims, so the")
    print("    contamination below does not disturb the within-document comparison.")
    print("    The ENDPOINTS are not: both gold sets are DEVELOPMENT sets — the ontology")
    print("    was tuned against each, and 6 gold labels were rewritten to match new")
    print("    taxonomy nodes. Neither 96.1 nor 89.7 is out-of-sample. No held-out set")
    print("    exists yet; see docs/ANNOTATION_PROTOCOL.md.")
    print("    The composite also has NO RECALL TERM, and the gain is not free —")
    print("    run_baselines.py measures the repair layer costing 5.5pp of table-fact")
    print("    recall on Tata. Report the trade, not just the gain.")


def _print_markdown(res):
    print("\n<!-- generated by backend/scripts/run_ablation.py — do not hand-edit -->")
    for label, data in res.items():
        print(f"\n**{label}** — {data['raw_claims']} raw LLM claims, scored vs `{data['gold']}`\n")
        print("| stage | kept | EXTRACTION_SCORE | Δ | precision | node | value | unit | type |")
        print("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
        prev = None
        for s in data["stages"]:
            sc = s["extraction_score"]
            d = "—" if prev is None else f"{sc - prev:+.1f}"
            print(f"| {s['stage']} | {s['claims_kept']} | **{sc:.1f}** | {d} | "
                  f"{_pct(s['candidate_precision']).strip()} | {_pct(s['aspect_node_acc']).strip()} | "
                  f"{_pct(s['value_acc']).strip()} | {_pct(s['unit_base_acc']).strip()} | "
                  f"{_pct(s['type_acc']).strip()} |")
            prev = sc
        s0, s1, last = data["stages"][0], data["stages"][1], data["stages"][-1]
        print(f"\nS0→S5 **{last['extraction_score'] - s0['extraction_score']:+.1f}** "
              f"({s0['extraction_score']} → {last['extraction_score']}) — note the node term is "
              f"inflated (S0 node accuracy is 0% by construction: free text vs taxonomy node). "
              f"S1→S5 **{last['extraction_score'] - s1['extraction_score']:+.1f}** "
              f"({s1['extraction_score']} → {last['extraction_score']}) is the defensible claim: "
              f"the repair layer alone, at zero LLM cost.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", help="write machine-readable results here")
    ap.add_argument("--markdown", action="store_true", help="emit a paper-ready markdown table")
    a = ap.parse_args()

    res = run()
    _print_markdown(res) if a.markdown else _print_table(res)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {a.json_out}")
