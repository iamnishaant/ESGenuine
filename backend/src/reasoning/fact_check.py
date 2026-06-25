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
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from extractors.ontology import UnitCanonicalizer
except ImportError:  # pragma: no cover
    from src.extractors.ontology import UnitCanonicalizer

_CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "evidence_corpus.json"
_TOL = 0.05  # within 5% canonical => agreement


# ── evidence sourcing ────────────────────────────────────────────────────────────
def load_external_corpus() -> List[Dict[str, Any]]:
    if not _CORPUS_PATH.exists():
        return []
    try:
        data = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
        return [e for e in data if e.get("company_id") not in (None, "_schema")]
    except Exception:
        return []


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
            out.append({**e, "kind": "external"})
    for c in peer_claims:
        if c.get("report_id") == claim.get("report_id") or c.get("company_id") != comp:
            continue
        if c.get("metric_key") == mk and _real_year(c.get("time_bucket")) == yr and c.get("metric_value") is not None:
            out.append({
                "company_id": comp, "metric_key": mk, "year": yr,
                "value": c.get("metric_value"), "unit": c.get("metric_unit"),
                "statement": (c.get("source_sentence") or "")[:200],
                "source": f"self-reported ({c.get('report_id')})", "url": "", "kind": "cross_report",
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
            "source": e.get("source"), "kind": e.get("kind"),
            "evidence_value": ev_v, "unit": ev_u, "rel_diff": round(rel, 3),
            "agree": rel <= _TOL, "statement": e.get("statement"), "url": e.get("url"),
        })

    base_out = {
        "claim_id": claim.get("claim_id"),
        "claim_text": (claim.get("source_sentence") or "")[:200],
        "metric_key": claim.get("metric_key"),
        "observability_type": claim.get("observability_type"),
        "reference_year": _real_year(claim.get("time_bucket")),
        "claim_value": cv, "claim_unit": cu,
    }
    if not compared:
        return {**base_out, "verdict": "UNVERIFIED", "confidence": 0.3, "evidence": [],
                "reasoning": "No comparable external or cross-report evidence for this metric and year."}
    agree = [c for c in compared if c["agree"]]
    if agree:
        return {**base_out, "verdict": "SUPPORTED",
                "confidence": round(min(0.6 + 0.1 * len(agree), 0.95), 2),
                "evidence": compared[:5],
                "reasoning": f"Matches {len(agree)} independent source(s) within {int(_TOL*100)}%."}
    closest = min(compared, key=lambda c: c["rel_diff"])
    return {**base_out, "verdict": "CONTRADICTED",
            "confidence": round(min(0.55 + closest["rel_diff"], 0.97), 2),
            "evidence": compared[:5],
            "reasoning": f"Diverges from {len(compared)} source(s); closest differs by "
                         f"{int(closest['rel_diff']*100)}% from the reported figure."}


# ── document-level aggregation ───────────────────────────────────────────────────
def fact_check_document(doc_claims: List[Dict[str, Any]], peer_claims: List[Dict[str, Any]],
                        external: Optional[List[Dict[str, Any]]] = None,
                        limit: int = 50) -> Dict[str, Any]:
    external = external if external is not None else load_external_corpus()
    results = []
    for c in doc_claims:
        mk = c.get("metric_key")
        if (c.get("metric_value") is None or not _real_year(c.get("time_bucket"))
                or not mk or mk == "uncategorized" or str(mk).endswith(".unspecified")):
            continue
        ev = find_evidence(c, peer_claims, external)
        if not ev:
            continue
        results.append(check_claim(c, ev))
        if len(results) >= limit:
            break
    counts = {"SUPPORTED": 0, "CONTRADICTED": 0, "UNVERIFIED": 0}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    checked = len(results)
    return {
        "checked": checked,
        "verdict_counts": counts,
        "credibility": round(counts["SUPPORTED"] / checked, 2) if checked else None,
        "results": sorted(results, key=lambda r: {"CONTRADICTED": 0, "UNVERIFIED": 1, "SUPPORTED": 2}[r["verdict"]]),
    }


# ── optional LLM verdict (narrative / nuance) ────────────────────────────────────
def llm_verdict(claim_text: str, evidence_statements: List[str], llm) -> Dict[str, Any]:
    """Use an LLMClient (.extract → JSON) to judge a narrative claim against evidence."""
    ev_block = "\n".join(f"- {s}" for s in evidence_statements[:6]) or "(no evidence found)"
    prompt = (
        "You are an ESG auditor. Given a CLAIM from a sustainability report and EVIDENCE "
        "from independent sources, decide if the claim is SUPPORTED, CONTRADICTED, or "
        "UNVERIFIED. Respond ONLY as JSON: "
        '{"verdict": "...", "confidence": 0.0-1.0, "reasoning": "one sentence citing the evidence"}.\n\n'
        f"CLAIM: {claim_text}\n\nEVIDENCE:\n{ev_block}\n"
    )
    try:
        raw = llm.extract(prompt)
        data = json.loads(raw)
        v = str(data.get("verdict", "UNVERIFIED")).upper()
        if v not in ("SUPPORTED", "CONTRADICTED", "UNVERIFIED"):
            v = "UNVERIFIED"
        return {"verdict": v, "confidence": float(data.get("confidence", 0.5)),
                "reasoning": data.get("reasoning", ""), "engine": "llm"}
    except Exception as e:
        return {"verdict": "UNVERIFIED", "confidence": 0.3, "reasoning": f"LLM verdict unavailable: {e}", "engine": "llm"}
