"""
ESGenuine — Week 4: ESG Ontology & Claim Normalization
=============================================================

This module aligns raw extracted claims to a standardized ESG 
taxonomy and computes Greenwashing risk signals (Vagueness, Claim Type).
"""

import json
from typing import Dict, Tuple

# ══════════════════════════════════════════════
# ESG TAXONOMY MAPPER
# ══════════════════════════════════════════════

class ESGOntology:
    """Standardizes raw aspect strings into a hierarchical taxonomy."""

    # Simple keyword-to-node mapping for now.
    # A full system would use sentence embeddings to map to the taxonomy graph.
    TAXONOMY = {
        # Environmental
        "emissions.scope1": ["scope 1", "direct emissions", "direct ghg", "fleet emissions", "stationary combustion"],
        "emissions.scope2": ["scope 2", "indirect emissions", "purchased electricity", "purchased energy"],
        "emissions.scope3": ["scope 3", "value chain emissions", "supply chain emissions", "indirect ghg"],
        "emissions.total": ["total emissions", "ghg emissions", "carbon footprint", "co2e"],
        "energy.renewable": ["renewable energy", "solar", "wind power", "clean energy", "green power"],
        "energy.total": ["energy consumption", "total energy", "power usage"],
        "water.consumption": ["water consumption", "water usage", "freshwater used"],
        "water.recycled": ["recycled water", "water reused", "wastewater treated"],
        "waste.total": ["total waste", "solid waste", "hazardous waste"],
        "waste.recycled": ["recycled waste", "waste diverted", "circular economy"],
        "biodiversity.conservation": ["biodiversity", "reforestation", "habitat protection", "tree planting"],

        # Social
        "social.diversity.gender": ["gender diversity", "women in management", "female employees", "female representation"],
        "social.health_safety.ltifr": ["ltifr", "lost time injury", "safety incident rate", "work-related injuries"],
        "social.health_safety.fatalities": ["fatalities", "workplace deaths"],
        "social.workforce.total": ["total employees", "workforce size", "employment"],
        "social.training.hours": ["training hours", "learning and development", "employee training"],
        
        # Governance
        "governance.board.diversity": ["board diversity", "independent directors", "women on board"],
        "governance.ethics.incidents": ["ethics incidents", "whistleblower", "corruption cases", "anti-bribery"],
    }

    @classmethod
    def normalize_aspect(cls, raw_aspect: str) -> str:
        """Finds the best matching canonical node for a raw aspect."""
        if not raw_aspect:
            return "uncategorized"
            
        raw_lower = raw_aspect.lower()
        
        # 1. Direct hit
        for node, keywords in cls.TAXONOMY.items():
            if raw_lower in keywords:
                return node
                
        # 2. Substring match
        for node, keywords in cls.TAXONOMY.items():
            for kw in keywords:
                if kw in raw_lower or raw_lower in kw:
                    return node
                    
        # 3. Fallback
        return "uncategorized"


# ══════════════════════════════════════════════
# GREENWASHING SIGNAL GENERATOR
# ══════════════════════════════════════════════

class ClaimAnalyzer:
    """Computes Risk signals (Claim Type, Vagueness)."""

    TARGET_VERBS = {"aim", "plan", "intend", "commit", "target", "aspire", "will", "goal"}
    PERFORMANCE_VERBS = {"reduced", "increased", "achieved", "delivered", "improved", "generated", "maintained"}

    @classmethod
    def classify_type(cls, action: str, raw_sentence: str) -> str:
        """Determines if a claim is a future promise or past performance."""
        lower_sent = (raw_sentence or "").lower()
        lower_action = (action or "reported").lower()

        # Check action verb directly
        if lower_action in cls.TARGET_VERBS:
            return "target"
        if lower_action in cls.PERFORMANCE_VERBS:
            return "performance"

        # Look in the surrounding sentence context
        for v in cls.TARGET_VERBS:
            if v in lower_sent:
                return "target"

        for v in cls.PERFORMANCE_VERBS:
            if v in lower_sent:
                return "performance"

        return "narrative"

    @classmethod
    def compute_vagueness(cls, claim) -> float:
        """
        Vagueness Score (0.0 to 1.0)
        1.0 means extremely vague (High greenwashing risk).
        """
        score = 0.0
        
        has_metric = claim.metric is not None and claim.metric.value is not None
        has_time = claim.time is not None and (claim.time.start_date or claim.time.end_date)
        has_location = claim.location is not None and claim.location.raw_text

        if not has_metric:
            score += 0.5
        if not has_time:
            score += 0.3
        if not has_location:
            score += 0.2

        return round(score, 2)

# ══════════════════════════════════════════════
# METRIC SIGNATURE GENERATOR (STANFORD BUCKETING)
# ══════════════════════════════════════════════

