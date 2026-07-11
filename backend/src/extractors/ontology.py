"""
ESGenuine — Week 4: ESG Ontology & Claim Normalization
=============================================================

This module aligns raw extracted claims to a standardized ESG 
taxonomy and computes Greenwashing risk signals (Vagueness, Claim Type).
"""

import json
import re
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
        # NOTE: no bare-"emissions"-containing keyword here — the B-rule (raw inside
        # keyword) would otherwise steal generic raw "emissions" from emissions.total.
        "emissions.air_pollutants": ["sox", "nox", "particulate matter", "air pollutant",
                                     "air pollutants", "air quality"],
        # Round 2 (gold v0.3 / Shell taxonomy-gap classes)
        "emissions.offsets": ["carbon credits", "carbon offsets", "carbon offset",
                              "emissions offset", "carbon-compensated", "carbon compensated"],
        "emissions.ccs": ["carbon capture", "ccs", "ccus", "carbon capture and storage"],
        "emissions.intensity": ["carbon intensity", "net carbon intensity",
                                "emission intensity", "emissions intensity"],
        "emissions.methane": ["methane", "methane emissions", "ogmp"],
        "energy.supply": ["lng", "liquefied natural gas", "gas supply", "energy security"],
        "energy.ev_charging": ["charge points", "charging points", "ev charging",
                               "electric vehicle charging", "charging stations"],
        "energy.investment": ["low-carbon investment", "investment in low-carbon",
                              "low-carbon energy solutions"],
        "energy.renewable": ["renewable energy", "solar", "wind power", "clean energy", "green power"],
        "energy.total": ["energy consumption", "total energy", "power usage",
                         "fuel consumption", "energy consumed", "electricity consumption"],
        "energy.efficiency": ["energy efficiency", "heat rate", "net heat rate",
                              "specific energy consumption"],
        "water.consumption": ["water consumption", "water usage", "freshwater used", "water use", "water withdrawal"],
        "water.recycled": ["recycled water", "water reused", "wastewater treated"],
        "water.discharge": ["water discharge", "water discharged", "effluent discharge", "effluent"],
        "waste.total": ["total waste", "solid waste", "hazardous waste", "waste generated", "plastic waste", "e-waste", "waste management"],
        "waste.recycled": ["recycled waste", "waste diverted", "circular economy", "waste recycling"],
        "biodiversity.conservation": ["biodiversity", "reforestation", "habitat protection", "tree planting"],

        # Social
        "social.diversity.gender": ["gender diversity", "women in management", "female employees", "female representation",
                                    "diversity", "workforce diversity", "diversity in workforce", "employee diversity"],
        "social.health_safety.ltifr": ["ltifr", "lost time injury", "safety incident rate", "work-related injuries"],
        "social.health_safety.fatalities": ["fatalities", "workplace deaths"],
        "social.workforce.total": ["total employees", "workforce size", "employment"],
        "social.training.hours": ["training hours", "learning and development", "employee training"],
        "social.human_rights": ["human rights", "human rights due diligence"],
        "social.community": ["csr", "corporate social responsibility", "community development",
                             "community investment", "beneficiaries"],
        "social.labor_relations": ["union membership", "collective bargaining",
                                   "freedom of association", "labor relations", "industrial relations"],
        "social.posh_complaints": ["posh", "sexual harassment"],
        "social.supply_chain.training": ["value chain partners", "value chain awareness"],
        "social.accessibility": ["accessibility", "differently abled", "assistive technologies"],
        # Round 2
        "social.supply_chain": ["suppliers", "supplier", "supply chain"],
        "social.health_safety": ["health and safety", "process safety", "safety assessment",
                                 "exposure hours", "occupational safety"],
        "social.health_safety.sif": ["serious injuries and fatalities", "sif rate"],

        # Governance
        "governance.board.diversity": ["board diversity", "independent directors", "women on board"],
        "governance.ethics.incidents": ["ethics incidents", "whistleblower", "corruption cases", "anti-bribery"],
        # Round 2
        "governance.stakeholder_engagement": ["stakeholder engagement", "materiality survey",
                                              "materiality assessment", "stakeholder consultation"],
        "governance.payments_to_governments": ["payments to governments", "production entitlements"],
        "governance.compliance": ["administrative penalty", "regulatory penalty", "penalties paid"],
        "governance.lobbying": ["lobbying", "transparency register"],
    }

    @classmethod
    def normalize_aspect(cls, raw_aspect: str) -> str:
        """Finds the best matching canonical node for a raw aspect.

        Matching is WORD-BOUNDARY based, not raw substring. The old substring rule
        (`raw_lower in kw`) made raw "diversity" match keyword "biodiversity" —
        the #19 diversity→biodiversity mislabel that poisoned workforce-diversity
        claims. `\\b` matching kills that class: "diversity" has no word boundary
        inside "biodiversity".

        Tie-breaking:
          A) keyword phrase found INSIDE the raw aspect → raw is specific; the
             LONGEST matching keyword wins ("gender diversity" beats "diversity").
          B) raw aspect found INSIDE a keyword → raw is generic; the SHORTEST
             containing keyword wins (raw "emissions" → "total emissions" /
             emissions.total, not "value chain emissions" / scope3).
          A beats B (a full keyword inside the raw text is stronger evidence).
        """
        if not raw_aspect:
            return "uncategorized"

        raw_lower = raw_aspect.lower().strip()

        # 1. Direct hit
        for node, keywords in cls.TAXONOMY.items():
            if raw_lower in keywords:
                return node

        # 2. Word-boundary match with specificity tie-breaking
        best_a = None   # (kw_len, node) — longest wins
        best_b = None   # (kw_len, node) — shortest wins
        for node, keywords in cls.TAXONOMY.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", raw_lower):
                    if best_a is None or len(kw) > best_a[0]:
                        best_a = (len(kw), node)
                elif re.search(rf"\b{re.escape(raw_lower)}\b", kw):
                    if best_b is None or len(kw) < best_b[0]:
                        best_b = (len(kw), node)
        if best_a:
            return best_a[1]
        if best_b:
            return best_b[1]

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
    # Order matters: more specific dimensions are checked before generic ones. In
    # particular `rate` (safety frequency rates) is matched before `intensity` so an LTIFR
    # "per million hours" denominator is not mistaken for an emissions intensity; and
    # `intensity` is matched before `co2e`/`energy`/`mass` so "tCO2e/MWh" (per-unit) is not
    # bucketed with absolute "tCO2e". The count family is split (fatalities/injuries/
    # headcount/incidents) so physically different quantities stop sharing a `.count` key
    # (existing_issues.md #19: fatalities vs employee headcount under `ltifr.count`).
    _DIM_RULES = [
        ("percent",   ("%", "percent", "per cent")),
        ("rate",      ("per million hours", "per 100 million", "per hundred thousand",
                       "per 100,000", "per one million", "/100 million", "million hours",
                       "ltifr", "frequency rate", " rate", "/hour")),
        # Per-unit intensity (emissions/energy normalized by a physical denominator). Must
        # precede co2e/energy/mass. Keyed on PHYSICAL denominators only (not bare "co2e/"
        # or a time denominator), so absolute "tCO2e/year" / "co2 per year" stay co2e.
        ("intensity", ("intensity", "/mj", "/gj", "/tj", "/kwh", "/mwh", "/gwh", "/boe",
                       "/inr", "/usd", "/tonne", "/m2", "/m²", "uedctm",
                       "per inr", "per boe", "per kwh", "per mwh", "per tonne", "per unit")),
        ("co2e",      ("co2e", "co2", "tco2", "mtco2", "ktco2", "ghg")),
        ("energy",    ("kwh", "mwh", "gwh", "twh", "kva", "gj", "tj", "joule")),
        # Power CAPACITY (MW/MWac/MWp) is not energy (MWh) — a 300 MWac wind farm
        # must never cross-match a 300 MWh generation figure. Checked after energy
        # so "mwh"/"gwh" have already matched; bare "mw"/"gw"/"watt" are then safe.
        ("power",     ("mwac", "wac", "mwp", "kwp", "gwp", "mw", "gw", "kw",
                       "megawatt", "gigawatt", "watt")),
        ("volume",    ("litre", "liter", "cubic met", "m3", "m³", "kilolitre",
                       "megalitre", "gallon", "barrel", "bbl")),
        ("area",      ("hectare", "acre", "km2", "km²", "sq km", "square", "m2", "m²")),
        ("currency",  ("usd", "inr", "eur", "gbp", "$", "dollar", "rupee", "euro", "spend", "cost")),
        ("mass",      ("tonne", "ton", "kilogram", "gram", "kg", "kt", "mt")),
        ("length",    ("km", "kilomet", "mile", "metre", "meter")),
        # Split count family — checked before the generic `count` catch-all (first match wins).
        ("fatalities", ("fatalit",)),
        ("injuries",   ("injur",)),
        ("headcount",  ("employee", "people", "person", "headcount", "fte", "staff",
                        "workforce", "worker", "director")),
        ("incidents",  ("incident", "event", "case", "breach", "spill", "assessment")),
        ("count",      ("count", "number", "tree", "sapling", "credit", "report", "hour")),
    ]

    # Plausible dimensions per metric family (prefix match). Used to collapse garbage
    # (e.g. emissions reported in 'km'/'litres') down to '.unspecified'. New split/intensity
    # dimensions are added per family so they are not collapsed to '.unspecified'.
    _PLAUSIBLE = {
        "emissions": {"co2e", "mass", "intensity", "percent"},
        "energy": {"energy", "power", "intensity", "percent", "count"},
        "water": {"volume", "mass", "intensity", "percent"},
        "waste": {"mass", "volume", "percent"},
        "biodiversity": {"area", "count", "headcount", "incidents", "percent"},
        "social.diversity": {"percent", "count", "headcount"},
        "social.health_safety": {"rate", "count", "fatalities", "injuries", "incidents", "headcount", "percent"},
        "social.workforce": {"count", "headcount", "percent"},
        "social.training": {"count", "headcount", "rate"},
        "social.community": {"currency", "count", "headcount", "percent"},
        "social.posh_complaints": {"count", "incidents", "percent"},
        "social.labor_relations": {"percent", "count", "headcount"},
        "governance": {"count", "incidents", "percent"},
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
        "gco2e": ("tCO2e", 1e-6), "kgco2e": ("tCO2e", 1e-3),
        # mass
        "tonnes": ("tonnes", 1.0), "tonne": ("tonnes", 1.0), "ton": ("tonnes", 1.0),
        "kg": ("tonnes", 1e-3), "kilograms": ("tonnes", 1e-3), "kilogram": ("tonnes", 1e-3),
        "g": ("tonnes", 1e-6), "gram": ("tonnes", 1e-6), "grams": ("tonnes", 1e-6),
        "kt": ("tonnes", 1e3), "mt": ("tonnes", 1.0),  # 'mt' read as metric tonne
        # energy  (1 MWh = 3600 MJ; verbose joule spellings added alongside the abbreviations)
        "kwh": ("MWh", 1e-3), "mwh": ("MWh", 1.0), "gwh": ("MWh", 1e3), "twh": ("MWh", 1e6),
        "mj": ("MWh", 2.777778e-4), "gj": ("MWh", 0.2777778), "tj": ("MWh", 277.7778),
        "pj": ("MWh", 277777.8),
        "joule": ("MWh", 2.777778e-10), "joules": ("MWh", 2.777778e-10),
        "megajoule": ("MWh", 2.777778e-4), "megajoules": ("MWh", 2.777778e-4),
        "gigajoule": ("MWh", 0.2777778), "gigajoules": ("MWh", 0.2777778),
        "terajoule": ("MWh", 277.7778), "terajoules": ("MWh", 277.7778),
        "petajoule": ("MWh", 277777.8), "petajoules": ("MWh", 277777.8),
        # volume  (oil barrel = 0.158987 m3; US gallon = 3.78541e-3 m3)
        "litres": ("m3", 1e-3), "litre": ("m3", 1e-3), "liters": ("m3", 1e-3), "liter": ("m3", 1e-3),
        "l": ("m3", 1e-3),
        "m3": ("m3", 1.0), "m³": ("m3", 1.0), "kl": ("m3", 1.0),
        "cubic metre": ("m3", 1.0), "cubic metres": ("m3", 1.0),
        "cubic meter": ("m3", 1.0), "cubic meters": ("m3", 1.0),
        "kilolitres": ("m3", 1.0), "kilolitre": ("m3", 1.0), "ml": ("m3", 1e3),
        "megalitres": ("m3", 1e3), "megalitre": ("m3", 1e3),
        "gallon": ("m3", 3.78541e-3), "gallons": ("m3", 3.78541e-3),
        "barrel": ("m3", 0.158987), "barrels": ("m3", 0.158987), "bbl": ("m3", 0.158987),
        # area  (1 m2 = 1e-4 hectares)
        "hectares": ("hectares", 1.0), "hectare": ("hectares", 1.0), "ha": ("hectares", 1.0),
        "acres": ("hectares", 0.404686), "acre": ("hectares", 0.404686),
        "km2": ("hectares", 100.0), "km²": ("hectares", 100.0), "sqkm": ("hectares", 100.0),
        "m2": ("hectares", 1e-4), "m²": ("hectares", 1e-4),
        "square metre": ("hectares", 1e-4), "square metres": ("hectares", 1e-4),
        "square meter": ("hectares", 1e-4), "square meters": ("hectares", 1e-4),
        # dimensionless / passthrough
        "%": ("%", 1.0), "percent": ("%", 1.0),
    }

    # Magnitude words that scale a base unit (e.g. "million tonnes"). Includes the
    # Indian-numbering words common in BRSR / Indian ESG reports (lakh = 1e5, crore = 1e7).
    _MAGNITUDE = [("trillion", 1e12), ("billion", 1e9), ("bn", 1e9), ("crore", 1e7),
                  ("million", 1e6), ("lakh", 1e5), ("thousand", 1e3)]

    # Trailing reporting-cadence qualifiers — a temporal suffix, NOT a ratio denominator.
    # "tonnes CO2e per year" is still an absolute tCO2e, so strip these before the
    # intensity/ratio guard (which otherwise drops anything containing "per"/"/").
    _CADENCE_SUFFIXES = (" per year", " per annum", " per yr", " per a", " annually",
                         "/year", "/yr", "/a", " p.a.", " pa")

    @classmethod
    def to_canonical(cls, value, unit) -> Tuple:
        """Return (canonical_value, canonical_unit). Unknown units pass through unchanged."""
        if value is None:
            return value, (unit or None)
        u = (unit or "").strip().lower()
        if not u:
            return value, None
        # 0) drop a trailing reporting cadence ("… per year") — it's temporal, not a
        #    ratio denominator, so it must not trip the intensity guard below.
        for suf in cls._CADENCE_SUFFIXES:
            if u.endswith(suf):
                u = u[: -len(suf)].strip()
                break
        # 1) exact canonical map (fast path)
        if u in cls._CONV:
            base, factor = cls._CONV[u]
            try:
                return value * factor, base
            except TypeError:
                return value, (unit or None)
        # 2) intensity / ratio units ("X per Y", "tonnes/tonne of steel", "gCO2e/MJ") are
        #    NOT a base quantity — keep them distinct so they're never compared with absolutes.
        if "/" in u or " per " in u:
            return value, (unit or None)
        # 3) substring heuristic for verbose / compound units (Mt CO2e, million tonnes,
        #    million hectares, grams CO2e…). `mag` captures a numbering word multiplier.
        mag = 1.0
        for w, m in cls._MAGNITUDE:
            if w in u:
                mag = m
                break
        try:
            if "co2" in u or "ghg" in u:
                f = mag
                if "ktco2" in u or "kt co2" in u or "kilotonne" in u:
                    f *= 1e3
                elif "mtco2" in u or "mt co2" in u or "megatonne" in u:
                    f *= 1e6
                elif "kgco2" in u or "kg co2" in u or "kilogram" in u:
                    f *= 1e-3
                elif "gco2" in u or re.search(r"\bg(ram)?s?\b", u):
                    f *= 1e-6
                return value * f, "tCO2e"
            if "tonne" in u or "tons" in u or u == "ton":
                f = mag
                if "ktonne" in u or "kilotonne" in u:
                    f *= 1e3
                elif "megatonne" in u:
                    f *= 1e6
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
            if "joule" in u:  # energy: verbose joules (1 MWh = 3600 MJ)
                if "peta" in u:
                    f = 277777.8
                elif "tera" in u:
                    f = 277.7778
                elif "giga" in u:
                    f = 0.2777778
                elif "mega" in u:
                    f = 2.777778e-4
                else:  # plain joules
                    f = 2.777778e-10
                return value * f * mag, "MWh"
            if "hectare" in u or "acre" in u:
                f = mag * (0.404686 if "acre" in u else 1.0)
                return value * f, "hectares"
            if "km2" in u or "km²" in u or "sq km" in u or "square kilomet" in u:
                return value * mag * 100.0, "hectares"
            if "square met" in u:  # verbose m2 -> hectares (kilometres handled above)
                return value * mag * 1e-4, "hectares"
            if "barrel" in u or "bbl" in u:  # oil & gas volume
                return value * mag * 0.158987, "m3"
            if "gallon" in u:
                return value * mag * 3.78541e-3, "m3"
            if "cubic met" in u:  # verbose m3
                return value * mag, "m3"
            if "litre" in u or "liter" in u:  # verbose volume (megalitre handled in _CONV)
                return value * mag * 1e-3, "m3"
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
        if k.endswith((".count", ".headcount", ".fatalities", ".injuries", ".incidents")):
            # counts are non-negative (near-)integers; 74.445 employees is a mislabel (#15)
            return v >= 0 and abs(v - round(v)) < 0.01
        if k.endswith(".rate"):
            return 0 <= v <= 10000
        return True
