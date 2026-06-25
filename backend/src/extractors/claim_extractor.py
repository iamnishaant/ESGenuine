"""
ESGenuine — Week 3: Context-Aware LLM AAMLT Extractor
=============================================================

Takes semantic chunks (Week 2, Step 7 output) and extracts structured
AAMLT claims using an LLM with Pydantic validation + retry.

Supports: OpenAI (GPT-4o), Anthropic (Claude), or local fallback.
"""

import json
import os
import re
import sys
import time
import difflib
import itertools
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# SECTION-LEVEL EXTRACTION PROMPT (SOTA: one call per section, full context)
# ══════════════════════════════════════════════

SECTION_EXTRACTION_PROMPT = """You are an ESG (Environmental, Social, Governance) claim extraction system.

You will receive ONE SECTION of a corporate sustainability report. Extract EVERY distinct, factual ESG claim it contains as structured JSON.

## Output Format
Return a JSON object: {{"claims": [ ... ]}}. Each claim object:
{{
  "source_sentence": "the exact sentence copied VERBATIM from the text below that states this claim (for traceability)",
  "aspect": "topic (emissions, water, energy, waste, biodiversity, safety, diversity, governance, etc.)",
  "action": "what was done (reduced, increased, achieved, maintained, etc.)",
  "metric": {{ "value": 40.0, "unit": "%", "direction": "decrease" }},
  "location": {{ "raw_text": "Pune facility", "specificity": "facility" }},
  "time": {{ "start_date": "2023-04-01", "end_date": "2024-03-31", "baseline_year": null }},
  "confidence": 0.9
}}

## Rules
1. "source_sentence" MUST be copied verbatim from the provided text so it can be traced back. Never invent it.
2. Any field not determinable from the text -> null.
3. metric.direction: "absolute" for a reported figure/snapshot, "decrease"/"increase" for changes. Most table figures are "absolute".
4. location.specificity: "facility","city","region","country","global". Do NOT default to "global"; use null if unknown.
5. Dates ISO (YYYY-MM-DD). Indian FY: FY2024 = 2023-04-01 to 2024-03-31. If a row shows current vs previous year, emit TWO claims.
6. Do NOT extract aspirational/policy intentions ("we aim to...", "we are committed to...", "we plan to...") — only factual, REPORTED data.
7. Numbers over 999 must have NO thousands separators: 22,372 -> 22372.0.
8. If a number has no explicit unit, infer it from context (employees, INR, %, hours, tCO2e, MWh, etc.).
9. Return at most 25 claims for this section; prefer the most specific and measurable.
10. If the section has no factual ESG claims, return {{"claims": []}}.

## Section title: {section_title}

## Section text
{section_text}

Return the JSON object now:"""


# ══════════════════════════════════════════════
# TABLE-CLAIMS PROMPT (Phase 2: from VLM-extracted markdown tables)
# ══════════════════════════════════════════════

TABLE_CLAIMS_PROMPT = """You are an ESG claim extraction system. You will receive MARKDOWN TABLES read from page {page} of a corporate sustainability report. Extract EVERY quantified ESG metric as a structured JSON claim.

Return {{"claims": [ ... ]}}. Each claim:
{{
  "source_sentence": "a short label identifying the row/metric, e.g. 'Scope 1 GHG emissions 2023'",
  "aspect": "emissions, water, energy, waste, biodiversity, safety, diversity, workforce, training, governance, ...",
  "action": "reported",
  "metric": {{ "value": 58.0, "unit": "million tonnes CO2e", "direction": "absolute" }},
  "location": null,
  "time": {{ "start_date": "2023-01-01", "end_date": "2023-12-31", "baseline_year": null }},
  "confidence": 0.9
}}

## Rules
1. ONE claim per (metric, year) cell. If a row shows current vs previous year (e.g. 2023 and 2022), emit TWO claims, each with its own year.
2. metric.value: numbers only, no thousands separators (1,234 -> 1234).
3. metric.unit: take the unit from the column header, the table title, or a units row, and INHERIT it for every row in that table. e.g. "million tonnes CO2e", "%", "GWh", "thousand m3", "MWh". NEVER output "number", "unit", or an empty unit if a unit is discernible from the table; only use null if truly none exists.
4. metric.direction: "absolute" for a reported figure (most table cells).
5. time: infer the year from the column header (calendar year unless the table states a fiscal year).
6. Skip non-numeric / explanatory rows. baseline_year must be an integer or null.
7. If the tables contain no quantified ESG metrics, return {{"claims": []}}.

## Page {page} tables
{tables}

Return the JSON object now:"""


