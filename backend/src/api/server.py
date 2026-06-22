"""
Pharos Integrity — FastAPI Server (Week 2 + 3)
===============================================
Serves:
  Week 2: 8-step document parsing pipeline
  Week 3: Claim extraction (text + table dual pipeline)
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import json
import shutil
import uvicorn

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.pdf_parser import DocumentParsingPipeline, PDFValidationError
from extractors.pipeline import ExtractionPipeline
from reasoning.api_reasoning import router as reasoning_router

app = FastAPI(
    title="Pharos Integrity API",
    version="4.0.0",
    description="ESG Report Parsing & Claim Extraction — Weeks 2+3+4",
)

app.include_router(reasoning_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
PARSED_DIR = Path(__file__).parent.parent.parent / "parsed"
UPLOAD_DIR.mkdir(exist_ok=True)
PARSED_DIR.mkdir(exist_ok=True)

document_registry: dict = {}
for path in PARSED_DIR.glob("*_full.json"):
    doc_id = path.name.replace("_full.json", "")
    # Minimal info since we only have the JSONs
    document_registry[doc_id] = {
        "filename": f"Discovered: {doc_id}",
        "status": "ready"
    }
print(f"  [Startup] Discovered {len(document_registry)} documents on disk.")

claims_registry: dict = {}


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
    return {"document_id": doc_id, "sections": _load_json(doc_id, "sections")}

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

    pipeline = ExtractionPipeline()
    claims = pipeline.run(chunks=chunks, table_rows=table_rows, document_id=doc_id)
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

@app.get("/v1/claims/{doc_id}")
async def get_claims(doc_id: str):
    """Get all extracted claims for a document."""
    if doc_id in claims_registry:
        claims = claims_registry[doc_id]
    else:
        try:
            claims = _load_json(doc_id, "claims")
        except HTTPException:
            raise HTTPException(status_code=404, detail=f"No claims found for {doc_id}.")
    return {"document_id": doc_id, "total": len(claims), "claims": claims}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pharos-integrity-api", "version": "3.0.0"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
