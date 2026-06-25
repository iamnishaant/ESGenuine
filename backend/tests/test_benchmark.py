"""
ESGenuine — Peer Benchmark & Trajectory regression suite
========================================================
Locks the numeric behaviour the Portfolio / Integrity-Audit pages depend on:
  * polarity routing (lower- vs higher-better),
  * cross-company ranking + percentile + cross-unit comparability (ktCO2e≡tCO2e),
  * modal-unit dropping (never compare an intensity against an absolute),
  * company scorecard verdicts (leading/lagging) and the ≥2-peer gate,
  * trajectory: the linear `avg_change_per_year` that feeds gap-to-target, the true
    compound `cagr` (positive-endpoints only), and the zero-baseline guards.

The trajectory cases in particular pin the 2026-06-25 CAGR fix (self_improvement.md):
the field that drives `on_track` must stay a *linear* absolute rate, while `cagr` is a
separate compound display number.

Runs two ways:
  * pytest:      pytest backend/tests/test_benchmark.py
  * standalone:  python backend/tests/test_benchmark.py   (no pytest needed)
"""

import sys
from pathlib import Path

# Add backend/src to path (mirrors the other tests in this folder).
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.benchmark import (  # noqa: E402
    polarity, cross_company, company_scorecard, trajectory,
)

_REL_TOL = 1e-6


def _close(got, exp) -> bool:
    if got is None:
        return exp is None
    return abs(got - exp) <= abs(exp) * _REL_TOL + 1e-15


def _claim(company, year, mk, value, unit):
    return {"company_id": company, "company_name": company, "report_year": year,
            "metric_key": mk, "metric_value": value, "metric_unit": unit}


def test_polarity_routing():
    assert polarity("emissions.scope1.co2e") == "lower_better"
    assert polarity("social.health_safety.ltifr.rate") == "lower_better"
    assert polarity("energy.renewable.percent") == "higher_better"
    assert polarity("social.diversity.gender.percent") == "higher_better"
    assert polarity("social.workforce.total.count") == "neutral"
    assert polarity("") == "neutral"
    assert polarity(None) == "neutral"


def test_cross_company_lower_better_and_cross_unit():
    # C reports in ktCO2e — must canonicalise to 1500 tCO2e and rank between A and B.
    claims = [
        _claim("A", 2020, "emissions.scope1.co2e", 1200, "tCO2e"),   # older year, ignored
        _claim("A", 2022, "emissions.scope1.co2e", 1000, "tCO2e"),
        _claim("B", 2022, "emissions.scope1.co2e", 2000, "tCO2e"),
        _claim("C", 2022, "emissions.scope1.co2e", 1.5, "ktCO2e"),
    ]
    d = cross_company(claims, "emissions.scope1.co2e")
    assert d["n"] == 3 and d["unit"] == "tCO2e"
    assert d["incomparable_dropped"] == 0
    assert _close(d["median"], 1500.0)
    by = {e["company"]: e for e in d["entries"]}
    # lower is better → A best (rank 1), C mid, B worst
    assert by["A"]["rank"] == 1 and by["A"]["value"] == 1000.0 and by["A"]["year"] == 2022
    assert by["C"]["rank"] == 2 and _close(by["C"]["value"], 1500.0)
    assert by["B"]["rank"] == 3 and by["B"]["value"] == 2000.0
    # percentile: A best=100, C middle=50, B worst=0
    assert by["A"]["percentile"] == 100
    assert by["C"]["percentile"] == 50
    assert by["B"]["percentile"] == 0


def test_cross_company_higher_better():
    claims = [
        _claim("A", 2023, "energy.renewable.percent", 20, "%"),
        _claim("B", 2023, "energy.renewable.percent", 50, "%"),
        _claim("C", 2023, "energy.renewable.percent", 80, "%"),
    ]
    d = cross_company(claims, "energy.renewable.percent")
    by = {e["company"]: e for e in d["entries"]}
    # higher is better → C best
    assert by["C"]["rank"] == 1 and by["C"]["percentile"] == 100
    assert by["B"]["rank"] == 2 and by["B"]["percentile"] == 50
    assert by["A"]["rank"] == 3 and by["A"]["percentile"] == 0


def test_cross_company_drops_incomparable_units():
    # Three absolutes (tCO2e) + one intensity (tCO2e/MWh) under the same metric_key.
    # The intensity canonicalises to a different unit and must be dropped, not averaged in.
    claims = [
        _claim("A", 2022, "emissions.scope1.co2e", 1000, "tCO2e"),
        _claim("B", 2022, "emissions.scope1.co2e", 1100, "tCO2e"),
        _claim("C", 2022, "emissions.scope1.co2e", 1200, "tCO2e"),
        _claim("D", 2022, "emissions.scope1.co2e", 0.5, "tCO2e/MWh"),
    ]
    d = cross_company(claims, "emissions.scope1.co2e")
    assert d["n"] == 3 and d["unit"] == "tCO2e"
    assert d["incomparable_dropped"] == 1
    assert "D" not in {e["company"] for e in d["entries"]}