# ══════════════════════════════════════════════
# LLM CLIENT ABSTRACTION
# ══════════════════════════════════════════════

class LLMClient:
    """Unified LLM client supporting OpenAI, Anthropic, or mock fallback."""

    def __init__(self):
        # Round-robin pool of OpenAI-compatible endpoints (NVIDIA + Groq, multi-key).
        # Concurrent workers spread across all keys/providers -> faster, fewer stalls.
        self.endpoints = self._build_pool()
        self._rr = itertools.count()
        self._rr_lock = threading.Lock()
        if self.endpoints:
            counts = {}
            for e in self.endpoints:
                counts[e["provider"]] = counts.get(e["provider"], 0) + 1
            self.provider = "pool[" + ", ".join(f"{p}x{n}" for p, n in counts.items()) + "]"
        else:
            self.provider = self._detect_provider()  # legacy single-provider / fallback

    @staticmethod
    def _keys(*env_names) -> list:
        """Collect API keys from env vars (comma-separated lists supported), de-duplicated."""
        out, seen = [], set()
        for name in env_names:
            for k in (os.environ.get(name, "") or "").split(","):
                k = k.strip()
                if k and k not in seen:
                    seen.add(k)
                    out.append(k)
        return out

    def _build_pool(self) -> list:
        eps = []
        nv_model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        for k in self._keys("NVIDIA_API_KEYS", "NVIDIA_API_KEY"):
            eps.append({"provider": "nvidia", "key": k, "model": nv_model,
                        "url": "https://integrate.api.nvidia.com/v1/chat/completions"})
        gq_model = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
        for k in self._keys("GROQ_API_KEYS", "GROQ_API_KEY"):
            eps.append({"provider": "groq", "key": k, "model": gq_model,
                        "url": "https://api.groq.com/openai/v1/chat/completions"})
        # HuggingFace Inference Providers (OpenAI-compatible router) — another route.
        hf_model = os.environ.get("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        for k in self._keys("HF_API_KEYS", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
            eps.append({"provider": "hf", "key": k, "model": hf_model,
                        "url": "https://router.huggingface.co/v1/chat/completions"})
        return eps

    def _next_endpoint(self) -> dict:
        with self._rr_lock:
            i = next(self._rr)
        return self.endpoints[i % len(self.endpoints)]

    def _call_endpoint(self, ep: dict, prompt: str) -> str:
        """Call any OpenAI-compatible chat endpoint (NVIDIA / Groq) with JSON mode."""
        import requests
        resp = requests.post(
            ep["url"],
            headers={"Authorization": f"Bearer {ep['key']}", "Content-Type": "application/json"},
            json={
                "model": ep["model"],
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "3000")),
                "response_format": {"type": "json_object"},
            },
            timeout=(15, 300),
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _detect_provider(self) -> str:
        # NVIDIA NIM is preferred when configured (larger/stronger models, no Groq
        # free-tier daily cap). Falls back through the other providers, then to the
        # rule-based extractor if no key is present.
        if os.environ.get("NVIDIA_API_KEY"):
            return "nvidia"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        print("[LLM] No API key found. Using rule-based fallback extractor.")
        return "fallback"

    def extract(self, prompt: str) -> str:
        # Pool path: round-robin across all configured NVIDIA/Groq keys.
        if self.endpoints:
            return self._call_endpoint(self._next_endpoint(), prompt)
        # Legacy single-provider fallback (openai/anthropic/rule-based).
        if self.provider == "openai":
            return self._call_openai(prompt)
        if self.provider == "anthropic":
            return self._call_anthropic(prompt)
        return self._fallback_extract(prompt)

    def _call_nvidia(self, prompt: str) -> str:
        """NVIDIA NIM (OpenAI-compatible). Model is configurable via NVIDIA_MODEL."""
        import requests

        model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['NVIDIA_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": int(os.environ.get("NVIDIA_MAX_TOKENS", "3000")),
                "response_format": {"type": "json_object"},
            },
            timeout=(15, 300),  # (connect, read) — large 70B section calls can be slow
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

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

    # ──────────────────────────────────────────────
    # SOTA: section-level extraction (one call per section, full context)
    # ──────────────────────────────────────────────

    _SIGNAL_NUM = re.compile(r"\d")
    _SIGNAL_ESG = re.compile(
        r"\b(emission|carbon|co2|ghg|scope\s*[123]|energy|renewable|solar|wind|water|waste|"
        r"recycl|biodiversity|safety|ltifr|injur|fatal|diversity|gender|women|employee|workforce|"
        r"training|governance|board|tonne|mwh|gwh|kwh|hectare|percent)\b|%", re.IGNORECASE)

    def _section_has_signal(self, text: str) -> bool:
        """Cheap pre-filter: skip boilerplate sections (no number AND no ESG term) to save calls."""
        return bool(self._SIGNAL_NUM.search(text) and self._SIGNAL_ESG.search(text))

    def _window_sentences(self, sentences: List[Dict[str, Any]], max_chars: int = 6000):
        """Yield consecutive-sentence windows that fit a per-call character budget."""
        window: List[Dict[str, Any]] = []
        size = 0
        for s in sentences:
            t = s.get("text", "") or ""
            if window and size + len(t) > max_chars:
                yield window
                window, size = [], 0
            window.append(s)
            size += len(t) + 1
        if window:
            yield window

    def _match_sentence(self, src: str, window: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Map a model-returned source_sentence back to the real parsed sentence (for provenance)."""
        if not src:
            return None
        src_l = src.lower()
        best, best_ratio = None, 0.0
        for s in window:
            tl = (s.get("text", "") or "").lower()
            if not tl:
                continue
            if src_l in tl or tl in src_l:
                return s
            r = difflib.SequenceMatcher(None, src_l, tl).ratio()
            if r > best_ratio:
                best, best_ratio = s, r
        return best if best_ratio >= 0.5 else None

    def extract_from_sections(
        self,
        sections: List[Dict[str, Any]],
        document_id: str = "",
        max_workers: Optional[int] = None,
    ) -> List[ExtractedClaim]:
        """
        SOTA extraction path: ONE LLM call per (windowed) section instead of per
        candidate sentence. Gives the model full section context (better quality),
        cuts calls ~10-20x, and runs the calls CONCURRENTLY (NVIDIA_CONCURRENCY).

        `sections` = [{"section_title": str,
                       "sentences": [{"text","page_number","sentence_id","bbox"}]}]
        """
        if max_workers is None:
            max_workers = int(os.environ.get("NVIDIA_CONCURRENCY", "6"))

        # 1) Build the work list (one item per windowed section that passes the pre-filter).
        work: List[tuple] = []
        for sec in sections:
            title = sec.get("section_title", "Unknown")
            sentences = sec.get("sentences", []) or []
            if not sentences:
                continue
            if not self._section_has_signal("\n".join(s.get("text", "") for s in sentences)):
                continue
            for window in self._window_sentences(sentences):
                work.append((title, window))

        print(f"[Extractor] Section mode: {len(work)} windows over {len(sections)} sections, "
              f"{max_workers}-way concurrent...")

        # 2) One window -> one LLM call -> validated claims.
        def process(item) -> List[ExtractedClaim]:
            title, window = item
            wtext = "\n".join(s.get("text", "") for s in window)
            prompt = SECTION_EXTRACTION_PROMPT.format(section_title=title, section_text=wtext)
            out: List[ExtractedClaim] = []
            try:
                raws = self._call_with_retry(prompt)
            except RuntimeError as e:
                print(f"  [Failed] section '{title}': {e}")
                return out
            for raw in raws:
                if not isinstance(raw, dict):
                    continue
                src = (raw.pop("source_sentence", "") or "").strip()
                matched = self._match_sentence(src, window) or window[0]
                chunk = {
                    "target_sentence": matched.get("text", src),
                    "page_number": matched.get("page_number", 0),
                    "chunk_id": matched.get("sentence_id", ""),
                    "candidate_id": matched.get("sentence_id", ""),
                    "section_title": title,
                    "bbox": matched.get("bbox"),
                }
                claim = self._validate_and_enrich(raw, chunk, document_id)
                if claim and self._is_meaningful_claim(claim):
                    out.append(claim)
            return out

        # 3) Fan out concurrently, with a live progress bar.
        all_claims: List[ExtractedClaim] = []
        total = len(work)
        if total:
            is_tty = sys.stdout.isatty()
            done = 0
            t0 = time.time()
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = [ex.submit(process, item) for item in work]
                for fut in as_completed(futures):
                    all_claims.extend(fut.result())
                    done += 1
                    filled = int(24 * done / total)
                    # ASCII bar when stdout is redirected (a Windows cp1252 log file
                    # can't encode the block glyph and would crash the whole ingest).
                    fill_ch, empty_ch = ("█", "·") if is_tty else ("#", "-")
                    bar = fill_ch * filled + empty_ch * (24 - filled)
                    rate = done / max(time.time() - t0, 1e-6)
                    eta = (total - done) / rate if rate else 0
                    msg = f"  [extract] |{bar}| {done}/{total} windows · {len(all_claims)} claims · ETA {eta:4.0f}s"
                    if is_tty:
                        print("\r" + msg, end="" if done < total else "\n", flush=True)
                    elif done == total or done % 5 == 0:
                        print(msg, flush=True)        # periodic lines for redirected logs

        print(f"[Extractor] Section mode done: {total} LLM calls -> {len(all_claims)} claims.")
        return all_claims

    def extract_from_table_markdown(
        self,
        tables: List[Dict[str, Any]],
        document_id: str = "",
        max_workers: Optional[int] = None,
    ) -> List[ExtractedClaim]:
        """
        Phase 2: turn VLM-extracted markdown tables into structured claims.
        `tables` = [{"page_number": int, "markdown": str}] (from VLMTableExtractor).
        """
        if max_workers is None:
            max_workers = int(os.environ.get("NVIDIA_CONCURRENCY", "4"))
        work = [t for t in tables if (t.get("markdown") or "").strip()]
        print(f"[Extractor] Table mode: {len(work)} table pages, {max_workers}-way concurrent...")

        def process(t) -> List[ExtractedClaim]:
            prompt = TABLE_CLAIMS_PROMPT.format(page=t["page_number"], tables=t["markdown"][:8000])
            out: List[ExtractedClaim] = []
            try:
                raws = self._call_with_retry(prompt)
            except RuntimeError as e:
                print(f"  [Failed] table page {t['page_number']}: {e}")
                return out
            for raw in raws:
                if not isinstance(raw, dict):
                    continue
                src = (raw.pop("source_sentence", "") or "").strip()
                chunk = {
                    "target_sentence": src or f"table page {t['page_number']}",
                    "page_number": t["page_number"],
                    "chunk_id": f"tbl_p{t['page_number']}",
                    "candidate_id": f"tbl_p{t['page_number']}",
                    "section_title": "Performance Data",
                    "bbox": None,
                }
                claim = self._validate_and_enrich(raw, chunk, document_id)
                if claim:
                    claim.source_type = "table"
                    if self._is_meaningful_claim(claim):
                        out.append(claim)
            return out

        all_claims: List[ExtractedClaim] = []
        if work:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                for res in ex.map(process, work):
                    all_claims.extend(res)
        print(f"[Extractor] Table mode done: {len(work)} calls -> {len(all_claims)} claims.")
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
                    # Normalize the unit (pass aspect so aspect-based inference works)
                    metric = self.normalizer.normalize_metric_field(
                        metric, context=chunk.get("target_sentence", ""),
                        aspect=str(raw.get("aspect", "")),
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
