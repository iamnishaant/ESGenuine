"""
ESGenuine — Week 4: Semantic Retrieval & Bucketing
=========================================================
Retrieves historically extracted claims from the Supabase 
Vector Store that share the same metric family and have 
high semantic similarity to the target claim.
"""

import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
# Service-role key when configured — it bypasses RLS and is REQUIRED for the write
# paths this client backs (claim_reviews upsert, contradictions delete+insert) once
# 2026-08-09_enable_rls.sql is applied, which demotes anon to SELECT-only. Falls back
# to the anon key so local dev / CI / read-only deploys keep working unchanged.
# NEVER expose SUPABASE_SERVICE_ROLE_KEY to the frontend — server-side only.
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY")
                or os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY"))
try:                                     # single source of truth for model + pinned revision
    from model_config import load_embedder
except ImportError:                      # path-setup fallback (repo root on sys.path)
    from src.model_config import load_embedder

class RetrievalError(RuntimeError):
    """The vector-search RPC failed. Raised (not swallowed) so callers can report the
    failure instead of a misleading '0 contradictions' — existing_issues #1: the old
    `except: return []` made semantic retrieval look like 'no conflicts found' whether
    the RPC was missing, the DB was down, or there genuinely were no matches."""


# Initialize singletons for performance
_model = None
_supabase = None

def get_model():
    global _model
    if _model is None:
        _model = load_embedder()          # pinned revision (model_config)
    return _model

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Missing SUPABASE credentials in .env")
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase

# -----------------------------
# SEMANTIC RETRIEVAL
# -----------------------------

def find_candidate_pairs(query_claim: Dict[Any, Any], similarity_threshold: float = 0.85) -> List[Dict[Any, Any]]:
    """
    Implements the Stanford Metric Signature Blocking trick.
    Only compares the query_claim against other claims in the database 
    that share the identical `metric_family`.
    """
    supabase = get_supabase()
    model = get_model()
    
    # 1. Generate embedding for query claim's source sentence
    source_sentence = query_claim.get("source_sentence", "")
    if not source_sentence:
        # Fallback to aspect if source_sentence is missing in test structures
        source_sentence = query_claim.get("aspect", "")
        
    query_embedding = model.encode(source_sentence).tolist()
    
    # 2. Extract the strict bucket ID (metric_family)
    metric_family = query_claim.get("metric_family")
    if not metric_family:
        metric_family = "uncategorized"
        
    query_id = query_claim.get("claim_id")

    # 3. Call the Supabase match_claims RPC (pgVector search). A transient connection
    #    drop ("Server disconnected") gets ONE reconnect+retry; any persistent failure
    #    (missing RPC, auth, DB down) raises RetrievalError so the caller surfaces it
    #    rather than silently reporting zero conflicts (existing_issues #1). Raising on
    #    the first claim also avoids the old behaviour of hammering a dead RPC once per
    #    claim (379 failing round-trips on a large report).
    global _supabase
    params = {
        'query_embedding': query_embedding,
        'match_threshold': similarity_threshold,
        'match_count': 10,
        'filter_family': metric_family,
        'exclude_claim_id': query_id,
    }
    for attempt in (1, 2):
        try:
            response = supabase.rpc('match_claims', params).execute()
            return response.data if response.data else []
        except Exception as e:
            msg = str(e).lower()
            transient = any(k in msg for k in ("disconnect", "timeout", "connection", "reset"))
            if transient and attempt == 1:
                _supabase = None                 # drop the dead client, reconnect once
                supabase = get_supabase()
                continue
            raise RetrievalError(f"match_claims RPC failed ({e})") from e

if __name__ == "__main__":
    # Test execution
    test_claim = {
        "claim_id": "test-query",
        "metric_family": "environment.emissions",
        "source_sentence": "We aim to reduce Scope 1 emissions by 40% globally by 2030."
    }
    
    print("Testing semantic retrieval...")
    results = find_candidate_pairs(test_claim, similarity_threshold=0.8)
    
    print(f"Found {len(results)} matches.")
    for res in results:
        print(f"  - [{res['similarity']:.3f}] {res['source_sentence']}")
