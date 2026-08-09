"""
ESGenuine — regression gates for the ablation + recall harnesses (roadmap Phase 6.1/6.2)
=======================================================================================
`test_gold_regression.py` locks the SHIPPED pipeline's score. These lock the two
measurements that make that score interpretable:

  * ABLATION — the deterministic repair layer must keep earning its keep. If a
    refactor quietly stops the quality gate / ontology from firing, the gold floors
    might still pass (the LLM fixture is frozen and already decent) while the
    project's actual contribution silently goes to zero. This asserts the S1->S5
    gain stays large.

  * RECALL — guards the number the evaluation was missing entirely until 2026-08-09.
    Floors are set below measured so ordinary noise does not fail CI, but a real
    regression (e.g. table-page detection breaking further) does.

Deliberately slim, like the gold gate: pydantic/ftfy only, no models, no creds, no
network — so it runs in the fast CI lane.

    pytest backend/tests/test_ablation_recall.py
    python backend/tests/test_ablation_recall.py
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_ablation                                                # noqa: E402
import run_recall                                                  # noqa: E402

TATA = "Tata Power BRSR FY24 (in-sample)"
SHELL = "Shell SR2022 (out-of-sample)"

# Measured 2026-08-09. Floors sit under the measured value so noise does not fail CI.
#   Tata  S1 71.5 -> S5 96.1  (+24.6)
#   Shell S1 82.7 -> S5 89.7  (+7.0)
_MIN_DETERMINISTIC_GAIN = {TATA: 20.0, SHELL: 5.0}
_MIN_FINAL_SCORE = {TATA: 96.0, SHELL: 89.5}

# Measured 2026-08-09. Raw cell recall: Tata 54.4%, Shell 8.0%. Distinct-fact recall
# (duplicates collapsed, governance-form cells excluded): Tata 59.5%, Shell 8.5%.
# Shell's cache covers only 5 targeted pages and its fixture is text-dominant — see
# run_recall.CASES; its floors are deliberately loose and are NOT a quality signal.
_MIN_RECALL = {"Tata Power BRSR FY24": 0.50, "Shell SR2022": 0.06}
_MIN_DISTINCT_RECALL = {"Tata Power BRSR FY24": 0.55, "Shell SR2022": 0.06}


def _ablation():
    if not hasattr(_ablation, "_cache"):
        _ablation._cache = run_ablation.run()
    return _ablation._cache


def _recall():
    if not hasattr(_recall, "_cache"):
        _recall._cache = run_recall.run()
    return _recall._cache


def test_deterministic_layer_still_earns_its_keep():
    """S1 (LLM + vocabulary mapping) -> S5 (shipped) must stay a large gain.

    This is the project's headline contribution. A silent regression here would not
    be caught by the gold floors alone.
    """
    for case, data in _ablation().items():
        s1 = data["stages"][1]["extraction_score"]
        s5 = data["stages"][-1]["extraction_score"]
        floor = _MIN_DETERMINISTIC_GAIN[case]
        assert s5 - s1 >= floor, (
            f"{case}: deterministic repair layer gain collapsed to {s5 - s1:+.1f} "
            f"(floor {floor}). S1={s1} S5={s5}. The quality gate or ontology likely "
            f"stopped firing — fix the stack, do not lower the floor.")


def test_ablation_endpoint_matches_shipped_score():
    """S5 must reproduce the shipped gold score — proves the ablation models the real
    pipeline rather than drifting into its own private code path."""
    for case, data in _ablation().items():
        s5 = data["stages"][-1]["extraction_score"]
        assert s5 >= _MIN_FINAL_SCORE[case], (
            f"{case}: ablation S5 = {s5} < {_MIN_FINAL_SCORE[case]}; the ablation no "
            f"longer mirrors the shipped stack (compare test_gold_regression.py).")


def test_ablation_stages_are_monotonic_enough():
    """No stage may make things dramatically worse. Small dips are tolerated (a
    correction can expose a harder claim), a collapse is a bug."""
    for case, data in _ablation().items():
        scores = [s["extraction_score"] for s in data["stages"]]
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1] - 1.0, (
                f"{case}: stage '{data['stages'][i]['stage']}' dropped the score "
                f"{scores[i - 1]} -> {scores[i]}; a deterministic stage should not "
                f"destroy accuracy.")


def test_table_cell_recall_floor():
    """Recall over enumerable table facts must not regress."""
    for case, data in _recall().items():
        r = data["table_cell_recall"]
        assert r is not None, f"{case}: no ground-truth cells found — parser broke?"
        assert r >= _MIN_RECALL[case], (
            f"{case}: table-cell recall fell to {100 * r:.1f}% "
            f"(floor {100 * _MIN_RECALL[case]:.0f}%). Either table-page detection or "
            f"table extraction regressed.")


def test_distinct_fact_recall_floor():
    """The headline recall metric: one (row_label, value) is ONE fact even when a wide
    matrix table repeats it, and governance-form cells are excluded entirely."""
    for case, data in _recall().items():
        r = data["distinct_fact_recall"]
        assert r is not None, f"{case}: no distinct facts derived — cell parser broke?"
        assert r >= _MIN_DISTINCT_RECALL[case], (
            f"{case}: distinct-fact recall fell to {100 * r:.1f}% "
            f"(floor {100 * _MIN_DISTINCT_RECALL[case]:.0f}%).")


def test_distinct_denominator_is_stricter_than_raw():
    """Guard the refinement itself: collapsing duplicates and dropping form cells must
    actually shrink the denominator, else the filters silently stopped matching."""
    for case, data in _recall().items():
        assert data["distinct_facts"] <= data["ground_truth_cells"]
        if case.startswith("Tata"):
            assert data["duplicate_cells_collapsed"] > 0, "duplicate collapsing stopped firing"
            assert data["form_cells_excluded"] > 0, "governance-form filter stopped firing"


def test_recall_reports_detection_split():
    """The detection-vs-extraction split must stay populated — it is what makes the
    recall number actionable rather than just alarming."""
    for case, data in _recall().items():
        assert "recall_on_processed_pages" in data
        assert data["cells_lost_to_detection"] >= 0
        assert data["ground_truth_cells"] > 0


_ALL_TESTS = [
    test_deterministic_layer_still_earns_its_keep,
    test_ablation_endpoint_matches_shipped_score,
    test_ablation_stages_are_monotonic_enough,
    test_table_cell_recall_floor,
    test_distinct_fact_recall_floor,
    test_distinct_denominator_is_stricter_than_raw,
    test_recall_reports_detection_split,
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
