"""
ESGenuine — Phase 3: Extraction Pipeline Orchestrator
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


def build_section_windows(sentences: List[Dict[str, Any]], max_chars: int = 3500) -> List[Dict[str, Any]]:
    """Group parsed sentences (reading order) into char-budgeted windows for
    section-level extraction (one LLM call each). Each window carries the most
    common section_title of its sentences."""
    blocks: List[Dict[str, Any]] = []
    cur: List[Dict[str, Any]] = []
    size = 0

    def flush():
        if cur:
            titles = [x.get("section_title") for x in cur if x.get("section_title")]
            title = max(set(titles), key=titles.count) if titles else "Document"
            blocks.append({"section_title": title, "sentences": list(cur)})

    for s in sentences:
        t = s.get("text", "") or ""
        if cur and size + len(t) > max_chars:
            flush(); cur.clear(); size = 0
        cur.append(s); size += len(t) + 1
    flush()
    return blocks


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
        chunks: Optional[List[Dict[str, Any]]] = None,
        pdf_path: str = "",
        table_rows: Optional[List[Dict[str, Any]]] = None,  # kept for backward compat
        document_id: str = "",
        report_metadata: Optional[Dict[str, Any]] = None,
        sentences: Optional[List[Dict[str, Any]]] = None,   # SOTA: section-level extraction
        checkpoint_path: Optional[str] = None,              # resumable per-LLM-unit save
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

        # Pipeline 1: Text claims via LLM.
        # SOTA path: section-level extraction (one call per section-window, full
        # context, ~15x fewer calls). Falls back to per-chunk if sentences absent.
        if sentences:
            section_blocks = build_section_windows(sentences)
            print(f"  Text pipeline (section mode): {len(section_blocks)} windows from {len(sentences)} sentences")
            text_claims = self.text_extractor.extract_from_sections(
                section_blocks, document_id, checkpoint_path=checkpoint_path)
        else:
            text_claims = self.text_extractor.extract_from_chunks(chunks or [], document_id)
        print(f"  Text pipeline: {len(text_claims)} claims")

        # Pipeline 2: Table claims.
        # SOTA path (USE_VLM_TABLES=1): VLM reads table pages as clean markdown ->
        # structured claims (existing_issues #5). Falls back to pdfplumber/legacy.
        import os as _os
        table_claims: List[ExtractedClaim] = []
        if pdf_path and _os.environ.get("USE_DOCLING_TABLES") == "1":
            # SOTA path: Docling (layout model + TableFormer) reads tables as clean
            # markdown with headers/row-labels/units preserved — fixes the pdfplumber
            # flattening that drives scope confusion + hallucinated values. Runs in an
            # isolated venv via subprocess. Fail-safe: any Docling error degrades to the
            # structured pdfplumber path so table trouble never discards text claims.
            md_tables = []
            try:
                from parsers.docling_tables import DoclingTableExtractor
                md_tables = DoclingTableExtractor().extract(pdf_path)
            except Exception as e:
                print(f"  Table pipeline (Docling) errored: {e}; falling back to structured.")
            if md_tables:
                table_claims = self.text_extractor.extract_from_table_markdown(
                    md_tables, document_id, checkpoint_path=checkpoint_path)
                print(f"  Table pipeline (Docling): {len(table_claims)} claims")
            else:
                table_claims = self.table_parser.parse(pdf_path, document_id)
                print(f"  Table pipeline (structured fallback): {len(table_claims)} claims")
        elif pdf_path and _os.environ.get("USE_VLM_TABLES") == "1":
            from .vlm_tables import VLMTableExtractor
            md_tables = VLMTableExtractor().extract(pdf_path)
            table_claims = self.text_extractor.extract_from_table_markdown(
                md_tables, document_id, checkpoint_path=checkpoint_path)
            print(f"  Table pipeline (VLM): {len(table_claims)} claims")
        elif pdf_path:
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

        # Deterministic quality gate: sentence-signal label corrections (scope/gender/
        # waste), table claim_type, fabricated-value + implausible-unit suspicion flags.
        from .quality_gate import gate_claims
        all_claims, gate_stats = gate_claims(all_claims)
        if gate_stats:
            print(f"  [QualityGate] {gate_stats}")

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
        # ASCII-only: a cp1252-redirected console (Windows log files) can't encode
        # the check/>= glyphs and a crash HERE would discard the whole merged run.
        print("Extraction Complete [OK]")
        print(f"  Total claims:           {len(enriched)}")
        print(f"  From text:              {text_count}")
        print(f"  From tables (NL):       {table_count}")
        print(f"  With location data:     {with_location}")
        print(f"  Groundable (>=0.75):    {groundable_high}")
        print(f"  Groundable (>=0.50):    {groundable_mid}")
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
