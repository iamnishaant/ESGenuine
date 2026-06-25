"""
ESGenuine — Route-level integration tests (light-import harness)
================================================================
Exercises the FastAPI reasoning routes end-to-end through the REAL orchestration
(`scan_contradictions`) and the REAL numeric engine — only Supabase + the embedding model
are faked. This closes the gap noted in self_improvement.md: the pure seams were unit-
tested, but the route wiring (fetch → seam → response, plus the 404 path) was not.

The blocker was that importing `api_reasoning` transitively imports `sentence_transformers`
(via `retrieval`/`agent`). We resolve it by stubbing the heavy import-time dependencies in
`sys.modules` *only for the duration of the import*, then removing them so other suites in
the same pytest process still get the real libraries. The lazy-loaded NLI model is never
touched (the test data triggers the deterministic numeric path).

Runs two ways: pytest backend/tests/test_api_routes.py  |  python backend/tests/test_api_routes.py
"""

import asyncio
import sys
import types
from pathlib import Path

# api_reasoning uses absolute `from src.reasoning...` imports → put the backend ROOT on path.
sys.path.insert(0, str(Path(__file__).parent.parent))


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


class _FakeLLMClient:
    """Stands in for extractors.claim_extractor.LLMClient; reports 'no LLM configured'."""
    def __init__(self, *a, **k):
        self.endpoints = []
        self.provider = "none"

    def extract(self, prompt):
        return "{}"


# Heavy libs imported at module load by retrieval.py / agent.py. We register lightweight
# stubs, import api_reasoning, then remove the ones we added (so we never shadow the real
# libraries for other test files in the same process).
_STUBS = {
    "sentence_transformers": _stub("sentence_transformers", SentenceTransformer=lambda *a, **k: None),
    "supabase": _stub("supabase", create_client=lambda *a, **k: None, Client=object),
    "dotenv": _stub("dotenv", load_dotenv=lambda *a, **k: None),
    "src.extractors.claim_extractor": _stub("src.extractors.claim_extractor", LLMClient=_FakeLLMClient),
}
_added = [n for n in _STUBS if n not in sys.modules]
for n in _added:
    sys.modules[n] = _STUBS[n]
try:
    from src.reasoning import api_reasoning as ar  # noqa: E402
finally:
    for n in _added:
        sys.modules.pop(n, None)  # stop shadowing real libs for the rest of the session


def _claim(cid, direction, value=40, doc="doc1"):
    return {"claim_id": cid, "doc_id": doc, "metric_key": "emissions.scope1.co2e",
            "metric_value": value, "metric_unit": "%", "time_bucket": "2023",
            "location_scope": "global", "metric_direction": direction,
            "source_sentence": f"emissions {direction}d", "page_number": 1}


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return types.SimpleNamespace(data=self._data)


class _FakeSupabase:
    def __init__(self, data):
        self._data = data

    def table(self, _name):
        return _FakeQuery(self._data)


def _run_contradictions(claims, retrieve, fake_nli=None):
    """Drive the real async route with a faked Supabase + retrieval. `fake_nli` controls
    the engine's textual path: None means 'must not be needed' (numeric should decide)."""
    ar.get_supabase = lambda: _FakeSupabase(claims)
    ar.find_candidate_pairs = lambda c, similarity_threshold=0.85: retrieve(c)
    ar.engine._nli_model = fake_nli   # never let the route load the real DistilBERT
    return asyncio.run(ar.get_contradictions("doc1"))


def test_route_dedups_symmetric_contradiction():
    a, b = _claim("A", "increase"), _claim("B", "decrease")  # Hard conflict (real engine)
    # symmetric retrieval: A finds B, B finds A — must be reported ONCE
    out = _run_contradictions([a, b], lambda c: [b] if c["claim_id"] == "A" else [a])
    assert out["total_conflicts"] == 1, out
    assert out["critical"] == 1                          # direction conflict → Critical/Hard
    assert out["conflicts"][0]["conflict_type"] == "Hard"
    assert out["conflicts"][0]["confidence"] == 1.0      # numeric → deterministic
    assert ar.engine._nli_model is None                  # numeric short-circuit: model untouched


def test_route_no_contradiction_when_consistent():
    a = _claim("A", "decrease")
    b = _claim("B", "decrease")                          # same direction → no numeric conflict
    # numeric clears the pair → the textual path runs; inject a NEUTRAL fake so no real model.
    out = _run_contradictions([a, b], lambda c: [b] if c["claim_id"] == "A" else [a],
                              fake_nli=lambda inp: {"label": "NEUTRAL", "score": 0.99})
    assert out["total_conflicts"] == 0
    assert out["critical"] == out["high"] == out["medium"] == out["low"] == 0


def test_route_404_when_no_claims():
    from fastapi import HTTPException
    ar.get_supabase = lambda: _FakeSupabase([])
    try:
        asyncio.run(ar.get_contradictions("missing"))
        raised = None
    except HTTPException as e:
        raised = e
    assert raised is not None and raised.status_code == 404


_ALL_TESTS = [
    test_route_dedups_symmetric_contradiction,
    test_route_no_contradiction_when_consistent,
    test_route_404_when_no_claims,
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
