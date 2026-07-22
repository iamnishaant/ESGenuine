"""
ESGenuine — FastAPI Server (Week 2 + 3)
===============================================
Serves:
  Week 2: 8-step document parsing pipeline
  Week 3: Claim extraction (text + table dual pipeline)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import json
import os
import re
import shutil
import uuid
import uvicorn

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.pdf_parser import DocumentParsingPipeline, PDFValidationError
from extractors.pipeline import ExtractionPipeline
from extractors.supabase_ingest import (
    ingest_claims_to_db, _get_sb, sha256_file, find_report_by_file_hash,
    create_job, update_job, get_job as get_job_state,
)
from reasoning.api_reasoning import router as reasoning_router, bench_router, audit_router
from api.auth_routes import router as auth_router
from api.auth import get_current_user

app = FastAPI(
    title="ESGenuine API",
    version="4.0.0",
    description="ESG Report Parsing & Claim Extraction — Weeks 2+3+4",
)

app.include_router(reasoning_router)
app.include_router(bench_router)
app.include_router(audit_router)
app.include_router(auth_router)

# CORS: localhost dev origins are always allowed; production origins are added
# via env so a deployed frontend works without a code change. Set either:
#   ALLOWED_ORIGINS       — comma-separated exact origins (e.g. https://app.example.com)
#   ALLOWED_ORIGIN_REGEX  — a regex (e.g. https://.*\.onrender\.com) for preview URLs
_DEV_ORIGINS = ["http://localhost:8080", "http://localhost:5173", "http://localhost:3000"]
_ENV_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS + _ENV_ORIGINS,
    allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── structured request logging (B5, scoped) ─────────────────────────────────────
# One JSON line per request: request_id, method, path, status, duration_ms. Enough
# to debug production latency/errors without a logging-framework migration; the
# request_id is echoed in the X-Request-ID header so a user report can be matched
# to its log line.
import logging
import time as _time

_req_log = logging.getLogger("esgenuine.request")
if not _req_log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(message)s"))
    _req_log.addHandler(_h)
    _req_log.setLevel(logging.INFO)


@app.middleware("http")
async def _log_requests(request, call_next):
    rid = uuid.uuid4().hex[:12]
    t0 = _time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        _req_log.info(json.dumps({
            "request_id": rid, "method": request.method, "path": request.url.path,
            "status": 500, "duration_ms": round((_time.perf_counter() - t0) * 1000, 1),
            "error": True,
        }))
        raise
    response.headers["X-Request-ID"] = rid
    _req_log.info(json.dumps({
        "request_id": rid, "method": request.method, "path": request.url.path,
        "status": response.status_code,
        "duration_ms": round((_time.perf_counter() - t0) * 1000, 1),
    }))
    return response

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
PARSED_DIR = Path(__file__).parent.parent.parent / "parsed"
UPLOAD_DIR.mkdir(exist_ok=True)
PARSED_DIR.mkdir(exist_ok=True)

document_registry: dict = {}
for path in PARSED_DIR.glob("*_full.json"):
    doc_id = path.name.replace("_full.json", "")
    # FIX (#12): the parse artifact already persists the real filename + stats — read
    # them back instead of showing a "Discovered: {id}" placeholder after restart.
    info = {"filename": f"Discovered: {doc_id}", "status": "ready"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            full = json.load(f)
        if full.get("filename"):
            info["filename"] = full["filename"]
        if full.get("statistics"):
            info["statistics"] = full["statistics"]
        if full.get("sections"):
            info["sections_detected"] = [s.get("title") for s in full["sections"]]
    except Exception as e:
        print(f"  [Startup] Could not read {path.name}: {e}")
    document_registry[doc_id] = info
print(f"  [Startup] Discovered {len(document_registry)} documents on disk.")

claims_registry: dict = {}
# Ingest job state now lives in the DB-backed store (create_job/update_job/get_job_state
# in supabase_ingest) so it survives restarts and is shared across workers.


# ──────────────────────────────────────────────
# Week 2: Upload & Parse
# ──────────────────────────────────────────────

@app.post("/v1/upload")
async def upload_and_parse(file: UploadFile = File(...)):
    """Upload a PDF and run the full 8-step parsing pipeline."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        pipeline = DocumentParsingPipeline(str(save_path))
        result = pipeline.run()
        pipeline.save(result, str(PARSED_DIR))
    except PDFValidationError as e:
        # Encrypted / corrupt / empty PDF — a client error, not a server fault.
        raise HTTPException(status_code=422, detail=f"Invalid PDF: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    doc_id = result["document_id"]
    triage = result.get("triage", {})
    document_registry[doc_id] = {
        "filename": file.filename,
        "statistics": result["statistics"],
        "sections_detected": [s["title"] for s in result["sections"]],
        "triage": triage,
    }

    return {
        "document_id": doc_id,
        "file_hash": result.get("file_hash"),
        "filename": file.filename,
        "status": "parsed",
        "extraction_path": triage.get("extraction_path"),
        "flags": triage.get("flags", []),
        "warnings": triage.get("warnings", []),
        **result["statistics"],
        "sections_detected": document_registry[doc_id]["sections_detected"],
    }


# ──────────────────────────────────────────────
# Week 2: Data Retrieval
# ──────────────────────────────────────────────

def _load_json(doc_id: str, suffix: str):
    path = PARSED_DIR / f"{doc_id}_{suffix}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{suffix} data not found for document {doc_id}.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/v1/documents/{doc_id}")
