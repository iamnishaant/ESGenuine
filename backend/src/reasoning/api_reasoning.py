"""
ESGenuine — Week 4: Reasoning API Endpoints
==================================================
Exposes the Contradiction Engine and Greenwashing Risk Score 
to the React Frontend Dashboard.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

try:
    from api.auth import get_current_user
except ImportError:  # pragma: no cover - path-setup fallback (mirrors this module's other imports)
    from src.api.auth import get_current_user
from typing import Optional
import itertools
import collections

# In a full production setup these would be imported from the DB layer
try:
    from reasoning.retrieval import find_candidate_pairs, get_supabase, RetrievalError
    from reasoning.nli_engine import ContradictionEngine
    from reasoning.contradiction_scan import scan_contradictions
    from reasoning.greenwash_taxonomy import GreenwashTaxonomy
    from reasoning.integrity_report import build_report
    from reasoning.benchmark import cross_company, company_scorecard, trajectory
    from reasoning.fact_check import fact_check_document, load_external_corpus
    from reasoning.agent import ask as agent_ask, synthesize_audit, suggest_questions, _get_llm, _has_llm
except ImportError:  # pragma: no cover - path-setup fallback (repo root on sys.path)
    from src.reasoning.retrieval import find_candidate_pairs, get_supabase, RetrievalError
    from src.reasoning.nli_engine import ContradictionEngine
    from src.reasoning.contradiction_scan import scan_contradictions
    from src.reasoning.greenwash_taxonomy import GreenwashTaxonomy
    from src.reasoning.integrity_report import build_report
    from src.reasoning.benchmark import cross_company, company_scorecard, trajectory
    from src.reasoning.fact_check import fact_check_document, load_external_corpus
    from src.reasoning.agent import ask as agent_ask, synthesize_audit, suggest_questions, _get_llm, _has_llm


def _optional_llm():
    """The configured LLMClient, or None — so fact-check stays deterministic when no LLM
    is available and only uses the (guarded) LLM fallback when one is."""
    try:
        return _get_llm() if _has_llm() else None
    except Exception:
        return None

router = APIRouter(prefix="/reports", tags=["Reasoning"])
bench_router = APIRouter(prefix="/benchmark", tags=["Benchmark"])
audit_router = APIRouter(prefix="/audit", tags=["Agent"])
engine = ContradictionEngine()
_SEV_FROM_TYPE = {"Hard": "Critical", "Metric": "High", "Temporal": "Medium", "Scope": "Low"}


def _numeric_contradictions(claims, cap: int = 3000):
    """Fast numeric-only contradiction pass (no NLI) for the audit summary.

    Returns (contradictions, truncated). `truncated` is True when the pairwise scan hit
    `cap` and stopped early, so callers can report an incomplete set instead of silently
    under-counting contradictions on a large single report (#3)."""
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
                return out, True
            r = engine._numeric_conflict(a, b)
            if r:
                out.append({"severity": _SEV_FROM_TYPE.get(r["type"], "Medium"),
                            "reasoning": r["reason"], "conflict_type": r["type"]})
    return out, False


class AskRequest(BaseModel):
    question: str
    doc_id: Optional[str] = None
    k: int = 8


class ReviewIn(BaseModel):
    """A reviewer's verdict on one flagged item (human-in-the-loop)."""
    subject_id: str                 # claim_id | contradiction hash | '__report__'
    flag_type: str
    verdict: str                    # 'dismissed' (false positive, +score) | 'confirmed' (valid)
    note: Optional[str] = None
    reviewer: Optional[str] = None

# Columns the reasoning/report surface needs (excludes the large embedding vector).
_CLAIM_COLS = (
    "claim_id,doc_id,report_id,company_id,company_name,report_year,page_number,source_sentence,"
    "aspect,normalized_aspect,metric_family,metric_key,metric_value,metric_unit,"
    "metric_direction,time_bucket,location_scope,claim_type,vagueness_score,groundability_score,"
    "observability_type"
)


def _fetch_doc_claims(doc_id: str):
    sb = get_supabase()
    res = sb.table("claims").select(_CLAIM_COLS).eq("doc_id", doc_id).execute()
    return res.data or []


def _fetch_reviews(doc_id: str):
    """Reviewer verdicts for this document's flags (drives the review-adjusted score).
    Tolerant of the table not existing yet (pre-migration) — returns [] so reports still load."""
    if not doc_id:
        return []
    try:
        sb = get_supabase()
        res = (sb.table("claim_reviews")
               .select("subject_id,flag_type,verdict,note,reviewer,created_at")
               .eq("doc_id", doc_id).execute())
        return res.data or []
    except Exception as e:
        print(f"[reviews] fetch failed for {doc_id} (proceeding without): {e}")
        return []

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

    # 2. For each claim, find historical/peer contradictions. The loop + unordered-pair
    #    dedup (NLI #4) live in the pure `scan_contradictions` so they are testable without
    #    Supabase / the NLI model; here we just inject the retrieval and engine.
    #    A retrieval failure is SURFACED (retrieval_available: false), not swallowed into a
    #    misleading "0 conflicts" (existing_issues #1). The persisted `contradictions` table
    #    + the integrity-report's numeric scan are unaffected — only this semantic/NLI view.
    try:
        conflicts, severity_counts = scan_contradictions(
            doc_claims,
            lambda c: find_candidate_pairs(c, similarity_threshold=0.85),
            engine,
        )
    except RetrievalError as e:
        return {
            "total_conflicts": 0, "critical": 0, "high": 0, "medium": 0, "low": 0,
            "conflicts": [], "retrieval_available": False, "retrieval_error": str(e),
        }

    return {
        "total_conflicts": len(conflicts),
        "critical": severity_counts["Critical"],
        "high": severity_counts["High"],
        "medium": severity_counts["Medium"],
        "low": severity_counts["Low"],
        "conflicts": conflicts,
        "retrieval_available": True,
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


def _factcheck_for(claims):
    """Deterministic fact-check (no LLM) for score integration (v2.2). Same corpus the
    fact-check endpoint uses, so the integrity score moves consistently on every page.
    Failure degrades to None → build_report scores exactly as v2.1."""
    try:
        company_id = claims[0].get("company_id") if claims else None
        peers = _fetch_company_claims(company_id) if company_id else []
        return fact_check_document(claims, peers, load_external_corpus(), limit=50)
    except Exception as e:
        print(f"[integrity] fact-check integration skipped: {e}")
        return None


def _satellite_for(doc_id):
    """Latest satellite_evidence row per claim for this report (v2.3), RE-LINKED to the
    current claims by the stable `check_key` — claim_id is a fresh uuid on every
    re-ingest, so a claim_id join would show stale/orphaned verdicts. We map each stored
    row back to a live claim via check_key and drop rows whose claim no longer exists,
    so the panel self-heals after a re-ingest. Failure degrades to None → scores as v2.2."""
    try:
        sb = get_supabase()
        # live check_key -> current claim_id for this report
        live = (sb.table("claims").select("claim_id,report_id,normalized_aspect,"
                                          "location_text,time_bucket")
                .eq("doc_id", doc_id).execute()).data or []
        from verification.satellite_evidence import check_key
        key_to_live = {check_key(c): c["claim_id"] for c in live}

        res = (sb.table("satellite_evidence")
               .select("claim_id,check_key,verdict,reason,ndvi_delta,z_score,bundle_sha256,checked_at")
               .eq("report_id", doc_id)
               .order("checked_at", desc=True).limit(2000).execute())
        latest = {}
        for r in (res.data or []):          # newest first — first wins per check
            k = r.get("check_key")
            live_id = key_to_live.get(k) if k else None
            if live_id is None:
                continue                    # orphaned (pre-check_key or removed claim)
            r["claim_id"] = live_id         # re-link to the current claim
            latest.setdefault(k, r)
        return list(latest.values()) or None
    except Exception as e:
        print(f"[integrity] satellite integration skipped: {e}")
        return None


@router.get("/{doc_id}/integrity-report")
async def get_integrity_report(doc_id: str):
    """Full ESG Integrity Report: score, grade, greenwashing flags, contradictions,
    and recommendations — the one-call deliverable for the dashboard."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    # Fast, deterministic numeric contradiction scan — the SAME source that populates the
    # persisted `contradictions` table and drives every other endpoint (review-queue,
    # greenwashing-flags, audit summary). The previous path called get_contradictions(),
    # which fires one Supabase vector-search RPC PER claim (379 round-trips on shell_2023
    # → 100–235s, many "Server disconnected") plus an NLI model pass. Semantic/NLI
    # retrieval stays available on the dedicated GET /{doc_id}/contradictions endpoint.
    contradictions = _numeric_contradictions(claims)[0]
    return build_report(claims, contradictions, _fetch_reviews(doc_id),
                        factcheck=_factcheck_for(claims), satellite=_satellite_for(doc_id))


@router.get("/{doc_id}/review-queue")
async def get_review_queue(doc_id: str):
    """Every reviewable flagged item for this report (per-claim flags, contradictions,
    report-level flags) + the model's stated reason + the reviewer's current verdict (if any).
    Drives the human-in-the-loop review UI."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    contradictions = _numeric_contradictions(claims)[0]
    items = GreenwashTaxonomy.attribute(claims, contradictions=contradictions)
    verdicts = {(r["subject_id"], r["flag_type"]): r for r in _fetch_reviews(doc_id)}
    for it in items:
        r = verdicts.get((it["subject_id"], it["flag_type"]))
        it["verdict"] = r.get("verdict") if r else None
        it["note"] = r.get("note") if r else None
    # Unreviewed first (actionable), then dismissed, then confirmed.
    _order = {None: 0, "dismissed": 1, "confirmed": 2}
    items.sort(key=lambda it: _order.get(it.get("verdict"), 0))
    return {"doc_id": doc_id, "total": len(items),
            "reviewed": sum(1 for it in items if it.get("verdict")), "items": items}


@router.post("/{doc_id}/reviews")
async def post_review(doc_id: str, body: ReviewIn, user: dict = Depends(get_current_user)):
    """Upsert a reviewer verdict on one flagged item (one current verdict per item).
    A 'dismissed' verdict raises the integrity score on the next recompute. Gated: requires
    a logged-in user, and the verdict is attributed to that user's email (auditable)."""
    if body.verdict not in ("dismissed", "confirmed"):
        raise HTTPException(status_code=400, detail="verdict must be 'dismissed' or 'confirmed'.")
    sb = get_supabase()
    row = {"doc_id": doc_id, "subject_id": body.subject_id, "flag_type": body.flag_type,
           "verdict": body.verdict, "note": body.note, "reviewer": user["email"]}
    try:
        sb.table("claim_reviews").upsert(row, on_conflict="doc_id,subject_id,flag_type").execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save review: {e}")
    return {"status": "ok", **row}


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


@router.get("/portfolio/integrity")
async def portfolio_integrity():
    """Per-company integrity scores computed with the SAME build_report() the Integrity
    Audit page uses — so the Portfolio headline score and the Integrity Audit score agree
    (single source of truth; fixes the "two products" score divergence where the frontend
    computed its own groundability-mean score that never matched the backend). Each company
    is scored on its latest report year."""
    all_claims = _fetch_all_claims()
    by_company = collections.defaultdict(list)
    for c in all_claims:
        cid = c.get("company_id") or c.get("company_name") or "unknown"
        by_company[cid].append(c)

    out = []
    for cid, claims in by_company.items():
        years = [c.get("report_year") for c in claims if c.get("report_year") is not None]
        latest = max(years) if years else None
        scored = [c for c in claims if c.get("report_year") == latest] if latest is not None else claims
        doc_id = scored[0].get("doc_id") if scored else None
        # Apply reviewer dismissals so the portfolio grade reflects human review app-wide
        # (consistent with the Integrity Audit page's adjusted score). Fact-check is
        # folded in too (v2.2) so Portfolio and Integrity Audit stay in agreement.
        report = build_report(scored, _numeric_contradictions(scored)[0], _fetch_reviews(doc_id),
                              factcheck=_factcheck_for(scored))
        out.append({
            "company_id": cid,
            "company_name": (scored[0].get("company_name") if scored else None) or cid,
            "report_year": latest,
            "doc_id": doc_id,
            "integrity_score": report.get("integrity_score"),
            "grade": report.get("grade"),
            "greenwashing_risk": report.get("greenwashing_risk"),
            "total_claims": (report.get("meta") or {}).get("total_claims", len(scored)),
        })
    out.sort(key=lambda r: (r["integrity_score"] is None, -(r["integrity_score"] or 0)))
    return {"count": len(out), "companies": out}


@router.get("/{doc_id}/fact-check")
async def get_fact_check(doc_id: str, limit: int = 50):
    """Verify each metric claim against external reference figures + the company's other
    reports. Returns SUPPORTED / CONTRADICTED / UNVERIFIED verdicts with citations."""
    doc_claims = _fetch_doc_claims(doc_id)
    if not doc_claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    company_id = doc_claims[0].get("company_id")
    peers = _fetch_company_claims(company_id) if company_id else []
    return fact_check_document(doc_claims, peers, load_external_corpus(), limit=limit, llm=_optional_llm())


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


@audit_router.get("/{doc_id}/suggested-questions")
async def audit_suggested_questions(doc_id: str):
    """Starter questions derived from this document's integrity report (no LLM)."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    report = build_report(claims, _numeric_contradictions(claims)[0])
    return {"doc_id": doc_id, "questions": suggest_questions(report)}


@audit_router.get("/{doc_id}/summary")
async def audit_summary(doc_id: str):
    """Agentic full audit: runs integrity + fact-check + benchmark, returns an LLM
    executive summary fusing all findings."""
    claims = _fetch_doc_claims(doc_id)
    if not claims:
        raise HTTPException(status_code=404, detail="No claims found for this document.")
    contradictions, contradictions_truncated = _numeric_contradictions(claims)
    company_id = claims[0].get("company_id")
    factcheck = fact_check_document(claims, _fetch_company_claims(company_id) if company_id else [],
                                    load_external_corpus(), limit=50, llm=_optional_llm())
    # Same factcheck feeds the score (v2.2) and the executive summary — one computation.
    report = build_report(claims, contradictions, factcheck=factcheck)
    scorecard = company_scorecard(_fetch_all_claims(), company_id) if company_id else {"metrics": []}
    audit = synthesize_audit(report, factcheck, scorecard)
    # Surface that the numeric contradiction scan was capped, so the summary's
    # contradiction findings are not silently treated as exhaustive (#3).
    audit["contradictions_truncated"] = contradictions_truncated
    return audit
