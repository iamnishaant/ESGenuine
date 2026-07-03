"""
ESGenuine — External Evidence Fact-Checking
===========================================
Moves verification beyond report-vs-itself to *claim-vs-ground-truth*: each metric
claim is checked against an evidence corpus — a pluggable set of external reference
figures (CDP / official filings) PLUS cross-report self-consistency (the same company's
other reports) — and given a verdict with citations.

Verdicts: SUPPORTED · CONTRADICTED · UNVERIFIED.

Numeric checking (canonical-unit comparison) is the fast, deterministic core. An
optional LLM layer (`llm_verdict`) handles narrative claims where numbers don't apply.
"""

import json
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from extractors.ontology import UnitCanonicalizer
except ImportError:  # pragma: no cover
    from src.extractors.ontology import UnitCanonicalizer

from .json_utils import loads_lenient

_CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "evidence_corpus.json"
_TOL = 0.05  # within 5% canonical => agreement

# Materiality weights by metric family — emissions matter more than e.g. training hours.
# Exposed per verdict and used for the *additive* weighted_credibility; plain credibility
# is unchanged. (Note: evidence freshness is N/A here — find_evidence matches on exact
# year, so evidence year always equals the claim year; no staleness gap can arise.)
_MATERIALITY = [("emissions", 3.0), ("energy", 2.0), ("water", 2.0), ("waste", 2.0),
                ("biodiversity", 2.0), ("governance", 1.5)]


def _materiality(metric_key) -> float:
    k = str(metric_key or "")
    for prefix, w in _MATERIALITY:
        if k.startswith(prefix):
            return w
    return 1.0


# Evidence trust tiers, highest first. A verdict's evidence_quality is the best tier among
# the sources it actually compared, so the UI can flag verdicts resting on illustrative data.
_QUALITY_RANK = {"verified": 3, "self_reported": 2, "illustrative": 1, "unverified": 0}


def _norm_quality(q) -> str:
    q = str(q or "").strip().lower()
    return q if q in _QUALITY_RANK else "unverified"


def _best_quality(qualities) -> Optional[str]:
    qs = [_norm_quality(q) for q in qualities if q]
    return max(qs, key=lambda x: _QUALITY_RANK[x]) if qs else None


# ── evidence sourcing ────────────────────────────────────────────────────────────
def load_external_corpus() -> List[Dict[str, Any]]:
    """Load evidence records from the corpus file.

    Current shape is ``{"_meta": {...}, "records": [...]}`` — metadata is cleanly
    separated from data. The legacy shape (a bare list that smuggled a ``_schema``
    pseudo-record into the data array) is still accepted so older corpus files keep
    working. Records without a ``company_id`` are dropped defensively."""
    if not _CORPUS_PATH.exists():
        return []
    try:
        data = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict):
        records = data.get("records", [])
    else:  # legacy: bare list with an inline "_schema" pseudo-record
        records = [e for e in data if isinstance(e, dict) and e.get("company_id") != "_schema"]
    # Normalize the trust tier so downstream code never has to guess (missing => unverified).
    return [{**r, "quality": _norm_quality(r.get("quality"))}
            for r in records if isinstance(r, dict) and r.get("company_id")]


