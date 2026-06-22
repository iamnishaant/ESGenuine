"""
Pharos Integrity — Week 3: Pydantic Models + Unit Normalizer + Groundability Scorer
=====================================================================================

Shared data models and utility functions used across the extraction pipeline.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
import re
import uuid


# ══════════════════════════════════════════════
# PYDANTIC MODELS (Schema Validation)
# ══════════════════════════════════════════════

class MetricField(BaseModel):
    value: float
    unit: str
    direction: Optional[str] = None  # "increase", "decrease", "absolute"
    normalized_value: Optional[float] = None
    normalized_unit: Optional[str] = None

class LocationField(BaseModel):
    raw_text: str
    specificity: str = "global"  # facility, city, region, country, global

    @field_validator("specificity")
    @classmethod
    def validate_specificity(cls, v):
        allowed = {"facility", "city", "region", "country", "global"}
        if v not in allowed:
            return "global"
        return v

class TimeField(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    baseline_year: Optional[int] = None

class ProvenanceField(BaseModel):
    source_sentence: str
    page_number: int
    chunk_id: str = ""
    block_id: str = ""
    section_label: str = ""
    bbox: Optional[Dict[str, float]] = None

class ExtractedClaim(BaseModel):
    """Validated AAMLT claim output from LLM extraction."""
    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    aspect: str
    normalized_aspect: Optional[str] = None  # Added for Week 4 Ontology Mapping
    action: str
    claim_type: str = "performance"  # "performance", "target", "narrative"
    metric: Optional[MetricField] = None
    location: Optional[LocationField] = None
    time: Optional[TimeField] = None
    provenance: ProvenanceField
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    observability_type: str = "not_observable"
    groundability_score: float = 0.0
    vagueness_score: float = 0.0  # Added for Week 4 Greenwashing detection
    
    # Week 4: Stanford Metric Signature Blocking
    metric_family: Optional[str] = None
    metric_key: Optional[str] = None
    time_bucket: Optional[str] = None
    location_scope: str = "global"
    claim_signature: Optional[str] = None
    
    source_type: str = "text"  # "text" or "table"
    
    # Week 4: Cross-Report Entity Tracking
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    report_year: Optional[int] = None
    report_id: Optional[str] = None

# ══════════════════════════════════════════════
# UNIT NORMALIZER
# ══════════════════════════════════════════════

class UnitNormalizer:
    """
    Normalizes metric values and units to canonical forms.

    Handles:
      - "40 percent" / "40%" / "0.4 reduction" → {value: 40, unit: "%"}
      - "tonnes" / "tons" / "metric tons" → "tonnes"
      - "hectares" / "ha" → "hectares"
      - Word numbers: "forty percent" → 40%
    """

    WORD_NUMBERS = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
        "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
        "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000,
        "million": 1_000_000, "billion": 1_000_000_000,
    }

    UNIT_MAP = {
        # Mass
        "tonnes": "tonnes", "tonne": "tonnes", "tons": "tonnes", "ton": "tonnes",
        "metric tons": "tonnes", "metric ton": "tonnes", "mt": "tonnes",
        "kg": "kg", "kilograms": "kg", "kilogram": "kg",
        # Emissions
        "tco2e": "tCO2e", "tonnes co2e": "tCO2e", "tonnes co2": "tCO2e",
        "tons co2e": "tCO2e", "mtco2e": "MtCO2e",
        # Energy
        "kwh": "kWh", "mwh": "MWh", "gwh": "GWh", "twh": "TWh",
        "megawatts": "MW", "mw": "MW", "gw": "GW",
        "gigajoules": "GJ", "gj": "GJ", "terajoules": "TJ", "tj": "TJ",
        # Area
        "hectares": "hectares", "hectare": "hectares", "ha": "hectares",
        "acres": "acres", "acre": "acres",
        "sq km": "km²", "square kilometers": "km²", "km2": "km²",
        # Volume
        "litres": "litres", "liters": "litres", "litre": "litres", "liter": "litres",
        "cubic meters": "m³", "m3": "m³",
        "kilolitres": "kL", "kiloliters": "kL", "kl": "kL",
        "megalitres": "ML", "megaliters": "ML", "ml": "ML",
        # Percentage
        "%": "%", "percent": "%", "per cent": "%", "percentage": "%",
        # Count
        "trees": "trees", "saplings": "trees",
        "employees": "employees", "people": "people",
    }

    DIRECTION_KEYWORDS = {
        "reduced": "decrease", "reduction": "decrease", "decreased": "decrease",
        "decline": "decrease", "declined": "decrease", "lower": "decrease",
        "cut": "decrease", "saved": "decrease", "avoided": "decrease",
        "increased": "increase", "increase": "increase", "grew": "increase",
        "growth": "increase", "higher": "increase", "expanded": "increase",
        "achieved": "absolute", "reached": "absolute", "maintained": "absolute",
        "generated": "absolute", "produced": "absolute", "consumed": "absolute",
    }

    @classmethod
    def normalize(cls, raw_text: str) -> Optional[MetricField]:
        """Extract and normalize a metric from raw text."""
        if not raw_text:
            return None

        text = raw_text.strip().lower()

        # Try numeric extraction first
        value = cls._extract_number(text)
        if value is None:
            return None

        unit = cls._extract_unit(text)
        direction = cls._extract_direction(text)

        # If value looks like a decimal fraction (0.0-1.0) near % context → convert
        if 0 < value < 1 and unit == "%" :
            value = value * 100

        normalized_value = value
        normalized_unit = unit

        return MetricField(
            value=value,
            unit=unit or "unspecified",
            direction=direction,
            normalized_value=normalized_value,
            normalized_unit=normalized_unit,
        )

    @classmethod
    def _extract_number(cls, text: str) -> Optional[float]:
        # Try standard numeric patterns: "40", "40.5", "1,234", "1,234.56"
        match = re.search(r'[\d,]+\.?\d*', text)
        if match:
            try:
                return float(match.group().replace(",", ""))
            except ValueError:
                pass

        # Try word numbers: "forty"
        for word, num in cls.WORD_NUMBERS.items():
            if word in text:
                return float(num)

        return None

    @classmethod
    def _extract_unit(cls, text: str) -> Optional[str]:
        for raw, canonical in cls.UNIT_MAP.items():
            if raw in text:
                return canonical
        return None

    @classmethod
    def _extract_direction(cls, text: str) -> Optional[str]:
        for keyword, direction in cls.DIRECTION_KEYWORDS.items():
            if keyword in text:
                return direction
        return None

    @classmethod
    def normalize_metric_field(cls, metric: Optional[MetricField], context: str = "", aspect: str = "") -> Optional[MetricField]:
        """Re-normalize an already-extracted metric with additional context."""
        if not metric:
            return None

        # Handle literal "None" string from bad JSON parsing
        raw_unit = metric.unit
        if raw_unit.lower() == "none" or not raw_unit.strip():
            raw_unit = "unspecified"

        # Attempt to infer unit from aspect if unspecified
        if raw_unit == "unspecified":
            aspect_lower = aspect.lower()
            if "employ" in aspect_lower or "work" in aspect_lower or "diversity" in aspect_lower:
                if metric.value > 100:
                    raw_unit = "employees"
            elif "emissions" in aspect_lower or "ghg" in aspect_lower:
                raw_unit = "tCO2e"
            elif "water" in aspect_lower:
                raw_unit = "kL"

        unit_lower = raw_unit.lower()
        normalized_unit = cls.UNIT_MAP.get(unit_lower, raw_unit)

        # Detect direction from context
        direction = metric.direction or cls._extract_direction(context.lower())

        return MetricField(
            value=metric.value,
            unit=normalized_unit,
            direction=direction,
            normalized_value=metric.value,
            normalized_unit=normalized_unit,
        )


# ══════════════════════════════════════════════
# GROUNDABILITY CLASSIFIER (CVE-lite)
# ══════════════════════════════════════════════

class GroundabilityClassifier:
    """
    Rule-based pre-CVE scorer. Determines if a claim is physically verifiable.

    Scoring matrix (LLM-aware):
      Numeric metric present              → +1.0
      Time field with a specific date     → +1.0
      Location field present              → +0.5
      Location specificity == facility    → +0.5 bonus (total +1.0)
      Location specificity == city/region → +0.25 bonus (total +0.75)
      Observable aspect (can see on map)  → +1.0

    Final score = points / 3.0, capped at 1.0.
    Score ≥ 0.75 → Groundable (route to contradiction engine)
    Score < 0.75 → Non-groundable (text analysis only)

    observability_type:
      "directly_observable"  — metric + location + time all present
      "reported_metric"      — metric present but no time or location
      "optical_possible"     — spatial aspect (reforestation, solar) regardless of fields
      "not_observable"       — policy statement / aspirational
    """

    OBSERVABLE_ASPECTS = {
        "reforestation", "deforestation", "land use", "vegetation", "forest",
        "plantation", "solar", "wind farm", "water surface", "green cover",
        "facility", "mining", "construction", "flooding", "wetland",
        "biodiversity", "habitat", "mangrove", "coral",
    }

    NOT_OBSERVABLE_ASPECTS = {
        "emissions", "carbon", "co2", "governance", "training",
        "diversity", "inclusion", "ethics", "anti-corruption",
        "human rights", "employee", "supply chain", "policy",
        "commitment", "strategy", "stakeholder", "safety",
        "gender", "wellbeing", "injuries",
    }

    @classmethod
    def score(cls, claim: "ExtractedClaim") -> tuple:
        """
        Returns (groundability_score: float, observability_type: str).
        """
        points = 0.0
        has_metric = claim.metric is not None and claim.metric.value is not None
        has_time = claim.time is not None and (claim.time.start_date or claim.time.end_date)
        has_location = claim.location is not None and bool(claim.location.raw_text)

        # ── Metric (most important) ──
        if has_metric:
            points += 1.0

        # ── Time ──
        if has_time:
            points += 1.0

        # ── Location ──
        if has_location:
            specificity = claim.location.specificity
            if specificity == "facility":
                points += 1.0
            elif specificity in ("city", "region"):
                points += 0.75
            elif specificity == "country":
                points += 0.5
            else:  # global — vague but present
                points += 0.25

        # ── Aspect observability ──
        aspect_lower = (claim.aspect or "").lower()
        obs_type = "not_observable"

        for keyword in cls.OBSERVABLE_ASPECTS:
            if keyword in aspect_lower:
                points += 1.0
                obs_type = "optical_possible"
                break

        # Determine fine-grained observability_type
        if obs_type != "optical_possible":
            if has_metric and has_location and has_time:
                obs_type = "directly_observable"
            elif has_metric:
                obs_type = "reported_metric"
            else:
                obs_type = "not_observable"

        # Denominator represents a standard highly groundable claim (metric + time + location bonus)
        score = round(min(points / 2.5, 1.0), 2)
        return score, obs_type

