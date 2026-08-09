"""
ESGenuine — Agentic Auditor & Conversational Audit
==================================================
Two capabilities on top of the analysis primitives:

  ask(question)        — natural-language Q&A over the claim corpus with page-cited
                         answers (semantic retrieval via the search_claims RPC + LLM).
  synthesize_audit(...) — an LLM executive summary that fuses the Integrity Report,
                         fact-check verdicts, and peer scorecard into one narrative.

Degrades gracefully: if no LLM key is configured, returns the retrieved evidence /
structured findings without the generated prose.
"""

import os
import json
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from supabase import create_client

try:
    from extractors.claim_extractor import LLMClient
except ImportError:  # pragma: no cover
    from src.extractors.claim_extractor import LLMClient

from .json_utils import loads_lenient

load_dotenv()
try:                                     # single source of truth for model + pinned revision
    from model_config import load_embedder
except ImportError:                      # path-setup fallback (repo root on sys.path)
    from src.model_config import load_embedder

_model = None
_sb = None
_llm = None


def _get_model():
    global _model
    if _model is None:
        _model = load_embedder()          # pinned revision (model_config)
    return _model


def _get_sb():
    global _sb
    if _sb is None:
        _sb = create_client(os.getenv("VITE_SUPABASE_URL"), os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY"))
    return _sb


def _get_llm():
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def _has_llm() -> bool:
    return bool(_get_llm().endpoints) or _get_llm().provider in ("openai", "anthropic")


# ── pure helpers (no I/O / no LLM) ───────────────────────────────────────────────
def suggest_questions(report: Dict[str, Any], limit: int = 5) -> List[str]:
    """Concrete starter questions derived from a report's flags/stats — no LLM."""
    company = (report.get("meta") or {}).get("company_name") or "this company"
    qs: List[str] = []
    for f in (report.get("flags") or []):
        t = (f.get("type") or "").lower()
        title = f.get("title") or f.get("type") or "this issue"
        if "vague" in t:
            qs.append("Which environmental claims lack measurable metrics?")
        elif "contradic" in t:
            qs.append("Where does this report contradict itself on emissions or targets?")
        elif "aspiration" in t or "narrative" in t:
            qs.append("Which targets have no baseline, deadline, or interim milestones?")
        else:
            qs.append(f"What evidence supports the '{title}' flag?")
    stats = report.get("statistics") or {}
    if stats.get("with_metric_pct") is not None and stats["with_metric_pct"] < 50:
        qs.append(f"Why are most of {company}'s claims qualitative rather than quantified?")
    if (stats.get("contradictions") or 0) > 0:
        qs.append("Summarise every numeric contradiction found in this report.")
    if not qs:
        qs = [f"What emissions targets has {company} set?",
              "Which claims are externally verifiable?",
              "Are there any contradictions in the social data?"]
    seen, out = set(), []
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= limit:
            break
    return out


def _key_findings(report: Dict[str, Any], factcheck: Dict[str, Any],
                  scorecard: Dict[str, Any]) -> List[str]:
    """Top structured findings as bullet strings — the richer non-LLM executive summary."""
    bullets: List[str] = []
    score = report.get("integrity_score")
    if score is not None:
        bullets.append(f"Integrity score {round(score)}/100 (grade {report.get('grade')}, "
                       f"{str(report.get('greenwashing_risk')).lower()} greenwashing risk).")
    flags = report.get("flags") or []
    if flags:
        top = flags[0]
        bullets.append(f"Top flag: {top.get('title') or top.get('type')} "
                       f"({top.get('count')} claim(s), {top.get('severity')}).")
    cred = factcheck.get("credibility")
    if cred is not None:
        cov = factcheck.get("coverage") or 0
        bullets.append(f"External fact-check: {int(cred * 100)}% of checked claims supported "
                       f"(coverage {int(cov * 100)}%).")
    lagging = [m for m in (scorecard.get("metrics") or []) if m.get("verdict") == "lagging"]
    if lagging:
        bullets.append(f"Lagging vs peers on {len(lagging)} metric(s), incl. {lagging[0].get('metric_key')}.")
    return bullets[:4] or ["No findings available for this report."]


def _unsupported_citations(used, valid_ns) -> List[int]:
    """Citation indices the LLM referenced that don't exist in the evidence set (hallucinated)."""
    valid = set(valid_ns)
    out = []
    for u in (used or []):
        try:
            n = int(u)
        except (TypeError, ValueError):
            continue
        if n not in valid:
            out.append(n)
    return out


def retrieve(question: str, doc_id: Optional[str] = None, k: int = 8) -> List[Dict[str, Any]]:
    """Semantic search over claims for the question (optionally scoped to one document)."""
    emb = _get_model().encode(question).tolist()
    res = _get_sb().rpc("search_claims", {
        "query_embedding": emb, "match_count": k, "filter_doc": doc_id,
    }).execute()
    return res.data or []


def ask(question: str, doc_id: Optional[str] = None, k: int = 8) -> Dict[str, Any]:
    """Answer an NL question with citations to specific claims (company/year/page)."""
    hits = retrieve(question, doc_id, k)
    citations = [{
        "n": i + 1,
        "company": h.get("company_name"),
        "year": h.get("report_year"),
        "page": h.get("page_number"),
        "doc_id": h.get("doc_id"),
        "text": (h.get("source_sentence") or "")[:240],
        "similarity": round(h.get("similarity", 0), 3),
    } for i, h in enumerate(hits)]

    if not citations:
        return {"question": question, "answer": "No relevant claims were found in the corpus.",
                "citations": [], "engine": "retrieval"}

    # Scope signal: if even the best match is weak, the question may be outside the corpus.
    top_similarity = round(max((c["similarity"] for c in citations), default=0.0), 3)
    low_relevance = top_similarity < 0.25

    if not _has_llm():
        return {"question": question,
                "answer": "LLM not configured — returning the most relevant claims as evidence.",
                "citations": citations, "engine": "retrieval",
                "top_similarity": top_similarity, "low_relevance": low_relevance}

    context = "\n".join(
        f"[{c['n']}] ({c['company']} {c['year']}, p{c['page']}) {c['text']}" for c in citations
    )
    prompt = (
        "You are an ESG audit assistant. Answer the QUESTION using ONLY the numbered "
        "EVIDENCE claims. Cite sources inline as [n]. If the evidence is insufficient, "
        "say so plainly. Respond ONLY as JSON: "
        '{"answer": "concise answer with [n] citations", "used": [n, ...]}.\n\n'
        f"QUESTION: {question}\n\nEVIDENCE:\n{context}\n"
    )
    try:
        data = loads_lenient(_get_llm().extract(prompt))
        used = data.get("used", [])
        return {"question": question, "answer": data.get("answer", ""),
                "used": used,
                # Hallucinated [n] references — citations not in the evidence set.
                "unsupported_citations": _unsupported_citations(used, {c["n"] for c in citations}),
                "citations": citations, "engine": "llm",
                "top_similarity": top_similarity, "low_relevance": low_relevance}
    except Exception as e:
        return {"question": question, "answer": f"(LLM error: {e}) Top evidence returned instead.",
                "citations": citations, "engine": "retrieval",
                "top_similarity": top_similarity, "low_relevance": low_relevance}


def synthesize_audit(report: Dict[str, Any], factcheck: Dict[str, Any],
                     scorecard: Dict[str, Any]) -> Dict[str, Any]:
    """Fuse the structured findings into an executive narrative (LLM optional)."""
    findings = {
        "company": report.get("meta", {}).get("company_name"),
        "integrity_score": report.get("integrity_score"),
        "grade": report.get("grade"),
        "top_flags": [{"type": f["type"], "severity": f["severity"], "count": f.get("count")}
                      for f in report.get("flags", [])[:5]],
        "fact_check": factcheck.get("verdict_counts"),
        "credibility": factcheck.get("credibility"),
        "benchmark_lagging": [m for m in scorecard.get("metrics", []) if m.get("verdict") == "lagging"][:5],
    }
    key_findings = _key_findings(report, factcheck, scorecard)
    findings["key_findings"] = key_findings
    out = {"findings": findings, "key_findings": key_findings}  # always present
    if not _has_llm():
        # Richer fallback than a single template line: a structured top-findings list.
        out["executive_summary"] = " ".join(key_findings)
        out["engine"] = "structured"
        return out
    prompt = (
        "You are a senior ESG auditor. Write a tight 4-6 sentence executive summary of "
        "this company's sustainability-report integrity, citing the concrete findings. "
        "Be specific and neutral; do not invent numbers. Respond ONLY as JSON: "
        '{"executive_summary": "...", "verdict": "Low|Moderate|High greenwashing risk"}.\n\n'
        f"FINDINGS: {json.dumps(findings, default=str)}\n"
    )
    try:
        data = loads_lenient(_get_llm().extract(prompt))
        out["executive_summary"] = data.get("executive_summary", report.get("summary", ""))
        out["verdict"] = data.get("verdict")
        out["engine"] = "llm"
    except Exception as e:
        out["executive_summary"] = " ".join(key_findings)
        out["engine"] = "structured"
        out["note"] = f"LLM summary unavailable: {e}"
    return out
