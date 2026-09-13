"""
ESGenuine — rebuild a demo database from the claims already committed to this repo.

No LLM calls. Loads the extracted claims saved for three reports, runs them through the
shipped deterministic layer (taxonomy normalisation where missing, then the quality gate,
which also drops page furniture), and writes them to Supabase with the normal ingest path
(embeddings + delete-then-insert by report, so re-running is safe).

    python backend/scripts/load_committed_claims.py --dry-run    # counts only, no writes
    python backend/scripts/load_committed_claims.py              # write to Supabase

Needs in .env: VITE_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (the write path).
Covers Tata Power BRSR FY24 and Shell 2022 / 2023. Infosys and Microsoft were never saved
locally; re-extracting them needs the LLM (scripts/reingest_corpus.py).
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # backend/
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT / "src"))

from extractors.models import ExtractedClaim                       # noqa: E402
from extractors.ontology import ESGOntology                        # noqa: E402
from extractors.quality_gate import gate_claims, _refresh_keys     # noqa: E402

# report_id -> committed claim files + report metadata (ids match reingest_corpus.py)
SOURCES = {
    "tata_power_2024": {
        "files": ["tests/eval/fixtures/tata_docling_full.jsonl"],
        "pdf": "business-responsibility-and-sustainability-report-2023-24.pdf",
        "company_id": "tata_power", "company_name": "Tata Power", "report_year": 2024},
    "shell_2022": {
        "files": ["parsed/shell-sustainability-report-2022_sota_claims.json",
                  "parsed/shell-sustainability-report-2022_table_claims.json"],
        "pdf": "shell-sustainability-report-2022.pdf",
        "company_id": "shell", "company_name": "Shell", "report_year": 2022},
    "shell_2023": {
        "files": ["parsed/shell-sustainability-report-2023_sota_claims.json",
                  "parsed/shell-sustainability-report-2023_table_claims.json"],
        "pdf": "shell-sustainability-report-2023.pdf",
        "company_id": "shell", "company_name": "Shell", "report_year": 2023},
}


def _read(path: Path) -> list:
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("claims", [])


def prepare(report_id: str, spec: dict):
    """Load, stamp report identity, normalise where missing, gate. Returns (claims, stats)."""
    claims = [ExtractedClaim.model_validate(c)
              for f in spec["files"] for c in _read(ROOT / f)]
    for c in claims:
        c.company_id, c.company_name = spec["company_id"], spec["company_name"]
        c.report_year, c.report_id = spec["report_year"], report_id
        if not c.normalized_aspect or c.normalized_aspect == c.aspect:
            c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
            _refresh_keys(c)
    kept, stats = gate_claims(claims)
    return claims, kept, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count and gate only; write nothing")
    ap.add_argument("reports", nargs="*", help=f"subset of {list(SOURCES)} (default: all)")
    a = ap.parse_args()

    ids = a.reports or list(SOURCES)
    unknown = [i for i in ids if i not in SOURCES]
    if unknown:
        sys.exit(f"unknown report id(s): {unknown}; valid: {list(SOURCES)}")

    if not a.dry_run:
        from extractors.supabase_ingest import ingest_claims_to_db, sha256_file

    total = 0
    for rid in ids:
        spec = SOURCES[rid]
        raw, kept, stats = prepare(rid, spec)
        dropped = stats.get("furniture_dropped", 0)
        print(f"{rid:<16} {len(raw):>5} loaded  {dropped:>4} furniture dropped  "
              f"{len(kept):>5} to ingest", flush=True)
        total += len(kept)
        if a.dry_run:
            continue
        meta = {"report_id": rid, "company_id": spec["company_id"],
                "company_name": spec["company_name"], "report_year": spec["report_year"]}
        pdf = ROOT / "ESG_Reports" / spec["pdf"]
        if pdf.exists():
            meta["file_hash"] = sha256_file(str(pdf))
        res = ingest_claims_to_db(kept, meta)
        print(f"{'':<16} -> {res}", flush=True)

    print(f"{'TOTAL':<16} {total:>5} claims {'(dry run — nothing written)' if a.dry_run else 'ingested'}")


if __name__ == "__main__":
    main()
