import os
import uuid
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# Load environment from the project root (backend/scripts/ -> project root).
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

URL = os.getenv("VITE_SUPABASE_URL")
KEY = os.getenv("VITE_SUPABASE_PUBLISHABLE_KEY")

if not URL or not KEY:
    print("Error: Supabase credentials missing.")
    exit(1)

supabase = create_client(URL, KEY)

def test_db():
    print(f"Testing Supabase connection to: {URL}")
    
    # Generate a dummy 768-dim vector (BAAI/BGE-base size)
    dummy_vector = np.random.uniform(-1, 1, 768).tolist()
    
    # Test Entry 1: Known Partition (Environment)
    test_entry_1 = {
        "claim_id": str(uuid.uuid4()),
        "metric_family": "environment.emissions", # Targeted partition
        "source_sentence": "This is a test claim for the environment partition.",
        "metric_value": 100.5,
        "metric_unit": "tons",
        "time_start": "2024-01-01",
        "time_end": "2024-12-31",
        "embedding": dummy_vector,
        "company_id": "test_corp",
        "report_year": 2024
    }
    
    # Test Entry 2: Default Partition (Catch-all)
    test_entry_2 = {
        "claim_id": str(uuid.uuid4()),
        "metric_family": "unknown.special_metric", # Triggers DEFAULT partition
        "source_sentence": "This is a test claim for the default catch-all partition.",
        "metric_value": 0.99,
        "metric_unit": "ratio",
        "time_start": None, # Testing null/None handling
        "time_end": None,
        "embedding": dummy_vector,
        "company_id": "test_corp",
        "report_year": 2024
    }

    print("\nAttempting to insert into specific partition...")
    try:
        res1 = supabase.table("claims").insert(test_entry_1).execute()
        print("✅ Entry 1 (Environment) inserted successfully.")
    except Exception as e:
        print(f"❌ Entry 1 FAILED: {e}")

    print("\nAttempting to insert into DEFAULT partition...")
    try:
        res2 = supabase.table("claims").insert(test_entry_2).execute()
        print("✅ Entry 2 (Default Catch-all) inserted successfully.")
    except Exception as e:
        print(f"❌ Entry 2 FAILED: {e}")

    # Cleanup — this test writes to the LIVE DB, so it MUST remove its own sentinels.
    # Without this, the two 'test_corp' rows leak into the corpus and show up as a bogus
    # 2-claim "test_corp" company (grade A/100) in the portfolio after every test run.
    supabase.table("claims").delete().eq("company_id", "test_corp").execute()
    print("\nTest entries cleaned up.")

if __name__ == "__main__":
    test_db()
