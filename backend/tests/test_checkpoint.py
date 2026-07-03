"""
ESGenuine — resumable claim-checkpoint regression suite
=======================================================
Locks `extractors.checkpoint.ClaimCheckpoint`: record is line-atomic, load resumes
completed units, a corrupt/truncated tail line is dropped (that unit re-runs), an
invalid stored claim is dropped but its unit stays done, and clear() removes the file.
This is what turns a crashy multi-call extraction into a resumable one so a single
crash never discards a whole credit-burning run.

Runs two ways: pytest backend/tests/test_checkpoint.py  |  python backend/tests/test_checkpoint.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.checkpoint import ClaimCheckpoint          # noqa: E402
from extractors.models import ExtractedClaim, ProvenanceField  # noqa: E402


def _claim(aspect="emissions.scope1", page=1):
    return ExtractedClaim(
        aspect=aspect, action="reported",
        provenance=ProvenanceField(source_sentence="s", page_number=page),
    )


def _tmp():
    fd, p = tempfile.mkstemp(suffix=".jsonl", prefix="ckpt_test_")
    os.close(fd)
    os.remove(p)   # start absent
    return p


def test_roundtrip_and_resume():
    p = _tmp()
    try:
        cp = ClaimCheckpoint(p)
        cp.record("sec::0", [_claim(), _claim("water.consumption")])
        cp.record("tbl::30", [_claim("waste.total")])
        done, claims = cp.load()
        assert done == {"sec::0", "tbl::30"}
        assert len(claims) == 3
        assert all(isinstance(c, ExtractedClaim) for c in claims)
    finally:
        os.path.exists(p) and os.remove(p)


def test_empty_unit_still_marks_done():
    # a window that produced zero claims must still count as done (don't re-pay for it)
    p = _tmp()
    try:
        cp = ClaimCheckpoint(p)
        cp.record("sec::5", [])
        done, claims = cp.load()
        assert done == {"sec::5"} and claims == []
    finally:
        os.path.exists(p) and os.remove(p)


def test_corrupt_tail_line_is_dropped():
    # simulate a crash mid-write: a valid unit followed by a truncated JSON line
    p = _tmp()
    try:
        cp = ClaimCheckpoint(p)
        cp.record("sec::0", [_claim()])
        with open(p, "a", encoding="utf-8") as f:
            f.write('{"unit": "sec::1", "claims": [ {"aspect": "x", ')  # truncated, no newline
        done, claims = cp.load()
        assert done == {"sec::0"}          # sec::1 dropped -> will re-run
        assert len(claims) == 1
    finally:
        os.path.exists(p) and os.remove(p)


def test_invalid_claim_dropped_but_unit_kept():
    # a well-formed line whose claims array holds one bad + one good claim
    p = _tmp()
    try:
        good = _claim().model_dump(mode="json")
        bad = {"aspect": "x"}   # missing required action + provenance -> won't validate
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit": "sec::0", "claims": [good, bad]}) + "\n")
        done, claims = ClaimCheckpoint(p).load()
        assert done == {"sec::0"}          # unit is done (line was complete)
        assert len(claims) == 1            # bad claim never carried forward
    finally:
        os.path.exists(p) and os.remove(p)


def test_clear_removes_file():
    p = _tmp()
    cp = ClaimCheckpoint(p)
    cp.record("sec::0", [_claim()])
    assert os.path.exists(p)
    cp.clear()
    assert not os.path.exists(p)
    # clear on an absent file is a no-op (no raise)
    cp.clear()


def test_load_absent_is_empty():
    done, claims = ClaimCheckpoint(_tmp()).load()
    assert done == set() and claims == []


_ALL_TESTS = [test_roundtrip_and_resume, test_empty_unit_still_marks_done,
              test_corrupt_tail_line_is_dropped, test_invalid_claim_dropped_but_unit_kept,
              test_clear_removes_file, test_load_absent_is_empty]


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
