"""
ESGenuine — evidence-corpus loader regression suite
===================================================
Locks `load_external_corpus`: it must read the current `{"_meta", "records"}` shape,
still accept the legacy bare-list shape (with an inline `_schema` pseudo-record), and
never leak metadata/blank rows into the evidence set (self_improvement.md New finding #6).

Runs two ways:
  * pytest:      pytest backend/tests/test_fact_check_corpus.py
  * standalone:  python backend/tests/test_fact_check_corpus.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import reasoning.fact_check as fc  # noqa: E402


def _load_from(obj):
    """Run load_external_corpus against a temp corpus file holding `obj`."""
    original = fc._CORPUS_PATH
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "corpus.json"
        p.write_text(json.dumps(obj), encoding="utf-8")
        fc._CORPUS_PATH = p
        try:
            return fc.load_external_corpus()
        finally:
            fc._CORPUS_PATH = original


def test_current_shape_real_file():
    # The shipped corpus must load cleanly and contain only real evidence rows.
    recs = fc.load_external_corpus()
    assert len(recs) >= 3
    for r in recs:
        assert isinstance(r, dict)
        assert r.get("company_id") not in (None, "", "_schema", "_meta")
        for field in ("metric_key", "year", "value", "unit"):
            assert field in r, f"record missing {field}: {r}"


def test_new_shape_extracts_records_only():
    recs = _load_from({
        "_meta": {"note": "metadata must never appear as evidence"},
        "records": [
            {"company_id": "x", "metric_key": "emissions.scope1.co2e", "year": 2022,
             "value": 1, "unit": "tCO2e"},
            {"company_id": "", "metric_key": "noise"},          # blank id → dropped
            "not-a-dict",                                        # junk → dropped
        ],
    })
    assert len(recs) == 1 and recs[0]["company_id"] == "x"


def test_legacy_list_shape_filters_schema_row():
    recs = _load_from([
        {"company_id": "_schema", "metric_key": "emissions.scope1.co2e", "_note": "ignore me"},
        {"company_id": "y", "metric_key": "emissions.scope1.co2e", "year": 2021,
         "value": 2, "unit": "tCO2e"},
    ])
    assert len(recs) == 1 and recs[0]["company_id"] == "y"


def test_missing_or_malformed_file_is_safe():
    assert _load_from({"records": []}) == []          # empty records
    assert _load_from({}) == []                        # no records key
    # malformed JSON / missing file → empty, never raises
    original = fc._CORPUS_PATH
    fc._CORPUS_PATH = Path(tempfile.gettempdir()) / "does_not_exist_esg_corpus.json"
    try:
        assert fc.load_external_corpus() == []
    finally:
        fc._CORPUS_PATH = original


def test_quality_normalized_on_load():
    # Explicit tier kept; missing/garbage tier defaults to "unverified".
    recs = _load_from({"records": [
        {"company_id": "a", "metric_key": "m", "year": 1, "value": 1, "unit": "u", "quality": "VERIFIED"},
        {"company_id": "b", "metric_key": "m", "year": 1, "value": 1, "unit": "u"},
        {"company_id": "c", "metric_key": "m", "year": 1, "value": 1, "unit": "u", "quality": "bogus"},
    ]})
    q = {r["company_id"]: r["quality"] for r in recs}
    assert q == {"a": "verified", "b": "unverified", "c": "unverified"}


def test_corpus_quality_illustrative_only():
    # No verified records → illustrative_only True; one verified flips it False.
    illus = [{"company_id": "x", "quality": "illustrative"}, {"company_id": "y", "quality": "illustrative"}]
    summ = fc.corpus_quality(illus)
    assert summ["total"] == 2 and summ["by_quality"]["illustrative"] == 2 and summ["illustrative_only"] is True
    mixed = fc.corpus_quality(illus + [{"company_id": "z", "quality": "verified"}])
    assert mixed["by_quality"]["verified"] == 1 and mixed["illustrative_only"] is False
    assert fc.corpus_quality([])["illustrative_only"] is False  # empty corpus is not "illustrative-only"


def test_evidence_quality_on_verdict():
    # A SUPPORTED verdict reports the best trust tier among compared sources.
    claim = {"claim_id": "1", "metric_key": "emissions.scope1.co2e", "time_bucket": "2022",
             "metric_value": 100.0, "metric_unit": "tCO2e", "company_id": "x"}
    ev = [{"company_id": "x", "metric_key": "emissions.scope1.co2e", "year": "2022",
           "value": 100.0, "unit": "tCO2e", "kind": "external", "quality": "illustrative"},
          {"company_id": "x", "metric_key": "emissions.scope1.co2e", "year": "2022",
           "value": 101.0, "unit": "tCO2e", "kind": "cross_report", "quality": "self_reported"}]
    v = fc.check_claim(claim, ev)
    assert v["verdict"] == "SUPPORTED"
    assert v["evidence_quality"] == "self_reported"  # self_reported > illustrative


_ALL_TESTS = [
    test_current_shape_real_file,
    test_new_shape_extracts_records_only,
    test_legacy_list_shape_filters_schema_row,
    test_missing_or_malformed_file_is_safe,
    test_quality_normalized_on_load,
    test_corpus_quality_illustrative_only,
    test_evidence_quality_on_verdict,
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
