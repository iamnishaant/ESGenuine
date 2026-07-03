"""
ESGenuine — per-claim regulatory framework tags suite (external eval #3)
========================================================================
Locks `extractors.frameworks.framework_tags`: aspect→clause mapping (GRI/ESRS/TCFD),
explicit GRI codes lifted from source rows, no hallucinated clauses for unknown
aspects, and the quality-gate wiring (tags assigned AFTER aspect correction).

Runs two ways: pytest backend/tests/test_frameworks.py  |  python backend/tests/test_frameworks.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.frameworks import framework_tags  # noqa: E402
from extractors.models import ExtractedClaim, MetricField, ProvenanceField  # noqa: E402
from extractors.quality_gate import apply_gate  # noqa: E402


def test_scope1_maps_to_gri_esrs_tcfd():
    tags = framework_tags("emissions.scope1")
    assert "GRI 305-1" in tags and "ESRS E1-6" in tags and "TCFD Metrics & Targets" in tags


def test_social_and_governance_nodes():
    assert "GRI 405-1" in framework_tags("social.diversity.gender")
    assert "GRI 403-9" in framework_tags("social.health_safety.ltifr")
    assert "GRI 205-3" in framework_tags("governance.ethics.incidents")


def test_unknown_aspect_no_hallucinated_clause():
    assert framework_tags("uncategorized") == []
    assert framework_tags(None) == []


def test_explicit_gri_code_lifted_from_row():
    # Shell's data rows literally print the GRI code (e.g. "305-3")
    tags = framework_tags("uncategorized", "Own production Million tonnes CO2e 332 CCE-4 - 305-3")
    assert tags == ["GRI 305-3"]


def test_no_duplicate_when_code_matches_mapping():
    tags = framework_tags("emissions.scope1", "Direct GHG emissions (Scope 1) 50 305-1")
    assert tags.count("GRI 305-1") == 1


def test_year_not_mistaken_for_gri_code():
    # "2023-24" must not become GRI 2023-24
    assert framework_tags(None, "Integrated Report & Annual Accounts 2023-24") == []


def test_gate_assigns_tags_after_aspect_fix():
    # gate fixes biodiversity->gender FIRST, so the tags follow the corrected aspect
    c = ExtractedClaim(
        aspect="diversity", normalized_aspect="biodiversity.conservation", action="reported",
        claim_type="narrative", metric=MetricField(value=20.0, unit="%"),
        provenance=ProvenanceField(source_sentence="Achieve 20% gender diversity in workforce",
                                   page_number=1),
        source_type="table",
    )
    apply_gate(c)
    assert c.normalized_aspect == "social.diversity.gender"
    assert "GRI 405-1" in c.framework_tags and "ESRS S1-9" in c.framework_tags


_ALL_TESTS = [test_scope1_maps_to_gri_esrs_tcfd, test_social_and_governance_nodes,
              test_unknown_aspect_no_hallucinated_clause, test_explicit_gri_code_lifted_from_row,
              test_no_duplicate_when_code_matches_mapping, test_year_not_mistaken_for_gri_code,
              test_gate_assigns_tags_after_aspect_fix]


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
