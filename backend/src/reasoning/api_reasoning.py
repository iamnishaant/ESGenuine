"""
ESGenuine — Week 4: Reasoning API Endpoints
==================================================
Exposes the Contradiction Engine and Greenwashing Risk Score 
to the React Frontend Dashboard.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import itertools
import collections

# In a full production setup these would be imported from the DB layer
from src.reasoning.retrieval import find_candidate_pairs, get_supabase
from src.reasoning.nli_engine import ContradictionEngine
from src.reasoning.greenwash_taxonomy import GreenwashTaxonomy
from src.reasoning.integrity_report import build_report
from src.reasoning.benchmark import cross_company, company_scorecard, trajectory
from src.reasoning.fact_check import fact_check_document, load_external_corpus
from src.reasoning.agent import ask as agent_ask, synthesize_audit

router = APIRouter(prefix="/reports", tags=["Reasoning"])
bench_router = APIRouter(prefix="/benchmark", tags=["Benchmark"])
audit_router = APIRouter(prefix="/audit", tags=["Agent"])
engine = ContradictionEngine()
_SEV_FROM_TYPE = {"Hard": "Critical", "Metric": "High", "Temporal": "Medium", "Scope": "Low"}


def _numeric_contradictions(claims, cap: int = 3000):
    """Fast numeric-only contradiction pass (no NLI) for the audit summary."""
    by = collections.defaultdict(list)
    for c in claims:
        mk = c.get("metric_key")
        if mk and mk != "uncategorized" and not str(mk).endswith(".unspecified"):
            by[mk].append(c)
    out, n = [], 0
    for group in by.values():
        for a, b in itertools.combinations(group, 2):
            n += 1
            if n > cap:
                return out
            r = engine._numeric_conflict(a, b)
            if r:
                out.append({"severity": _SEV_FROM_TYPE.get(r["type"], "Medium"),
                            "reasoning": r["reason"], "conflict_type": r["type"]})
    return out


class AskRequest(BaseModel):
    question: str
    doc_id: Optional[str] = None
    k: int = 8

# Columns the reasoning/report surface needs (excludes the large embedding vector).
_CLAIM_COLS = (
    "claim_id,doc_id,report_id,company_id,company_name,report_year,page_number,source_sentence,"
    "aspect,normalized_aspect,metric_family,metric_key,metric_value,metric_unit,"
    "metric_direction,time_bucket,location_scope,claim_type,vagueness_score,groundability_score"
)


def _fetch_doc_claims(doc_id: str):
    sb = get_supabase()
    res = sb.table("claims").select(_CLAIM_COLS).eq("doc_id", doc_id).execute()
    return res.data or []

@router.get("/{doc_id}/contradictions")
async def get_contradictions(doc_id: str):
    """
    1. Fetches all claims for the given document.
    2. Runs the Semantic Retrieval + NLI Engine to find contradictions.
    """
    supabase = get_supabase()
    
    # 1. Fetch claims for this document
    res = supabase.table("claims").select("*").eq("doc_id", doc_id).execute()
    doc_claims = res.data if res.data else []
    
    if not doc_claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")

    conflicts = []
    severity_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    
    # 2. For each claim, find historical/peer contradictions
    for claim in doc_claims:
        # Signature Bucketing + Vector Retrieval
        candidates = find_candidate_pairs(claim, similarity_threshold=0.85)
        
        for candidate in candidates:
            # Numeric & NLI Reasoning
            eval_result = engine.evaluate_pair(claim, candidate)
            
            if eval_result.get("has_contradiction"):
                severity = eval_result["severity"]
                severity_counts[severity] += 1
                
                conflicts.append({
                    "claim_a_id": claim.get("claim_id"),
                    "claim_a_text": claim.get("source_sentence"),
                    "claim_a_page": claim.get("page_number"),
                    
                    "claim_b_id": candidate.get("claim_id"),
                    "claim_b_text": candidate.get("source_sentence"),
                    "claim_b_doc": candidate.get("doc_id"), # Might be Cross-Report!
                    
                    "severity": severity,
                    "conflict_type": eval_result["conflict_type"],
                    "reasoning": eval_result["reasoning"],
                    "confidence": eval_result["nli_data"]["confidence"] if "nli_data" in eval_result else 1.0
                })

    return {
        "total_conflicts": len(conflicts),
        "critical": severity_counts["Critical"],
        "high": severity_counts["High"],
        "medium": severity_counts["Medium"],
        "low": severity_counts["Low"],
        "conflicts": conflicts
    }

@router.get("/{doc_id}/risk-score")
async def get_risk_score(doc_id: str):
    """
    Calculates the Greenwashing Risk Score based on the formula:
    risk_score = 0.4*vague + 0.3*contradictions + 0.2*narrative + 0.1*missing_metrics
    """
    supabase = get_supabase()
    res = supabase.table("claims").select("vagueness_score, claim_type, metric_value").eq("doc_id", doc_id).execute()
    claims = res.data if res.data else []
    
    if not claims:
        return {"greenwashing_risk": 0.0, "status": "No Data"}

    total = len(claims)
    
    # Calculate Ratios
    vague_claims = sum(1 for c in claims if c.get('vagueness_score', 0) >= 0.4)
    narrative_claims = sum(1 for c in claims if c.get('claim_type') == 'narrative')
    missing_metrics = sum(1 for c in claims if c.get('metric_value') is None)
    
    v_ratio = vague_claims / total
    n_ratio = narrative_claims / total
    m_ratio = missing_metrics / total
    
    # Fetch Contradiction Ratio (Normally cached in DB, computing here for demo)
    contradictions_data = await get_contradictions(doc_id)
    c_ratio = contradictions_data["total_conflicts"] / total if total > 0 else 0
    
    # The Formula
    risk_score = (0.4 * v_ratio) + (0.3 * c_ratio) + (0.2 * n_ratio) + (0.1 * m_ratio)
    
    # Bound score between 0 and 1
    risk_score = min(max(risk_score, 0.0), 1.0)
    
    # Interpretation
    status = "Low Risk"
    if risk_score > 0.6: status = "High Risk"
    elif risk_score > 0.3: status = "Moderate Risk"

    return {
        "greenwashing_risk": round(risk_score, 2),
        "status": status,
        "vague_claims": vague_claims,
        "narrative_claims": narrative_claims,
        "missing_metrics": missing_metrics,
        "contradictions": contradictions_data["total_conflicts"],
        "high_severity": contradictions_data["critical"] + contradictions_data["high"]
    }


@router.get("/{doc_id}/greenwashing-flags")
async def get_greenwashing_flags(doc_id: str):
    """Structured greenwashing taxonomy flags (with evidence + regulatory mapping)."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    flags = GreenwashTaxonomy.analyze(claims)
    return {
        "document_id": doc_id,
        "total_flags": len(flags),
        "flags": [f.to_dict() for f in flags],
    }