async def get_full_document(doc_id: str):
    return _load_json(doc_id, "full")

@app.get("/v1/documents/{doc_id}/sections")
async def get_sections(doc_id: str):
    sections = _load_json(doc_id, "sections")
    return {"document_id": doc_id, "total": len(sections), "sections": sections}

@app.get("/v1/documents/{doc_id}/sentences")
async def get_sentences(doc_id: str, section: str = None):
    sentences = _load_json(doc_id, "sentences")
    if section:
        sentences = [s for s in sentences if s.get("section_title") == section]
    return {"document_id": doc_id, "total": len(sentences), "sentences": sentences}

@app.get("/v1/documents/{doc_id}/candidates")
async def get_candidates(doc_id: str, min_score: float = 0.0):
    candidates = _load_json(doc_id, "candidates")
    if min_score > 0:
        candidates = [c for c in candidates if c.get("score", 0) >= min_score]
    return {"document_id": doc_id, "total": len(candidates), "candidates": candidates}

@app.get("/v1/documents/{doc_id}/chunks")
async def get_chunks(doc_id: str):
    chunks = _load_json(doc_id, "chunks")
    return {"document_id": doc_id, "total": len(chunks), "chunks": chunks}

@app.get("/v1/documents/{doc_id}/tables")
async def get_tables(doc_id: str):
    tables = _load_json(doc_id, "table_rows")
    return {"document_id": doc_id, "total": len(tables), "table_rows": tables}

@app.get("/v1/documents/{doc_id}/provenance")
async def get_provenance(doc_id: str):
    provenance = _load_json(doc_id, "provenance")
    return {"document_id": doc_id, "total": len(provenance), "provenance": provenance}

@app.get("/v1/documents")
async def list_documents():
    return {"documents": document_registry}


# ──────────────────────────────────────────────
# Week 3: Claim Extraction
# ──────────────────────────────────────────────

class ExtractRequest(BaseModel):
    document_id: str

@app.post("/v1/claims/extract")
async def extract_claims(req: ExtractRequest):
    """
    Run Week 3 extraction pipeline on a parsed document.
    Uses semantic chunks (text) + table rows (tables) as inputs.
    Returns structured AAMLT claims.
    """
    doc_id = req.document_id

    try:
        chunks = _load_json(doc_id, "chunks")
        table_rows = _load_json(doc_id, "table_rows")
    except HTTPException:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} not found. Upload and parse a PDF first."
        )

    # SOTA: prefer section-level extraction when parsed sentences are available
    # (full context, ~15x fewer LLM calls). Falls back to per-chunk otherwise.
    try:
        sentences = _load_json(doc_id, "sentences")
    except HTTPException:
        sentences = None

    pipeline = ExtractionPipeline()
    claims = pipeline.run(chunks=chunks, table_rows=table_rows, document_id=doc_id, sentences=sentences)
    pipeline.save(claims, str(PARSED_DIR), doc_id)

    claims_data = [c.model_dump() for c in claims]
    claims_registry[doc_id] = claims_data

    groundable = [c for c in claims if c.groundability_score >= 0.75]
    text_claims = [c for c in claims if c.source_type == "text"]
    table_claims = [c for c in claims if c.source_type == "table"]

    return {
        "document_id": doc_id,
        "total_claims": len(claims),
        "from_text": len(text_claims),
        "from_tables": len(table_claims),
        "groundable": len(groundable),
        "non_groundable": len(claims) - len(groundable),
        "claims": claims_data,
    }

_SB_CLAIM_COLS = (
    "claim_id,doc_id,report_id,company_name,page_number,chunk_id,source_sentence,"
    "aspect,normalized_aspect,metric_family,metric_key,metric_value,metric_unit,"
    "metric_direction,time_start,time_end,time_bucket,location_text,location_scope,"
    "claim_type,vagueness_score,groundability_score,observability_type,claim_signature"
)


def _fetch_claims_from_supabase(doc_id: str):
    """FIX (#8): the async ingest path writes claims only to Supabase, and some legacy
    disk artifacts are empty. Fall back to Supabase (the canonical store) keyed by
    doc_id or report_id. Returns [] if unavailable/none."""
    try:
        sb = _get_sb()
        res = (
            sb.table("claims")
            .select(_SB_CLAIM_COLS)
            .or_(f"doc_id.eq.{doc_id},report_id.eq.{doc_id}")
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"  [claims] Supabase fallback failed for {doc_id}: {e}")
        return []


