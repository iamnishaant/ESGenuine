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
from sentence_transformers import SentenceTransformer

try:
    from extractors.claim_extractor import LLMClient
except ImportError:  # pragma: no cover
    from src.extractors.claim_extractor import LLMClient

load_dotenv()
EMBED_MODEL = "BAAI/bge-base-en-v1.5"

_model = None
_sb = None
_llm = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
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

    if not _has_llm():
        return {"question": question,
                "answer": "LLM not configured — returning the most relevant claims as evidence.",
                "citations": citations, "engine": "retrieval"}

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
        data = json.loads(_get_llm().extract(prompt))
        return {"question": question, "answer": data.get("answer", ""),
                "used": data.get("used", []), "citations": citations, "engine": "llm"}
    except Exception as e:
        return {"question": question, "answer": f"(LLM error: {e}) Top evidence returned instead.",
                "citations": citations, "engine": "retrieval"}


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
    out = {"findings": findings}
    if not _has_llm():
        out["executive_summary"] = report.get("summary", "")
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
        data = json.loads(_get_llm().extract(prompt))
        out["executive_summary"] = data.get("executive_summary", report.get("summary", ""))
        out["verdict"] = data.get("verdict")
        out["engine"] = "llm"
    except Exception as e:
        out["executive_summary"] = report.get("summary", "")
        out["engine"] = "structured"
        out["note"] = f"LLM summary unavailable: {e}"
    return out
