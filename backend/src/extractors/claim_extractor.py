"""
Pharos Integrity — Week 3: Context-Aware LLM AAMLT Extractor
=============================================================

Takes semantic chunks (Week 2, Step 7 output) and extracts structured
AAMLT claims using an LLM with Pydantic validation + retry.

Supports: OpenAI (GPT-4o), Anthropic (Claude), or local fallback.
"""

import json
import os
import re
import time
from typing import List, Optional, Dict, Any
from pydantic import ValidationError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .models import (
    ExtractedClaim, MetricField, LocationField, TimeField,
    ProvenanceField, UnitNormalizer, GroundabilityClassifier,
)
from .ontology import ESGOntology, ClaimAnalyzer, SignatureGenerator

# ══════════════════════════════════════════════
# EXTRACTION PROMPT (Production-Grade)
# ══════════════════════════════════════════════

AAMLT_EXTRACTION_PROMPT = """You are an ESG (Environmental, Social, Governance) claim extraction system.

Given the following text excerpt from an ESG sustainability report, extract ALL environmental or sustainability claims as structured JSON.

## Input Format
You will receive:
- Section title (which part of the ESG report this comes from)
- Context sentences (surrounding text for disambiguation)
- The target sentence(s) to extract claims from

## Output Format
Return a JSON array. Each claim must have these fields:

```json
[
  {{
    "aspect": "The topic (emissions, water, biodiversity, reforestation, energy, waste, etc.)",
    "action": "What was done (reduced, increased, achieved, planted, maintained, etc.)",
    "metric": {{
      "value": 40.0,
      "unit": "%",
      "direction": "decrease"
    }},
    "location": {{
      "raw_text": "Pune manufacturing facility",
      "specificity": "facility"
    }},
    "time": {{
      "start_date": "2023-04-01",
      "end_date": "2024-03-31",
      "baseline_year": null
    }},
    "confidence": 0.9
  }}
]
```

## Rules
1. If a field cannot be determined from the text, set it to null.
2. For metric.direction: use "absolute" for snapshot/table data (a reported figure), "decrease" for reductions, "increase" for growth. Most table figures are "absolute".
3. For location.specificity, use: "facility", "city", "region", "country", or "global". Only use "global" if no specific geography is mentioned. Do NOT default to "global" — use null location if unknown.
4. Dates should be ISO format (YYYY-MM-DD). If only a year is mentioned, use YYYY-04-01 to (YYYY+1)-03-31 for Indian FY.
5. FY2024 = April 2023 to March 2024. Use start_date=2023-04-01, end_date=2024-03-31.
6. CRITICAL: If a table shows two columns (current year vs previous year), extract TWO separate claims with different time ranges — one for FY2024 and one for FY2023. Do NOT span both years in a single time range.
7. confidence should be 0.0-1.0 reflecting how clearly the claim is stated.
8. If NO claims exist in the text, return an empty array [].
9. Do NOT extract policy intentions or aspirational statements as claims (e.g. "we aim to reduce..."). Only extract factual, reported data.
10. Return at most 5 claims per text excerpt to avoid over-extraction from data tables.
11. CRITICAL: Numbers over 999 must NOT contain commas or decimal points for thousands. 22,372 must be 22372.0.
12. CRITICAL: Do NOT leave metric.unit as null if there is a number. Infer the unit from context (e.g., "employees", "INR", "%", "hours").

## Text to Analyze

Section: {section_title}

Context:
{context_text}

Target sentence:
{target_sentence}

Extract all claims as JSON:"""


# ══════════════════════════════════════════════
# LLM CLIENT ABSTRACTION
# ══════════════════════════════════════════════

