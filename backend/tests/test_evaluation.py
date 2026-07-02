"""
ESGenuine — extraction-quality eval harness regression suite
============================================================
Locks `scripts/run_evaluation.py`: the unit->family mapper, the value-tolerance
rule, gold<->extraction matching (claim_id + source_sentence fallback), and the
end-to-end evaluate() invariants on the checked-in gold set. This is the measuring
stick for the Docling swap, so its scoring must not drift silently.

Runs two ways: pytest backend/tests/test_evaluation.py  |  python backend/tests/test_evaluation.py
"""

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_evaluation as ev  # noqa: E402

GOLD = json.loads((_REPO / "backend" / "tests" / "eval" / "gold_set.json").read_text(encoding="utf-8"))
EXTRACTION = ev.load_extraction(_REPO / "backend" / "test_results" / "incremental_claims_backup.jsonl")


def test_unit_to_base():
    cases = {
        "%": "percent", "percent": "percent",
        "tCO2e": "co2e_mass", "million tonnes CO2e": "co2e_mass", "g CO2e": "co2e_mass",
        "Kilo Litres/INR": "rate", "kcal/kwh": "rate",
        "MWp": "power_capacity", "MW": "power_capacity",
        "Million Litres": "volume", "m3": "volume",
        "GWh": "energy", "MWh": "energy", "PJ": "energy",
        "metric tonnes": "mass", "tonnes": "mass",
        "GBP": "currency",
        "employees": "count",
        "unspecified": None, "": None, None: None,
    }
    for u, want in cases.items():
        got = ev.unit_to_base(u)
        assert got == want, f"unit_to_base({u!r}) = {got!r}, want {want!r}"


def test_pillar_of():
    assert ev.pillar_of("emissions.scope1") == "emissions"
    assert ev.pillar_of("social.diversity.gender") == "social"
    assert ev.pillar_of("uncategorized") == "uncategorized"
    assert ev.pillar_of(None) is None


def test_within_tol():
    assert ev.within_tol(100, 99) is True       # 1% inside 5%
    assert ev.within_tol(10.1, 10.8) is False    # ~6.5% outside 5%
    assert ev.within_tol(0.0, 0.0) is True       # zero handled exactly
    assert ev.within_tol(5, 0) is False          # nonzero vs zero gold
    assert ev.within_tol(None, 5) is False


def test_source_sentence_fallback_match():
    # a gold rec matched by sentence even if the claim_id is absent from the index
    g = {"claim_id": "does-not-exist", "source_sentence": GOLD["claims"][0]["source_sentence"]}
    by_id, by_sent = ev.index_extraction(EXTRACTION)
    r, how = ev.match(g, by_id, by_sent)
    assert r is not None and how == "source_sentence"


def test_evaluate_invariants():
    res = ev.evaluate(GOLD, EXTRACTION)
    t, m = res["tallies"], res["metrics"]
    # every gold claim matches the backup it was labeled from
    assert t["gold_total"] == 46
    assert t["matched"] == 46 and t["unmatched"] == 0
    # precision is scored over all emitted (matched) claims
    assert t["prec_den"] == 46
    # node/type accuracy scored only over real claims (is_esg_claim=true)
    real = sum(1 for g in GOLD["claims"] if g["is_esg_claim"])
    assert t["node_den"] == real and t["type_den"] == real
    # headline score is a sane number
    assert m["extraction_score"] is not None
    assert 0.0 <= m["extraction_score"] <= 100.0
    # rates are within [0,1]
    for k in ("candidate_precision", "aspect_node_acc", "value_acc", "unit_base_acc", "type_acc"):
        assert 0.0 <= m[k] <= 1.0


def test_flagship_mislabel_is_caught():
    # the #19 diversity->biodiversity mislabel must register as a node error
    res = ev.evaluate(GOLD, EXTRACTION)
    row = next(r for r in res["per_claim"] if r["claim_id"] == "72be4d75-09f")
    assert row["is_esg_claim"] is True
    assert row["node_ok"] is False       # biodiversity.conservation != social.diversity.gender
    assert row["type_ok"] is False       # narrative != target


def test_page_footer_is_not_a_claim():
    # fabricated-value page footer must count against candidate precision
    res = ev.evaluate(GOLD, EXTRACTION)
    row = next(r for r in res["per_claim"] if r["claim_id"] == "2654c76d-1a9")
    assert row["matched"] is True and row["is_esg_claim"] is False


_ALL_TESTS = [test_unit_to_base, test_pillar_of, test_within_tol,
              test_source_sentence_fallback_match, test_evaluate_invariants,
              test_flagship_mislabel_is_caught, test_page_footer_is_not_a_claim]


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