def corpus_quality(external: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Trust-tier summary of the external corpus so the UI can warn when fact-checking
    rests on illustrative (placeholder) reference data rather than verified figures."""
    by = {"verified": 0, "self_reported": 0, "illustrative": 0, "unverified": 0}
    for r in external:
        by[_norm_quality(r.get("quality"))] += 1
    return {
        "total": len(external),
        "by_quality": by,
        # True when the corpus has zero verified records — credibility is then only as
        # trustworthy as the placeholders, and must be presented with that caveat.
        "illustrative_only": by["verified"] == 0 and len(external) > 0,
    }


def _real_year(tb) -> Optional[str]:
    s = str(tb or "").strip()
    return s if s.isdigit() else None


def find_evidence(claim: Dict[str, Any], peer_claims: List[Dict[str, Any]],
                  external: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Evidence about the same (company, metric_key, reference-year) from a *different*
    source than the claim itself (external corpus or another report)."""
    mk = claim.get("metric_key")
    comp = claim.get("company_id")
    yr = _real_year(claim.get("time_bucket"))
    if not mk or yr is None:
        return []
    out: List[Dict[str, Any]] = []
    for e in external:
        if e.get("metric_key") == mk and str(e.get("year")) == yr and e.get("company_id") == comp:
            out.append({**e, "kind": "external", "quality": _norm_quality(e.get("quality"))})
    for c in peer_claims:
        if c.get("report_id") == claim.get("report_id") or c.get("company_id") != comp:
            continue
        if c.get("metric_key") == mk and _real_year(c.get("time_bucket")) == yr and c.get("metric_value") is not None:
            out.append({
                "company_id": comp, "metric_key": mk, "year": yr,
                "value": c.get("metric_value"), "unit": c.get("metric_unit"),
                "statement": (c.get("source_sentence") or "")[:200],
                # Cross-report evidence is the company's own filing — real, self-reported.
                "source": f"self-reported ({c.get('report_id')})", "url": "",
                "kind": "cross_report", "quality": "self_reported",
            })
    return out


# ── verdict (numeric) ────────────────────────────────────────────────────────────
def check_claim(claim: Dict[str, Any], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    cv, cu = UnitCanonicalizer.to_canonical(claim.get("metric_value"), claim.get("metric_unit"))
    cu_l = (cu or "").strip().lower()
    compared = []
    for e in evidence:
        ev_v, ev_u = UnitCanonicalizer.to_canonical(e.get("value"), e.get("unit"))
        if ev_v is None or cv is None or (ev_u or "").strip().lower() != cu_l:
            continue
        base = max(abs(cv), abs(ev_v))
        rel = abs(cv - ev_v) / base if base > 1e-9 else 0.0
        compared.append({
            "source": e.get("source"), "kind": e.get("kind"), "quality": _norm_quality(e.get("quality")),
            "evidence_value": ev_v, "unit": ev_u, "rel_diff": round(rel, 3),
            "agree": rel <= _TOL, "statement": e.get("statement"), "url": e.get("url"),
        })

    base_out = {
        "claim_id": claim.get("claim_id"),
        "claim_text": (claim.get("source_sentence") or "")[:200],
        "metric_key": claim.get("metric_key"),
        "materiality": _materiality(claim.get("metric_key")),
        "observability_type": claim.get("observability_type"),
        "reference_year": _real_year(claim.get("time_bucket")),
        "claim_value": cv, "claim_unit": cu,
    }
    if not compared:
        mk = claim.get("metric_key")
        yr = _real_year(claim.get("time_bucket"))
        comp = claim.get("company_id") or claim.get("company_name") or "this company"
        # Say what would resolve it, not just "no evidence" (actionable UNVERIFIED).
        if evidence:  # evidence existed but units were incomparable
            reason = (f"Evidence exists for {mk} ({yr}) but in an incomparable unit "
                      f"({cu or 'unknown'} vs the reference); cannot numerically verify.")
        else:
            reason = (f"No comparable reference for {mk} at year {yr} for {comp}. "
                      f"Add a CDP/official-filing figure or a prior-year report value in the same unit.")
        return {**base_out, "verdict": "UNVERIFIED", "confidence": 0.3, "evidence": [],
                "reasoning": reason}
    best_q = _best_quality(c.get("quality") for c in compared)
    agree = [c for c in compared if c["agree"]]
    if agree:
        return {**base_out, "verdict": "SUPPORTED", "evidence_quality": best_q,
                "confidence": round(min(0.6 + 0.1 * len(agree), 0.95), 2),
                "evidence": compared[:5],
                "reasoning": f"Matches {len(agree)} independent source(s) within {int(_TOL*100)}%."}
    closest = min(compared, key=lambda c: c["rel_diff"])
    return {**base_out, "verdict": "CONTRADICTED", "evidence_quality": best_q,
            "confidence": round(min(0.55 + closest["rel_diff"], 0.97), 2),
            "evidence": compared[:5],
            "reasoning": f"Diverges from {len(compared)} source(s); closest differs by "
                         f"{int(closest['rel_diff']*100)}% from the reported figure."}


# ── document-level aggregation ───────────────────────────────────────────────────
def fact_check_document(doc_claims: List[Dict[str, Any]], peer_claims: List[Dict[str, Any]],
                        external: Optional[List[Dict[str, Any]]] = None,
                        limit: int = 50, llm=None) -> Dict[str, Any]:
    """Verdict each metric claim that has independent evidence.

    The deterministic numeric comparison (`check_claim`) is always authoritative. When an
    `llm` is supplied (opt-in), it is used ONLY as a fallback for claims that have evidence
    but the numeric pass could not compare (e.g. incomparable units) — never to override a
    numeric SUPPORTED/CONTRADICTED. With `llm=None` (the default) behaviour is unchanged."""
    external = external if external is not None else load_external_corpus()
    results = []
    llm_assisted = 0
    checkable = 0   # claims that COULD be checked (real metric+year+key), evidence or not
    for c in doc_claims:
        mk = c.get("metric_key")
        if (c.get("metric_value") is None or not _real_year(c.get("time_bucket"))
                or not mk or mk == "uncategorized" or str(mk).endswith(".unspecified")):
            continue
        checkable += 1
        ev = find_evidence(c, peer_claims, external)
        if not ev:
            continue
        verdict = check_claim(c, ev)
        if llm is not None and verdict["verdict"] == "UNVERIFIED":
            statements = [e.get("statement") for e in ev if e.get("statement")]
            lv = llm_verdict(verdict["claim_text"], statements, llm)
            if lv.get("engine") == "llm" and lv["verdict"] != "UNVERIFIED":
                verdict = {**verdict, "verdict": lv["verdict"], "confidence": lv["confidence"],
                           "reasoning": lv["reasoning"], "engine": "llm"}
                llm_assisted += 1
        results.append(verdict)
        if len(results) >= limit:
            break
    counts = {"SUPPORTED": 0, "CONTRADICTED": 0, "UNVERIFIED": 0}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    checked = len(results)
    # Materiality-weighted credibility (additive; plain credibility above is unchanged):
    # a SUPPORTED emissions claim counts more than a SUPPORTED training-hours claim.
    wsum = sum(_materiality(r.get("metric_key")) for r in results)
    wsup = sum(_materiality(r.get("metric_key")) for r in results if r["verdict"] == "SUPPORTED")
    return {
        "checked": checked,
        "checkable": checkable,
        # Coverage = how much of the checkable surface we actually had evidence for.
        # Distinct from credibility: 80% credibility over 5% coverage ≠ over 60%.
        "coverage": round(checked / checkable, 2) if checkable else None,
        "verdict_counts": counts,
        "credibility": round(counts["SUPPORTED"] / checked, 2) if checked else None,
        "weighted_credibility": round(wsup / wsum, 2) if wsum else None,
        # Trust tier of the external corpus behind these verdicts. When illustrative_only is
        # true the credibility % is backed by placeholders, not verified figures — the UI
        # must caveat it rather than present it as production ground truth.
        "corpus_quality": corpus_quality(external),
        # Which metric families have reference evidence vs. blind spots (A4): tells the
        # user exactly where the corpus needs records to lift coverage.
        "corpus_coverage_by_metric": dict(Counter(
            str(e.get("metric_key", "")).split(".")[0] or "unknown" for e in external)),
        "llm_assisted": llm_assisted,
        "results": sorted(results, key=lambda r: {"CONTRADICTED": 0, "UNVERIFIED": 1, "SUPPORTED": 2}[r["verdict"]]),
    }


# ── optional LLM verdict (narrative / nuance) ────────────────────────────────────
def llm_verdict(claim_text: str, evidence_statements: List[str], llm) -> Dict[str, Any]:
    """Use an LLMClient (.extract → JSON) to judge a narrative claim against evidence.

    Grounding guards (so a generative model can't fabricate a verdict):
      1. **No evidence ⇒ no LLM call.** With nothing to ground a judgement, the only
         honest answer is UNVERIFIED — asking the model anyway just invites a hallucinated
         verdict. Returns deterministically with engine="guard".
      2. **A confident verdict must be explained.** If the model returns SUPPORTED or
         CONTRADICTED with no rationale, it is downgraded to UNVERIFIED — an unexplained
         confident verdict is treated as ungrounded.
      3. Confidence is clamped to [0, 1].
    The prompt also instructs the model to answer UNVERIFIED when the evidence does not
    directly address the claim. Callers keep the deterministic numeric verdict authoritative
    and use this only as a fallback (see `fact_check_document(..., llm=...)`).
    """
    real_ev = [str(s).strip() for s in (evidence_statements or []) if s and str(s).strip()]
    if not real_ev:  # guard #1
        return {"verdict": "UNVERIFIED", "confidence": 0.3, "engine": "guard",
                "reasoning": "No evidence available to assess this claim."}
    ev_block = "\n".join(f"- {s}" for s in real_ev[:6])
    prompt = (
        "You are an ESG auditor. Given a CLAIM from a sustainability report and EVIDENCE "
        "from independent sources, decide if the claim is SUPPORTED, CONTRADICTED, or "
        "UNVERIFIED. Use ONLY the evidence below — do not rely on outside knowledge. If the "
        "evidence does not directly address the claim, answer UNVERIFIED. Respond ONLY as JSON: "
        '{"verdict": "...", "confidence": 0.0-1.0, "reasoning": "one sentence citing the evidence"}.\n\n'
        f"CLAIM: {claim_text}\n\nEVIDENCE:\n{ev_block}\n"
    )
    try:
        data = loads_lenient(llm.extract(prompt))
        v = str(data.get("verdict", "UNVERIFIED")).upper()
        if v not in ("SUPPORTED", "CONTRADICTED", "UNVERIFIED"):
            v = "UNVERIFIED"
        reasoning = str(data.get("reasoning", "")).strip()
        if v in ("SUPPORTED", "CONTRADICTED") and not reasoning:  # guard #2
            v, reasoning = "UNVERIFIED", "Model gave no rationale; treated as unverified."
        try:
            conf = min(max(float(data.get("confidence", 0.5)), 0.0), 1.0)  # guard #3
        except (TypeError, ValueError):
            conf = 0.5
        return {"verdict": v, "confidence": round(conf, 2), "reasoning": reasoning, "engine": "llm"}
    except Exception as e:
        return {"verdict": "UNVERIFIED", "confidence": 0.3, "reasoning": f"LLM verdict unavailable: {e}", "engine": "llm"}
