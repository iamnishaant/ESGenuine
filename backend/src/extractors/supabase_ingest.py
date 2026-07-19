"""
ESGenuine — Supabase ingest (the missing write path).

Embeds extracted claims and writes them to the Supabase `claims` table that the
frontend dashboard reads. Fixes existing_issues #3: doc_id is a real document id
(report_id), NOT a chunk id.
"""
import os
import uuid
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

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


def sha256_file(path: str) -> str:
    """Full-file SHA-256 — the stable content-hash dedup key. Matches the digest
    Step0_IngestTriage computes, so the same PDF hashes identically on either path."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_report_by_file_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    """Return the existing reports row for this exact file content, or None.
    Used by the ingest endpoint to short-circuit a re-upload of an already-ingested
    PDF instead of spawning a job that would duplicate its claims."""
    if not file_hash:
        return None
    try:
        sb = _get_sb()
        res = (
            sb.table("reports")
            .select("report_id,company_name,report_year,file_hash,claim_count,ingested_at")
            .eq("file_hash", file_hash)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        # A dedup-lookup failure must not block ingest — fall through to a normal run.
        print(f"[ingest] dedup lookup failed (proceeding without it): {e}")
        return None


def _delete_existing_claims(sb: Client, report_id: str, doc_id: str) -> bool:
    """Idempotent re-ingest: remove this report's prior claims before writing the
    fresh set, so re-ingesting the same report never accumulates duplicate rows.
    Returns True if the delete call succeeded (it may have deleted zero rows)."""
    try:
        sb.table("claims").delete().or_(
            f"report_id.eq.{report_id},doc_id.eq.{doc_id}"
        ).execute()
        return True
    except Exception as e:
        # If this fails (e.g. RLS forbids delete), inserts below would duplicate.
        # Surface it loudly rather than silently double-writing.
        print(f"[ingest] WARNING: could not clear existing claims for {report_id} "
              f"(re-ingest may duplicate): {e}")
        return False


def _upsert_report(sb: Client, meta: Dict[str, Any], claim_count: int) -> None:
    """Persist/refresh the reports row (keyed by report_id) so future ingests can
    dedup by content hash and the dashboard has accurate per-report metadata."""
    row = {
        "report_id": meta.get("report_id"),
        "company_id": meta.get("company_id"),
        "company_name": meta.get("company_name"),
        "report_year": meta.get("report_year"),
        "file_hash": meta.get("file_hash"),
        "claim_count": claim_count,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        sb.table("reports").upsert(row, on_conflict="report_id").execute()
    except Exception as e:
        print(f"[ingest] reports upsert failed for {meta.get('report_id')}: {e}")


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
        # Regulatory clause IDs + quality-gate flags (migration 2026-07-03). _insert
        # retries without these when the DB predates the migration.
        "framework_tags": getattr(claim, "framework_tags", None) or [],
        "quality_flags": getattr(claim, "quality_flags", None) or [],
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
        # DB predates the 2026-07-03 migration (framework_tags/quality_flags columns
        # missing): retry once without the new fields so ingest keeps working; the
        # tags land after the idempotent migration is applied.
        msg = str(e)
        if "framework_tags" in msg or "quality_flags" in msg:
            print("[ingest] framework_tags/quality_flags columns missing — retrying without "
                  "(apply backend/database/2026-07-03_framework_tags_quality_flags.sql).")
            slim = [{k: v for k, v in row.items()
                     if k not in ("framework_tags", "quality_flags")} for row in rows]
            try:
                r = sb.table("claims").insert(slim).execute()
                return len(r.data) if r.data else 0
            except Exception as e2:
                print(f"[ingest] batch insert failed: {e2}")
                return 0
        print(f"[ingest] batch insert failed: {e}")
        return 0


def ingest_claims_to_db(claims: List, report_meta: Dict[str, Any], batch_size: int = 50) -> Dict[str, Any]:
    """
    Embed + write claims to Supabase, idempotently.

    report_meta: {report_id, company_id, company_name, report_year, file_hash}.

    Re-ingesting the same report replaces its claims (delete-then-insert keyed by
    report_id) rather than appending, so repeated runs never accumulate duplicates.
    Also upserts the matching reports row (carrying file_hash for content-hash dedup).
    Returns {inserted, total, doc_id, replaced}.
    """
    if not claims:
        # Empty extraction: do NOT wipe a prior good ingest for this report.
        return {"inserted": 0, "total": 0, "doc_id": report_meta.get("report_id"), "replaced": False}

    sb = _get_sb()
    model = _get_model()
    doc_id = report_meta.get("report_id") or report_meta.get("document_id") or "doc"
    report_id = report_meta.get("report_id") or doc_id

    # Idempotent replace: clear this report's existing claims before writing the new set.
    replaced = _delete_existing_claims(sb, report_id, doc_id)

    texts = [(c.provenance.source_sentence or "") for c in claims]
    embs = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()

    inserted, batch = 0, []
    slim_rows = []   # claim rows minus embedding, for the contradiction persist
    for c, emb in zip(claims, embs):
        row = _row(c, doc_id, emb, report_meta)
        slim_rows.append({k: v for k, v in row.items() if k != "embedding"})
        batch.append(row)
        if len(batch) >= batch_size:
            inserted += _insert(sb, batch)
            batch = []
    if batch:
        inserted += _insert(sb, batch)

    # Record/refresh report metadata (file_hash powers future content-hash dedup).
    # Only when something was actually written — otherwise a totally failed insert
    # would leave a reports row that dedup-blocks the retry of an empty report.
    if inserted > 0:
        _upsert_report(sb, report_meta, inserted)
        # Keep the UI-facing `contradictions` table in sync with the fresh claim set
        # (delete-then-insert by doc_id; deterministic numeric scan, no model load).
        # Guarded: a contradiction-persist failure must never fail an ingest.
        try:
            from reasoning.persist_contradictions import persist_doc_contradictions
            persist_doc_contradictions(sb, doc_id, slim_rows)
        except Exception as e:
            print(f"[ingest] contradiction persist failed for {doc_id} (non-fatal): {e}")

    print(f"[ingest] {inserted}/{len(claims)} claims -> Supabase (doc_id={doc_id}, replaced={replaced})")
    return {"inserted": inserted, "total": len(claims), "doc_id": doc_id, "replaced": replaced}


# ── durable ingest-job state (DB-backed, with in-memory fallback) ─────────────
# Replaces the in-memory `ingest_jobs` dict in server.py so job status survives a
# restart and is shared across workers. The full flat payload is stored in `detail`
# so the /v1/jobs API returns the same shape as before; status/error are mirrored to
# columns. Every DB call is guarded — if the DB is unreachable the job still tracks in
# memory (dev without creds, or a transient outage, never breaks the ingest flow).
_jobs_mem: Dict[str, Dict[str, Any]] = {}


def _job_row(flat: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "job_id": flat.get("job_id"),
        "report_id": flat.get("report_id"),
        "company_name": flat.get("company_name"),
        "report_year": flat.get("report_year"),
        "status": flat.get("status"),
        "error": flat.get("error"),
        "detail": flat,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def create_job(job_id: str, base: Dict[str, Any]) -> None:
    """Create/replace a job's state (memory + DB)."""
    _jobs_mem[job_id] = dict(base)
    try:
        _get_sb().table("jobs").upsert(_job_row(_jobs_mem[job_id]), on_conflict="job_id").execute()
    except Exception as e:
        print(f"[jobs] persist create failed for {job_id} (memory only): {e}")


def update_job(job_id: str, **fields) -> None:
    """Merge fields into a job's state (memory + DB)."""
    j = _jobs_mem.setdefault(job_id, {"job_id": job_id})
    j.update(fields)
    try:
        _get_sb().table("jobs").upsert(_job_row(j), on_conflict="job_id").execute()
    except Exception as e:
        print(f"[jobs] persist update failed for {job_id} (memory only): {e}")


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return a job's flat payload — DB first (survives restart), then memory."""
    try:
        res = _get_sb().table("jobs").select("detail").eq("job_id", job_id).limit(1).execute()
        if res.data and res.data[0].get("detail"):
            return res.data[0]["detail"]
    except Exception as e:
        print(f"[jobs] DB read failed for {job_id} (falling back to memory): {e}")
    return _jobs_mem.get(job_id)
