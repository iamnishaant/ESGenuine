"""
ESGenuine — persisted per-document contradictions (UI sync fix #3)
==================================================================
The frontend reasoning views read the `contradictions` table straight from
Supabase; historically it was written once by an offline test run and then
rotted. This module makes it a maintained artifact: after every claim ingest,
the report's deterministic numeric contradictions are recomputed and replace
that document's rows (delete-then-insert by doc_id — the same idempotency
pattern as claims).

Numeric-only on purpose: `ContradictionEngine._numeric_conflict` is
deterministic and model-free (the NLI weights stay unloaded), so this adds
seconds — not model loads — to an ingest.
"""
import collections
import itertools
from typing import Any, Dict, List, Tuple

try:  # robust to both import roots (same pattern as nli_engine)
    from reasoning.nli_engine import ContradictionEngine
except ImportError:  # pragma: no cover
    from src.reasoning.nli_engine import ContradictionEngine

_engine = ContradictionEngine()          # lazy NLI: numeric path never loads it
_SEV_FROM_TYPE = {"Hard": "Critical", "Metric": "High", "Temporal": "Medium", "Scope": "Low"}


def doc_numeric_contradictions(claims: List[Dict[str, Any]],
                               cap: int = 3000) -> Tuple[List[Dict[str, Any]], bool]:
    """Deterministic numeric contradiction rows (WITH claim ids) for one document.

    Same grouping as api_reasoning._numeric_contradictions (same metric_key,
    skipping uncategorized/.unspecified), but keeps claim_a_id/claim_b_id so the
    rows are persistable and the UI can join back to live claims.
    Returns (rows, truncated).
    """
    by: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for c in claims:
        mk = c.get("metric_key")
        if mk and mk != "uncategorized" and not str(mk).endswith(".unspecified"):
            by[mk].append(c)

    out: List[Dict[str, Any]] = []
    n = 0
    for group in by.values():
        for a, b in itertools.combinations(group, 2):
            n += 1
            if n > cap:
                return out, True
            r = _engine._numeric_conflict(a, b)
            if r:
                out.append({
                    "claim_a_id": a.get("claim_id"),
                    "claim_b_id": b.get("claim_id"),
                    "severity": _SEV_FROM_TYPE.get(r["type"], "Medium"),
                    "conflict_type": r["type"],
                    "reasoning": r["reason"],
                    "confidence": 1.0,   # numeric verdicts are deterministic
                })
    return out, False


def persist_doc_contradictions(sb, doc_id: str,
                               claim_rows: List[Dict[str, Any]]) -> int:
    """Replace `contradictions` rows for doc_id with a fresh numeric scan.

    claim_rows: the claim dicts as ingested (must carry claim_id, metric_key,
    metric_value, metric_unit, time_bucket, location_scope, metric_direction).
    Returns the number of rows written. Raises nothing upward that should stop
    an ingest — callers wrap in try/except.
    """
    rows, truncated = doc_numeric_contradictions(claim_rows)
    if truncated:
        print(f"[contradictions] {doc_id}: pairwise scan truncated at cap — persisted set is partial")

    sb.table("contradictions").delete().eq("doc_id", doc_id).execute()
    if rows:
        for r in rows:
            r["doc_id"] = doc_id
        # batch in chunks to stay under PostgREST payload limits
        for i in range(0, len(rows), 200):
            sb.table("contradictions").insert(rows[i:i + 200]).execute()
    print(f"[contradictions] {doc_id}: persisted {len(rows)} numeric contradictions")
    return len(rows)
