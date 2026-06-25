"""
ESGenuine — ESG Integrity Report
================================
Synthesis layer: combines claim statistics, the greenwashing taxonomy, and the
contradiction engine into a single defensible "ESG Integrity Report" for a document.

`build_report(claims, contradictions)` is pure (no I/O) so it is unit-testable; the
API layer fetches the inputs and calls it.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import collections

from .greenwash_taxonomy import GreenwashTaxonomy, _SEV_RANK

# Penalty (points off a 100 integrity score) per flag severity.
_PENALTY = {"Critical": 25, "High": 15, "Medium": 8, "Low": 3, "None": 0}

# Bump when the scoring formula / flag set changes so a stored score's provenance is clear.
_REPORT_VERSION = "1.0"


# Mirror of frontend verificationMethod() (lib/api.ts) — keep the two in sync.
_OBS_TO_METHOD = {
    "optical_possible": "imagery",
    "directly_observable": "data_crosscheck",
    "reported_metric": "data_crosscheck",
    "not_observable": "document_review",
}


def _verification_method(claim: Dict[str, Any]) -> str:
    """How this claim *can* be checked (imagery / data_crosscheck / document_review)."""
    ot = (claim.get("observability_type") or "").strip().lower()
    if ot in _OBS_TO_METHOD:
        return _OBS_TO_METHOD[ot]
    # legacy rows without observability_type: a claim with a metric is data-checkable.
    return "data_crosscheck" if claim.get("metric_value") is not None else "document_review"


def _grade(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_report(claims: List[Dict[str, Any]],
                 contradictions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    contradictions = contradictions or []
    total = len(claims)
    if total == 0:
        return {"status": "No Data", "integrity_score": None, "grade": None, "flags": []}

    # ── metadata (claims share company/report/year) ─────────────────────────────
    first = claims[0]
    meta = {
        "doc_id": first.get("doc_id"),
        "report_id": first.get("report_id"),
        "company_name": first.get("company_name"),
        "report_year": first.get("report_year"),
        "total_claims": total,
    }

    # ── claim statistics ────────────────────────────────────────────────────────
    ctype = collections.Counter((c.get("claim_type") or "narrative") for c in claims)
    with_metric = sum(1 for c in claims if c.get("metric_value") is not None)
    grounds = [g for g in (_num(c.get("groundability_score")) for c in claims) if g is not None]
    avg_ground = round(sum(grounds) / len(grounds), 3) if grounds else None
    # How the report's claims can be verified (honest disclosure profile).
    verification_profile = collections.Counter(_verification_method(c) for c in claims)
    stats = {
        "by_type": dict(ctype),
        "with_metric": with_metric,
        "with_metric_pct": round(with_metric * 100 / total),
        "avg_groundability": avg_ground,
        "contradictions": len(contradictions),
        "verification_profile": {
            "imagery": verification_profile.get("imagery", 0),
            "data_crosscheck": verification_profile.get("data_crosscheck", 0),
            "document_review": verification_profile.get("document_review", 0),
        },
    }

    # ── greenwashing flags (taxonomy) ───────────────────────────────────────────
    flags = GreenwashTaxonomy.analyze(claims, contradictions=contradictions)
    flag_dicts = [f.to_dict() for f in flags]
    flag_counts = collections.Counter(f.severity for f in flags)

    # ── integrity score: 100 minus a flat per-flag severity penalty ─────────────
    # NOTE: this is a flat subtraction (one penalty per distinct flag type), NOT
    # count-weighted or diminishing. Count-weighting (penalty scaled by how many
    # claims triggered the flag) is a planned improvement — see self_improvement.md.
    score = 100.0
    penalty_breakdown = []
    for f in flags:
        pts = _PENALTY.get(f.severity, 0)
        score -= pts
        penalty_breakdown.append({
            "type": f.type, "title": f.title, "severity": f.severity,
            "count": f.count, "points_deducted": pts,
        })
    score = max(0.0, min(100.0, score))
    # Most-impactful first, so the UI can render "this flag cost you N points".
    penalty_breakdown.sort(key=lambda p: p["points_deducted"], reverse=True)
    grade = _grade(score)

    risk = "Low" if score >= 70 else ("Moderate" if score >= 50 else "High")

    # ── recommendations (de-duplicated, severity-ordered) ───────────────────────
    recs = []
    seen = set()
    for f in flags:
        if f.recommendation and f.recommendation not in seen:
            seen.add(f.recommendation)
            recs.append({"severity": f.severity, "action": f.recommendation, "for": f.type})

    # ── executive summary line ──────────────────────────────────────────────────
    top = flags[0] if flags else None
    summary = (
        f"{meta['company_name'] or 'This report'} scores {round(score)}/100 (grade {grade}, "
        f"{risk.lower()} greenwashing risk) across {total} extracted claims. "
        + (f"Primary concern: {top.title.lower()} ({top.count})." if top else "No greenwashing flags raised.")
    )

    return {
        "status": "ok",
        "meta": meta,
        "integrity_score": round(score, 1),
        "grade": grade,
        "greenwashing_risk": risk,
        "summary": summary,
        "statistics": stats,
        "flag_summary": {"total": len(flags), "by_severity": dict(flag_counts)},
        "penalty_breakdown": penalty_breakdown,
        "flags": flag_dicts,
        "recommendations": recs,
        # Provenance: when/with-which-formula this score was computed (auditability).
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "report_version": _REPORT_VERSION,
    }
