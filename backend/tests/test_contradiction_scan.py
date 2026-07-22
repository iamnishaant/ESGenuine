"""
ESGenuine — Contradiction scan / dedup regression suite
=======================================================
Locks the per-document contradiction orchestration extracted into `scan_contradictions`,
in particular the NLI #4 fix: retrieval is symmetric, so within one document (A,B) and
(B,A) both surface — they must be reported (and severity-counted) exactly once.

I/O is injected (a fake retrieve_fn + a fake engine), so this runs with no Supabase and
no NLI model — fast and dependency-light.

Runs two ways: pytest backend/tests/test_contradiction_scan.py  |  python backend/tests/test_contradiction_scan.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.contradiction_scan import scan_contradictions  # noqa: E402


class FakeEngine:
    """evaluate_pair flags a contradiction for any unordered pair in `hits`."""
    def __init__(self, hits, conflict_type="Metric", severity="High"):
        self.hits = {frozenset(p) for p in hits}
        self.conflict_type = conflict_type
        self.severity = severity
        self.calls = 0

    def evaluate_pair(self, a, b):
        self.calls += 1
        key = frozenset((a.get("claim_id"), b.get("claim_id")))
        if key in self.hits:
            return {"has_contradiction": True, "severity": self.severity,
                    "conflict_type": self.conflict_type, "reasoning": "conflict",
                    "nli_data": {"confidence": 0.88, "label": "contradiction"}}
        return {"has_contradiction": False, "severity": "None", "conflict_type": "None",
                "reasoning": "", "nli_data": {"confidence": 0.0, "label": "neutral"}}


def _claim(cid, doc="d1", text="t", page=1):
    return {"claim_id": cid, "doc_id": doc, "source_sentence": text, "page_number": page}


def test_symmetric_pair_reported_once():
    A, B = _claim("A"), _claim("B")
    # symmetric retrieval: A finds B, B finds A
    retrieve = {"A": [B], "B": [A]}
    eng = FakeEngine(hits=[("A", "B")])
    conflicts, counts = scan_contradictions([A, B], lambda c: retrieve[c["claim_id"]], eng)
    assert len(conflicts) == 1                 # not 2
    assert counts["High"] == 1                 # severity counted once
    assert eng.calls == 1                      # the duplicate pair was never re-evaluated


def test_self_pair_skipped():
    A = _claim("A")
    eng = FakeEngine(hits=[("A", "A")])
    conflicts, counts = scan_contradictions([A], lambda c: [A], eng)   # retrieval returns itself
    assert conflicts == [] and eng.calls == 0


def test_cross_report_candidate_recorded_once():
    A = _claim("A", doc="d1")
    X = _claim("X", doc="d2")                  # candidate from another report
    eng = FakeEngine(hits=[("A", "X")])
    conflicts, _ = scan_contradictions([A], lambda c: [X], eng)
    assert len(conflicts) == 1
    assert conflicts[0]["claim_b_doc"] == "d2"  # cross-report doc surfaced


def test_confidence_numeric_vs_textual():
    A, B, C = _claim("A"), _claim("B"), _claim("C")
    # numeric (Metric) → confidence 1.0
    num = FakeEngine(hits=[("A", "B")], conflict_type="Metric")
    conflicts, _ = scan_contradictions([A], lambda c: [B], num)
    assert conflicts[0]["confidence"] == 1.0
    # textual → carries the model confidence
    txt = FakeEngine(hits=[("A", "C")], conflict_type="Textual")
    conflicts2, _ = scan_contradictions([A], lambda c: [C], txt)
    assert conflicts2[0]["confidence"] == 0.88


def test_missing_ids_are_still_evaluated():
    # candidates without a claim_id can't be deduped, but must still be evaluated.
    A = _claim("A")
    nob = {"doc_id": "d9", "source_sentence": "no id", "page_number": 2}  # no claim_id
    eng = FakeEngine(hits=[])  # no hit, but we assert it was consulted
    scan_contradictions([A], lambda c: [nob], eng)
    assert eng.calls == 1


def test_no_candidates_is_empty():
    A = _claim("A")
    eng = FakeEngine(hits=[("A", "B")])
    conflicts, counts = scan_contradictions([A], lambda c: [], eng)
    assert conflicts == [] and counts == {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    assert eng.calls == 0


def test_retrieval_failure_propagates_not_swallowed():
    # existing_issues #1: a retrieval failure must SURFACE (the endpoint reports
    # retrieval_available:false), never be silently swallowed into "0 conflicts".
    # scan_contradictions is pure — it lets a raising retrieve_fn propagate.
    A = _claim("A")
    eng = FakeEngine(hits=[])

    def boom(_claim):
        raise RuntimeError("match_claims RPC failed (Server disconnected)")

    try:
        scan_contradictions([A], boom, eng)
        raise AssertionError("expected the retrieval error to propagate")
    except RuntimeError as e:
        assert "RPC failed" in str(e)


_ALL_TESTS = [
    test_symmetric_pair_reported_once,
    test_self_pair_skipped,
    test_cross_report_candidate_recorded_once,
    test_confidence_numeric_vs_textual,
    test_missing_ids_are_still_evaluated,
    test_no_candidates_is_empty,
    test_retrieval_failure_propagates_not_swallowed,
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
