"""
⑥ Regate + re-ingest an ALREADY-EXTRACTED report JSONL through the CURRENT
deterministic stack (ontology round-2 + gate + FY-column repair + furniture drop),
then replace its claims in Supabase. NO LLM cost — the LLM-extracted JSONL in
backend/test_results/reingest/<id>.jsonl is reused; only the cheap deterministic
post-processing is re-applied so batch-written reports (which predate ontology
round 2) end up round-2-consistent in the live DB.

    python backend/scripts/regate_ingest.py [report_id ...]   # default: the 3 batch-complete reports

Idempotent (delete-then-insert by report_id). Docling cache auto-located by pdf hash.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # backend/
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT / "src"))

from extractors.models import ExtractedClaim                          # noqa: E402
from extractors.ontology import ESGOntology                           # noqa: E402
from extractors.quality_gate import (                                 # noqa: E402
    gate_claims, fix_fy_column, _value_in_source, _refresh_keys)
from extractors.supabase_ingest import ingest_claims_to_db, sha256_file  # noqa: E402
from parsers.docling_tables import _CACHE_DIR                         # noqa: E402
import hashlib                                                        # noqa: E402

# Same meta as reingest_corpus.py (report_id -> pdf + company + year).
REPORTS = {
    "tata_power_2024": ("business-responsibility-and-sustainability-report-2023-24.pdf",
                        "tata_power", "Tata Power", 2024),
    "infosys_2023": ("infosys-esg-report-2022-23.pdf", "infosys", "Infosys", 2023),
    "infosys_2025": ("infosys-esg-report-2024-25.pdf", "infosys", "Infosys", 2025),
    "shell_2022": ("shell-sustainability-report-2022.pdf", "shell", "Shell", 2022),
    "shell_2023": ("shell-sustainability-report-2023.pdf", "shell", "Shell", 2023),
    "microsoft_2024": ("Microsoft-2024-Environmental-Sustainability-Report.pdf",
                       "microsoft", "Microsoft", 2024),
}
DEFAULT = ["infosys_2023", "tata_power_2024", "shell_2022"]
OUT_DIR = ROOT / "test_results" / "reingest"


def _load_docling_md(pdf: Path) -> dict:
    """page_number -> markdown, from the full-doc docling cache (if present)."""
    h = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    cache = _CACHE_DIR / f"{h}_all.json"
    if not cache.exists():
        print(f"  [warn] no docling cache {cache.name}; FY-column repair skipped")
        return {}
    return {e["page_number"]: e["markdown"] for e in json.load(open(cache, encoding="utf-8"))}


def regate_one(report_id: str) -> dict:
    pdf = ROOT / "ESG_Reports" / REPORTS[report_id][0]
    jsonl = OUT_DIR / f"{report_id}.jsonl"
    if not jsonl.exists():
        return {"report_id": report_id, "error": f"missing {jsonl.name}"}

    claims = []
    with open(jsonl, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                claims.append(ExtractedClaim.model_validate(json.loads(line)))
    n_in = len(claims)
    md_by_page = _load_docling_md(pdf)

    for c in claims:
        c.quality_flags = []
        c.framework_tags = []
        c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
        _refresh_keys(c)
        md = md_by_page.get(c.provenance.page_number if c.provenance else None)
        if md and c.metric is not None and c.metric.value is not None:
            fix_fy_column(c, md)
            if c.source_type == "table" and not _value_in_source(float(c.metric.value), md):
                c.quality_flags.append("value_not_in_table")

    kept, stats = gate_claims(claims)
    print(f"[{report_id}] regate {n_in} -> {len(kept)} kept; stats: {stats}")

    _, cid, cname, year = REPORTS[report_id]
    meta = {"report_id": report_id, "company_id": cid, "company_name": cname,
            "report_year": year, "file_hash": sha256_file(str(pdf))}
    res = ingest_claims_to_db(kept, meta)
    return {"report_id": report_id, "in": n_in, "kept": len(kept),
            "ingested": res.get("inserted", 0), "replaced": res.get("replaced")}


def main():
    ids = sys.argv[1:] or DEFAULT
    unknown = [i for i in ids if i not in REPORTS]
    if unknown:
        sys.exit(f"unknown report_id(s): {unknown}")
    results = [regate_one(i) for i in ids]
    print(f"\n{'='*60}\n[6] REGATE+INGEST SUMMARY\n{'='*60}")
    for r in results:
        if "error" in r:
            print(f"  {r['report_id']:<18} ERROR: {r['error']}")
        else:
            print(f"  {r['report_id']:<18} {r['in']:>4} in -> {r['kept']:>4} kept, "
                  f"ingested {r['ingested']} (replaced={r['replaced']})")


if __name__ == "__main__":
    main()