def test_company_scorecard_verdict_and_peer_gate():
    claims = [
        # shared metric across 3 companies → comparable
        _claim("A", 2022, "emissions.scope1.co2e", 1000, "tCO2e"),
        _claim("B", 2022, "emissions.scope1.co2e", 2000, "tCO2e"),
        _claim("C", 2022, "emissions.scope1.co2e", 3000, "tCO2e"),
        # metric only A reports → must be excluded by the ≥2-peer gate
        _claim("A", 2022, "water.recycled.percent", 40, "%"),
    ]
    sc = company_scorecard(claims, "A")
    keys = {m["metric_key"] for m in sc["metrics"]}
    assert "emissions.scope1.co2e" in keys
    assert "water.recycled.percent" not in keys          # single-company metric gated out
    em = next(m for m in sc["metrics"] if m["metric_key"] == "emissions.scope1.co2e")
    assert em["of"] == 3 and em["rank"] == 1              # A has the lowest emissions
    assert em["percentile"] == 100 and em["verdict"] == "leading"


def test_peer_depth_confidence():
    # 3 peers → confidence ok; 2 peers → low (thin sample).
    three = [_claim(c, 2022, "emissions.scope1.co2e", v, "tCO2e")
             for c, v in (("A", 1), ("B", 2), ("C", 3))]
    assert cross_company(three, "emissions.scope1.co2e")["confidence"] == "ok"
    two = three[:2]
    d2 = cross_company(two, "emissions.scope1.co2e")
    assert d2["confidence"] == "low" and d2["n"] == 2
    # scorecard flags the thin metric
    sc = company_scorecard(two, "A")
    em = next(m for m in sc["metrics"] if m["metric_key"] == "emissions.scope1.co2e")
    assert em["low_confidence"] is True
    assert sc["low_confidence_metrics"] == 1


def test_trajectory_linear_rate_and_compound_cagr():
    # decreasing emissions 1000 → 810 over 2 years
    claims = [
        _claim("acme", 2020, "emissions.scope1.co2e", 1000, "tCO2e"),
        _claim("acme", 2022, "emissions.scope1.co2e", 810, "tCO2e"),
    ]
    t = trajectory(claims, "acme", "emissions.scope1.co2e", target_value=500, target_year=2030)
    assert t["points"] == 2 and t["polarity"] == "lower_better" and t["trend"] == "down"
    assert _close(t["change"], -190.0)
    assert _close(t["change_pct"], -19.0)
    assert _close(t["avg_change_per_year"], -95.0)        # linear: (810-1000)/2
    assert _close(t["cagr"], -0.1)                        # compound: sqrt(0.81)-1
    assert "cagr_per_year" not in t                       # old misleading key is gone
    # gap-to-target uses the LINEAR rate vs the linear required rate (no dimension error)
    assert t["target"]["required_per_year"] == -38.75     # (500-810)/8
    assert t["target"]["on_track"] is True                # -95/yr drops faster than -38.75/yr


def test_trajectory_increasing_compound_cagr():
    claims = [
        _claim("z", 2021, "energy.renewable.percent", 100, "%"),
        _claim("z", 2023, "energy.renewable.percent", 400, "%"),
    ]
    t = trajectory(claims, "z", "energy.renewable.percent")
    assert _close(t["avg_change_per_year"], 150.0)        # (400-100)/2
    assert _close(t["cagr"], 1.0)                         # (400/100)^(1/2)-1 = 1.0


def test_trajectory_zero_baseline_and_single_point():
    # zero baseline: compound cagr & pct are undefined → None; linear rate still defined
    z = trajectory([
        _claim("z", 2021, "emissions.scope1.co2e", 0, "tCO2e"),
        _claim("z", 2023, "emissions.scope1.co2e", 40, "tCO2e"),
    ], "z", "emissions.scope1.co2e")
    assert z["cagr"] is None and z["change_pct"] is None
    assert _close(z["avg_change_per_year"], 20.0)
    # single data point: no trend/change/cagr emitted at all
    one = trajectory([
        _claim("solo", 2022, "emissions.scope1.co2e", 500, "tCO2e"),
    ], "solo", "emissions.scope1.co2e")
    assert one["points"] == 1
    for k in ("change", "change_pct", "avg_change_per_year", "cagr", "trend", "target"):
        assert k not in one


_ALL_TESTS = [
    test_polarity_routing,
    test_cross_company_lower_better_and_cross_unit,
    test_cross_company_higher_better,
    test_cross_company_drops_incomparable_units,
    test_company_scorecard_verdict_and_peer_gate,
    test_peer_depth_confidence,
    test_trajectory_linear_rate_and_compound_cagr,
    test_trajectory_increasing_compound_cagr,
    test_trajectory_zero_baseline_and_single_point,
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
