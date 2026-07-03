"""
ESGenuine — LLM key-pool smart-rotation regression suite
========================================================
Locks the multi-key scheduling in `LLMClient`: round-robin across all keys, failure
COOLDOWN (a key that timed out / 429'd sits out COOLDOWN_S and sheds load to healthy
keys), no deadlock when everything is cooling down, and pool-scaled worker defaults
(5 NVIDIA keys behind 4 fixed workers left keys idle).

Runs two ways: pytest backend/tests/test_llm_pool.py  |  python backend/tests/test_llm_pool.py
"""
import itertools
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from extractors.claim_extractor import LLMClient  # noqa: E402


def _client(n_keys=3):
    """LLMClient with a fake n-key pool (no env/keys/network needed)."""
    c = LLMClient.__new__(LLMClient)
    c.endpoints = [{"provider": "nvidia", "key": f"k{i}", "model": "m", "url": "u"}
                   for i in range(n_keys)]
    c._rr = itertools.count()
    c._rr_lock = threading.Lock()
    c._cooldown_until = {}
    return c


def test_round_robin_spreads_load():
    c = _client(3)
    assert [c._next_endpoint()[0] for _ in range(6)] == [0, 1, 2, 0, 1, 2]


def test_cooled_key_is_skipped():
    c = _client(3)
    c._mark_cooldown(1)
    picks = [c._next_endpoint()[0] for _ in range(6)]
    assert 1 not in picks
    assert set(picks) == {0, 2}


def test_all_cooled_never_deadlocks():
    c = _client(3)
    for i in range(3):
        c._mark_cooldown(i)
    idx, ep = c._next_endpoint()
    assert idx in (0, 1, 2) and ep["key"] == f"k{idx}"


def test_cooldown_expires():
    c = _client(2)
    c._mark_cooldown(0)
    c._cooldown_until[0] = 0.0        # simulate expiry
    assert 0 in {c._next_endpoint()[0] for _ in range(4)}


def test_extract_marks_cooldown_on_failure():
    c = _client(2)
    calls = []

    def boom(ep, prompt):
        calls.append(ep["key"])
        raise RuntimeError("simulated timeout")

    c._call_endpoint = boom
    for _ in range(2):
        try:
            c.extract("p")
        except RuntimeError:
            pass
    # first call hit k0 and cooled it; second call must have rotated to k1
    assert calls == ["k0", "k1"]
    assert len(c._cooldown_until) == 2


def test_pool_scaled_worker_default():
    from extractors.claim_extractor import ClaimExtractor
    import os
    ce = ClaimExtractor.__new__(ClaimExtractor)
    ce.llm = _client(10)
    saved = os.environ.pop("NVIDIA_CONCURRENCY", None)
    try:
        assert ce._default_workers(fallback=4) == 10   # scales up to pool size
        ce.llm = _client(2)
        assert ce._default_workers(fallback=4) == 4    # never below fallback
        ce.llm = _client(50)
        assert ce._default_workers(fallback=4) == 12   # capped
        os.environ["NVIDIA_CONCURRENCY"] = "3"
        assert ce._default_workers(fallback=4) == 3    # env always wins
    finally:
        os.environ.pop("NVIDIA_CONCURRENCY", None)
        if saved is not None:
            os.environ["NVIDIA_CONCURRENCY"] = saved


_ALL_TESTS = [test_round_robin_spreads_load, test_cooled_key_is_skipped,
              test_all_cooled_never_deadlocks, test_cooldown_expires,
              test_extract_marks_cooldown_on_failure, test_pool_scaled_worker_default]


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
