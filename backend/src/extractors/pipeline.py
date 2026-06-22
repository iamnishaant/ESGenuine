"""
Pharos Integrity — Phase 3: Extraction Pipeline Orchestrator
=============================================================

Extended from Week 3 to include:
- Structured table extraction (table_parser.py) replacing text-blob table extraction
- Geographic NER enrichment (location_extractor.py)
- Cross-report metadata attachment (company_id, report_year, report_id)

Pipeline:
  semantic_chunks  ─→ LLM AAMLT extraction  ─→ validate ─→ normalize ─→ score ─┐
  pdf_tables       ─→ table_parser (NL)      ─→ validate ─→ normalize ─→ score ─┤
                                                                                  ├─→ deduplicate
                                                                                  ├─→ location enrichment
                                                                                  ├─→ cross-report metadata
                                                                                  └─→ store
"""

import json
from pathlib import Path
from dataclasses import asdict
from typing import List, Dict, Any, Optional

from .claim_extractor import ClaimExtractor
from .table_parser import StructuredTableParser
from .models import ExtractedClaim
from .location_extractor import LocationExtractor


class ExtractionPipeline:
    """
    Orchestrates Phase 3 claim extraction.

    Usage:
        pipeline = ExtractionPipeline()
        claims = pipeline.run(
            chunks=week2_chunks,
            pdf_path="path/to/report.pdf",
            document_id="abc123",
            report_metadata={
                "company_id": "tata_steel",
                "company_name": "Tata Steel",
                "report_year": 2024,
                "report_id": "tata_steel_2024",
            }
        )
    """

    def __init__(self):
        self.text_extractor = ClaimExtractor()
        self.table_parser = StructuredTableParser()
        self.location_extractor = LocationExtractor()

    def run(
        self,
        chunks: List[Dict[str, Any]],
        pdf_path: str = "",
        table_rows: Optional[List[Dict[str, Any]]] = None,  # kept for backward compat
        document_id: str = "",
        report_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ExtractedClaim]:
        """
        Run both extraction pipelines and merge results.

        Args:
            chunks:          Semantic text chunks from Week 2 parser
            pdf_path:        Optional direct PDF path for table parsing
            table_rows:      Legacy: structured table rows (fallback if no pdf_path)
            document_id:     Document identifier
            report_metadata: Cross-report metadata {company_id, company_name, report_year, report_id}
        """
        print(f"\n{'='*60}")
        print(f"Phase 3 — Claim Extraction Pipeline")
        print(f"{'='*60}\n")

        # Pipeline 1: Text claims from LLM on semantic chunks
        text_claims = self.text_extractor.extract_from_chunks(chunks, document_id)
        print(f"  Text pipeline: {len(text_claims)} claims")

        # Pipeline 2: Structured table parsing
        table_claims: List[ExtractedClaim] = []
        if pdf_path:
            table_claims = self.table_parser.parse(pdf_path, document_id)
            print(f"  Table pipeline (structured): {len(table_claims)} claims")
        elif table_rows:
            # Legacy fallback — still filtered through garbage check in ingest
            from .table_extractor import TableClaimExtractor
            legacy = TableClaimExtractor()
            table_claims = legacy.extract_from_tables(table_rows, document_id)
            print(f"  Table pipeline (legacy): {len(table_claims)} claims")

        # Merge
        all_claims = text_claims + table_claims

        # Deduplicate (same aspect + metric + page = duplicate)
        deduplicated = self._deduplicate(all_claims)
        print(f"  After dedup: {len(deduplicated)} claims")

        # Phase 3: Location enrichment — fill in missing location fields
        enriched = self.location_extractor.enrich_claims(deduplicated)

        # Phase 3: Attach cross-report metadata to every claim
        if report_metadata:
            for claim in enriched:
                claim.company_id = report_metadata.get("company_id")
                claim.company_name = report_metadata.get("company_name")
                claim.report_year = report_metadata.get("report_year")
                claim.report_id = report_metadata.get("report_id")

        # Stats
        groundable_high = sum(1 for c in enriched if c.groundability_score >= 0.75)
        groundable_mid = sum(1 for c in enriched if 0.5 <= c.groundability_score < 0.75)
        text_count = sum(1 for c in enriched if c.source_type == "text")
        table_count = sum(1 for c in enriched if c.source_type == "table")
        with_location = sum(1 for c in enriched if c.location is not None)

        print(f"\n{'='*60}")
        print(f"Extraction Complete ✓")
        print(f"  Total claims:           {len(enriched)}")
        print(f"  From text:              {text_count}")
        print(f"  From tables (NL):       {table_count}")
        print(f"  With location data:     {with_location}")
        print(f"  Groundable (≥0.75):     {groundable_high}")
        print(f"  Groundable (≥0.50):     {groundable_mid}")
        print(f"  Non-groundable (<0.50): {len(enriched) - groundable_high - groundable_mid}")
        print(f"{'='*60}\n")

        return enriched

    def _deduplicate(self, claims: List[ExtractedClaim]) -> List[ExtractedClaim]:
        """Remove near-duplicate claims (same aspect + metric on same page)."""
        seen = set()
        unique = []

        for claim in claims:
            metric_val = claim.metric.value if claim.metric else None
            key = (
                claim.aspect.lower(),
                claim.action.lower(),
                metric_val,
                claim.provenance.page_number,
            )
            if key not in seen:
                seen.add(key)
                unique.append(claim)

        removed = len(claims) - len(unique)
        if removed:
            print(f"  [Dedup] Removed {removed} duplicates.")
        return unique

    def save(
        self,
        claims: List[ExtractedClaim],
        output_dir: str,
        document_id: str,
    ) -> str:
        """Save extracted claims to JSON file."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        filepath = out / f"{document_id}_claims.json"
        data = [claim.model_dump() for claim in claims]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        print(f"[Saved] {len(claims)} claims to {filepath}")
        return str(filepath)
