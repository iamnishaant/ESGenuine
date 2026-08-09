"""
ESGenuine — model pinning + seeding guards
==========================================
Cheap, offline assertions that the reproducibility guarantees are actually in force.
Deliberately does NOT load any model (that needs weights on disk) — it locks the
*configuration*, which is what silently rots.

Why this matters: every local model used to load by bare name, so an upstream re-upload
could change embeddings -> retrieval -> contradictions -> every published score, with
nothing in git to explain it.
"""
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))

import model_config as M                                          # noqa: E402

_SHA = re.compile(r"^[0-9a-f]{40}$")


def test_revisions_are_pinned_to_full_shas():
    """A tag or 'main' would still float. Only a 40-char commit SHA is a real pin."""
    assert _SHA.match(M.EMBED_REVISION), (
        f"EMBED_REVISION={M.EMBED_REVISION!r} is not a 40-char commit SHA — the embedder "
        f"would float and silently change every stored vector.")
    assert _SHA.match(M.NLI_REVISION), (
        f"NLI_REVISION={M.NLI_REVISION!r} is not a 40-char commit SHA.")


def test_embed_model_matches_schema_dimension():
    """The DB column is VECTOR(768); bge-base is 768-dim. Swapping to bge-large (1024)
    without a migration would fail at insert time, in production, mid-ingest."""
    assert "bge-base" in M.EMBED_MODEL, (
        f"EMBED_MODEL={M.EMBED_MODEL!r} — schema expects a 768-dim model. Changing this "
        f"requires a VECTOR(n) migration AND a full corpus re-embed.")


def test_seeding_is_deterministic():
    import random
    M.seed_everything(123)
    a = [random.random() for _ in range(5)]
    M.seed_everything(123)
    b = [random.random() for _ in range(5)]
    assert a == b, "seed_everything did not make python's RNG reproducible"


def test_provenance_reports_everything_needed_to_reproduce():
    p = M.model_provenance()
    for k in ("embed_model", "embed_revision", "nli_model", "nli_revision", "seed"):
        assert k in p and p[k] not in (None, ""), f"provenance missing {k}"


def test_rev_helper_treats_main_as_unpinned():
    """'main'/empty must become None so the loader floats deliberately, not accidentally."""
    assert M._rev("main") is None
    assert M._rev("") is None
    assert M._rev("abc123") == "abc123"


_ALL_TESTS = [
    test_revisions_are_pinned_to_full_shas,
    test_embed_model_matches_schema_dimension,
    test_seeding_is_deterministic,
    test_provenance_reports_everything_needed_to_reproduce,
    test_rev_helper_treats_main_as_unpinned,
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
