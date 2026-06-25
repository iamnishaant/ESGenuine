"""
ESGenuine — Agent pure-helper regression suite
===============================================
Locks the no-LLM helpers added this session (self_improvement.md):
  * suggest_questions(report)      — starter questions from flags/stats
  * _key_findings(...)             — structured bullets (richer non-LLM summary)
  * _unsupported_citations(...)    — hallucinated [n] detection
  * synthesize_audit fallback      — structured path emits key_findings

Importing `agent` normally pulls sentence_transformers/supabase; we stub those during the
import then remove the stubs (same harness as test_api_routes). `_has_llm` is forced False
so synthesize_audit takes the deterministic structured path (no network).

Runs two ways: pytest backend/tests/test_agent_helpers.py  |  python backend/tests/test_agent_helpers.py
"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


class _FakeLLMClient:
    def __init__(self, *a, **k):
        self.endpoints = []
        self.provider = "none"

    def extract(self, prompt):
        return "{}"


_STUBS = {
    "sentence_transformers": _stub("sentence_transformers", SentenceTransformer=lambda *a, **k: None),
    "supabase": _stub("supabase", create_client=lambda *a, **k: None, Client=object),
    "dotenv": _stub("dotenv", load_dotenv=lambda *a, **k: None),
    "extractors.claim_extractor": _stub("extractors.claim_extractor", LLMClient=_FakeLLMClient),
}
_added = [n for n in _STUBS if n not in sys.modules]
for n in _added:
    sys.modules[n] = _STUBS[n]
try:
    from reasoning import agent  # noqa: E402
finally:
    for n in _added:
        sys.modules.pop(n, None)

agent._has_llm = lambda: False  # force the structured (no-network) path


_REPORT = {
    "meta": {"company_name": "Acme"},
    "integrity_score": 55, "grade": "C", "greenwashing_risk": "Moderate",
    "flags": [{"type": "Vague", "title": "Vague claims", "severity": "High", "count": 4}],
    "statistics": {"with_metric_pct": 30, "contradictions": 2},
}


def test_suggest_questions_from_flags_and_stats():
    qs = agent.suggest_questions(_REPORT)
    assert "Which environmental claims lack measurable metrics?" in qs        # vague flag
    assert any("qualitative" in q for q in qs)                                # <50% metric
    assert any("contradiction" in q.lower() for q in qs)                      # contradictions>0
    assert len(qs) == len(set(qs)) <= 5                                       # deduped, capped


def test_suggest_questions_defaults_when_no_flags():
    qs = agent.suggest_questions({"meta": {"company_name": "X"}, "flags": [], "statistics": {}})
    assert qs and any("emissions targets" in q for q in qs)


def test_unsupported_citations():
    assert agent._unsupported_citations([1, 2, 9], {1, 2, 3}) == [9]
    assert agent._unsupported_citations([1, "x", None], {1}) == []   # non-ints ignored, 1 valid
    assert agent._unsupported_citations([], {1}) == []


def test_key_findings_and_structured_fallback():
    fc = {"credibility": 0.8, "coverage": 0.5, "verdict_counts": {}}
    sc = {"metrics": [{"verdict": "lagging", "metric_key": "emissions.scope1.co2e"}]}
    out = agent.synthesize_audit(_REPORT, fc, sc)
    assert out["engine"] == "structured"
    kf = out["key_findings"]
    assert isinstance(kf, list) and kf
    assert any("Integrity score 55" in b for b in kf)
    assert any("80%" in b for b in kf)              # credibility surfaced
    assert any("Lagging vs peers" in b for b in kf)
    assert out["executive_summary"] == " ".join(kf)


_ALL_TESTS = [
    test_suggest_questions_from_flags_and_stats,
    test_suggest_questions_defaults_when_no_flags,
    test_unsupported_citations,
    test_key_findings_and_structured_fallback,
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