@app.get("/v1/claims/{doc_id}")
async def get_claims(doc_id: str):
    """Get all extracted claims for a document (memory → disk → Supabase fallback)."""
    if doc_id in claims_registry and claims_registry[doc_id]:
        return {"document_id": doc_id, "total": len(claims_registry[doc_id]),
                "claims": claims_registry[doc_id], "source": "memory"}

    try:
        disk = _load_json(doc_id, "claims")
    except HTTPException:
        disk = None
    if disk:  # non-empty disk artifact
        return {"document_id": doc_id, "total": len(disk), "claims": disk, "source": "disk"}

    # FIX (#8): disk artifact empty/missing → fall back to the canonical Supabase store.
    sb_claims = _fetch_claims_from_supabase(doc_id)
    if sb_claims:
        return {"document_id": doc_id, "total": len(sb_claims), "claims": sb_claims, "source": "supabase"}

    raise HTTPException(status_code=404, detail=f"No claims found for {doc_id}.")


# ──────────────────────────────────────────────
# Production ingest: parse → extract → embed → Supabase (the write path the UI needs)
# ──────────────────────────────────────────────

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "company"


def _run_ingest(job_id: str, pdf_path: str, meta: dict, use_tables: bool):
    try:
        if use_tables:
            os.environ["USE_VLM_TABLES"] = "1"
        update_job(job_id, status="parsing")
        res = DocumentParsingPipeline(pdf_path).run(skip_tables=True)
        update_job(job_id, status="extracting", pages=res["triage"]["page_count"], sentences=len(res["sentences"]))
        pipe = ExtractionPipeline()
        claims = pipe.run(
            sentences=res["sentences"],
            pdf_path=pdf_path if use_tables else "",
            document_id=meta["report_id"],
            report_metadata=meta,
        )
        update_job(job_id, status="ingesting", extracted=len(claims))
        out = ingest_claims_to_db(claims, meta)
        update_job(job_id, status="done", inserted=out["inserted"], total=out["total"], doc_id=out["doc_id"])
    except PDFValidationError as e:
        update_job(job_id, status="error", error=f"Invalid PDF: {e}")
    except Exception as e:
        update_job(job_id, status="error", error=str(e))


@app.post("/v1/reports/ingest")
async def ingest_report(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    company_name: str = Form(...),
    report_year: int = Form(...),
    use_vlm_tables: bool = Form(False),
    user: dict = Depends(get_current_user),   # gated: ingest requires a logged-in user
):
    """
    Upload an ESG PDF → parse → extract → embed → write to Supabase (async).
    Returns a job_id; poll GET /v1/jobs/{job_id} for progress. This is the path
    that actually populates the dashboard.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    save_path = UPLOAD_DIR / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Content-hash dedup: if this exact PDF was already ingested, return the existing
    # report instead of spawning a job that would duplicate its claims (#2, idempotency).
    file_hash = sha256_file(str(save_path))
    existing = find_report_by_file_hash(file_hash)
    if existing:
        return {
            "status": "duplicate",
            "report_id": existing["report_id"],
            "file_hash": file_hash,
            "claim_count": existing.get("claim_count"),
            "ingested_at": existing.get("ingested_at"),
            "message": "This exact PDF was already ingested; returning the existing report.",
        }

    company_id = _slug(company_name)
    meta = {
        "report_id": f"{company_id}_{report_year}",
        "company_id": company_id,
        "company_name": company_name,
        "report_year": int(report_year),
        "file_hash": file_hash,
    }
    job_id = str(uuid.uuid4())[:8]
    create_job(job_id, {
        "job_id": job_id, "status": "queued",
        "report_id": meta["report_id"], "company_name": company_name, "report_year": int(report_year),
        "file_hash": file_hash,
    })
    background.add_task(_run_ingest, job_id, str(save_path), meta, bool(use_vlm_tables))
    return {"job_id": job_id, "status": "queued", "report_id": meta["report_id"]}


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    job = get_job_state(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/health")
async def health():
    """Liveness + readiness (B6). `ready` aggregates the checks an orchestrator
    (Docker healthcheck / Railway / Render) needs before routing traffic:
    DB reachable, upload disk headroom, embedding model importable. Each check is
    reported individually so a degradation is diagnosable, not just a red light."""
    checks = {}

    # Database connectivity (Supabase) — the one hard dependency.
    try:
        sb = _get_sb()
        sb.table("reports").select("report_id").limit(1).execute()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:120]}"

    # Disk headroom for uploads/parsed artifacts (fail under 500 MB free).
    try:
        free_mb = shutil.disk_usage(str(UPLOAD_DIR)).free // (1024 * 1024)
        checks["disk"] = "ok" if free_mb >= 500 else f"low: {free_mb}MB free"
        checks["disk_free_mb"] = free_mb
    except OSError as e:
        checks["disk"] = f"error: {e}"

    # Embedding model availability — import only (loading weights here would make
    # every probe pay a model spin-up; the NLI model is lazy-loaded by design).
    try:
        import sentence_transformers  # noqa: F401
        checks["embedding_model"] = "ok"
    except Exception as e:
        checks["embedding_model"] = f"error: {str(e)[:120]}"

    ready = (checks.get("database") == "ok"
             and checks.get("disk") == "ok"
             and checks.get("embedding_model") == "ok")
    return {"status": "ok" if ready else "degraded", "ready": ready,
            "service": "esgenuine-api", "version": app.version, "checks": checks}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
