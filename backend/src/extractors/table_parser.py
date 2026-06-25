"""
ESGenuine — Phase 3: Structured Table Parser
=====================================================

Replaces the broken text-blob table extraction with proper
pdfplumber table parsing that produces NATURAL LANGUAGE claims.

Problem this solves:
    Old: "Female 2,117 2,117 NA NA" → garbage LLM claim 
    New: "The company had 2,117 female employees in FY2024." → structured claim

Usage:
    from .table_parser import StructuredTableParser
    
    parser = StructuredTableParser()
    claims = parser.parse(pdf_path="report.pdf", document_id="abc123")
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple

try:
    import pdfplumber
except ImportError:
    raise ImportError("pdfplumber is required: pip install pdfplumber")

from .models import ExtractedClaim, MetricField, LocationField, TimeField, ProvenanceField, GroundabilityClassifier


# ══════════════════════════════════════════════════════════════════
# COLUMN HEADER CLASSIFICATION
# Determines what role each column plays in the table
# ══════════════════════════════════════════════════════════════════

METRIC_COLUMN_PATTERNS = re.compile(
    r'(fy\s*\d{2,4}|20\d{2}[-\s]?\d{0,2}|current\s*year|previous\s*year|'
    r'amount|value|total|quantity|actual|result|this\s*year|last\s*year)',
    re.IGNORECASE,
)

UNIT_COLUMN_PATTERNS = re.compile(r'(unit|uom|measure)', re.IGNORECASE)

YEAR_EXTRACTOR = re.compile(r'(20\d{2})')


# ══════════════════════════════════════════════════════════════════
# ESG ASPECT → NATURAL LANGUAGE TEMPLATE MAP
# Maps row descriptor keywords to a claim template
# ══════════════════════════════════════════════════════════════════

ASPECT_TEMPLATES: List[Tuple[re.Pattern, str, str]] = [
    # (pattern, aspect, template)
    (re.compile(r'scope\s*1', re.I),      "Scope 1 emissions",
     "The company reported Scope 1 GHG emissions of {value} {unit} in {period}."),

    (re.compile(r'scope\s*2', re.I),      "Scope 2 emissions",
     "The company reported Scope 2 GHG emissions of {value} {unit} in {period}."),

    (re.compile(r'scope\s*3', re.I),      "Scope 3 emissions",
     "The company reported Scope 3 GHG emissions of {value} {unit} in {period}."),

    (re.compile(r'(total\s+)?ghg|total\s+emission', re.I), "Total GHG emissions",
     "Total GHG emissions were {value} {unit} in {period}."),

    (re.compile(r'energy\s+consumption|total\s+energy', re.I), "Energy consumption",
     "Total energy consumption was {value} {unit} in {period}."),

    (re.compile(r'renewable\s+energy', re.I), "Renewable energy",
     "Renewable energy usage was {value} {unit} in {period}."),

    (re.compile(r'water\s+(consumption|withdrawal|usage)', re.I), "Water consumption",
     "Water consumption was {value} {unit} in {period}."),

    (re.compile(r'(waste\s+to\s+landfill|landfill\s+waste)', re.I), "Waste to landfill",
     "Waste to landfill was {value} {unit} in {period}."),

    (re.compile(r'waste\s+(recycl|diverted|recovered)', re.I), "Waste recycled",
     "Waste recycled or diverted was {value} {unit} in {period}."),

    (re.compile(r'total\s+(permanent\s+)?employee', re.I), "Employee count",
     "Total employees were {value} in {period}."),

    (re.compile(r'female\s+(employee|worker)', re.I), "Female employees",
     "The company had {value} female employees in {period}."),

    (re.compile(r'male\s+(employee|worker)', re.I), "Male employees",
     "The company had {value} male employees in {period}."),

    (re.compile(r'(ltifr|lost\s+time\s+injury)', re.I), "Safety - LTIFR",
     "Lost Time Injury Frequency Rate (LTIFR) was {value} per million hours worked in {period}."),

    (re.compile(r'(injury|fatali|accident)', re.I), "Safety incidents",
     "The number of safety incidents reported was {value} in {period}."),

    (re.compile(r'(tree|forest|reforest|hectare)', re.I), "Reforestation",
     "The company reported {value} {unit} of reforestation or tree planting activity in {period}."),

    (re.compile(r'(training|learning|development)\s+hour', re.I), "Training hours",
     "Total employee training hours were {value} in {period}."),
]


class StructuredTableParser:
    """
    Extracts claims from PDF tables using pdfplumber's native table detection.
    Converts structured rows into natural-language ESG claims.
    """

    def __init__(self):
        self.classifier = GroundabilityClassifier()

    def parse(self, pdf_path: str, document_id: str = "") -> List[ExtractedClaim]:
        """Parse all tables from a PDF and extract claims."""
        claims = []
        path = Path(pdf_path)

        if not path.exists():
            print(f"[TableParser] File not found: {pdf_path}")
            return claims

        with pdfplumber.open(str(path)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                for table in tables:
                    page_claims = self._process_table(
                        table=table,
                        page_number=page_num,
                        document_id=document_id,
                    )
                    claims.extend(page_claims)

        print(f"[TableParser] Extracted {len(claims)} structured claims from {path.name}")
        return claims

    def _process_table(
        self,
        table: List[List[Optional[str]]],
        page_number: int,
        document_id: str,
    ) -> List[ExtractedClaim]:
        """Process a single table (list of rows) into claims."""
        if not table or len(table) < 2:
            return []

        # First row = header
        header = [cell or "" for cell in table[0]]
        claims = []

        for row in table[1:]:
            if not row:
                continue
            row = [cell or "" for cell in row]
            if len(row) < 2:
                continue

            # The first non-empty cell is the row descriptor (metric name)
            descriptor = next((cell.strip() for cell in row if cell.strip()), "")
            if not descriptor or len(descriptor) < 3:
                continue

            # Match against our known aspect templates
            matched = self._match_aspect(descriptor)
            if not matched:
                continue

            aspect_name, template = matched

            # Collect ALL year-value pairs for this row (for Y-o-Y comparison)
            year_values: List[Tuple[str, float]] = []  # [(year, value), ...]
            unit = ""

            for col_idx, header_cell in enumerate(header):
                if col_idx >= len(row):
                    break
                if not METRIC_COLUMN_PATTERNS.search(header_cell):
                    continue

                raw_value = row[col_idx].strip()
                if not raw_value or raw_value.upper() in ("NA", "N/A", "-", ""):
                    continue

                numeric_val = self._parse_number(raw_value)
                if numeric_val is None:
                    continue

                year_match = YEAR_EXTRACTOR.search(header_cell)
                year = year_match.group(1) if year_match else None
                unit = self._infer_unit(descriptor, raw_value)

                if year:
                    year_values.append((year, numeric_val))
                else:
                    # No year in column header — generate single-point claim
                    period = "the reporting period"
                    sentence = template.format(
                        value=f"{numeric_val:,.0f}" if numeric_val >= 1 else str(numeric_val),
                        unit=unit,
                        period=period,
                    )
                    claims.append(self._build_claim(
                        sentence=sentence, aspect_name=aspect_name,
                        numeric_val=numeric_val, unit=unit, year=None,
                        page_number=page_number,
                    ))

            # Sort by year ascending so we can detect direction
            year_values.sort(key=lambda x: x[0])

            # Generate year-by-year individual claims
            prev_year, prev_val = None, None
            for year, val in year_values:
                period = f"FY{year}"

                if prev_year and prev_val is not None:
                    # Generate comparative claim
                    if val < prev_val:
                        direction_word = "decreased"
                        pct = round(abs(val - prev_val) / prev_val * 100, 1) if prev_val != 0 else 0
                        sentence = (
                            f"{aspect_name} {direction_word} from {prev_val:,.0f} {unit} in FY{prev_year} "
                            f"to {val:,.0f} {unit} in FY{year} (−{pct}%)."
                        )
                    elif val > prev_val:
                        direction_word = "increased"
                        pct = round(abs(val - prev_val) / prev_val * 100, 1) if prev_val != 0 else 0
                        sentence = (
                            f"{aspect_name} {direction_word} from {prev_val:,.0f} {unit} in FY{prev_year} "
                            f"to {val:,.0f} {unit} in FY{year} (+{pct}%)."
                        )
                    else:
                        sentence = (
                            f"{aspect_name} remained stable at {val:,.0f} {unit} in both FY{prev_year} and FY{year}."
                        )

                    claims.append(self._build_claim(
                        sentence=sentence, aspect_name=aspect_name,
                        numeric_val=val, unit=unit, year=year,
                        page_number=page_number,
                        direction=direction_word,
                    ))
                else:
                    # First data point — single claim
                    sentence = template.format(
                        value=f"{val:,.0f}" if val >= 1 else str(val),
                        unit=unit, period=period,
                    )
                    claims.append(self._build_claim(
                        sentence=sentence, aspect_name=aspect_name,
                        numeric_val=val, unit=unit, year=year,
                        page_number=page_number,
                    ))

                prev_year, prev_val = year, val

        return claims

    def _build_claim(
        self, sentence: str, aspect_name: str, numeric_val: float,
        unit: str, year: Optional[str], page_number: int, direction: str = "absolute"
    ) -> "ExtractedClaim":
        """Helper to construct a single ExtractedClaim from parsed table data."""
        provenance = ProvenanceField(
            source_sentence=sentence,
            page_number=page_number,
            chunk_id=f"table_p{page_number}",
            block_id=f"table_p{page_number}",
            section_label="Table Data",
        )

        time_field = None
        if year:
            time_field = TimeField(
                start_date=f"{int(year)-1}-04-01",
                end_date=f"{year}-03-31",
            )

        metric = MetricField(
            value=numeric_val,
            unit=unit,
            direction=direction,
        )

        claim = ExtractedClaim(
            aspect=aspect_name,
            action="reported",
            metric=metric,
            location=None,
            time=time_field,
            provenance=provenance,
            confidence=0.88,
            source_type="table",
        )

        score, obs_type = self.classifier.score(claim)
        claim.groundability_score = score
        claim.observability_type = obs_type
        return claim

    def _match_aspect(self, descriptor: str) -> Optional[Tuple[str, str]]:
        """Return (aspect_name, template) if descriptor matches a known ESG metric."""
        for pattern, aspect_name, template in ASPECT_TEMPLATES:
            if pattern.search(descriptor):
                return aspect_name, template
        return None

    def _parse_number(self, text: str) -> Optional[float]:
        """Extract a numeric value from a raw cell string."""
        # Remove commas, spaces, units up front
        cleaned = re.sub(r'[,\s]', '', text)
        # Try to extract first number
        match = re.search(r'-?\d+\.?\d*', cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                pass
        return None

    def _infer_unit(self, descriptor: str, raw_value: str) -> str:
        """Infer the unit from descriptor text or raw value."""
        desc_lower = descriptor.lower()
        val_lower = raw_value.lower()

        if '%' in raw_value:
            return '%'
        if any(kw in desc_lower for kw in ['tco2', 'co2e', 'ghg', 'emission']):
            return 'tCO2e'
        if any(kw in desc_lower for kw in ['energy', 'electricity']):
            return 'GJ'
        if any(kw in desc_lower for kw in ['water']):
            return 'ML'
        if any(kw in desc_lower for kw in ['waste']):
            return 'MT'
        if any(kw in desc_lower for kw in ['employee', 'worker', 'people', 'person']):
            return 'employees'
        if any(kw in desc_lower for kw in ['hour', 'hrs']):
            return 'hours'
        if any(kw in desc_lower for kw in ['hectare', 'ha']):
            return 'hectares'
        if 'per' in desc_lower and 'million' in desc_lower:
            return 'per million person-hours'
        return 'units'


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python table_parser.py <path_to_pdf>")
        sys.exit(1)

    parser = StructuredTableParser()
    claims = parser.parse(sys.argv[1], document_id="test")
    for c in claims:
        print(f"  [{c.aspect}] {c.provenance.source_sentence}")
    print(f"\nTotal: {len(claims)} claims")
