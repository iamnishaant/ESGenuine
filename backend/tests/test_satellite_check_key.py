"""
ESGenuine — satellite check_key stability suite
================================================
Locks the durable re-link key (existing_issues #21e): satellite_evidence keyed on
claim_id, but every ingest is delete-then-insert with a fresh uuid, so each
re-ingest orphaned all stored verdicts. `check_key` keys on the CONTENT verified —
(report, aspect, place, year) — so it is invariant across re-ingests and lets
`_satellite_for` re-link stored rows to the current claim.

Needs numpy/requests (satellite_evidence imports the NDVI + geocode modules) — runs
in the full backend-tests CI lane, not the slim gold-gate lane. Pure/offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from verification.satellite_evidence import check_key  # noqa: E402


_BASE = {
    "claim_id": "uuid-original",
    "report_id": "shell_2023",
    "normalized_aspect": "biodiversity.conservation",
    "location_text": "Jarama riverbed, Madrid",
    "time_bucket": "2023",
}


def test_stable_across_claim_id_change():
    # the whole point: a re-ingest assigns a new uuid; the key must not move.
    reingested = dict(_BASE, claim_id="uuid-fresh-after-reingest")
    assert check_key(_BASE) == check_key(reingested)


def test_distinguishes_place():
    other_place = dict(_BASE, location_text="Lake Xochimilco")
    assert check_key(_BASE) != check_key(other_place)


def test_distinguishes_year_and_report_and_aspect():
    assert check_key(_BASE) != check_key(dict(_BASE, time_bucket="2022"))
    assert check_key(_BASE) != check_key(dict(_BASE, report_id="shell_2022"))
    assert check_key(_BASE) != check_key(dict(_BASE, normalized_aspect="energy.renewable"))


def test_is_short_hex():
    k = check_key(_BASE)
    assert len(k) == 16 and all(c in "0123456789abcdef" for c in k)


_ALL_TESTS = [
    test_stable_across_claim_id_change,
    test_distinguishes_place,
    test_distinguishes_year_and_report_and_aspect,
    test_is_short_hex,
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
