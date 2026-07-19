"""
ESGenuine — CI-enforced gold-score regression gate (roadmap Phase 5, final piece)
=================================================================================
Re-applies the CURRENT deterministic post-extraction stack (ontology normalize +
quality gate + FY-column repair + furniture drop — the same loop as
scripts/regate_claims.py) to FROZEN raw LLM extractions, scores the result
against the committed gold sets, and asserts the achieved floors:

    Tata  v0.2.1 gold : EXTRACTION_SCORE >= 96.0   (measured 96.1)
    Shell v0.3  gold  : EXTRACTION_SCORE >= 89.5   (measured 89.7)

Any gate/ontology/taxonomy change that silently regresses either gold now FAILS
CI instead of relying on someone remembering to re-score both golds by hand
(the round-2 protocol that caught two regressions — now automated). Fixtures in
eval/fixtures/ are the frozen raw extractions + their Docling page-markdown
caches; they must NOT be regenerated when scores drop — fix the stack instead.

Deliberately slim: needs only pydantic/ftfy (no models, no creds) so it runs in
the fast CI lane. Runs two ways:
  pytest backend/tests/test_gold_regression.py | python backend/tests/test_gold_regression.py
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_evaluation as ev                                       # noqa: E402
from extractors.models import ExtractedClaim                      # noqa: E402
from extractors.ontology import ESGOntology                       # noqa: E402
from extractors.quality_gate import (                             # noqa: E402
    gate_claims, fix_fy_column, _value_in_source, _refresh_keys)

_FIX = _REPO / "backend" / "tests" / "eval" / "fixtures"
_GOLD = _REPO / "backend" / "tests" / "eval"

# (fixture jsonl, docling cache, gold set, floor)
_CASES = [
    ("tata_docling_full.jsonl", "docling_tata.json",
     "gold_set_docling_tata.json", 96.0),
    ("shell_2022_raw.jsonl", "docling_shell2022.json",
     "gold_set_shell_v03.json", 89.5),
]


def _regate_and_score(fixture: str, cache: str, gold_file: str) -> float:
    """Mirror scripts/regate_claims.py, then score against the gold set."""
    md_by_page = {e["page_number"]: e["markdown"]
                  for e in json.loads((_FIX / cache).read_text(encoding="utf-8"))}
    claims = []
    with open(_FIX / fixture, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                claims.append(ExtractedClaim.model_validate(json.loads(line)))

    for c in claims:
        c.quality_flags = []
        c.framework_tags = []
        c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
        _refresh_keys(c)
        md = md_by_page.get(c.provenance.page_number if c.provenance else None)
        if md and c.metric is not None and c.metric.value is not None:
            fix_fy_column(c, md)
            if c.source_type == "table" and not _value_in_source(float(c.metric.value), md):
                c.quality_flags.append("value_not_in_table")
    kept, _ = gate_claims(claims)

    # ev.load_extraction reads a JSONL path; feed it the regated rows the same way.
    rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in kept]
    gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))
    result = ev.evaluate(gold, rows)
    return result["metrics"]["extraction_score"]


def test_tata_gold_floor():
    score = _regate_and_score(*_CASES[0][:3])
    assert score >= _CASES[0][3], (
        f"Tata gold regressed: {score} < {_CASES[0][3]} — a gate/ontology change "
        f"broke v0.2.1. Fix the stack; do not regenerate the fixture.")


def test_shell_gold_floor():
    score = _regate_and_score(*_CASES[1][:3])
    assert score >= _CASES[1][3], (
        f"Shell gold regressed: {score} < {_CASES[1][3]} — a gate/ontology change "
        f"broke v0.3 out-of-sample. Fix the stack; do not regenerate the fixture.")


_ALL_TESTS = [test_tata_gold_floor, test_shell_gold_floor]


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
