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


# ── gold-v0.2 upgrades: aspect backstops, furniture, FY-column, text types ──

def test_air_pollutants_from_row_text():
    c = _claim("SOx", aspect="emissions.total", value=110962.0, unit="tonnes")
    apply_gate(c)
    assert c.normalized_aspect == "emissions.air_pollutants"
    assert "aspect_fixed" in c.quality_flags


def test_heat_rate_overrides_emissions():
    c = _claim("Jojobera Power Plant Target Net Heat Rate (Kcal/kwh) (FY25)",
               aspect="emissions.total", value=2817.0, unit="Kcal/kwh", ctype="target")
    apply_gate(c)
    assert c.normalized_aspect == "energy.efficiency"
    assert c.claim_type == "target"                          # future marker present


def test_non_renewable_not_renewable():
    c = _claim("Total energy consumed from non-renewable sources (D+E+F) (GJ) FY 24",
               aspect="energy.renewable", value=505276706.0, unit="GJ")
    apply_gate(c)
    assert c.normalized_aspect == "energy.total"


def test_discharge_destination_fragment():
    c = _claim("To Surface water\n1,24,89,82,509\n1,23,19,41,000",
               aspect="water.consumption", value=1231941000.0, unit="litres", source="text")
    apply_gate(c)
    assert c.normalized_aspect == "water.discharge"
    assert c.claim_type == "performance"                     # digits + value -> reported


def test_zld_reuse_is_recycled_not_discharge():
    c = _claim("major thermal power plants has Zero-Liquid Discharge (ZLD) wherein the "
               "waste water is treated and reused",
               aspect="water.consumption", source="text", ctype="target")
    apply_gate(c)
    assert c.normalized_aspect == "water.recycled"
    assert c.claim_type == "narrative"                       # no future marker -> not a target


def test_posh_beats_gender_rescue():
    c = _claim("Complaints on POSH as a % of female employees / workers\n0.08%\n0.09%",
               aspect="social.health_safety.ltifr", value=0.08, unit="%", source="text")
    apply_gate(c)
    assert c.normalized_aspect == "social.posh_complaints"


def test_female_workforce_row_is_diversity():
    c = _claim("Female FY23", aspect="social.workforce.total", value=1901.0, unit="number")
    apply_gate(c)
    assert c.normalized_aspect == "social.diversity.gender"


def test_afforestation_categorized():
    c = _claim("Since 1972, Tata Power have been arranging mega afforestation drive",
               aspect="uncategorized", source="text")
    apply_gate(c)
    assert c.normalized_aspect == "biodiversity.conservation"


def test_furniture_dropped_by_gate_claims():
    from extractors.quality_gate import is_furniture
    drops = [
        _claim("Please specify, if any.", value=5963380.0, unit="t", source="text"),
        _claim("Do you have a business continuity plan?", source="text"),
        _claim("Permanent Employees", value=22372.0, unit="employees", source="text"),
        _claim("No. of employees/workers that are\nrehabilitated and placed in suitable employment",
               value=0.0, unit="cases", source="text"),
        _claim("Disclose wages paid to persons employed as % of total wage cost",
               value=72.0, unit="%", source="text"),
    ]
    keeps = [
        _claim("Please specify, if any.", value=1.0, unit="t"),      # table rows exempt
        _claim("These facilities include wheelchairs and ramps for the mobility-impaired "
               "plus assistive technologies and Braille instructions for visually impaired people",
               value=59.0, unit="%", source="text"),                 # long real narrative
    ]
    assert all(is_furniture(c) for c in drops)
    assert not any(is_furniture(c) for c in keeps)
    kept, stats = gate_claims(drops + keeps)
    assert stats["furniture_dropped"] == len(drops)
    assert len(kept) == len(keeps)


_FY_MD = """| Parameter | FY 24 | FY 23 |
|---|---|---|
| Total | 75,94,749 | 58,28,617 |
"""


def test_fy_column_wrong_cell_repaired():
    from extractors.quality_gate import fix_fy_column
    c = _claim("Total waste disposed FY 23", value=7594749.0, unit="metric tonnes")
    fix_fy_column(c, _FY_MD)
    assert c.metric.value == 5828617.0
    assert "fy_column_fixed" in c.quality_flags


def test_fy_column_correct_cell_untouched():
    from extractors.quality_gate import fix_fy_column
    c = _claim("Total waste disposed FY 23", value=5828617.0, unit="metric tonnes")
    fix_fy_column(c, _FY_MD)
    assert c.metric.value == 5828617.0
    assert "fy_column_fixed" not in c.quality_flags


def test_digit_free_performance_downgraded():
    c = _claim("These facilities include wheelchairs and ramps for the mobility-impaired "
               "plus assistive technologies for the visually and hearing-speech impaired people",
               value=59.0, unit="%", source="text", ctype="performance")
    apply_gate(c)
    assert c.claim_type == "narrative"


_ALL_TESTS = [test_scope1_fixed_from_row_text, test_combined_scope_1_and_2_stays_total,
              test_gender_row_rescued_from_biodiversity, test_waste_water_swap_fixed,
              test_water_row_not_stomped, test_table_value_row_is_performance,
              test_future_marker_makes_target, test_text_claims_type_untouched,
              test_fabricated_value_flagged, test_table_claims_skip_sentence_value_check,
              test_real_value_not_flagged, test_implausible_unit_flagged,
              test_gate_claims_stats,
              test_air_pollutants_from_row_text, test_heat_rate_overrides_emissions,
              test_non_renewable_not_renewable, test_discharge_destination_fragment,
              test_zld_reuse_is_recycled_not_discharge, test_posh_beats_gender_rescue,
              test_female_workforce_row_is_diversity, test_afforestation_categorized,
              test_furniture_dropped_by_gate_claims, test_fy_column_wrong_cell_repaired,
              test_fy_column_correct_cell_untouched, test_digit_free_performance_downgraded]


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
