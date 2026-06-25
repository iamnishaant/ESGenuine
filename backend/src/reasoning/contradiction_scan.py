"""
ESGenuine — Contradiction scan orchestration (pure, I/O-injected)
=================================================================
The per-document contradiction loop, separated from FastAPI / Supabase / the NLI model so
it is unit-testable without any of them. Callers inject the I/O:

  retrieve_fn(claim) -> list[candidate claim dicts]     (semantic retrieval)
  engine_obj         -> object exposing .evaluate_pair(a, b) -> result dict

Dedups unordered claim-id pairs (NLI #4): retrieval is symmetric, so within one document
both (A, B) and (B, A) surface and would otherwise be reported — and severity-counted —
twice. Cross-report candidates (a claim from another document) are evaluated only once
anyway, because only the current document's claims are iterated as queries.
"""

from typing import Any, Callable, Dict, List, Tuple

_SEVERITIES = ("Critical", "High", "Medium", "Low")


def scan_contradictions(doc_claims: List[Dict[str, Any]],
                        retrieve_fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
                        engine_obj) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Return (conflicts, severity_counts) for one document's claims."""
    conflicts: List[Dict[str, Any]] = []
    severity_counts = {s: 0 for s in _SEVERITIES}
    seen_pairs = set()

    for claim in doc_claims:
        for candidate in (retrieve_fn(claim) or []):
            a_id, b_id = claim.get("claim_id"), candidate.get("claim_id")
            if a_id and b_id:
                if a_id == b_id:
                    continue  # never compare a claim with itself
                pair_key = frozenset((a_id, b_id))
                if pair_key in seen_pairs:
                    continue  # this unordered pair was already evaluated
                seen_pairs.add(pair_key)

            res = engine_obj.evaluate_pair(claim, candidate)
            if not res.get("has_contradiction"):
                continue

            severity = res["severity"]
            if severity in severity_counts:
                severity_counts[severity] += 1
            conflicts.append({
                "claim_a_id": a_id,
                "claim_a_text": claim.get("source_sentence"),
                "claim_a_page": claim.get("page_number"),
                "claim_b_id": b_id,
                "claim_b_text": candidate.get("source_sentence"),
                "claim_b_doc": candidate.get("doc_id"),  # may be a cross-report match
                "severity": severity,
                "conflict_type": res["conflict_type"],
                # Numeric contradictions are deterministic (confidence 1.0); only the
                # "Textual" path carries a (model) confidence.
                "reasoning": res["reasoning"],
                "confidence": res["nli_data"]["confidence"] if res.get("conflict_type") == "Textual" else 1.0,
            })

    return conflicts, severity_counts
