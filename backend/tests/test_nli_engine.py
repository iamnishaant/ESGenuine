"""
ESGenuine — Contradiction Engine regression suite
=================================================
Locks the numeric contradiction rules (the high-confidence, deterministic core) and the
evaluate_pair orchestration. These were previously only spot-checked via the module's
`__main__` block.

Made possible by the 2026-06-25 lazy-load fix: `ContradictionEngine()` no longer loads
DistilBERT (or even imports `transformers`) on construction, so the numeric path is
testable in isolation and the textual path can be exercised with an injected fake model
— no 250 MB download, no torch required for the numeric cases.

Asserts, among other things, that the numeric path NEVER triggers a model load.

Runs two ways:
  * pytest:      pytest backend/tests/test_nli_engine.py
  * standalone:  python backend/tests/test_nli_engine.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.nli_engine import ContradictionEngine  # noqa: E402

_BASE = {"metric_key": "emissions.scope1.co2e", "metric_unit": "tCO2e"}


def _c(**kw):
    return {**_BASE, "location_scope": "global", "source_sentence": "", **kw}


def test_construction_does_not_load_model():
    e = ContradictionEngine()
    assert e._nli_model is None, "model must not load on construction (lazy)"


def test_hard_direction_conflict():
    e = ContradictionEngine()
    a = _c(metric_value=40, time_bucket="2023", metric_direction="increase", metric_unit="%")
    b = _c(metric_value=40, time_bucket="2023", metric_direction="decrease", metric_unit="%")
    r = e._numeric_conflict(a, b)
    assert r and r["type"] == "Hard"


def test_metric_value_mismatch_same_year():
    e = ContradictionEngine()
    a = _c(metric_value=40, time_bucket="2023", metric_unit="%")
    b = _c(metric_value=50, time_bucket="2023", metric_unit="%")
    r = e._numeric_conflict(a, b)
    assert r and r["type"] == "Metric"


def test_temporal_shift_across_years():
    e = ContradictionEngine()
    a = _c(metric_value=40, time_bucket="2023", metric_unit="%")
    b = _c(metric_value=30, time_bucket="2024", metric_unit="%")
    r = e._numeric_conflict(a, b)
    assert r and r["type"] == "Temporal"


def test_scope_conflict_same_year_diff_scope():
    e = ContradictionEngine()
    a = _c(metric_value=1000, time_bucket="2023", location_scope="europe")
    b = _c(metric_value=2000, time_bucket="2023", location_scope="asia")
    r = e._numeric_conflict(a, b)
    assert r and r["type"] == "Scope"


def test_canonical_units_prevent_false_conflict():
    # 1000 tCO2e vs 1.0 ktCO2e are the SAME quantity → must NOT be a contradiction.
    e = ContradictionEngine()
    a = _c(metric_value=1000, metric_unit="tCO2e", time_bucket="2023")
    b = _c(metric_value=1.0, metric_unit="ktCO2e", time_bucket="2023")
    assert e._numeric_conflict(a, b) is None


def test_incomparable_units_are_gated_out():
    # same metric_key, but an intensity vs an absolute → not comparable → no conflict.
    e = ContradictionEngine()
    a = _c(metric_value=1000, metric_unit="tCO2e", time_bucket="2023")
    b = _c(metric_value=0.5, metric_unit="tCO2e/MWh", time_bucket="2023")
    assert e._numeric_conflict(a, b) is None


def test_zero_baseline_is_not_a_conflict():
    e = ContradictionEngine()
    a = _c(metric_value=0.0, time_bucket="2023", metric_unit="%")
    b = _c(metric_value=2.8, time_bucket="2023", metric_unit="%")
    assert e._numeric_conflict(a, b) is None


def test_extreme_yoy_ratio_on_absolute_is_suppressed():
    # 10 -> 100000 tCO2e across years is a unit/extraction error, not a real annual change.
    e = ContradictionEngine()
    a = _c(metric_value=10, metric_unit="tCO2e", time_bucket="2023")
    b = _c(metric_value=100000, metric_unit="tCO2e", time_bucket="2024")
    assert e._numeric_conflict(a, b) is None


def test_different_metric_keys_not_compared():
    e = ContradictionEngine()
    a = {"metric_key": "social.workforce.total.percent", "metric_unit": "%",
         "metric_value": 9134, "time_bucket": "unknown_time", "location_scope": "global"}
    b = {"metric_key": "social.workforce.total.count", "metric_unit": "count",
         "metric_value": 453608, "time_bucket": "2024", "location_scope": "global"}
    assert e._numeric_conflict(a, b) is None


def test_mislabeled_value_is_gated_by_plausibility():
    # a ".count" carrying 74.445 is an extraction mislabel (#15) → not comparable.
    e = ContradictionEngine()
    a = {"metric_key": "social.workforce.total.count", "metric_unit": "count",
         "metric_value": 74.445, "time_bucket": "2023", "location_scope": "global"}
    b = {"metric_key": "social.workforce.total.count", "metric_unit": "count",
         "metric_value": 500000, "time_bucket": "2023", "location_scope": "global"}
    assert e._numeric_conflict(a, b) is None


def test_evaluate_pair_short_circuits_nli_on_numeric_hit():
    e = ContradictionEngine()
    a = _c(metric_value=40, time_bucket="2023", metric_direction="increase", metric_unit="%")
    b = _c(metric_value=40, time_bucket="2023", metric_direction="decrease", metric_unit="%")
    res = e.evaluate_pair(a, b)
    assert res["has_contradiction"] and res["severity"] == "Critical"
    assert res["conflict_type"] == "Hard"
    assert res["nli_data"]["label"] == "skipped"      # NLI not consulted
    assert e._nli_model is None                        # ...and the model was never loaded


def test_textual_path_with_injected_fake_model():
    # No numeric signal (no metric_key) → NLI fallback runs. Inject a fake pipeline so the
    # textual branch is exercised without DistilBERT.
    e = ContradictionEngine()
    e._nli_model = lambda inp: {"label": "CONTRADICTION", "score": 0.91}
    a = {"metric_key": None, "source_sentence": "Our emissions fell sharply in 2023."}
    b = {"metric_key": None, "source_sentence": "Our emissions rose sharply in 2023."}
    res = e.evaluate_pair(a, b)
    assert res["has_contradiction"] and res["conflict_type"] == "Textual"
    assert res["severity"] == "High"
    assert res["nli_data"]["confidence"] == 0.91

    # A low-confidence or neutral model verdict must NOT be reported as a contradiction.
    e2 = ContradictionEngine()
    e2._nli_model = lambda inp: {"label": "NEUTRAL", "score": 0.99}
    res2 = e2.evaluate_pair(a, b)
    assert not res2["has_contradiction"] and res2["conflict_type"] == "None"


_ALL_TESTS = [
    test_construction_does_not_load_model,
    test_hard_direction_conflict,
    test_metric_value_mismatch_same_year,
    test_temporal_shift_across_years,
    test_scope_conflict_same_year_diff_scope,
    test_canonical_units_prevent_false_conflict,
    test_incomparable_units_are_gated_out,
    test_zero_baseline_is_not_a_conflict,
    test_extreme_yoy_ratio_on_absolute_is_suppressed,
    test_different_metric_keys_not_compared,
    test_mislabeled_value_is_gated_by_plausibility,
    test_evaluate_pair_short_circuits_nli_on_numeric_hit,
    test_textual_path_with_injected_fake_model,
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
