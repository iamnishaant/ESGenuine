"""
ESGenuine — fact-check → integrity-score integration suite (v2.2, improve_rating A3)
====================================================================================
Locks `build_report(..., factcheck=)`: no factcheck ⇒ identical to v2.1; CONTRADICTED
verdicts become an EXTERNAL_CONTRADICTION flag (Critical when verified-backed, High when
self_reported-only); externally-consistent reports earn a gated bonus recorded as
NEGATIVE points_deducted so `score == 100 − Σ(points)` stays invariant.

Runs two ways: pytest backend/tests/test_report_factcheck.py  |  python backend/tests/test_report_factcheck.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.integrity_report import build_report  # noqa: E402


def _claims(n=20):
    """Mixed-quality claims so the base score sits below 100 (bonus headroom exists)."""
    out = []
    for i in range(n):
        good = i % 2 == 0
        out.append({"claim_id": f"c{i}",
                    "claim_type": "performance" if good else "narrative",
                    "metric_value": 1.0 if good else None,
                    "groundability_score": 0.8 if good else 0.2,
                    "company_name": "TestCo", "report_year": 2024,
                    "metric_key": "emissions.scope1.co2e" if good else "uncategorized",
                    "time_bucket": "2024",
                    "vagueness_score": 0.1 if good else 0.9,
                    "observability_type": "reported_metric"})
    return out


def _fc(contradicted=0, supported=0, quality="verified", coverage=0.5, wcred=0.9):
    results = ([{"verdict": "CONTRADICTED", "evidence_quality": quality,
                 "statement": "ref says X", "reason": "diverges", "metric_key": "emissions.scope1.co2e"}] * contradicted
               + [{"verdict": "SUPPORTED", "evidence_quality": quality,
                   "metric_key": "emissions.scope1.co2e"}] * supported)
    checked = len(results)
    return {"checked": checked, "checkable": checked * 2, "coverage": coverage,
            "credibility": None, "weighted_credibility": wcred, "results": results}


def _invariant(report):
    total_pts = round(sum(p["points_deducted"] for p in report["penalty_breakdown"]), 1)
    assert abs(report["integrity_score"] - round(100.0 - total_pts, 1)) < 0.11, \
        (report["integrity_score"], total_pts)


def test_no_factcheck_unchanged():
    r = build_report(_claims())
    assert r["fact_check"] is None
    assert not any(p["type"] == "EXTERNAL_CONTRADICTION" for p in r["penalty_breakdown"])
    _invariant(r)


def test_verified_contradiction_is_critical():
    base = build_report(_claims())["integrity_score"]
    r = build_report(_claims(), factcheck=_fc(contradicted=3, quality="verified", coverage=0.1))
    fx = r["fact_check"]
    assert fx["external_contradictions"] == 3 and fx["severity"] == "Critical"
    assert any(f["type"] == "EXTERNAL_CONTRADICTION" and f["severity"] == "Critical"
               for f in r["flags"])
    assert r["integrity_score"] < base
    _invariant(r)


def test_self_reported_contradiction_is_high():
    r = build_report(_claims(), factcheck=_fc(contradicted=2, quality="self_reported", coverage=0.1))
    assert r["fact_check"]["severity"] == "High"
    _invariant(r)


def test_bonus_when_consistent_and_covered():
    base = build_report(_claims())["integrity_score"]
    r = build_report(_claims(), factcheck=_fc(supported=8, coverage=0.5, wcred=0.95))
    assert r["fact_check"]["bonus"] > 0
    assert r["integrity_score"] > base
    bonus_rows = [p for p in r["penalty_breakdown"] if p["type"] == "FACT_CHECK_BONUS"]
    assert len(bonus_rows) == 1 and bonus_rows[0]["points_deducted"] < 0
    _invariant(r)


def test_bonus_gated_on_coverage():
    r = build_report(_claims(), factcheck=_fc(supported=8, coverage=0.05, wcred=0.95))
    assert r["fact_check"]["bonus"] == 0.0


def test_bonus_gated_on_credibility():
    r = build_report(_claims(), factcheck=_fc(supported=8, coverage=0.5, wcred=0.5))
    assert r["fact_check"]["bonus"] == 0.0


def test_empty_factcheck_ignored():
    r = build_report(_claims(), factcheck={"checked": 0, "results": []})
    assert r["fact_check"] is None
    _invariant(r)


_ALL_TESTS = [test_no_factcheck_unchanged, test_verified_contradiction_is_critical,
              test_self_reported_contradiction_is_high, test_bonus_when_consistent_and_covered,
              test_bonus_gated_on_coverage, test_bonus_gated_on_credibility,
              test_empty_factcheck_ignored]


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
