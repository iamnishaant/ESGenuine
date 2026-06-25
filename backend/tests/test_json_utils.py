"""
ESGenuine — lenient LLM-JSON parser regression suite
=====================================================
Locks `json_utils.loads_lenient`: parse JSON from raw / ```fenced``` / preamble+trailing
output, and raise (not silently mis-parse) when there is no object — so the LLM callers
(ask / synthesize_audit / llm_verdict) stop losing whole answers to a stray code fence.

Runs two ways: pytest backend/tests/test_json_utils.py  |  python backend/tests/test_json_utils.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.json_utils import loads_lenient  # noqa: E402


def test_plain_json():
    assert loads_lenient('{"verdict": "SUPPORTED", "confidence": 0.8}')["verdict"] == "SUPPORTED"


def test_code_fenced():
    assert loads_lenient('```json\n{"a": 1}\n```')["a"] == 1
    assert loads_lenient('```\n{"a": 2}\n```')["a"] == 2


def test_preamble_and_trailing_prose():
    assert loads_lenient('Sure, here you go: {"a": 3}. Hope that helps!')["a"] == 3


def test_nested_object_recovered():
    raw = 'noise {"answer": "x", "used": [1, 2], "meta": {"k": "v"}} tail'
    out = loads_lenient(raw)
    assert out["used"] == [1, 2] and out["meta"]["k"] == "v"


def test_garbage_raises():
    for bad in ("no json here", "", None):
        try:
            loads_lenient(bad)
            raised = False
        except (ValueError, Exception):
            raised = True
        assert raised, f"expected raise for {bad!r}"


_ALL_TESTS = [test_plain_json, test_code_fenced, test_preamble_and_trailing_prose,
              test_nested_object_recovered, test_garbage_raises]


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
