"""
Pharos Integrity — End-to-End Pipeline Test (Weeks 2+3)
========================================================
Runs the full pipeline on a real ESG report:
  Week 2: PDF → blocks → classify → sections → sentences → tables → candidates → chunks → provenance
  Week 3: chunks → LLM/fallback extraction → table extraction → normalize → score → deduplicate
"""

import sys
import json
import time
from pathlib import Path

# Add backend src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from parsers.pdf_parser import DocumentParsingPipeline
from extractors.pipeline import ExtractionPipeline


def run_test(pdf_path: str):
    print("=" * 70)
    print(f"PHAROS INTEGRITY — End-to-End Pipeline Test")
    print(f"PDF: {Path(pdf_path).name}")
    print("=" * 70)

    # ─── Week 2: Document Parsing ───
    print("\n" + "─" * 50)
    print("WEEK 2: Document Parsing Pipeline (8 Steps)")
    print("─" * 50)

    t0 = time.time()
    parsing_pipeline = DocumentParsingPipeline(pdf_path)
    parse_result = parsing_pipeline.run()

    output_dir = str(Path(pdf_path).parent / "test_output")
    parsing_pipeline.save(parse_result, output_dir)
    t1 = time.time()

    print(f"\n⏱  Week 2 completed in {t1 - t0:.1f}s")

    # ─── Week 3: Claim Extraction ───
    print("\n" + "─" * 50)
    print("WEEK 3: Claim Extraction Pipeline")
    print("─" * 50)

    t2 = time.time()
    extraction_pipeline = ExtractionPipeline()
    claims = extraction_pipeline.run(
        chunks=parse_result["chunks"],
        table_rows=parse_result.get("table_rows", []),
        document_id=parse_result["document_id"],
    )
    extraction_pipeline.save(claims, output_dir, parse_result["document_id"])
    t3 = time.time()

    print(f"\n⏱  Week 3 completed in {t3 - t2:.1f}s")

    # ─── Summary ───
    print("\n" + "=" * 70)
    print("FULL PIPELINE SUMMARY")
    print("=" * 70)
    print(f"  Total time: {t3 - t0:.1f}s")
    print(f"\n  Week 2 Statistics:")
    for k, v in parse_result["statistics"].items():
        print(f"    {k}: {v}")

    print(f"\n  Week 3 Results:")
    print(f"    Total claims: {len(claims)}")
    text_c = [c for c in claims if c.source_type == "text"]
    table_c = [c for c in claims if c.source_type == "table"]
    ground = [c for c in claims if c.groundability_score >= 0.75]
    print(f"    From text: {len(text_c)}")
    print(f"    From tables: {len(table_c)}")
    print(f"    Groundable (≥0.75): {len(ground)}")
    print(f"    Non-groundable: {len(claims) - len(ground)}")

    # Show first 5 claims
    print(f"\n  Sample Claims (first 5):")
    print("  " + "─" * 60)
    for i, claim in enumerate(claims[:5]):
        print(f"\n  Claim {i+1}: [{claim.source_type.upper()}]")
        print(f"    Aspect:   {claim.aspect}")
        print(f"    Action:   {claim.action}")
        if claim.metric:
            print(f"    Metric:   {claim.metric.value} {claim.metric.unit} ({claim.metric.direction or 'n/a'})")
        if claim.location:
            print(f"    Location: {claim.location.raw_text} ({claim.location.specificity})")
        if claim.time:
            print(f"    Time:     {claim.time.start_date} → {claim.time.end_date}")
        print(f"    Ground:   {claim.groundability_score} | Observable: {claim.observability_type}")
        print(f"    Source:   p.{claim.provenance.page_number} | {claim.provenance.section_label}")
        print(f"    Confidence: {claim.confidence}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE ✓")
    print(f"Output saved to: {output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    # Use the first ESG report
    reports_dir = Path(__file__).parent.parent / "ESG_Reports"
    pdfs = list(reports_dir.glob("*.pdf"))

    if not pdfs:
        print("No PDF files found in ESG_Reports/")
        sys.exit(1)

    print(f"Found {len(pdfs)} ESG reports:")
    for p in pdfs:
        print(f"  • {p.name}")

    # Test with first report
    run_test(str(pdfs[0]))
