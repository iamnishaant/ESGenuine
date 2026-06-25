"""
ESGenuine — Supabase ingest (the missing write path).

Embeds extracted claims and writes them to the Supabase `claims` table that the
frontend dashboard reads. Fixes existing_issues #3: doc_id is a real document id
(report_id), NOT a chunk id.
"""
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

load_dotenv()

EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")  # 768-dim (matches schema VECTOR(768))
_model = None
_sb: Client = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _get_sb() -> Client:
    global _sb
    if _sb is None:
        url = os.getenv("VITE_SUPABASE_URL")
        key = os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
        if not url or not key:
            raise ValueError("Missing Supabase credentials (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY).")
        _sb = create_client(url, key)
    return _sb


def _clean_str(v):
    """Null out placeholder/junk strings (#9) so the DB never stores the literal
    'null'/'none'/'nan' or empty text in free-text columns like location_text."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "nan", "n/a"):
        return None
    return s


def _clean_date(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "nan"):
        return None
    for f in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _row(claim, doc_id: str, emb: list, meta: Dict[str, Any]) -> dict:
    m = claim.metric
    t = claim.time
    return {
        "claim_id": str(uuid.uuid4()),  # DB column is UUID; model claim_id is a short internal id
        "doc_id": doc_id,  # FIX (#3): real document id, not chunk_id
        "page_number": claim.provenance.page_number,
        "chunk_id": claim.provenance.chunk_id,
        "source_sentence": claim.provenance.source_sentence,
        "aspect": claim.aspect,
        "normalized_aspect": claim.normalized_aspect,
        "metric_family": claim.metric_family or "uncategorized",
        "metric_key": claim.metric_key,
        "metric_value": m.value if m else None,
        "metric_unit": m.unit if m else None,
        "metric_direction": m.direction if m else None,
        "time_start": _clean_date(t.start_date if t else None),
        "time_end": _clean_date(t.end_date if t else None),
        "time_bucket": claim.time_bucket,
        "location_text": _clean_str(claim.location.raw_text if claim.location else None),
        "location_scope": claim.location_scope or "global",
        "claim_type": claim.claim_type,
        "vagueness_score": claim.vagueness_score,
        "groundability_score": claim.groundability_score,
        "observability_type": getattr(claim, "observability_type", None) or "not_observable",
        "claim_signature": claim.claim_signature,
        "embedding": emb,
        "company_id": meta.get("company_id"),
        "company_name": meta.get("company_name"),
        "report_year": meta.get("report_year"),
        "report_id": meta.get("report_id"),
    }


def _insert(sb: Client, rows: list) -> int:
    try:
        r = sb.table("claims").insert(rows).execute()
        return len(r.data) if r.data else 0
    except Exception as e:
        print(f"[ingest] batch insert failed: {e}")
        return 0


def ingest_claims_to_db(claims: List, report_meta: Dict[str, Any], batch_size: int = 50) -> Dict[str, Any]:
    """
    Embed + write claims to Supabase.
    report_meta: {report_id, company_id, company_name, report_year}.
    Returns {inserted, total, doc_id}.
    """
    if not claims:
        return {"inserted": 0, "total": 0, "doc_id": report_meta.get("report_id")}

    sb = _get_sb()
    model = _get_model()
    doc_id = report_meta.get("report_id") or report_meta.get("document_id") or "doc"

    texts = [(c.provenance.source_sentence or "") for c in claims]
    embs = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()

    inserted, batch = 0, []
    for c, emb in zip(claims, embs):
        batch.append(_row(c, doc_id, emb, report_meta))
        if len(batch) >= batch_size:
            inserted += _insert(sb, batch)
            batch = []
    if batch:
        inserted += _insert(sb, batch)

    print(f"[ingest] {inserted}/{len(claims)} claims -> Supabase (doc_id={doc_id})")
    return {"inserted": inserted, "total": len(claims), "doc_id": doc_id}
