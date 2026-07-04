"""
Re-ingest the full live corpus through the current (96.1-quality) pipeline:
Docling tables + ontology + FY-column repair + quality gate + framework tags,
then replace each report's claims in Supabase (delete-then-insert by report_id).

    python backend/scripts/reingest_corpus.py [report_id ...]   # default: all 6

Safety:
  - per-report resumable checkpoint (crash/429 never re-pays completed LLM units)
  - claims saved to JSONL BEFORE any DB write
  - DB replace is SKIPPED when any LLM unit failed all retries (a partial new set
    must not replace a complete old one); re-run to resume, or FORCE_INGEST=1.
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # backend/
load_dotenv(ROOT.parent / ".env")
sys.path.insert(0, str(ROOT / "src"))

os.environ["USE_DOCLING_TABLES"] = "1"
os.environ.setdefault("NVIDIA_CONCURRENCY", "15")   # 5 keys x 40 rpm

from parsers.pdf_parser import DocumentParsingPipeline   # noqa: E402
from extractors.pipeline import ExtractionPipeline       # noqa: E402
from extractors.supabase_ingest import ingest_claims_to_db, sha256_file  # noqa: E402

# Imported modules re-run load_dotenv(), so blank (don't pop) Groq/HF keys AFTER
# imports to force the NVIDIA-only pool (Groq/HF entries are 8B = quality pollution).
# HUGGING_FACE_HUB_TOKEN doesn't start with HF_ — match every non-NVIDIA pool var.
for k in list(os.environ):
    if k.startswith(("GROQ_", "HF_", "HUGGING")):
        os.environ[k] = ""

REPORTS = {
    "tata_power_2024": {
        "pdf": "business-responsibility-and-sustainability-report-2023-24.pdf",
        "company_id": "tata_power", "company_name": "Tata Power", "report_year": 2024},
    "infosys_2023": {
        "pdf": "infosys-esg-report-2022-23.pdf",
        "company_id": "infosys", "company_name": "Infosys", "report_year": 2023},
    "infosys_2025": {
        "pdf": "infosys-esg-report-2024-25.pdf",
        "company_id": "infosys", "company_name": "Infosys", "report_year": 2025},
    "shell_2022": {
        "pdf": "shell-sustainability-report-2022.pdf",
        "company_id": "shell", "company_name": "Shell", "report_year": 2022},
    "shell_2023": {
        "pdf": "shell-sustainability-report-2023.pdf",
        "company_id": "shell", "company_name": "Shell", "report_year": 2023},
    "microsoft_2024": {
        "pdf": "Microsoft-2024-Environmental-Sustainability-Report.pdf",
        "company_id": "microsoft", "company_name": "Microsoft", "report_year": 2024},
}

OUT_DIR = ROOT / "test_results" / "reingest"


def run_one(report_id: str, spec: dict) -> dict:
    pdf = ROOT / "ESG_Reports" / spec["pdf"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)   # checkpoint appends here mid-run
    out = OUT_DIR / f"{report_id}.jsonl"
    ckpt = str(out) + ".checkpoint.jsonl"
    meta = {"report_id": report_id, "company_id": spec["company_id"],
            "company_name": spec["company_name"], "report_year": spec["report_year"],
            "file_hash": sha256_file(str(pdf))}

    print(f"\n{'#'*70}\n# {report_id}  ({spec['pdf']})\n{'#'*70}", flush=True)
    t0 = time.time()
    parsed = DocumentParsingPipeline(str(pdf)).run(skip_tables=True)
    print(f"[{report_id}] parsed {len(parsed['sentences'])} sentences "
          f"in {time.time()-t0:.0f}s", flush=True)

    pipe = ExtractionPipeline()
    claims = pipe.run(sentences=parsed["sentences"], pdf_path=str(pdf),
                      document_id=parsed["document_id"], report_metadata=meta,
                      checkpoint_path=ckpt)
    failed = pipe.text_extractor.failed_units

    with open(out, "w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c.model_dump(), ensure_ascii=False, default=str) + "\n")
    print(f"[{report_id}] {len(claims)} claims -> {out.name} "
          f"({failed} failed units) in {time.time()-t0:.0f}s", flush=True)

    if failed and os.environ.get("FORCE_INGEST") != "1":
        print(f"[{report_id}] SKIPPING DB replace ({failed} failed units; "
              f"checkpoint kept — re-run to resume, or FORCE_INGEST=1).", flush=True)
        return {"report_id": report_id, "claims": len(claims), "failed_units": failed,
                "ingested": 0, "skipped": True}

    res = ingest_claims_to_db(claims, meta)
    # Complete run whose claims are safely in the DB: drop the checkpoint.
    if res.get("inserted", 0) > 0 and not failed:
        from extractors.checkpoint import ClaimCheckpoint
        ClaimCheckpoint(ckpt).clear()
    return {"report_id": report_id, "claims": len(claims), "failed_units": failed,
            "ingested": res.get("inserted", 0), "skipped": False}


def main():
    ids = sys.argv[1:] or list(REPORTS)
    unknown = [i for i in ids if i not in REPORTS]
    if unknown:
        sys.exit(f"unknown report_id(s): {unknown}; valid: {list(REPORTS)}")

    results = []
    for rid in ids:
        try:
            results.append(run_one(rid, REPORTS[rid]))
        except Exception as e:
            print(f"[{rid}] FAILED: {e}", flush=True)
            results.append({"report_id": rid, "error": str(e)})

    print(f"\n{'='*70}\nRE-INGEST SUMMARY\n{'='*70}")
    for r in results:
        if "error" in r:
            print(f"  {r['report_id']:<18} ERROR: {r['error']}")
        else:
            tag = "SKIPPED-DB" if r["skipped"] else "ingested"
            print(f"  {r['report_id']:<18} {r['claims']:>4} claims, "
                  f"{r['failed_units']} failed units, {tag} {r['ingested']}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
