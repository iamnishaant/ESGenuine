"""
Pharos Integrity — Phase 3: Geographic Claim Extractor
=======================================================

Uses spaCy NER to detect location entities in claim sentences.
Post-enriches claims that have location=None.

Detected entity types:
  GPE  → geopolitical entity (city, country, region)
  LOC  → generic location (mountain, river, region)
  FAC  → facility, building

Usage:
    from .location_extractor import LocationExtractor
    
    extractor = LocationExtractor()
    location = extractor.extract("We reduced emissions at our Pune facility.")
    # → {"raw_text": "Pune", "location_type": "facility", "country": "India"}
"""

import re
from typing import Optional, Dict, List

try:
    import spacy
    from spacy.language import Language
except ImportError:
    raise ImportError("spaCy is required: pip install spacy && python -m spacy download en_core_web_sm")


# ══════════════════════════════════════════════
# COUNTRY INFERENCE HEURISTICS
# ══════════════════════════════════════════════

# City → Country mapping for common ESG report locations
CITY_COUNTRY_MAP: Dict[str, str] = {
    "mumbai": "India", "delhi": "India", "pune": "India", "bangalore": "India",
    "bengaluru": "India", "hyderabad": "India", "chennai": "India", "kolkata": "India",
    "ahmedabad": "India", "jamshedpur": "India", "surat": "India", "noida": "India",
    "gurugram": "India", "gurgaon": "India", "bhubaneswar": "India", "vadodara": "India",
    "nagpur": "India", "lucknow": "India", "chandigarh": "India", "raipur": "India",
    "visakhapatnam": "India", "vizag": "India", "kochi": "India", "coimbatore": "India",
    "singapore": "Singapore",
    "london": "United Kingdom", "manchester": "United Kingdom", "edinburgh": "United Kingdom",
    "berlin": "Germany", "frankfurt": "Germany", "munich": "Germany", "hamburg": "Germany",
    "paris": "France", "lyon": "France",
    "new york": "USA", "houston": "USA", "chicago": "USA", "san francisco": "USA",
    "los angeles": "USA", "seattle": "USA", "boston": "USA", "dallas": "USA",
    "sydney": "Australia", "melbourne": "Australia", "perth": "Australia",
    "tokyo": "Japan", "osaka": "Japan", "yokohama": "Japan",
    "beijing": "China", "shanghai": "China", "shenzhen": "China", "guangzhou": "China",
    "dubai": "UAE", "abu dhabi": "UAE", "sharjah": "UAE",
    "johannesburg": "South Africa", "cape town": "South Africa", "durban": "South Africa",
    "são paulo": "Brazil", "rio de janeiro": "Brazil", "brasilia": "Brazil",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands",
    "stockholm": "Sweden", "oslo": "Norway", "copenhagen": "Denmark",
    "zurich": "Switzerland", "geneva": "Switzerland",
    "seoul": "South Korea", "busan": "South Korea",
    "jakarta": "Indonesia", "kuala lumpur": "Malaysia", "bangkok": "Thailand",
}

COUNTRY_NAMES = {
    "india", "china", "usa", "united states", "uk", "united kingdom",
    "germany", "france", "japan", "australia", "brazil", "singapore",
    "uae", "south africa", "canada", "mexico", "indonesia", "bangladesh",
}

FACILITY_KEYWORDS = re.compile(
    r'(plant|factory|facility|site|campus|mine|refinery|mill|warehouse|depot)',
    re.IGNORECASE,
)


