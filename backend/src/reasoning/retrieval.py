"""
Pharos Integrity — Week 4: Semantic Retrieval & Bucketing
=========================================================
Retrieves historically extracted claims from the Supabase 
Vector Store that share the same metric family and have 
high semantic similarity to the target claim.
"""

import os
from typing import List, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

# -----------------------------
# CONFIG
# -----------------------------
load_dotenv()
SUPABASE_URL = os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")
EMBED_MODEL = "BAAI/bge-base-en-v1.5"

# Initialize singletons for performance
_model = None
_supabase = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
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

    # 3. Call the Supabase Match RPC function to perform pgVector search
    # Note: We need to create this RPC function in the database.
    try:
        response = supabase.rpc(
            'match_claims',
            {
                'query_embedding': query_embedding,
                'match_threshold': similarity_threshold,
                'match_count': 10,
                'filter_family': metric_family,
                'exclude_claim_id': query_id
            }
        ).execute()
        
        matches = response.data if response.data else []
        return matches
    except Exception as e:
        print(f"Error executing vector search RPC: {e}")
        return []

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
