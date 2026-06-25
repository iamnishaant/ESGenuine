"""
ESGenuine — Week 3: Table Claim Extractor
==================================================

Parallel extraction pipeline for claims embedded in tables.

ESG reports contain critical metrics in tables that text extraction misses:
  - Scope 1/2/3 emissions totals
  - Energy consumption breakdowns
  - Water usage figures
  - Waste diversion rates
"""

import re
from typing import List, Dict, Any, Optional

from .models import (
    ExtractedClaim, MetricField, LocationField, TimeField,
    ProvenanceField, UnitNormalizer, GroundabilityClassifier,
)


class TableClaimExtractor:
    """
    Extracts structured AAMLT claims from parsed table rows.

    Input: table_rows from Week 2 Step 5 output.
    Each row has: table_id, page_number, row_index, cells (dict of header→value).
    """

    # Column headers that indicate ESG-relevant tables
    ESG_COLUMN_KEYWORDS = {
        "emissions", "scope", "co2", "ghg", "carbon",
        "energy", "electricity", "renewable",
        "water", "discharge", "consumption",
        "waste", "recycl", "divert", "landfill",
        "biodiversity", "hectares", "trees", "planted",
    }

    # Column headers that typically contain metric values
    VALUE_HEADERS = re.compile(
        r'(fy\s*\d{2,4}|20\d{2}|amount|value|total|quantity|'
        r'current\s*year|previous\s*year|target|actual|result)',
        re.IGNORECASE,
    )

    # Column headers that typically contain units
    UNIT_HEADERS = re.compile(
        r'(unit|uom|measure|metric)',
        re.IGNORECASE,
    )

    ASPECT_MAP = {
        "scope 1": "Scope 1 emissions",
        "scope 2": "Scope 2 emissions",
        "scope 3": "Scope 3 emissions",
        "total emissions": "total emissions",
        "ghg emissions": "GHG emissions",
        "energy consumption": "energy consumption",
        "electricity": "electricity consumption",
        "renewable energy": "renewable energy",
        "water consumption": "water consumption",
        "water withdrawal": "water withdrawal",
        "waste generated": "waste generation",
        "waste diverted": "waste diversion",
        "waste recycled": "waste recycling",
        "hazardous waste": "hazardous waste",
        "trees planted": "reforestation",
    }

    def __init__(self):
        self.normalizer = UnitNormalizer()
        self.classifier = GroundabilityClassifier()

    def extract_from_tables(
        self,
        table_rows: List[Dict[str, Any]],
        document_id: str = "",
    ) -> List[ExtractedClaim]:
        """Extract claims from structured table rows."""
        claims: List[ExtractedClaim] = []

        if not table_rows:
            print("[TableExtractor] No table rows to process.")
            return claims

        # Group rows by table_id
        tables: Dict[str, List[Dict]] = {}
        for row in table_rows:
            tid = row.get("table_id", "unknown")
            if tid not in tables:
                tables[tid] = []
            tables[tid].append(row)

        for table_id, rows in tables.items():
            # Check if table is ESG-relevant
            if not self._is_esg_table(rows):
                continue

            for row in rows:
                extracted = self._extract_from_row(row)
                if extracted:
                    claims.extend(extracted)

        print(f"[TableExtractor] Extracted {len(claims)} claims from {len(tables)} tables.")
        return claims

    def _is_esg_table(self, rows: List[Dict]) -> bool:
        """Check if any column header or cell content is ESG-related in the first few rows."""
        if not rows:
            return False
        
        all_text = ""
        for row in rows[:5]:
            cells = row.get("cells", {})
            all_text += " ".join(list(cells.keys()) + list(cells.values())).lower() + " "
            
        return any(kw in all_text for kw in self.ESG_COLUMN_KEYWORDS)

    def _extract_from_row(self, row: Dict[str, Any]) -> List[ExtractedClaim]:
        """Extract one or more claims from a single table row."""
        cells = row.get("cells", {})
        if not cells:
            return []

        claims = []

        # Identify the descriptor column (first column = metric name)
        descriptor_col = None
        value_cols = []
        unit_col = None

        for header in cells.keys():
            if self.UNIT_HEADERS.search(header):
                unit_col = header
            elif self.VALUE_HEADERS.search(header):
                value_cols.append(header)
            elif descriptor_col is None:
                descriptor_col = header

        if not descriptor_col:
            return []

        descriptor = cells.get(descriptor_col, "").strip()
        if not descriptor:
            return []

        # Match to known aspect
        aspect = self._match_aspect(descriptor)
        if not aspect:
            return []

        # Extract unit from dedicated column or descriptor text
        unit_text = ""
        if unit_col:
            unit_text = cells.get(unit_col, "").strip()

        # Create a claim for each value column (typically year columns)
        for val_col in value_cols:
            raw_value = cells.get(val_col, "").strip()
            if not raw_value:
                continue

            # Parse the numeric value
            metric = self._parse_table_metric(raw_value, unit_text or descriptor)
            if not metric:
                continue

            # Parse time from column header (e.g., "FY2023", "2022")
            time_field = self._parse_time_from_header(val_col)

            provenance = ProvenanceField(
                source_sentence=f"{descriptor}: {raw_value} ({val_col})",
                page_number=row.get("page_number", 0),
                chunk_id=row.get("table_id", ""),
                block_id=row.get("table_id", ""),
                section_label="Table Data",
            )

            claim = ExtractedClaim(
                aspect=aspect,
                action="reported",
                metric=metric,
                location=None,  # Tables rarely specify per-row locations
                time=time_field,
                provenance=provenance,
                confidence=0.85,  # Table data is typically high confidence
                source_type="table",
            )

            # Score
            score, obs_type = self.classifier.score(claim)
            claim.groundability_score = score
            claim.observability_type = obs_type

            claims.append(claim)

        return claims

    def _match_aspect(self, descriptor: str) -> Optional[str]:
        lower = descriptor.lower()
        for pattern, aspect in self.ASPECT_MAP.items():
            if pattern in lower:
                return aspect
        return None

    def _parse_table_metric(self, raw_value: str, unit_context: str) -> Optional[MetricField]:
        """Parse a numeric value from a table cell."""
        # Clean common formatting
        cleaned = raw_value.replace(",", "").replace(" ", "").strip()

        try:
            value = float(cleaned)
        except ValueError:
            # Try extracting from mixed text like "118.727 tonnes"
            m = re.search(r'([\d.]+)', cleaned)
            if m:
                try:
                    value = float(m.group(1))
                except ValueError:
                    return None
            else:
                return None

        unit = self.normalizer._extract_unit(unit_context.lower()) or "unspecified"

        return MetricField(
            value=value,
            unit=unit,
            direction="absolute",
            normalized_value=value,
            normalized_unit=unit,
        )

    def _parse_time_from_header(self, header: str) -> Optional[TimeField]:
        """Extract year/FY from a column header like 'FY2023' or '2022-23'."""
        # FY pattern
        fy = re.search(r'FY\s*(\d{4})', header, re.IGNORECASE)
        if fy:
            year = int(fy.group(1))
            return TimeField(
                start_date=f"{year-1}-04-01",
                end_date=f"{year}-03-31",
            )

        # Plain year
        yr = re.search(r'(20\d{2})', header)
        if yr:
            year = int(yr.group(1))
            return TimeField(
                start_date=f"{year}-01-01",
                end_date=f"{year}-12-31",
            )

        return None
