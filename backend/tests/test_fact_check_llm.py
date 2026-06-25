"""
ESGenuine — LLM fact-check fallback + grounding-guard regression suite
======================================================================
Locks `llm_verdict`'s grounding guards and the opt-in LLM fallback in
`fact_check_document` (self_improvement.md: "llm_verdict defined but never called —
needs a grounding guard before wiring"). Uses a fake LLM (no network / no model):

  * no evidence            ⇒ UNVERIFIED, deterministically, with the LLM never called
  * confident + no reason  ⇒ downgraded to UNVERIFIED (ungrounded)
  * confidence out of range⇒ clamped to [0, 1]
  * malformed JSON         ⇒ UNVERIFIED, engine="llm"
  * fallback only fires on numeric-UNVERIFIED claims that *have* evidence, and never
    overrides a deterministic numeric verdict.

Runs two ways: pytest backend/tests/test_fact_check_llm.py  |  python backend/tests/test_fact_check_llm.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.fact_check import llm_verdict, fact_check_document  # noqa: E402


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def extract(self, prompt):
        self.calls += 1
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def test_guard_no_evidence_skips_llm():
    llm = FakeLLM({"verdict": "SUPPORTED", "confidence": 0.9, "reasoning": "x"})
    out = llm_verdict("Some claim", [], llm)
    assert out["verdict"] == "UNVERIFIED" and out["engine"] == "guard"
    assert llm.calls == 0          # the model is never consulted with no evidence
    # blank/whitespace-only statements count as no evidence too
    assert llm_verdict("c", ["", "   ", None], llm)["engine"] == "guard"
    assert llm.calls == 0


def test_guard_confident_verdict_without_reasoning_is_downgraded():
    llm = FakeLLM({"verdict": "CONTRADICTED", "confidence": 0.95, "reasoning": ""})
    out = llm_verdict("claim", ["some evidence"], llm)
    assert out["verdict"] == "UNVERIFIED" and llm.calls == 1


def test_confidence_is_clamped():
    llm = FakeLLM({"verdict": "SUPPORTED", "confidence": 5.0, "reasoning": "cited"})
    assert llm_verdict("claim", ["ev"], llm)["confidence"] == 1.0
    llm2 = FakeLLM({"verdict": "SUPPORTED", "confidence": -2, "reasoning": "cited"})
    assert llm_verdict("claim", ["ev"], llm2)["confidence"] == 0.0


def test_valid_supported_passes_through():
    llm = FakeLLM({"verdict": "supported", "confidence": 0.8, "reasoning": "matches the filing"})
    out = llm_verdict("claim", ["ev"], llm)
    assert out["verdict"] == "SUPPORTED" and out["confidence"] == 0.8 and out["engine"] == "llm"


def test_malformed_json_is_unverified():
    out = llm_verdict("claim", ["ev"], FakeLLM("not json at all"))
    assert out["verdict"] == "UNVERIFIED" and out["engine"] == "llm"


# ── fallback wiring in fact_check_document ───────────────────────────────────────
def _claim(value, unit):
    return {"claim_id": "c1", "source_sentence": "Scope 1 emissions were as reported.",
            "metric_key": "emissions.scope1.co2e", "metric_value": value, "metric_unit": unit,
            "time_bucket": "2022", "company_id": "x", "report_id": "r1"}


def _external(value, unit):
    return [{"company_id": "x", "metric_key": "emissions.scope1.co2e", "year": 2022,
             "value": value, "unit": unit, "statement": "Independent reference figure.",
             "source": "test", "url": ""}]


def test_fallback_upgrades_numeric_unverified_when_evidence_exists():
    # Evidence is an intensity (tCO2e/MWh) → numerically incomparable with the absolute
    # claim → numeric verdict UNVERIFIED, but evidence statements exist → LLM fallback runs.
    llm = FakeLLM({"verdict": "CONTRADICTED", "confidence": 0.7, "reasoning": "diverges from the reference"})
    out = fact_check_document([_claim(100, "tCO2e")], [], external=_external(0.5, "tCO2e/MWh"), llm=llm)
    assert out["checked"] == 1 and out["llm_assisted"] == 1
    assert out["results"][0]["verdict"] == "CONTRADICTED" and out["results"][0]["engine"] == "llm"


def test_fallback_never_overrides_numeric_verdict():
    # Comparable evidence → numeric SUPPORTED. Even with an LLM present that would say
    # CONTRADICTED, the deterministic numeric verdict must stand and the LLM not be called.
    llm = FakeLLM({"verdict": "CONTRADICTED", "confidence": 0.99, "reasoning": "noise"})
    out = fact_check_document([_claim(100, "tCO2e")], [], external=_external(100, "tCO2e"), llm=llm)
    assert out["results"][0]["verdict"] == "SUPPORTED"
    assert out["llm_assisted"] == 0 and llm.calls == 0


def test_no_llm_is_unchanged_default():
    out = fact_check_document([_claim(100, "tCO2e")], [], external=_external(0.5, "tCO2e/MWh"))
    assert out["llm_assisted"] == 0 and out["results"][0]["verdict"] == "UNVERIFIED"


_ALL_TESTS = [
    test_guard_no_evidence_skips_llm,
    test_guard_confident_verdict_without_reasoning_is_downgraded,
    test_confidence_is_clamped,
    test_valid_supported_passes_through,
    test_malformed_json_is_unverified,
    test_fallback_upgrades_numeric_unverified_when_evidence_exists,
    test_fallback_never_overrides_numeric_verdict,
    test_no_llm_is_unchanged_default,
]


if __name__ == "__main__":
    failures = 0
    for t in _ALL_TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(_ALL_TESTS) - failures}/{len(_ALL_TESTS)} passed")
    sys.exit(1 if failures else 0)
