"""
ESGenuine — pinned model revisions + deterministic seeding (roadmap: prod-hardening)
====================================================================================

WHY THIS EXISTS
---------------
Every local model was loaded by BARE NAME (`SentenceTransformer("BAAI/bge-base-en-v1.5")`),
which resolves to whatever is currently on the `main` branch of that HuggingFace repo. A
silent upstream re-upload therefore changes the embeddings, which changes retrieval, which
changes contradictions and every published score — with no code change, no version bump and
nothing in git to explain the drift. That is fatal for a result anyone is meant to reproduce.

The model name was also duplicated across four modules (`ingest_claims`, `supabase_ingest`,
`reasoning.agent`, `reasoning.retrieval`), so they could silently disagree about which
embedder built the vectors versus which one queries them — a dimension/semantics mismatch
that fails at retrieval time, not at load time.

Both problems are fixed here: ONE place defines the model, its pinned commit, and the loader.

THE PINS
--------
The SHAs below are the revisions ALREADY in the local HF cache — i.e. the exact weights that
produced the currently reported numbers (extraction 96.1/89.7, the live corpus embeddings).
Pinning to them makes the existing results reproducible rather than freezing an arbitrary
new version.

To move a pin deliberately: change the SHA here, re-embed the corpus (vectors from two
different embedders are NOT comparable), and re-run the gold + ablation + recall gates.
Override at runtime with `EMBED_MODEL` / `EMBED_REVISION` / `NLI_MODEL` / `NLI_REVISION`;
set a revision to "main" to deliberately float (not recommended outside experiments).
"""
import os
import random

# ── embedder ────────────────────────────────────────────────────────────────────
# 768-dim, matches the schema's VECTOR(768). Changing this REQUIRES re-embedding the
# corpus — stored vectors from a different model are not comparable.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
EMBED_REVISION = os.getenv("EMBED_REVISION", "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a")

# ── NLI (contradiction engine) ──────────────────────────────────────────────────
NLI_MODEL = os.getenv("NLI_MODEL", "typeform/distilbert-base-uncased-mnli")
NLI_REVISION = os.getenv("NLI_REVISION", "cfa538a0fddbbd978fefe8966c1aeff7ad409c90")

# Global seed. Exposed so a paper can state it; override with SEED.
SEED = int(os.getenv("SEED", "42"))

_EMBEDDER = None
_NLI = None


def seed_everything(seed: int = None) -> int:
    """Seed python/numpy/torch RNGs. Call once at process start.

    Embedding and NLI inference are deterministic in principle, but sampling helpers,
    dropout-at-inference bugs and any future shuffling are not — seeding removes a class
    of "why did the number move?" that is very expensive to debug after the fact.
    Torch/numpy are imported lazily so this stays cheap for callers that never load a model.
    """
    s = SEED if seed is None else seed
    random.seed(s)
    os.environ.setdefault("PYTHONHASHSEED", str(s))
    try:
        import numpy as np
        np.random.seed(s)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(s)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(s)
    except ImportError:
        pass
    return s


def _rev(value: str):
    """'main' (or empty) means deliberately unpinned -> pass None to the loader."""
    return None if not value or value.lower() == "main" else value


def load_embedder(cache: bool = True):
    """The pinned SentenceTransformer, loaded once per process."""
    global _EMBEDDER
    if cache and _EMBEDDER is not None:
        return _EMBEDDER
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL, revision=_rev(EMBED_REVISION))
    if cache:
        _EMBEDDER = model
    return model


def load_nli(cache: bool = True):
    """The pinned NLI text-classification pipeline, loaded once per process."""
    global _NLI
    if cache and _NLI is not None:
        return _NLI
    from transformers import pipeline
    nli = pipeline("text-classification", model=NLI_MODEL, revision=_rev(NLI_REVISION))
    if cache:
        _NLI = nli
    return nli


def model_provenance() -> dict:
    """Exactly which weights this process is using — for run logs and the paper's
    reproducibility statement."""
    return {
        "embed_model": EMBED_MODEL, "embed_revision": EMBED_REVISION,
        "nli_model": NLI_MODEL, "nli_revision": NLI_REVISION,
        "seed": SEED,
    }
