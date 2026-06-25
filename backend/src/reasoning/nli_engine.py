"""
ESGenuine — Week 4: NLI & Numeric Reasoning Engine
===========================================================
Executes Natural Language Inference (RoBERTa-MNLI) and strict
numeric comparison rules to detect contradictions between
two closely related ESG claims.
"""

try:  # canonical unit conversion + value sanity (#15/#16); robust to import path
    from extractors.ontology import UnitCanonicalizer
except ImportError:  # pragma: no cover
    from src.extractors.ontology import UnitCanonicalizer

_NLI_MODEL_NAME = "typeform/distilbert-base-uncased-mnli"


class ContradictionEngine:
    def __init__(self):
        # Lazy load (NLI Improvement Opportunity #2): the DistilBERT-MNLI weights are
        # ~250–350 MB resident and the torch/transformers import dominates cold start.
        # The numeric path decides most pairs and never needs the model, so we defer
        # loading (and even the `transformers` import) until the first *textual*
        # comparison. This also keeps the module import-safe — constructible without
        # torch installed — so the numeric reasoning is unit-testable in isolation.
        self._nli_model = None

    @property
    def nli_model(self):
        """The HF text-classification pipeline, loaded on first access."""
        if self._nli_model is None:
            print("Loading DistilBERT-MNLI model for rapid textual reasoning...")
            from transformers import pipeline  # deferred: only paid for textual NLI
            self._nli_model = pipeline("text-classification", model=_NLI_MODEL_NAME)
        return self._nli_model

    @staticmethod
    def _normalize_label(raw) -> str:
        """Map a model label to one of contradiction/neutral/entailment.
        Handles named labels (CONTRADICTION/…) and is defensive about LABEL_x ids
        (returned as-is lowercased, so they never accidentally read as a contradiction)."""
        l = str(raw or "").lower()
        if "contra" in l:
            return "contradiction"
        if "entail" in l:
            return "entailment"
        if "neutral" in l:
            return "neutral"
        return l

    def _textual_entailment(self, text_a: str, text_b: str) -> dict:
        """
        Decide whether text_b (hypothesis) contradicts text_a (premise) using
        DistilBERT-MNLI as a proper premise/hypothesis PAIR.

        FIX (self_improvement.md / take_step_forward.md §3.3): the previous version
        concatenated both sentences into one string with a bogus `</s></body>`
        separator and ran *single-sequence* classification — the model never received
        a premise/hypothesis pair, so every "Textual" verdict was unreliable. The HF
        text-classification pipeline tokenizes {"text": premise, "text_pair": hypothesis}
        as a real NLI pair (premise [SEP] hypothesis).
        """
        a = (text_a or "").strip()
        b = (text_b or "").strip()
        if not a or not b:
            return {"is_contradiction": False, "label": "neutral", "confidence": 0.0}

        result = self.nli_model({"text": a, "text_pair": b})
        if isinstance(result, list):
            result = result[0]

        label = self._normalize_label(result["label"])
        score = float(result["score"])
        is_contradiction = label == "contradiction" and score > 0.6
        return {
            "is_contradiction": is_contradiction,
            "label": label,
            "confidence": score,
        }

    # Metric keys that carry no comparable numeric semantics.
    _VAGUE_KEYS = ("", "uncategorized")

    # (The absolute-quantity / extreme-YoY guard was removed with #18: cross-year value
    #  differences are no longer treated as contradictions at all, so there is nothing left
    #  to guard against an implausible year-over-year ratio.)

    @staticmethod
    def _real_bucket(t) -> bool:
        """A time_bucket we can actually compare on (a real year, not a placeholder)."""
        if t is None:
            return False
        return str(t).strip().lower() not in ("", "unknown_time", "unknown", "null", "none", "n/a")

    @classmethod
    def _comparable(cls, a: dict, b: dict) -> bool:
        """
        Two claims are numerically comparable only if they describe the SAME metric
        (identical, meaningful `metric_key`) in the SAME unit.

        FIX (#7): the retrieval RPC blocks by `metric_family`, which is far too coarse
        — e.g. `social.workforce.total.percent` and `social.workforce.count` both sit
        in family `social.workforce` but mean different things. Comparing their values
        produced the noisy false positives (12.3M vs 453K, unit-blind) logged as #7.
        """
        ka, kb = a.get("metric_key"), b.get("metric_key")
        if not ka or not kb or ka != kb:
            return False
        if ka in cls._VAGUE_KEYS or str(ka).endswith(".unspecified"):
            return False
        # (#15) Reject claims whose value contradicts the shape its metric_key implies
        # (e.g. a 74.445 "count") — these are extraction mislabels, not real conflicts.
        if not UnitCanonicalizer.is_value_plausible(ka, a.get("metric_value")):
            return False
        if not UnitCanonicalizer.is_value_plausible(kb, b.get("metric_value")):
            return False
        # (#16) Require the same *canonical* unit. Canonicalization lets us compare
        # e.g. ktCO2e vs tCO2e (same dimension, rescaled) instead of dropping them as
        # a unit mismatch — and still blocks genuinely incomparable units.
        _, ua = UnitCanonicalizer.to_canonical(a.get("metric_value"), a.get("metric_unit"))
        _, ub = UnitCanonicalizer.to_canonical(b.get("metric_value"), b.get("metric_unit"))
        ua = (ua or "").strip().lower()
        ub = (ub or "").strip().lower()
        if ua and ub and ua != ub:
            return False
        return True

    def _numeric_conflict(self, claim_a: dict, claim_b: dict) -> dict:
        """
        Applies strict mathematical rules to detect Metric, Temporal, Scope, and Hard
        (direction) contradictions — but only between claims about the *same* metric.
        """
        # Gate: never numerically compare two different metrics/units (#7).
        if not self._comparable(claim_a, claim_b):
            return None

        # Compare on canonical values so unit scale differences (kt vs t) don't read
        # as contradictions (#16).
        val_a, _ = UnitCanonicalizer.to_canonical(claim_a.get("metric_value"), claim_a.get("metric_unit"))
        val_b, _ = UnitCanonicalizer.to_canonical(claim_b.get("metric_value"), claim_b.get("metric_unit"))
        time_a, time_b = claim_a.get("time_bucket"), claim_b.get("time_bucket")
        scope_a, scope_b = claim_a.get("location_scope"), claim_b.get("location_scope")
        real_a, real_b = self._real_bucket(time_a), self._real_bucket(time_b)
        same_scope = scope_a == scope_b

        # 1. Numeric value rules — require real, comparable temporal context.
        if val_a is not None and val_b is not None:
            # Zero-baseline guard (#7): a change measured against ~0 (often a missing
            # value recorded as 0.0, e.g. "0.0 -> 2.8") is not a meaningful conflict.
            if abs(val_a) > 1e-9 and abs(val_b) > 1e-9:
                base = max(abs(val_a), abs(val_b))
                if abs(val_a - val_b) / base > 0.05 and real_a and real_b:
                    mk = claim_a.get("metric_key")
                    if time_a == time_b and same_scope:
                        return {"type": "Metric", "reason": f"Value mismatch: {val_a} vs {val_b} for {mk} in {time_a}/{scope_a}"}
                    elif not same_scope and time_a == time_b and scope_a and scope_b:
                        return {"type": "Scope", "reason": f"Value {val_a} vs {val_b} across scopes {scope_a}/{scope_b} in {time_a}"}
                    # NOTE (#18): a value difference across DIFFERENT real years is NOT a
                    # contradiction — it's a normal year-over-year time series (e.g. LTIFR
                    # 0.4 in 2022 vs 1.7 in 2021). Flagging every cross-year pair as a
                    # "Temporal shift" inflated the contradiction count ~3x (569/956 on
                    # shell_2022) and saturated every integrity score to grade F. A genuine
                    # same-year double-reporting is caught by the Metric rule above. A
                    # trend that contradicts a *stated* direction is the Hard rule below.
                    # So cross-year (time_a != time_b, same scope) falls through to None.

        # 2. Hard: logical impossibility — same metric, same real time, same scope.
        dir_a, dir_b = claim_a.get("metric_direction"), claim_b.get("metric_direction")
        if dir_a and dir_b and real_a and real_b and time_a == time_b and same_scope:
            if {dir_a.lower(), dir_b.lower()} == {"increase", "decrease"}:
                return {"type": "Hard", "reason": f"Direction conflict for {claim_a.get('metric_key')} in {time_a}: {dir_a} vs {dir_b}"}

        return None

    def evaluate_pair(self, claim_a: dict, claim_b: dict) -> dict:
        """
        Evaluates a candidate pair returned from the semantic retrieval buckets
        to determine if there is a contradiction.
        """
        # 1. Run strict numeric rules first (they are cheaper and more definitive)
        numeric_result = self._numeric_conflict(claim_a, claim_b)

        # 2. NLI is only a fallback for subtle textual contradictions. If the numeric
        #    rules already decided, skip the expensive (and lower-confidence) NLI pass.
        if numeric_result:
            nli_result = {"is_contradiction": False, "label": "skipped", "confidence": 0.0}
        else:
            text_a = claim_a.get("source_sentence", "")
            text_b = claim_b.get("source_sentence", "")
            nli_result = self._textual_entailment(text_a, text_b)
        
        severity = "None"
        conflict_type = "None"
        reasoning_text = ""
        
        if numeric_result:
            conflict_type = numeric_result["type"]
            reasoning_text = numeric_result["reason"]
            # Assign severity levels (Hard > Metric > Temporal > Scope).
            if conflict_type == "Hard": severity = "Critical"
            elif conflict_type == "Metric": severity = "High"
            elif conflict_type == "Temporal": severity = "Medium"
            elif conflict_type == "Scope": severity = "Low"
            
        elif nli_result["is_contradiction"]:
            conflict_type = "Textual"
            severity = "High"
            reasoning_text = f"NLI Model detected {nli_result['label']} (Conf: {nli_result['confidence']:.2f})"
        
        return {
            "has_contradiction": (severity != "None"),
            "severity": severity,
            "conflict_type": conflict_type,
            "reasoning": reasoning_text,
            "nli_data": nli_result
        }