class LocationExtractor:
    """
    Extracts geographic location entities from ESG claim sentences.
    Returns a structured location dict compatible with the claims schema.
    """

    def __init__(self, model: str = "en_core_web_trf"):
        self.nlp: Language = self._load_with_fallback(model)

    @staticmethod
    def _load_with_fallback(preferred: str) -> Language:
        """Try the preferred model, then fall back through smaller models."""
        FALLBACK_CHAIN = [preferred, "en_core_web_lg", "en_core_web_sm"]
        # De-duplicate while keeping order
        seen = set()
        chain = [m for m in FALLBACK_CHAIN if not (m in seen or seen.add(m))]

        for model_name in chain:
            try:
                nlp = spacy.load(model_name)
                print(f"[LocationExtractor] Loaded NER model: {model_name}")
                return nlp
            except Exception as e:
                print(f"[LocationExtractor] Could not load {model_name}: {e}")
                # Try downloading it
                try:
                    import subprocess, sys
                    print(f"[LocationExtractor] Attempting download of {model_name}...")
                    subprocess.check_call(
                        [sys.executable, "-m", "spacy", "download", model_name],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                    nlp = spacy.load(model_name)
                    print(f"[LocationExtractor] Successfully loaded {model_name} after download")
                    return nlp
                except Exception:
                    print(f"[LocationExtractor] Download of {model_name} also failed, trying next...")
                    continue

        raise RuntimeError(
            f"[LocationExtractor] Could not load any spaCy model. Tried: {chain}. "
            "Install at least one: python -m spacy download en_core_web_sm"
        )

    def extract(self, text: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Extract the most specific location from a claim sentence.

        Returns: {
            "raw_text": str,
            "specificity": "facility" | "city" | "region" | "country" | "global",
            "country": str | None
        }
        or None if no location found.
        """
        if not text or not text.strip():
            return None

        doc = self.nlp(text)

        gpe_entities = []
        loc_entities = []
        fac_entities = []

        for ent in doc.ents:
            if ent.label_ == "GPE":
                gpe_entities.append(ent.text)
            elif ent.label_ == "LOC":
                loc_entities.append(ent.text)
            elif ent.label_ == "FAC":
                fac_entities.append(ent.text)

        # Priority order: FAC > GPE > LOC
        if fac_entities:
            raw = fac_entities[0]
            return {
                "raw_text": raw,
                "specificity": "facility",
                "country": self._infer_country(raw, gpe_entities),
            }

        if gpe_entities:
            raw = gpe_entities[0]
            specificity = self._infer_specificity(raw)
            country = self._infer_country(raw, gpe_entities)
            return {
                "raw_text": raw,
                "specificity": specificity,
                "country": country,
            }

        if loc_entities:
            raw = loc_entities[0]
            return {
                "raw_text": raw,
                "specificity": "region",
                "country": None,
            }

        # Check for facility keyword hints even without NER detection
        if FACILITY_KEYWORDS.search(text):
            return {
                "raw_text": "Company facility",
                "specificity": "facility",
                "country": None,
            }

        return None

    def _infer_specificity(self, location_text: str) -> str:
        """Infer whether the location is a city, country, or region."""
        lower = location_text.lower()
        if lower in COUNTRY_NAMES:
            return "country"
        if lower in CITY_COUNTRY_MAP:
            return "city"
        return "region"

    def _infer_country(self, primary: str, all_gpe: List[str]) -> Optional[str]:
        """Try to figure out country from primary location or context entities."""
        lower = primary.lower()

        if lower in COUNTRY_NAMES:
            return primary.title()

        if lower in CITY_COUNTRY_MAP:
            return CITY_COUNTRY_MAP[lower]

        # Check other entities in the sentence for country context
        for ent in all_gpe:
            ent_lower = ent.lower()
            if ent_lower in COUNTRY_NAMES:
                return ent.title()

        return None

    def enrich_claims(self, claims: List) -> List:
        """
        Post-process a list of ExtractedClaim objects, filling in
        location data for claims where it's currently None.
        """
        enriched = 0
        for claim in claims:
            if claim.location is None and claim.provenance:
                result = self.extract(claim.provenance.source_sentence)
                if result:
                    from .models import LocationField
                    claim.location = LocationField(
                        raw_text=result["raw_text"],
                        specificity=result["specificity"],
                        country=result.get("country"),
                    )
                    enriched += 1

        if enriched:
            print(f"[LocationExtractor] Enriched {enriched} claims with location data.")

        return claims


if __name__ == "__main__":
    extractor = LocationExtractor()

    test_sentences = [
        "We reduced emissions by 30% at our Pune manufacturing facility.",
        "Carbon neutral operations were achieved across all Singapore offices.",
        "Water consumption fell 15% globally.",
        "Our Jamshedpur plant achieved zero waste to landfill.",
        "The Berlin data center runs on 100% renewable energy.",
    ]

    print("Location Extraction Test:\n")
    for sent in test_sentences:
        result = extractor.extract(sent)
        print(f"  Input:  {sent}")
        print(f"  Output: {result}")
        print()
