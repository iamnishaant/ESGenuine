"""
ESGenuine — Integrity-report + fact-check additive-field regression suite
=========================================================================
Locks this session's additive improvements (self_improvement.md):
  * build_report → `penalty_breakdown` (per-flag points), `computed_at`, `report_version`
    — and the score still equals 100 − Σ(points) (or 0 when over-penalised).
  * fact_check_document → `coverage` = checked / checkable (distinct from credibility).
  * check_claim → actionable UNVERIFIED reasons (names the metric/year, or the unit clash).

Runs two ways: pytest backend/tests/test_report_extras.py  |  python backend/tests/test_report_extras.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoning.integrity_report import build_report  # noqa: E402
from reasoning.fact_check import fact_check_document, check_claim  # noqa: E402


def _claim(cid, ctype="narrative", value=None, vague=0.0, ground=0.5):
    return {"claim_id": cid, "doc_id": "d1", "company_name": "Acme", "report_year": 2023,
            "claim_type": ctype, "metric_value": value, "vagueness_score": vague,
            "groundability_score": ground, "source_sentence": f"sentence {cid}",
            "metric_key": "emissions.scope1.co2e" if value is not None else None}


def test_build_report_penalty_breakdown_and_provenance():
    claims = [_claim(f"c{i}", ctype="narrative", vague=0.9) for i in range(8)]
    rep = build_report(claims, contradictions=[])
    assert rep["status"] == "ok"
    # provenance present
    assert rep["report_version"] == "2.1"
    assert isinstance(rep["computed_at"], str) and "T" in rep["computed_at"]
    # decomposition present and well-formed
    bd = rep["penalty_breakdown"]
    assert isinstance(bd, list)
    for item in bd:
        assert set(("type", "title", "severity", "count", "points_deducted")) <= set(item)
    # sorted most-impactful first
    pts = [i["points_deducted"] for i in bd]
    assert pts == sorted(pts, reverse=True)
    # score reconciles with the breakdown: 100 − Σ(points), clamped at 0
    total_pts = sum(pts)
    assert round(rep["integrity_score"]) == round(max(0, 100 - total_pts))


def test_score_is_count_weighted_by_prevalence():
    """The headline guarantee: the SAME flag costs more when it is more pervasive.
    A report where 10% of claims are vague must outscore one where 90% are — flat
    per-flag-type scoring gave both the identical deduction (everyone an F)."""
    def report_with_vague_fraction(frac, n=50):
        n_vague = round(n * frac)
        claims = ([_claim(f"v{i}", ctype="narrative", vague=0.9) for i in range(n_vague)] +
                  [_claim(f"c{i}", ctype="narrative", vague=0.0, ground=0.9) for i in range(n - n_vague)])
        return build_report(claims, contradictions=[])

    light = report_with_vague_fraction(0.10)
    heavy = report_with_vague_fraction(0.90)
    assert heavy["integrity_score"] < light["integrity_score"]   # prevalence discriminates
    # the breakdown exposes prevalence, and points scale with it
    lv = next(p for p in light["penalty_breakdown"] if p["type"] == "VAGUE")
    hv = next(p for p in heavy["penalty_breakdown"] if p["type"] == "VAGUE")
    assert hv["prevalence"] > lv["prevalence"]
    assert hv["points_deducted"] > lv["points_deducted"]


def test_review_dismissal_raises_score_raw_unchanged():
    """Human-in-the-loop: dismissing flagged claims as false positives removes them from
    the flag's count → score rises; the raw (pre-review) score is still reported; a
    'confirmed' verdict changes nothing."""
    claims = ([_claim(f"v{i}", ctype="narrative", vague=0.9) for i in range(45)] +
              [_claim(f"c{i}", ctype="narrative", vague=0.0, ground=0.9) for i in range(5)])
    base = build_report(claims, contradictions=[])

    reviews = [{"subject_id": f"v{i}", "flag_type": "VAGUE", "verdict": "dismissed"} for i in range(30)]
    adj = build_report(claims, contradictions=[], reviews=reviews)
    assert adj["integrity_score"] > base["integrity_score"]        # dismissals raised the score
    assert adj["integrity_score_raw"] == base["integrity_score"]   # raw == machine score, unhidden
    assert adj["reviews_applied"] == 30
    # the surviving VAGUE flag now counts 15 (45 − 30 dismissed), not 45
    vague = next(p for p in adj["penalty_breakdown"] if p["type"] == "VAGUE")
    assert vague["count"] == 15
    # reconciliation still holds on the adjusted set
    assert round(adj["integrity_score"]) == round(max(0, 100 - sum(p["points_deducted"] for p in adj["penalty_breakdown"])))

    # 'confirmed' verdicts must NOT move the score
    conf = build_report(claims, contradictions=[],
                        reviews=[{"subject_id": "v0", "flag_type": "VAGUE", "verdict": "confirmed"}])
    assert conf["integrity_score"] == base["integrity_score"]
    assert conf["reviews_applied"] == 0


def test_build_report_no_data():
    assert build_report([], [])["integrity_score"] is None


def _doc_claim(cid, value, year, unit="tCO2e"):
    return {"claim_id": cid, "source_sentence": "Scope 1 emissions.",
            "metric_key": "emissions.scope1.co2e", "metric_value": value, "metric_unit": unit,
            "time_bucket": str(year), "company_id": "x", "report_id": "r1"}


def _ext(value, unit="tCO2e", year=2022):
    return [{"company_id": "x", "metric_key": "emissions.scope1.co2e", "year": year,
             "value": value, "unit": unit, "statement": "Reference.", "source": "t", "url": ""}]


def test_fact_check_coverage():
    # two checkable claims; only the 2022 one has matching evidence
    claims = [_doc_claim("a", 100, 2022), _doc_claim("b", 200, 2099)]
    out = fact_check_document(claims, [], external=_ext(100, year=2022))
    assert out["checkable"] == 2
    assert out["checked"] == 1
    assert out["coverage"] == 0.5
    # coverage is independent of credibility
    assert out["credibility"] == 1.0   # the one checked claim agrees


def test_check_claim_unverified_reasons_are_actionable():
    claim = _doc_claim("a", 100, 2022)
    # no evidence at all → reason names what's needed
    r1 = check_claim(claim, [])
    assert r1["verdict"] == "UNVERIFIED"
    assert "No comparable reference" in r1["reasoning"] and "emissions.scope1.co2e" in r1["reasoning"]
    # evidence exists but incomparable unit → reason says so
    r2 = check_claim(claim, [{"value": 0.5, "unit": "tCO2e/MWh", "statement": "intensity",
                              "source": "t", "url": "", "kind": "external"}])
    assert r2["verdict"] == "UNVERIFIED" and "incomparable" in r2["reasoning"]


def test_verification_profile():
    claims = [
        {"claim_id": "1", "observability_type": "optical_possible", "claim_type": "metric",
         "metric_value": 1, "source_sentence": "forest cover", "company_name": "Acme", "report_year": 2023},
        {"claim_id": "2", "observability_type": "reported_metric", "claim_type": "metric",
         "metric_value": 2, "source_sentence": "emissions", "company_name": "Acme", "report_year": 2023},
        {"claim_id": "3", "observability_type": "not_observable", "claim_type": "narrative",
         "metric_value": None, "source_sentence": "we care", "company_name": "Acme", "report_year": 2023},
    ]
    prof = build_report(claims, [])["statistics"]["verification_profile"]
    assert prof == {"imagery": 1, "data_crosscheck": 1, "document_review": 1}


def test_weighted_credibility_and_materiality():
    claims = [_doc_claim("a", 100, 2022),  # emissions (materiality 3) — will be SUPPORTED
              {"claim_id": "b", "source_sentence": "training", "metric_key": "social.training.hours",
               "metric_value": 10, "metric_unit": "hours", "time_bucket": "2022",
               "company_id": "x", "report_id": "r1"}]                       # social (1) — CONTRADICTED
    external = (_ext(100, year=2022) +
                [{"company_id": "x", "metric_key": "social.training.hours", "year": 2022,
                  "value": 999, "unit": "hours", "statement": "diverges", "source": "t", "url": ""}])
    out = fact_check_document(claims, [], external=external)
    assert out["credibility"] == 0.5            # 1 of 2 supported (unweighted)
    assert out["weighted_credibility"] == 0.75  # emissions(3) supported / (3+1)
    mats = {r["metric_key"].split(".")[0]: r["materiality"] for r in out["results"]}
    assert mats["emissions"] == 3.0 and mats["social"] == 1.0


_ALL_TESTS = [
    test_build_report_penalty_breakdown_and_provenance,
    test_score_is_count_weighted_by_prevalence,
    test_review_dismissal_raises_score_raw_unchanged,
    test_build_report_no_data,
    test_fact_check_coverage,
    test_check_claim_unverified_reasons_are_actionable,
    test_verification_profile,
    test_weighted_credibility_and_materiality,
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