if __name__ == "__main__":
    engine = ContradictionEngine()
    
    base = {"metric_key": "emissions.scope1.co2e", "metric_unit": "%"}

    # Test 1: Hard Contradiction (same metric, same time/scope, opposite directions)
    c1 = {**base, "metric_direction": "increase", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We increased emissions by 40% globally in 2023."}
    c2 = {**base, "metric_direction": "decrease", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We decreased emissions by 40% globally in 2023."}

    # Test 2: Cross-year shift (same metric/scope, different real years) — NOT a contradiction (#18)
    c3 = {**base, "metric_direction": "decrease", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We achieved a 40% reduction in emissions globally."}
    c4 = {**base, "metric_direction": "decrease", "metric_value": 15, "time_bucket": "2024", "location_scope": "global", "source_sentence": "Total emissions reductions reached 15% globally."}

    # Test 3: should NOT flag — different metric_key in same family
    c5 = {"metric_key": "social.workforce.total.percent", "metric_unit": "%", "metric_value": 9134, "time_bucket": "unknown_time", "location_scope": "global", "source_sentence": "Women represent a share of the workforce."}
    c6 = {"metric_key": "social.workforce.count", "metric_unit": "count", "metric_value": 453608, "time_bucket": "2024", "location_scope": "global", "source_sentence": "Total workforce headcount."}

    # Test 4: should NOT flag — zero baseline
    c7 = {**base, "metric_value": 0.0, "time_bucket": "2023", "location_scope": "global", "source_sentence": "No change reported."}
    c8 = {**base, "metric_value": 2.8, "time_bucket": "2023", "location_scope": "global", "source_sentence": "Increased by 2.8."}

    print("\n[Test 1] Hard Conflict (expect Critical/Hard):")
    print(engine._numeric_conflict(c1, c2))

    print("\n[Test 2] Cross-year shift (expect None — time series, not a contradiction):")
    print(engine._numeric_conflict(c3, c4))

    print("\n[Test 3] Different metric_key (expect None):")
    print(engine._numeric_conflict(c5, c6))

    print("\n[Test 4] Zero baseline (expect None):")
    print(engine._numeric_conflict(c7, c8))