@router.get("/{doc_id}/integrity-report")
async def get_integrity_report(doc_id: str):
    """Full ESG Integrity Report: score, grade, greenwashing flags, contradictions,
    and recommendations — the one-call deliverable for the dashboard."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    try:
        contradictions = (await get_contradictions(doc_id)).get("conflicts", [])
    except HTTPException:
        contradictions = []
    return build_report(claims, contradictions)


def _fetch_all_claims():
    """All claims across companies (paginated past the PostgREST 1000-row cap)."""
    sb = get_supabase()
    out, start = [], 0
    while True:
        batch = sb.table("claims").select(_CLAIM_COLS).range(start, start + 999).execute().data or []
        out += batch
        if len(batch) < 1000:
            break
        start += 1000
    return out


def _fetch_company_claims(company_id: str):
    """All of one company's claims across its reports (paginated)."""
    sb = get_supabase()
    out, start = [], 0
    while True:
        batch = sb.table("claims").select(_CLAIM_COLS).eq("company_id", company_id).range(start, start + 999).execute().data or []
        out += batch
        if len(batch) < 1000:
            break
        start += 1000
    return out


@router.get("/{doc_id}/fact-check")
async def get_fact_check(doc_id: str, limit: int = 50):
    """Verify each metric claim against external reference figures + the company's other
    reports. Returns SUPPORTED / CONTRADICTED / UNVERIFIED verdicts with citations."""
    doc_claims = _fetch_doc_claims(doc_id)
    if not doc_claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    company_id = doc_claims[0].get("company_id")
    peers = _fetch_company_claims(company_id) if company_id else []
    return fact_check_document(doc_claims, peers, load_external_corpus(), limit=limit)


@bench_router.get("/metric/{metric_key:path}")
async def benchmark_metric(metric_key: str, year: Optional[int] = None):
    """Cross-company distribution for one canonical metric_key (lower/higher-better aware)."""
    return cross_company(_fetch_all_claims(), metric_key, year)


@bench_router.get("/company/{company_id}")
async def benchmark_company(company_id: str):
    """Scorecard: where this company ranks on every metric it shares with ≥2 peers."""
    return company_scorecard(_fetch_all_claims(), company_id)


@bench_router.get("/trajectory/{company_id}/{metric_key:path}")
async def benchmark_trajectory(company_id: str, metric_key: str,
                               target_value: Optional[float] = None,
                               target_year: Optional[int] = None):
    """Per-year canonical value series for a company+metric, with trend + gap-to-target."""
    return trajectory(_fetch_all_claims(), company_id, metric_key, target_value, target_year)


@audit_router.post("/ask")
async def audit_ask(req: AskRequest):
    """Conversational audit: NL question → page-cited answer over the claim corpus."""
    return agent_ask(req.question, req.doc_id, req.k)


@audit_router.get("/{doc_id}/summary")
async def audit_summary(doc_id: str):
    """Agentic full audit: runs integrity + fact-check + benchmark, returns an LLM
    executive summary fusing all findings."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    contradictions = _numeric_contradictions(claims)
    report = build_report(claims, contradictions)
    company_id = claims[0].get("company_id")
    factcheck = fact_check_document(claims, _fetch_company_claims(company_id) if company_id else [],
                                    load_external_corpus(), limit=50)
    scorecard = company_scorecard(_fetch_all_claims(), company_id) if company_id else {"metrics": []}
    return synthesize_audit(report, factcheck, scorecard)
