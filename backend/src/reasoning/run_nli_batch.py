"""
ESGenuine — Semantic Vector Reasoner
===========================================
Replaces O(N^2) brute-force reasoning with an O(1) semantic neighborhood search.
Uses pgvector (HNSW) to find the Top 3 most semantically identical claims
across the dataset, and evaluates only those highly-linked pairs using NLI.
"""
import os
import uuid
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

from nli_engine import ContradictionEngine

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# No default — see backend/scripts/audit_pharos_db.py.
CONN_STR = os.environ["DATABASE_URL"]

def run_semantic_nli():
    engine = ContradictionEngine()
    
    print("Connecting to Supabase (Vector Search Reasoner)...")
    conn = psycopg2.connect(CONN_STR)
    cur = conn.cursor()
    
    # 1. Fetch all root claims
    cur.execute("""
        SELECT 
            claim_id, normalized_aspect, metric_value, metric_unit, metric_direction,
            time_bucket, location_scope, source_sentence, company_name, report_year, embedding
        FROM claims
        WHERE metric_value IS NOT NULL AND embedding IS NOT NULL;
    """)
    root_claims = cur.fetchall()
    print(f"Loaded {len(root_claims)} claims for neighborhood evaluation.")
    
    contradictions_found = list()
    evaluated_pairs = set() # Avoid evaluating A->B and B->A
    
    for r in root_claims:
        c1 = {
            "claim_id": r[0], "normalized_aspect": r[1], "metric_value": r[2],
            "metric_unit": r[3], "metric_direction": r[4], "time_bucket": r[5],
            "location_scope": r[6], "source_sentence": r[7], "company_name": r[8],
            "report_year": r[9]
        }
        embedding_str = str(r[10]) # For pgvector binding
        
        # 2. Retrieve Top-3 nearest neighbors from the entire database
        # distance filter at 0.15 gives us similarity > 85%
        cur.execute("""
            SELECT 
                claim_id, normalized_aspect, metric_value, metric_unit, metric_direction,
                time_bucket, location_scope, source_sentence, company_name, report_year,
                (embedding <=> %s::vector) as distance
            FROM claims
            WHERE claim_id != %s
              AND (embedding <=> %s::vector) < 0.15
              AND normalized_aspect = %s
            ORDER BY embedding <=> %s::vector
            LIMIT 3;
        """, (embedding_str, c1["claim_id"], embedding_str, c1["normalized_aspect"], embedding_str))
        
        neighbors = cur.fetchall()
        
        for n in neighbors:
            c2 = {
                "claim_id": n[0], "normalized_aspect": n[1], "metric_value": n[2],
                "metric_unit": n[3], "metric_direction": n[4], "time_bucket": n[5],
                "location_scope": n[6], "source_sentence": n[7], "company_name": n[8],
                "report_year": n[9]
            }
            distance = n[10]
            
            # Prevent reverse evaluation
            pair_key = frozenset([c1["claim_id"], c2["claim_id"]])
            if pair_key in evaluated_pairs:
                continue
            evaluated_pairs.add(pair_key)
            
            # Exact identical strings are meaningless to test internally
            if c1["source_sentence"] == c2["source_sentence"]:
                continue
                
            # 3. Vector matched! Pass to the logical engine.
            result = engine.evaluate_pair(c1, c2)
            
            if result.get("has_contradiction"):
                contradictions_found.append({
                    "claim_a_id": c1["claim_id"],
                    "claim_b_id": c2["claim_id"],
                    "severity": result["severity"],
                    "conflict_type": result["conflict_type"],
                    "reasoning": result["reasoning"],
                    "confidence": result["nli_data"]["confidence"] if "nli_data" in result else 0.99
                })

    if contradictions_found:
        print(f"\n[ALERT] Found {len(contradictions_found)} live logical contradictions!")
        print("Saving to database...")
        for conf in contradictions_found:
            cur.execute("""
                INSERT INTO contradictions (claim_a_id, claim_b_id, severity, conflict_type, reasoning, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                conf["claim_a_id"], conf["claim_b_id"], conf["severity"], 
                conf["conflict_type"], conf["reasoning"], conf["confidence"]
            ))
        conn.commit()
    else:
        print("\n[OK] Safe Dataset! No contradictions detected in semantic neighborhood matches.")
        
    cur.close()
    conn.close()
    print("Semantic NLI Reasoner run complete.")

if __name__ == "__main__":
    run_semantic_nli()
