"""
Re-apply the deterministic post-extraction stack (ontology normalize + quality
gate + FY-column repair + furniture drop) to an ALREADY-EXTRACTED claims JSONL,
with no LLM calls. Lets a gate/ontology change be measured against the gold set
in seconds instead of re-paying for a 26-minute 70B run.

    python backend/scripts/regate_claims.py \
        --in  backend/test_results/tata_docling_full.jsonl \
        --out backend/test_results/tata_docling_regated.jsonl \
        --docling-cache backend/.docling_cache/ebb997f913227a52_all.json

claim_ids are preserved so the gold set still matches by id.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # backend/
sys.path.insert(0, str(ROOT / "src"))

from extractors.models import ExtractedClaim                      # noqa: E402
from extractors.ontology import ESGOntology                      # noqa: E402
from extractors.quality_gate import (                            # noqa: E402
    gate_claims, fix_fy_column, _value_in_source, _refresh_keys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--docling-cache", default=None,
                    help="page->markdown cache JSON for FY-column + value-in-table checks")
    args = ap.parse_args()

    md_by_page = {}
    if args.docling_cache:
        for e in json.load(open(args.docling_cache, encoding="utf-8")):
            md_by_page[e["page_number"]] = e["markdown"]

    claims = []
    with open(args.inp, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                claims.append(ExtractedClaim.model_validate(json.loads(line)))

    for c in claims:
        # reset gate-derived state, then re-run the current deterministic stack
        c.quality_flags = []
        c.framework_tags = []
        c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
        _refresh_keys(c)
        md = md_by_page.get((c.provenance.page_number if c.provenance else None))
        if md and c.metric is not None and c.metric.value is not None:
            fix_fy_column(c, md)
            if c.source_type == "table" and not _value_in_source(float(c.metric.value), md):
                c.quality_flags.append("value_not_in_table")

    kept, stats = gate_claims(claims)
    print(f"[regate] {len(claims)} in -> {len(kept)} kept; stats: {stats}")

    with open(args.out, "w", encoding="utf-8") as f:
        for c in kept:
            f.write(json.dumps(c.model_dump(), ensure_ascii=False, default=str) + "\n")
    print(f"[regate] wrote {args.out}")


if __name__ == "__main__":
    main()
