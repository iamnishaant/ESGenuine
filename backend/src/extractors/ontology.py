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

        # FIX (#17): forward-looking / aspirational language is inherently vaguer than
        # delivered performance, even when a number is attached.
        ctype = (getattr(claim, "claim_type", "") or "").lower()
        if ctype == "narrative":
            score += 0.2
        elif ctype == "target":
            score += 0.1

        return round(min(score, 1.0), 2)

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


# ══════════════════════════════════════════════
# UNIT CANONICALIZER  (#16 cross-year drift / #15 value sanity)
# ══════════════════════════════════════════════

class UnitCanonicalizer:
    """
    Convert (value, unit) to a canonical base unit per physical dimension so that
    cross-year / cross-report comparisons are valid (#16) — e.g. 1.2 ktCO2e and
    1200 tCO2e become the same number on the same scale. Also sanity-checks a value
    against the shape its metric_key implies, to catch extraction mislabels (#15)
    such as a workforce ".count" carrying 74.445.

    Unit spellings are the canonical forms emitted by UnitNormalizer.UNIT_MAP plus a
    few raw variants, mapped to (base_unit, multiplicative_factor).
    """

    _CONV: Dict[str, Tuple[str, float]] = {
        # emissions
        "tco2e": ("tCO2e", 1.0), "ktco2e": ("tCO2e", 1e3), "mtco2e": ("tCO2e", 1e6),
        # mass
        "tonnes": ("tonnes", 1.0), "tonne": ("tonnes", 1.0), "ton": ("tonnes", 1.0),
        "kg": ("tonnes", 1e-3), "kilograms": ("tonnes", 1e-3),
        "kt": ("tonnes", 1e3), "mt": ("tonnes", 1.0),  # 'mt' read as metric tonne
        # energy
        "kwh": ("MWh", 1e-3), "mwh": ("MWh", 1.0), "gwh": ("MWh", 1e3), "twh": ("MWh", 1e6),
        "gj": ("MWh", 0.2777778), "tj": ("MWh", 277.7778),
        # volume
        "litres": ("m3", 1e-3), "litre": ("m3", 1e-3), "liters": ("m3", 1e-3),
        "m3": ("m3", 1.0), "m³": ("m3", 1.0), "kl": ("m3", 1.0),
        "kilolitres": ("m3", 1.0), "ml": ("m3", 1e3), "megalitres": ("m3", 1e3),
        # area
        "hectares": ("hectares", 1.0), "hectare": ("hectares", 1.0), "ha": ("hectares", 1.0),
        "acres": ("hectares", 0.404686), "acre": ("hectares", 0.404686),
        "km2": ("hectares", 100.0), "km²": ("hectares", 100.0),
        # dimensionless / passthrough
        "%": ("%", 1.0), "percent": ("%", 1.0),
    }

    # Magnitude words that scale a base unit (e.g. "million tonnes").
    _MAGNITUDE = [("billion", 1e9), ("bn", 1e9), ("million", 1e6), ("thousand", 1e3)]

    @classmethod
    def to_canonical(cls, value, unit) -> Tuple:
        """Return (canonical_value, canonical_unit). Unknown units pass through unchanged."""
        if value is None:
            return value, (unit or None)
        u = (unit or "").strip().lower()
        if not u:
            return value, None
        # 1) exact canonical map (fast path)
        if u in cls._CONV:
            base, factor = cls._CONV[u]
            try:
                return value * factor, base
            except TypeError:
                return value, (unit or None)
        # 2) intensity / ratio units ("X per Y", "tonnes/tonne of steel") are NOT a base
        #    quantity — keep them distinct so they're never compared with absolutes.
        if "/" in u or " per " in u:
            return value, (unit or None)
        # 3) substring heuristic for verbose / compound units (Mt CO2e, million tonnes…)
        mag = 1.0
        for w, m in cls._MAGNITUDE:
            if w in u:
                mag = m
                break
        try:
            if "co2" in u or "ghg" in u:
                f = mag
                if "ktco2" in u or "kt co2" in u or "kilotonne" in u:
                    f = max(f, 1e3)
                elif "mtco2" in u or "mt co2" in u or "megatonne" in u:
                    f = max(f, 1e6)
                return value * f, "tCO2e"
            if "tonne" in u or "tons" in u or u == "ton":
                f = mag
                if "ktonne" in u or "kilotonne" in u:
                    f = max(f, 1e3)
                elif "megatonne" in u:
                    f = max(f, 1e6)
                return value * f, "tonnes"
            if "wh" in u:  # energy: kWh / MWh / GWh / TWh
                if "twh" in u:
                    f = 1e6
                elif "gwh" in u:
                    f = 1e3
                elif "kwh" in u:
                    f = 1e-3
                else:  # mwh / wh default
                    f = 1.0
                return value * f * mag, "MWh"
        except TypeError:
            return value, (unit or None)
        return value, (unit or None)

    @classmethod
    def is_value_plausible(cls, metric_key, value) -> bool:
        """
        Cheap shape check against the dimension encoded in the metric_key suffix
        (generate_metric_key appends the canonical dimension). Catches obvious
        extraction mislabels (#15) without rejecting legitimate data.
        """
        if value is None or metric_key is None:
            return True
        try:
            v = float(value)
        except (TypeError, ValueError):
            return True
        k = str(metric_key)
        if k.endswith(".percent"):
            return -100.0 <= v <= 1000.0
        if k.endswith(".count"):
            # counts are non-negative (near-)integers; 74.445 employees is a mislabel
            return v >= 0 and abs(v - round(v)) < 0.01
        if k.endswith(".rate"):
            return 0 <= v <= 10000
        return True
