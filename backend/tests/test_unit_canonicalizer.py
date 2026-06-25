"""
ESGenuine — UnitCanonicalizer regression suite
==============================================
Locks the canonical-unit conversions that three features depend on at once
(fact-check, peer benchmark, contradiction engine). Before this suite the gates
were only spot-checked; a silent change to a conversion factor or a dropped unit
spelling would corrupt cross-report comparisons without any signal.

Runs two ways:
  * pytest:      pytest backend/tests/test_unit_canonicalizer.py
  * standalone:  python backend/tests/test_unit_canonicalizer.py   (no pytest needed)
"""

import sys
from pathlib import Path

# Add backend/src to path (mirrors the other tests in this folder).
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.ontology import UnitCanonicalizer as U, SignatureGenerator as S  # noqa: E402

_REL_TOL = 1e-6


def _close(got, exp) -> bool:
    if got is None:
        return exp is None
    return abs(got - exp) <= abs(exp) * _REL_TOL + 1e-15


# (value, unit, expected_value, expected_canonical_unit)
_CONVERSIONS = [
    # emissions → tCO2e
    (1, "tCO2e", 1.0, "tCO2e"),
    (1, "ktCO2e", 1e3, "tCO2e"),
    (1, "MtCO2e", 1e6, "tCO2e"),
    (1, "gCO2e", 1e-6, "tCO2e"),
    (1, "kgCO2e", 1e-3, "tCO2e"),
    (1, "Mt CO2e", 1e6, "tCO2e"),
    (1, "million tonnes CO2e", 1e6, "tCO2e"),
    # mass → tonnes
    (1, "tonnes", 1.0, "tonnes"),
    (1, "kg", 1e-3, "tonnes"),
    (1, "kt", 1e3, "tonnes"),
    (2, "million tonnes", 2e6, "tonnes"),
    # energy → MWh  (1 MWh = 3600 MJ)
    (1, "kWh", 1e-3, "MWh"),
    (1, "MWh", 1.0, "MWh"),
    (1, "GWh", 1e3, "MWh"),
    (1, "GJ", 0.2777778, "MWh"),
    (1, "TJ", 277.7778, "MWh"),
    (3600, "megajoules", 1.0, "MWh"),       # gap fixed: verbose joules
    (1, "gigajoules", 0.2777778, "MWh"),
    (1, "terajoules", 277.7778, "MWh"),
    (1, "joules", 2.777778e-10, "MWh"),
    (2, "million gigajoules", 2 * 0.2777778 * 1e6, "MWh"),
    (1, "million kWh", 1e3, "MWh"),
    # volume → m3
    (1, "litres", 1e-3, "m3"),
    (1, "m3", 1.0, "m3"),
    (1, "kilolitres", 1.0, "m3"),
    (1, "megalitres", 1e3, "m3"),
    (1, "cubic metres", 1.0, "m3"),         # gap fixed: verbose m3
    (1, "cubic meter", 1.0, "m3"),
    (1, "gallons", 3.78541e-3, "m3"),       # gap fixed
    (1, "barrels", 0.158987, "m3"),         # gap fixed: oil & gas (Shell/BP)
    (1, "bbl", 0.158987, "m3"),
    (2, "million barrels", 2 * 0.158987 * 1e6, "m3"),
    # area → hectares
    (1, "hectares", 1.0, "hectares"),
    (1, "acres", 0.404686, "hectares"),
    (1, "km2", 100.0, "hectares"),
    (1, "sq km", 100.0, "hectares"),
    (1, "m2", 1e-4, "hectares"),            # gap fixed
    (1, "square metres", 1e-4, "hectares"),
    (2, "million hectares", 2e6, "hectares"),
    # percent passthrough
    (50, "%", 50.0, "%"),
]


def test_conversions():
    for v, u, ev, eu in _CONVERSIONS:
        cv, cu = U.to_canonical(v, u)
        assert _close(cv, ev), f"{u}: value {cv} != {ev}"
        assert cu == eu, f"{u}: unit {cu!r} != {eu!r}"


def test_intensity_units_kept_distinct():
    # Ratios/intensities must NOT be canonicalised to a base quantity — otherwise
    # they'd be compared against absolutes. They pass through unchanged.
    for u in ("gCO2e/MJ", "tonnes/tonne of steel", "kgCO2e per tonne", "tCO2e/MWh"):
        cv, cu = U.to_canonical(1.0, u)
        assert cv == 1.0 and cu == u, f"intensity {u} should pass through, got {cv} {cu}"


def test_reporting_cadence_stripped():
    # A trailing cadence ("per year") is temporal, not a denominator → stays absolute.
    for u in ("tCO2e per year", "tCO2e per annum", "MWh/yr"):
        cv, cu = U.to_canonical(1.0, u)
        assert cu in ("tCO2e", "MWh"), f"cadence {u} should stay absolute, got {cu}"


def test_unknown_unit_passthrough():
    cv, cu = U.to_canonical(5.0, "widgets")
    assert cv == 5.0 and cu == "widgets"
    assert U.to_canonical(None, "tCO2e") == (None, "tCO2e")


def test_value_plausibility_gates():
    assert U.is_value_plausible("social.workforce.total.count", 453608) is True
    assert U.is_value_plausible("social.workforce.total.count", 74.445) is False   # #15 mislabel
    assert U.is_value_plausible("social.diversity.gender.percent", 35) is True
    assert U.is_value_plausible("social.diversity.gender.percent", 5000) is False
    assert U.is_value_plausible("social.health_safety.ltifr.rate", 1.2) is True
    assert U.is_value_plausible("emissions.scope1.co2e", 1.23e7) is True           # no gate on co2e


def test_metric_key_dimension_routing():
    assert S.generate_metric_key("emissions.scope1", "tCO2e") == "emissions.scope1.co2e"
    assert S.generate_metric_key("emissions.scope1", "km") == "emissions.scope1.unspecified"
    assert S.generate_metric_key("social.workforce.total", "employees") == "social.workforce.total.count"
    assert S.generate_metric_key("uncategorized", "tCO2e") == "uncategorized"


def test_cross_unit_equivalence():
    # The whole point: 1.2 ktCO2e and 1200 tCO2e must land on the same number/unit.
    a = U.to_canonical(1.2, "ktCO2e")
    b = U.to_canonical(1200, "tCO2e")
    assert _close(a[0], b[0]) and a[1] == b[1] == "tCO2e"
    # GJ vs MWh
    g = U.to_canonical(3600, "GJ")      # 3600 GJ = 1000 MWh
    m = U.to_canonical(1000, "MWh")
    assert _close(g[0], m[0]) and g[1] == m[1] == "MWh"


_ALL_TESTS = [
    test_conversions,
    test_intensity_units_kept_distinct,
    test_reporting_cadence_stripped,
    test_unknown_unit_passthrough,
    test_value_plausibility_gates,
    test_metric_key_dimension_routing,
    test_cross_unit_equivalence,
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
