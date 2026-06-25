"""
ESGenuine — Week 4: Postgres Vector Ingestion
====================================================
Validates, embeds, and batch-inserts extracted JSON claims
into the partitioned PostgreSQL Vector Store.
"""

import json
import uuid
import psycopg2
from pathlib import Path
from sentence_transformers import SentenceTransformer

# -----------------------------
# CONFIG
# -----------------------------

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")

# Resolve relative to this file (backend/src/extractors/ -> backend/parsed/) for portability.
CLAIMS_FILE = Path(__file__).resolve().parents[2] / "parsed" / "08dbf8224013_claims.json"
EMBED_MODEL = "BAAI/bge-base-en-v1.5"


def clean_date(value):
    """Return a valid ISO date string (YYYY-MM-DD) or None.

    Postgres DATE columns reject the literal string "null", empty strings, and
    malformed values — previously this caused entire batch inserts to fail with
    'invalid input syntax for type date: "null"'. Year-only values are normalized
    to Jan 1 of that year.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "nan"):
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None

# -----------------------------
# CLAIM VALIDATION (Defensive Filtering)
# -----------------------------

def validate_claim(claim):
    """Filters out vague or incomplete claims before they reach the reasoning engine."""
    if claim.get("vagueness_score", 1.0) >= 0.4:
        print(f"  [Reject] Vagueness Score too high: {claim.get('vagueness_score')}")
        return None

    metric = claim.get("metric", {})
    if not metric:
        print("  [Reject] Missing metric block entirely.")
        return None
        
    unit_val = metric.get("unit")
    if not unit_val or str(unit_val).lower() in ("unspecified", "none", "null"):
        print("  [Reject] Metric unit is unspecified or null.")
        return None

    if metric.get("value") is None:
        print("  [Reject] Metric value is missing.")
        return None

    import re
    source = claim.get("provenance", {}).get("source_sentence", "")
    
    # 3-Signal Garbage Filter for unstructured table dumps
    numbers = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', source)
    
    # Signal 1: too many numbers
    if len(numbers) > 6:
        print(f"  [Reject] Source sentence has too many numbers ({len(numbers)}).")
        return None

    # Signal 2: high density of numbers vs words
    tokens = source.split()
    if tokens and (len(numbers) / max(len(tokens), 1)) > 0.5:
        print("  [Reject] Number density is too high (likely table row).")
        return None

    # Signal 3: lack of verbs (table rows usually lack action verbs)
    if not re.search(r"(increase|reduce|decrease|maintain|achieve|improve|drop|fall|rise)", source, re.IGNORECASE):
        print("  [Reject] Source sentence lacks action verbs (likely table row).")
        return None

    return claim

# -----------------------------
# LOAD CLAIMS
# -----------------------------

def load_claims():
    with open(CLAIMS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data)} total claims from JSON.")
    return data

# -----------------------------
# BATCH INSERT
# -----------------------------

def insert_batch(supabase: Client, rows: list):
    try:
        response = supabase.table("claims").insert(rows).execute()
        return len(response.data) if response.data else 0
    except Exception as e:
        print(f"Failed to insert batch: {e}")
        return 0

# -----------------------------
# MAIN PIPELINE
# -----------------------------

def ingest_claims(report_metadata: dict = None):
    """
    Full ingestion pipeline.
    
    Args:
        report_metadata: Optional cross-report info:
            {
                "company_id": "tata_steel",
                "company_name": "Tata Steel",
                "report_year": 2024,
                "report_id": "tata_steel_2024"
            }
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing SUPABASE credentials in .env")
        return

    print(f"Loading embedding model: {EMBED_MODEL} ...")
    model = SentenceTransformer(EMBED_MODEL)

    print(f"Connecting to Supabase at {SUPABASE_URL}...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    claims = load_claims()

    # FIX (#3): doc_id must be a stable DOCUMENT id, not a per-chunk id. Prefer the
    # report_id from metadata; fall back to the claims filename stem. Previously this
    # was prob["chunk_id"][:12], which scattered one document across many "doc_ids"
    # and made document-level reasoning impossible.
    doc_id = (report_metadata or {}).get("report_id") or CLAIMS_FILE.stem.replace("_claims", "")

    batch = []
    inserted_count = 0
    rejected_count = 0

    print("Beginning ingestion loop...")
    for c in claims:
        # Pass the claim dict through validation
        claim = validate_claim(c)
        if claim is None:
            rejected_count += 1
            continue

        # Extract nested structures for the flat SQL table
        prob = claim.get("provenance", {})
        met = claim.get("metric", {})
        time = claim.get("time", {})
        loc = claim.get("location", {})

        src_sentence = prob.get("source_sentence", "Unknown source sentence")
        
        # Postgres requires the vector to be a list
        embedding = model.encode(src_sentence).tolist()

        row = {
            "claim_id": str(uuid.uuid4()),
            "doc_id": doc_id,  # FIX (#3): real document id, not per-chunk id
            "page_number": prob.get("page_number", 0),
            "chunk_id": prob.get("chunk_id", ""),
            "source_sentence": src_sentence,

            "aspect": claim.get("aspect"),
            "normalized_aspect": claim.get("normalized_aspect"),
            "metric_family": claim.get("metric_family") or ('.'.join(claim.get("normalized_aspect").split('.')[:2]) if claim.get("normalized_aspect") and '.' in claim.get("normalized_aspect") else "uncategorized"),
            "metric_key": claim.get("metric_key"),

            "metric_value": met.get("value"),
            "metric_unit": met.get("unit"),
            "metric_direction": met.get("direction"),

            "time_start": clean_date(time.get("start_date")),
            "time_end": clean_date(time.get("end_date")),
            "time_bucket": claim.get("time_bucket"),

            "location_text": (lambda s: None if s is None or str(s).strip().lower() in ("", "null", "none", "nan", "n/a") else str(s).strip())(loc.get("raw_text") if loc else None),  # FIX (#9): no junk strings
            "location_scope": claim.get("location_scope") or 'Global',

            "claim_type": claim.get("claim_type"),
            "vagueness_score": claim.get("vagueness_score"),
            "groundability_score": claim.get("groundability_score"),

            "claim_signature": claim.get("claim_signature"),
            "embedding": embedding,

            # Phase 3: Cross-report columns
            "company_id":   (report_metadata or {}).get("company_id"),
            "company_name": (report_metadata or {}).get("company_name"),
            "report_year":  (report_metadata or {}).get("report_year"),
            "report_id":    (report_metadata or {}).get("report_id"),
        }

        batch.append(row)

        if len(batch) >= 50: # Slightly smaller batch for REST API 
            inserted = insert_batch(supabase, batch)
            inserted_count += inserted
            batch.clear()

    # Flush remaining
    if batch:
        inserted = insert_batch(supabase, batch)
        inserted_count += inserted

    print("\n=====================================")
    print("Ingestion Complete!")
    print(f"  Total Inserted: {inserted_count}")
    print(f"  Total Rejected: {rejected_count}")
    print("=====================================")

if __name__ == "__main__":
    ingest_claims()
