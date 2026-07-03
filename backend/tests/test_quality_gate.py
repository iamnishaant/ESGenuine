"""
ESGenuine — deterministic quality-gate regression suite (improve_rating C2)
===========================================================================
Locks `extractors.quality_gate`: scope-from-row-text correction, gender/biodiversity
rescue, waste/water swap fix, table claim_type correction, fabricated-value and
implausible-unit suspicion flags, and derived-key (metric_key/signature) refresh
after an aspect correction.

Runs two ways: pytest backend/tests/test_quality_gate.py  |  python backend/tests/test_quality_gate.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.models import ExtractedClaim, MetricField, ProvenanceField  # noqa: E402
from extractors.quality_gate import apply_gate, gate_claims, _value_in_source  # noqa: E402


def _claim(sent, aspect="uncategorized", value=None, unit="unspecified",
           ctype="narrative", source="table"):
    return ExtractedClaim(
        aspect=aspect, normalized_aspect=aspect, action="reported", claim_type=ctype,
        metric=None if value is None else MetricField(value=value, unit=unit),
        provenance=ProvenanceField(source_sentence=sent, page_number=1),
        source_type=source,
    )


def test_scope1_fixed_from_row_text():
    c = _claim("Total Scope 1 emissions (Break-up of the GHG into CO2...) 3,86,71,851",
               aspect="emissions.total", value=38671851.0, unit="tCO2e")
    apply_gate(c)
    assert c.normalized_aspect == "emissions.scope1"
    assert "scope_fixed" in c.quality_flags
    assert c.metric_key.startswith("emissions.scope1")      # derived keys follow


def test_combined_scope_1_and_2_stays_total():
    c = _claim("Total Scope 1 and Scope 2 emission intensity per rupee of turnover 0.0000186",
               aspect="emissions.scope1", value=0.0000186, unit="tCO2e/INR")
    apply_gate(c)
    assert c.normalized_aspect == "emissions.total"


def test_gender_row_rescued_from_biodiversity():
    c = _claim("Male 5,082 Female 992 median remuneration",
               aspect="biodiversity.conservation", value=992.0, unit="employees")
    apply_gate(c)
    assert c.normalized_aspect == "social.diversity.gender"
    assert "gender_fixed" in c.quality_flags


def test_waste_water_swap_fixed():
    c = _claim("Plastic waste (A) 2,070 E-waste (B) 215",
               aspect="water.recycled", value=2070.0, unit="metric tonnes")
    apply_gate(c)
    assert c.normalized_aspect == "waste.total"
    assert "waste_water_fixed" in c.quality_flags


def test_water_row_not_stomped():
    c = _claim("Total volume of water withdrawal 85,840",
               aspect="water.consumption", value=85840.0, unit="Million Litres")
    apply_gate(c)
    assert c.normalized_aspect == "water.consumption"
    assert "waste_water_fixed" not in c.quality_flags


def test_table_value_row_is_performance():
    c = _claim("Total Scope 2 emissions 28,86,646", aspect="emissions.scope2",
               value=2886646.0, unit="tCO2e", ctype="narrative")
    apply_gate(c)
    assert c.claim_type == "performance"
    assert "type_fixed" in c.quality_flags


def test_future_marker_makes_target():
    c = _claim("Achieve 20% diversity in workforce by 2025 target", value=20.0,
               unit="%", ctype="narrative")
    apply_gate(c)
    assert c.claim_type == "target"


def test_text_claims_type_untouched():
    c = _claim("some narrative", value=5.0, source="text", ctype="narrative")
    apply_gate(c)
    assert c.claim_type == "narrative"


def test_fabricated_value_flagged():
    # the page-footer class (TEXT pipeline): value nowhere in the sentence
    c = _claim("117th Year Integrated Report & Annual Accounts 2023-24 158",
               value=22372.0, unit="tCO2e", source="text")
    apply_gate(c)
    assert "value_not_in_source" in c.quality_flags


def test_table_claims_skip_sentence_value_check():
    # table source_sentence is only the row label; value verified vs markdown instead
    c = _claim("Board of Directors (BoD)", value=1.0, unit="count", source="table")
    apply_gate(c)
    assert "value_not_in_source" not in c.quality_flags


def test_real_value_not_flagged():
    for sent, val in [("capacity of 14,707 MW based on", 14707.0),
                      ("Total Scope 1 emissions 3,86,71,851", 38671851.0),   # Indian grouping
                      ("intensity (PPP) 0.0000186 0.0000159", 0.0000186)]:
        assert _value_in_source(val, sent), (sent, val)
        c = _claim(sent, value=val, unit="tCO2e", source="text")
        apply_gate(c)
        assert "value_not_in_source" not in c.quality_flags, sent


def test_implausible_unit_flagged():
    c = _claim("LTIFR total 3", aspect="social.health_safety.ltifr",
               value=3.0, unit="USD")
    apply_gate(c)
    assert "implausible_unit" in c.quality_flags


def test_gate_claims_stats():
    claims = [
        _claim("Total Scope 1 emissions 3,86,71,851", aspect="emissions.total",
               value=38671851.0, unit="tCO2e"),
        _claim("Male 21,358 Female 2,294", aspect="biodiversity.conservation",
               value=2294.0, unit="employees"),
    ]
    _, stats = gate_claims(claims)
    assert stats.get("scope_fixed") == 1
    assert stats.get("gender_fixed") == 1


_ALL_TESTS = [test_scope1_fixed_from_row_text, test_combined_scope_1_and_2_stays_total,
              test_gender_row_rescued_from_biodiversity, test_waste_water_swap_fixed,
              test_water_row_not_stomped, test_table_value_row_is_performance,
              test_future_marker_makes_target, test_text_claims_type_untouched,
              test_fabricated_value_flagged, test_table_claims_skip_sentence_value_check,
              test_real_value_not_flagged, test_implausible_unit_flagged,
              test_gate_claims_stats]


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
