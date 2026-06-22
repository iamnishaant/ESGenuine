"""
Pharos Integrity — Week 4: NLI & Numeric Reasoning Engine
===========================================================
Executes Natural Language Inference (RoBERTa-MNLI) and strict
numeric comparison rules to detect contradictions between
two closely related ESG claims.
"""

from transformers import pipeline

class ContradictionEngine:
    def __init__(self):
        print("Loading DistilBERT-MNLI model for rapid textual reasoning...")
        # Swapped to a lightweight, fast NLI model to avoid massive RAM hangs on local CPU
        self.nli_model = pipeline("text-classification", model="typeform/distilbert-base-uncased-mnli")

    def _textual_entailment(self, text_a: str, text_b: str) -> dict:
        """
        Runs RoBERTa-MNLI to determine if text_b contradicts text_a.
        MNLI labels typically map to: 0 -> contradiction, 1 -> neutral, 2 -> entailment
        """
        # Format for MNLI models: "premise </s></body> hypothesis"
        input_text = f"{text_a} </s></body> {text_b}"
        result = self.nli_model(input_text)[0]
        
        label = result['label'].lower()
        score = result['score']
        
        is_contradiction = score > 0.6 and label == "contradiction"
        return {
            "is_contradiction": is_contradiction,
            "label": label,
            "confidence": score
        }

    def _numeric_conflict(self, claim_a: dict, claim_b: dict) -> dict:
        """
        Applies strict mathematical rules to detect Metric, Temporal, and Scope contradictions.
        """
        # 1. Metric: Direct Numeric Contradiction
        # If the units and directions match, but values are wildly different
        val_a, val_b = claim_a.get("metric_value"), claim_b.get("metric_value")
        if val_a is not None and val_b is not None:
            # If the value difference is greater than 5%
            if abs(val_a - val_b) / (max(abs(val_a), 1)) > 0.05:
                # Need to check if they share the same time bucket and scope
                time_a, time_b = claim_a.get("time_bucket"), claim_b.get("time_bucket")
                scope_a, scope_b = claim_a.get("location_scope"), claim_b.get("location_scope")
                
                if time_a == time_b and scope_a == scope_b:
                    return {"type": "Metric", "reason": f"Value mismatch: {val_a} vs {val_b} for same time/scope"}
                elif time_a and time_b and time_a != time_b and scope_a == scope_b:
                    return {"type": "Temporal", "reason": f"Value shifted {val_a}->{val_b} between {time_a} and {time_b}"}
                elif scope_a and scope_b and scope_a != scope_b and time_a == time_b:
                     return {"type": "Scope", "reason": f"Value mismatch {val_a} vs {val_b} across scopes {scope_a} and {scope_b}"}

        # 2. Hard: Logical Impossibility
        # E.g. direction == 'increase' vs 'decrease'
        dir_a, dir_b = claim_a.get("metric_direction"), claim_b.get("metric_direction")
        if dir_a and dir_b:
            d_a, d_b = dir_a.lower(), dir_b.lower()
            if set([d_a, d_b]) == {"increase", "decrease"}:
                 return {"type": "Hard", "reason": f"Direction conflict: {dir_a} vs {dir_b}"}
             
        return None

    def evaluate_pair(self, claim_a: dict, claim_b: dict) -> dict:
        """
        Evaluates a candidate pair returned from the semantic retrieval buckets
        to determine if there is a contradiction.
        """
        # 1. Run strict numeric rules first (they are cheaper and more definitive)
        numeric_result = self._numeric_conflict(claim_a, claim_b)
        
        # 2. Run NLI reasoning to catch subtle textual contradictions
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
    
    # Test 1: Hard Contradiction
    c1 = {"metric_direction": "increase", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We increased emissions by 40% globally in 2023."}
    c2 = {"metric_direction": "decrease", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We decreased emissions by 40% globally in 2023."}
    
    # Test 2: Temporal Shift
    c3 = {"metric_direction": "decrease", "metric_value": 40, "time_bucket": "2023", "location_scope": "global", "source_sentence": "We achieved a 40% reduction in emissions globally."}
    c4 = {"metric_direction": "decrease", "metric_value": 15, "time_bucket": "2024", "location_scope": "global", "source_sentence": "Total emissions reductions reached 15% globally."}
    
    print("\n[Test 1] Hard Conflict:")
    print(engine.evaluate_pair(c1, c2))
    
    print("\n[Test 2] Temporal Shift:")
    print(engine.evaluate_pair(c3, c4))
