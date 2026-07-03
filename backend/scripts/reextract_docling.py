"""
Re-extract one ESG report through the Docling table path (USE_DOCLING_TABLES=1)
and the configured LLM (NVIDIA 70B by default), writing claims as JSONL in the
same shape run_evaluation.py scores.

    python backend/scripts/reextract_docling.py <pdf> [--company NAME] [--year YYYY]
        [--company-id ID] [--out path.jsonl]

Text claims come from the parser's sentences (section-mode); table claims come from
Docling's structured markdown instead of pdfplumber's flattened rows. Step 5
(pdfplumber) is skipped since Docling supersedes it.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]          # backend/
load_dotenv(ROOT.parent / ".env")                   # repo-root .env (keys, NVIDIA_MODEL)
sys.path.insert(0, str(ROOT / "src"))

os.environ["USE_DOCLING_TABLES"] = "1"              # enable the Docling table branch

from parsers.pdf_parser import DocumentParsingPipeline   # noqa: E402
from extractors.pipeline import ExtractionPipeline       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--company", default="Tata Power")
    ap.add_argument("--company-id", default="tata_power")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--out", default=str(ROOT / "test_results" / "tata_docling_reextract.jsonl"))
    ap.add_argument("--force", action="store_true",
                    help="ignore any existing checkpoint and re-extract from scratch")
    ap.add_argument("--tables-only", action="store_true",
                    help="extract ONLY Docling table claims (skip the slow text section pipeline)")
    ap.add_argument("--pages", default="",
                    help="comma-separated page numbers to extract (tables-only mode); "
                         "cheap targeted test before spending on a full run")
    args = ap.parse_args()

    # Resumable checkpoint: sits next to the output. A crash mid-run keeps every
    # completed LLM unit; a plain re-run resumes; --force starts clean.
    from extractors.checkpoint import ClaimCheckpoint
    ckpt_path = args.out + ".checkpoint.jsonl"
    if args.force:
        ClaimCheckpoint(ckpt_path).clear()
        print(f"[force] cleared checkpoint {ckpt_path}")

    meta = {
        "company_id": args.company_id,
        "company_name": args.company,
        "report_year": args.year,
        "report_id": f"{args.company_id}_{args.year}_docling",
    }

    if args.tables_only:
        # Docling tables are what we're measuring; skip the slow/timeout-heavy text
        # section pipeline entirely. doc_id mirrors DocumentParsingPipeline's scheme.
        doc_id = hashlib.md5(Path(args.pdf).read_bytes()[:4096]).hexdigest()[:12]
        sentences = None
        print(f"[1/3] tables-only (skipping text pipeline); doc_id={doc_id}")
    else:
        print(f"[1/3] Parsing {os.path.basename(args.pdf)} (skip_tables=True; Docling handles tables)...")
        parsed = DocumentParsingPipeline(args.pdf).run(skip_tables=True)
        sentences = parsed["sentences"]
        doc_id = parsed["document_id"]
        print(f"      {len(sentences)} sentences, doc_id={doc_id}")

    print(f"[2/3] Extracting via {os.environ.get('NVIDIA_MODEL','?')} + Docling tables...")
    t0 = time.time()
    if args.pages:
        # Targeted mini-run: only the named table pages, direct extractor call
        # (skips dedup/location enrichment — this is a cheap smoke test, not ingest).
        want = {int(p) for p in args.pages.split(",") if p.strip()}
        from parsers.docling_tables import DoclingTableExtractor
        # pages= converts ONLY those pages (minutes -> ~1 min) and caches the result
        md_tables = DoclingTableExtractor().extract(args.pdf, pages=want)
        print(f"      --pages {sorted(want)}: {len(md_tables)} table-page(s) selected")
        from extractors.claim_extractor import ClaimExtractor
        extractor = ClaimExtractor()
        claims = extractor.extract_from_table_markdown(
            md_tables, doc_id, checkpoint_path=ckpt_path)
        for c in claims:
            c.company_id, c.company_name = meta["company_id"], meta["company_name"]
            c.report_year, c.report_id = meta["report_year"], meta["report_id"]
        failed = extractor.failed_units
    else:
        pipe = ExtractionPipeline()
        claims = pipe.run(sentences=sentences, pdf_path=args.pdf, document_id=doc_id,
                          report_metadata=meta, checkpoint_path=ckpt_path)
        failed = pipe.text_extractor.failed_units
    dt = time.time() - t0

    rows = [c.model_dump() for c in claims]
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    # Drop the checkpoint ONLY on a complete run. If any LLM unit failed all its
    # retries, keep it so the next plain run resumes and retries just those units
    # (clearing here would re-pay for every completed unit).
    if failed:
        print(f"[3/3] {failed} unit(s) failed — checkpoint KEPT; re-run to retry just those.")
    else:
        ClaimCheckpoint(ckpt_path).clear()

    tbl = sum(1 for c in claims if c.source_type == "table")
    print(f"[3/3] {len(rows)} claims ({tbl} from tables) in {dt:.0f}s -> {outp}")


if __name__ == "__main__":
    main()