class SignatureGenerator:
    """
    Generates structured claim signatures (metric_key|time_bucket|location_scope)
    used to prune O(N^2) contradiction comparisons down by 90-99%.
    """
    
    @classmethod
    def generate_metric_family(cls, normalized_aspect: str) -> str:
        """
        Extracts the parent node for DB partitioning.
        Example: 'social.diversity.gender' -> 'social.diversity'
        """
        if not normalized_aspect or normalized_aspect == "uncategorized":
            return "uncategorized"
            
        parts = normalized_aspect.split('.')
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[1]}" # e.g., social.diversity
        return parts[0]

    # Canonical physical DIMENSION for a unit string (ordered keyword match).
    # Order matters: more specific dimensions (co2e, rate) checked before generic ones.
    _DIM_RULES = [
        ("percent",  ("%", "percent", "per cent")),
        ("rate",     ("per million hours", "per 100 million", "per hundred thousand",
                      "per 100,000", "ltifr", "frequency rate", " rate", "/hour")),
        ("co2e",     ("co2e", "co2", "tco2", "mtco2", "ktco2", "ghg")),
        ("energy",   ("kwh", "mwh", "gwh", "twh", "mwac", "wac", "kva", "gj", "tj",
                      "joule", "megawatt", "gigawatt", "watt")),
        ("volume",   ("litre", "liter", "cubic met", "m3", "m³", "kilolitre",
                      "megalitre", "gallon", "barrel", "bbl")),
        ("area",     ("hectare", "acre", "km2", "km²", "sq km", "square", "m2", "m²")),
        ("currency", ("usd", "inr", "eur", "gbp", "$", "dollar", "rupee", "euro", "spend", "cost")),
        ("mass",     ("tonne", "ton", "kilogram", "gram", "kg", "kt", "mt")),
        ("length",   ("km", "kilomet", "mile", "metre", "meter")),
        ("count",    ("employee", "people", "person", "headcount", "fte", "count", "number",
                      "incident", "event", "case", "tree", "sapling", "credit", "report",
                      "fatalit", "injur", "women", "men", "director", "hour")),
    ]

    # Plausible dimensions per metric family (prefix match). Used to collapse garbage
    # (e.g. emissions reported in 'km'/'litres') down to '.unspecified'.
    _PLAUSIBLE = {
        "emissions": {"co2e", "mass", "percent"},
        "energy": {"energy", "percent"},
        "water": {"volume", "mass", "percent"},
        "waste": {"mass", "volume", "percent"},
        "biodiversity": {"area", "count", "percent"},
        "social.diversity": {"percent", "count"},
        "social.health_safety": {"rate", "count", "percent"},
        "social.workforce": {"count", "percent"},
        "social.training": {"count", "rate"},
        "governance": {"count", "percent"},
    }

    @classmethod
    def dimension_of(cls, unit) -> str:
        """Map a raw unit string to a canonical physical dimension."""
        if not unit:
            return "unspecified"
        u = str(unit).lower().strip()
        if u in ("", "unspecified", "none", "null"):
            return "unspecified"
        for dim, keys in cls._DIM_RULES:
            if any(k in u for k in keys):
                return dim
        return "unspecified"

    @classmethod
    def is_plausible_metric(cls, normalized_aspect: str, unit: str) -> bool:
        """Is this unit's dimension physically plausible for the aspect?"""
        dim = cls.dimension_of(unit)
        if dim == "unspecified":
            return True
        fam = (normalized_aspect or "").split(".")
        for key, allowed in cls._PLAUSIBLE.items():
            kp = key.split(".")
            if fam[:len(kp)] == kp:
                return dim in allowed
        return True  # unknown family -> don't filter

    @classmethod
    def generate_metric_key(cls, normalized_aspect: str, unit: str) -> str:
        """
        normalized_aspect + canonical unit DIMENSION (not a raw-unit slug).
        Implausible (aspect, dimension) pairs collapse to '.unspecified' so garbage
        units (emissions in 'km'/'litres', LTIFR in 'cages') no longer spawn distinct
        keys and pollute cross-year matching. e.g. emissions.scope1 + 'tCO2e' ->
        'emissions.scope1.co2e'; emissions.scope1 + 'km' -> 'emissions.scope1.unspecified'.
        """
        if not normalized_aspect or normalized_aspect == "uncategorized":
            return "uncategorized"
        dim = cls.dimension_of(unit)
        if not cls.is_plausible_metric(normalized_aspect, unit):
            dim = "unspecified"
        return f"{normalized_aspect}.{dim}"

    @classmethod
    def generate_time_bucket(cls, claim) -> str:
        """Converts raw dates into a year bucket (e.g., 2024)."""
        if not claim.time:
            return "unknown_time"
            
        # Prefer end_date for FY buckets
        date_str = claim.time.end_date or claim.time.start_date
        if date_str and len(date_str) >= 4:
            return date_str[:4] # Extract YYYY
            
        return "unknown_time"

    @classmethod
    def generate_location_scope(cls, claim) -> str:
        """Normalizes location into broad buckets for matching."""
        if not claim.location or not claim.location.specificity:
            return "global"
        return claim.location.specificity.lower()

    @classmethod
    def generate_signature(cls, metric_key: str, time_bucket: str, scope: str) -> str:
        """Returns the final bucket hash: metric_key|time_bucket|location_scope"""
        return f"{metric_key}|{time_bucket}|{scope}"