class LLMClient:
    """Unified LLM client supporting OpenAI, Anthropic, or mock fallback."""

    def __init__(self):
        self.provider = self._detect_provider()

    def _detect_provider(self) -> str:
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        print("[LLM] No API key found. Using rule-based fallback extractor.")
        return "fallback"

    def extract(self, prompt: str) -> str:
        if self.provider == "openai":
            return self._call_openai(prompt)
        elif self.provider == "anthropic":
            return self._call_anthropic(prompt)
        elif self.provider == "groq":
            return self._call_groq(prompt)
        else:
            return self._fallback_extract(prompt)

    def _call_openai(self, prompt: str) -> str:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _call_anthropic(self, prompt: str) -> str:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _call_groq(self, prompt: str) -> str:
        from groq import Groq
        import time
        client = Groq()
        
        # Groq free tier has a 30 RPM limit (2s per request)
        # Adding a small sleep to help avoid 429s when processing hundreds of chunks
        time.sleep(2.1)
        
        response = client.chat.completions.create(
            # Using the 8b model to bypass 70b strict rate limits (30k TPM vs 6k TPM)
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            # Groq natively supports response_format for strict JSON
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def _fallback_extract(self, prompt: str) -> str:
        """Rule-based extraction when no LLM API key is available."""
        # Extract the target sentence from the prompt
        match = re.search(r'Target sentence:\n(.+?)(?:\n\nExtract|$)', prompt, re.DOTALL)
        if not match:
            return "[]"

        sentence = match.group(1).strip()
        claims = RuleBasedExtractor.extract_from_sentence(sentence)
        return json.dumps(claims, ensure_ascii=False)


# ══════════════════════════════════════════════
# RULE-BASED FALLBACK EXTRACTOR
# ══════════════════════════════════════════════

class RuleBasedExtractor:
    """Extracts AAMLT fields using regex when no LLM is available."""

    ASPECT_PATTERNS = {
        r'\b(scope\s*[123]|ghg|greenhouse|carbon|co2|emission)': "emissions",
        r'\b(water|wastewater|effluent)': "water",
        r'\b(energy|electricity|renewable|solar|wind)': "energy",
        r'\b(waste|recycl|circular|landfill)': "waste",
        r'\b(reforest|afforest|tree|plant|vegetation|forest|biodiversity)': "reforestation",
        r'\b(deforest|land.?use|land.?cover)': "deforestation",
    }

    ACTION_PATTERNS = {
        r'\b(reduc|decreas|lower|cut|sav|avoid)': "reduced",
        r'\b(increas|grew|growth|expand|rais)': "increased",
        r'\b(achiev|reach|maintain|certif)': "achieved",
        r'\b(plant|restor|conserv|protect)': "planted",
        r'\b(generat|produc|sourc|procur)': "generated",
    }

    LOCATION_PATTERNS = [
        (r'\b(?:at|in|near)\s+(?:our\s+)?(\w+(?:\s+\w+)?)\s+(?:facility|plant|factory|site|campus|hub|office)', "facility"),
        (r'\b(?:in|across)\s+(\w+(?:\s+\w+)?)\s+(?:district|city|town|municipality)', "city"),
        (r'\b(?:in|across)\s+(\w+(?:\s+\w+)?)\s+(?:state|province|region)', "region"),
    ]

    TIME_PATTERN = re.compile(
        r'(?:FY\s*)?(\d{4})\s*[-–to]+\s*(?:FY\s*)?(\d{4})|'
        r'(?:FY|fy)\s*(\d{4})|'
        r'(?:in|during|since|by)\s+(\d{4})',
        re.IGNORECASE,
    )

    METRIC_PATTERN = re.compile(
        r'([\d,]+\.?\d*)\s*(%|percent|per\s*cent|tonnes?|tons?|mt|'
        r'hectares?|ha|kwh|mwh|gwh|trees?|saplings?|litres?|liters?|'
        r'employees?|people|kg|gj|tj)',
        re.IGNORECASE,
    )

    @classmethod
    def extract_from_sentence(cls, sentence: str) -> List[Dict[str, Any]]:
        lower = sentence.lower()

        # Aspect
        aspect = None
        for pattern, label in cls.ASPECT_PATTERNS.items():
            if re.search(pattern, lower):
                aspect = label
                break
        if not aspect:
            return []

        # Action
        action = None
        for pattern, label in cls.ACTION_PATTERNS.items():
            if re.search(pattern, lower):
                action = label
                break
        action = action or "reported"

        # Metric
        metric = None
        m = cls.METRIC_PATTERN.search(sentence)
        if m:
            try:
                metric = {
                    "value": float(m.group(1).replace(",", "")),
                    "unit": m.group(2),
                    "direction": None,
                }
            except (ValueError, IndexError):
                pass

        # Location
        location = None
        for pattern, spec in cls.LOCATION_PATTERNS:
            loc_match = re.search(pattern, sentence, re.IGNORECASE)
            if loc_match:
                location = {"raw_text": loc_match.group(1), "specificity": spec}
                break

        # Time
        time_field = None
        t = cls.TIME_PATTERN.search(sentence)
        if t:
            if t.group(1) and t.group(2):
                time_field = {"start_date": f"{t.group(1)}-01-01", "end_date": f"{t.group(2)}-12-31"}
            elif t.group(3):
                fy = int(t.group(3))
                time_field = {"start_date": f"{fy-1}-04-01", "end_date": f"{fy}-03-31"}
            elif t.group(4):
                time_field = {"start_date": f"{t.group(4)}-01-01", "end_date": f"{t.group(4)}-12-31"}

        return [{
            "aspect": aspect,
            "action": action,
            "metric": metric,
            "location": location,
            "time": time_field,
            "confidence": 0.6,
        }]


# ══════════════════════════════════════════════
# MAIN EXTRACTOR (Orchestrates LLM + Validation)
# ══════════════════════════════════════════════

class ClaimExtractor:
    """
    Production-grade claim extraction pipeline.

    Flow:
      semantic_chunks → context_prompt → LLM → JSON parse → Pydantic validate
      → unit normalize → groundability score → ExtractedClaim[]
    """

    MAX_RETRIES = 2
    MAX_CLAIMS_PER_CHUNK = 5  # Cap to prevent single-table over-extraction

    def __init__(self):
        self.llm = LLMClient()
        self.normalizer = UnitNormalizer()
        self.classifier = GroundabilityClassifier()

    def _is_meaningful_claim(self, claim: ExtractedClaim) -> bool:
        """
        Returns False for aspirational/policy claims with no verifiable data.
        These cause false positives in the contradiction engine.
        A claim is meaningful if it has at least ONE of: metric, specific time, or location.
        """
        has_metric = claim.metric is not None
        has_time = claim.time is not None and (claim.time.start_date or claim.time.end_date)
        has_location = claim.location is not None and bool(claim.location.raw_text)

        return has_metric or has_time or has_location

    def extract_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str = "",
    ) -> List[ExtractedClaim]:
        """
        Extract claims from all semantic chunks (Week 2 Step 7 output).
        Each chunk has: section_title, context_before, target_sentence, context_after.
        """
        all_claims: List[ExtractedClaim] = []
        print(f"[Extractor] Processing {len(chunks)} semantic chunks...")

        for i, chunk in enumerate(chunks):
            # Build context-aware prompt
            prompt = AAMLT_EXTRACTION_PROMPT.format(
                section_title=chunk.get("section_title", "Unknown"),
                context_text=self._build_context(chunk),
                target_sentence=chunk.get("target_sentence", ""),
            )

            # Call LLM with retry
            try:
                raw_claims = self._call_with_retry(prompt)
            except RuntimeError as e:
                if "RateLimitExceeded" in str(e):
                    print(f"\n  [ABORT] Hard limit hit: {e}")
                    print(f"  [ABORT] Halting extraction at chunk {i}/{len(chunks)}. Moving forward with {len(all_claims)} claims.")
                    break
                else:
                    print(f"  [Failed] Skipping chunk: {e}")
                    continue

            # Validate, normalize, score
            chunk_claims: List[ExtractedClaim] = []
            for raw in raw_claims:
                claim = self._validate_and_enrich(
                    raw, chunk, document_id
                )
                if claim and self._is_meaningful_claim(claim):
                    chunk_claims.append(claim)

            # Cap at MAX_CLAIMS_PER_CHUNK to prevent single-table over-extraction
            # Sort by groundability_score descending → keep the best ones
            chunk_claims.sort(key=lambda c: c.groundability_score, reverse=True)
            chunk_claims = chunk_claims[:self.MAX_CLAIMS_PER_CHUNK]

            all_claims.extend(chunk_claims)
            
            # --- Incremental Save ---
            try:
                os.makedirs("test_results", exist_ok=True)
                with open("test_results/incremental_claims_backup.jsonl", "a", encoding="utf-8") as bk:
                    for c in chunk_claims:
                        bk.write(c.model_dump_json() + "\n")
            except Exception as e:
                pass # Fail silently for backups

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(chunks)}] Extracted {len(all_claims)} claims so far...")

        print(f"[Extractor] Done. {len(all_claims)} total claims extracted.")
        return all_claims

    def _build_context(self, chunk: Dict[str, Any]) -> str:
        """Build context window from chunk neighbors."""
        parts = []
        if chunk.get("context_before"):
            parts.append(chunk["context_before"])
        parts.append(chunk.get("target_sentence", ""))
        if chunk.get("context_after"):
            parts.append(chunk["context_after"])
        return "\n".join(parts)

    def _call_with_retry(self, prompt: str) -> List[Dict]:
        """Call LLM and parse JSON, with retries on failure."""
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                raw_response = self.llm.extract(prompt)
                parsed = self._parse_json_response(raw_response)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict) and "claims" in parsed:
                    return parsed["claims"]
                elif isinstance(parsed, dict):
                    return [parsed]
            except Exception as e:
                err_str = str(e).lower()
                
                # Check for fatal daily rate limit or long TPM wait 
                import re
                m = re.search(r'try again in (?:(\d+)h)?\s*(?:(\d+)m)?\s*(\d+(?:\.\d+)?)s', err_str)
                wait_seconds = 0
                if m:
                    h = int(m.group(1)) if m.group(1) else 0
                    mins = int(m.group(2)) if m.group(2) else 0
                    sec = float(m.group(3)) if m.group(3) else 0
                    wait_seconds = h * 3600 + mins * 60 + sec
                    
                if wait_seconds > 60 or "used 49" in err_str:
                    raise RuntimeError(f"RateLimitExceeded: {e}")

                if attempt < self.MAX_RETRIES:
                    # Exponential backoff on rate limits
                    sleep_time = (attempt + 1) * 5
                    if "429" in err_str or "rate limit" in err_str:
                        sleep_time = 15
                    print(f"  [Retry {attempt+1}] LLM call failed ({e}). Sleeping {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                raise RuntimeError(f"Failed after {self.MAX_RETRIES} retries: {e}")
        return []

    def _parse_json_response(self, response: str) -> Any:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Strip markdown code fences if present
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r'^```\w*\n?', '', response)
            response = re.sub(r'\n?```$', '', response)

        return json.loads(response)

    def _validate_and_enrich(
        self,
        raw: Dict[str, Any],
        chunk: Dict[str, Any],
        document_id: str,
    ) -> Optional[ExtractedClaim]:
        """Validate raw LLM output via Pydantic, normalize units, score groundability."""
        try:
            # Build provenance from chunk metadata
            provenance = ProvenanceField(
                source_sentence=chunk.get("target_sentence", ""),
                page_number=chunk.get("page_number", 0),
                chunk_id=chunk.get("chunk_id", ""),
                block_id=chunk.get("candidate_id", ""),
                section_label=chunk.get("section_title", ""),
                bbox=chunk.get("bbox"),
            )

            # Build metric field
            metric = None
            if raw.get("metric"):
                m = raw["metric"]
                if isinstance(m, dict) and m.get("value") is not None:
                    metric = MetricField(
                        value=float(m["value"]),
                        unit=str(m.get("unit", "unspecified")),
                        direction=m.get("direction"),
                    )
                    # Normalize the unit
                    metric = self.normalizer.normalize_metric_field(
                        metric, context=chunk.get("target_sentence", "")
                    )

            # Build location field
            location = None
            if raw.get("location"):
                loc = raw["location"]
                if isinstance(loc, dict) and loc.get("raw_text"):
                    location = LocationField(
                        raw_text=loc.get("raw_text") or "",
                        specificity=loc.get("specificity") or "global",
                    )
                elif isinstance(loc, str):
                    location = LocationField(raw_text=loc, specificity="region")

            # Build time field
            time_field = None
            if raw.get("time"):
                t = raw["time"]
                if isinstance(t, dict):
                    def clean(val):
                        if val is None or str(val).lower() == "null":
                            return None
                        return val
                    time_field = TimeField(
                        start_date=clean(t.get("start_date")),
                        end_date=clean(t.get("end_date")),
                        baseline_year=clean(t.get("baseline_year")),
                    )

            # Greenwashing signals: Claim Type (Target vs Performance)
            target_sentence = chunk.get("target_sentence", "")
            action_verb = raw.get("action") or "reported"
            claim_type = ClaimAnalyzer.classify_type(action_verb, target_sentence)

            # Normalization: Ontology mapping
            raw_aspect = raw.get("aspect") or "unknown"
            normalized_aspect = ESGOntology.normalize_aspect(raw_aspect)

            # Construct validated claim
            claim = ExtractedClaim(
                aspect=raw_aspect,
                normalized_aspect=normalized_aspect,
                action=action_verb,
                claim_type=claim_type,
                metric=metric,
                location=location,
                time=time_field,
                provenance=provenance,
                confidence=float(raw.get("confidence", 0.5)),
                source_type="text",
            )
            
            # Stanford Metric Signature Bucketing
            claim.metric_family = SignatureGenerator.generate_metric_family(normalized_aspect)
            claim.metric_key = SignatureGenerator.generate_metric_key(
                normalized_aspect, metric.unit if metric else None
            )
            claim.time_bucket = SignatureGenerator.generate_time_bucket(claim)
            claim.location_scope = SignatureGenerator.generate_location_scope(claim)
            claim.claim_signature = SignatureGenerator.generate_signature(
                claim.metric_key, claim.time_bucket, claim.location_scope
            )

            # Score groundability
            score, obs_type = self.classifier.score(claim)
            claim.groundability_score = score
            claim.observability_type = obs_type
            
            # Greenwashing signals: Vagueness score
            claim.vagueness_score = ClaimAnalyzer.compute_vagueness(claim)

            return claim

        except (ValidationError, Exception) as e:
            print(f"  [Validation] Skipped malformed claim: {e}")
            return None
