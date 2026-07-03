"""
ESGenuine — aspect-normalization regression suite
=================================================
Locks the word-boundary `ESGOntology.normalize_aspect` fix. The old substring rule
made raw "diversity" match keyword "biodiversity" (the #19 mislabel: workforce-
diversity claims tagged biodiversity.conservation — 17/28 claims in the first Docling
table run). Word-boundary matching + specificity tie-breaks kill that class.

Runs two ways: pytest backend/tests/test_ontology_aspects.py  |  python backend/tests/test_ontology_aspects.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.ontology import ESGOntology  # noqa: E402

N = ESGOntology.normalize_aspect


def test_diversity_is_not_biodiversity():
    # the #19 bug class: "diversity" has no word boundary inside "biodiversity"
    assert N("diversity") == "social.diversity.gender"
    assert N("gender diversity") == "social.diversity.gender"
    assert N("workforce diversity") == "social.diversity.gender"
    assert N("diversity in workforce") == "social.diversity.gender"


def test_biodiversity_still_maps_right():
    assert N("biodiversity") == "biodiversity.conservation"
    assert N("biodiversity conservation") == "biodiversity.conservation"
    assert N("tree planting") == "biodiversity.conservation"


def test_board_diversity_is_governance():
    assert N("board diversity") == "governance.board.diversity"


def test_generic_emissions_is_total_not_scope1():
    # direction-B shortest-keyword rule: "emissions" -> "total emissions"
    assert N("emissions") == "emissions.total"
    assert N("scope 1") == "emissions.scope1"
    assert N("scope 3 emissions") == "emissions.scope3"


def test_waste_water_separation():
    # the waste->water swap class from the gold set
    assert N("plastic waste") == "waste.total"
    assert N("waste generated") == "waste.total"
    assert N("waste recycling") == "waste.recycled"
    assert N("water withdrawal") == "water.consumption"
    assert N("recycled water") == "water.recycled"


def test_fallbacks():
    assert N("") == "uncategorized"
    assert N(None) == "uncategorized"
    assert N("xyzzy quux") == "uncategorized"


_ALL_TESTS = [test_diversity_is_not_biodiversity, test_biodiversity_still_maps_right,
              test_board_diversity_is_governance, test_generic_emissions_is_total_not_scope1,
              test_waste_water_separation, test_fallbacks]


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
