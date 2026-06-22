"""
Pharos Integrity — Week 4: Reasoning API Endpoints
==================================================
Exposes the Contradiction Engine and Greenwashing Risk Score 
to the React Frontend Dashboard.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List

# In a full production setup these would be imported from the DB layer
from src.reasoning.retrieval import find_candidate_pairs, get_supabase
from src.reasoning.nli_engine import ContradictionEngine

router = APIRouter(prefix="/reports", tags=["Reasoning"])
engine = ContradictionEngine()

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
