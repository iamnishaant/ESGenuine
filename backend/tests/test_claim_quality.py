import json
import sys
from collections import Counter
from pathlib import Path

# Resolve relative to this file (backend/tests/ -> backend/parsed/) for portability.
JSON_PATH = Path(__file__).resolve().parents[1] / "parsed" / "08dbf8224013_claims.json"

def run_tests():
    print(f"Loading claims from {JSON_PATH}...")
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            claims = json.load(f)
    except Exception as e:
        print(f"FAILED to load JSON: {e}")
        sys.exit(1)

    print(f"\nTotal claims extracted: {len(claims)}\n")

    # 1. Count Groundable Claims (Score >= 0.5 and >= 0.75)
    highly_groundable = sum(1 for c in claims if c.get("groundability_score", 0) >= 0.75)
    moderately_groundable = sum(1 for c in claims if 0.5 <= c.get("groundability_score", 0) < 0.75)
    print(f"Groundability >= 0.75: {highly_groundable}")
    print(f"Groundability >= 0.50: {moderately_groundable}\n")

    # 2. Check Metrics and Greenwashing Signals
    metric_count = sum(1 for c in claims if c.get("metric") and c["metric"].get("value") is not None)
    print(f"Claims with a valid Metric: {metric_count}/{len(claims)}")
    for c in claims:
        if c.get("metric") and c["metric"].get("value"):
            print(f"  - [{c.get('normalized_aspect', c['aspect'])}] {c['action']} {c['metric']['value']} {c['metric']['unit']} (Direction: {c['metric']['direction']})")
            print(f"      ↳ Type: {c.get('claim_type', 'performance').upper()} | Vagueness: {c.get('vagueness_score', 0.0)}")
            print(f"      ↳ Block Hash: {c.get('claim_signature', 'MISSING')}")
    # 3. Check Geography
    specific_locations = []
    global_locations = []
    
    for c in claims:
        loc = c.get("location")
        if loc and loc.get("raw_text"):
            if loc.get("specificity") in ["facility", "city", "region", "country"]:
                specific_locations.append(f"{loc['raw_text']} ({loc['specificity']})")
            else:
                global_locations.append(f"{loc['raw_text']} ({loc.get('specificity', 'global')})")
                
    print(f"\nClaims with Specific Geographies (facility, city, region, country): {len(specific_locations)}")
    for sl in specific_locations:
        print(f"  - {sl}")
        
    print(f"Claims with Global/General locations: {len(global_locations)}")

    # 4. Check Time
    time_count = sum(1 for c in claims if c.get("time") and (c["time"].get("start_date") or c["time"].get("end_date")))
    print(f"\nClaims with a Timeframe: {time_count}/{len(claims)}")
    for c in claims:
        if c.get("time") and (c["time"].get("start_date") or c["time"].get("end_date")):
            t = c["time"]
            print(f"  - {t.get('start_date')} to {t.get('end_date')}")

    # 5. Assertions
    print("\n--- Running Assertions ---")
    
    try:
        assert len(claims) > 0, "No claims were extracted"
        assert metric_count > 0, "No metrics successfully extracted"
        # We don't guarantee specific locations in this small chunk set, but let's check if the fields exist.
        assert time_count > 0, "No timeframes extracted"
        print("ALL TESTS PASSED! ✅")
    except AssertionError as e:
        print(f"TEST FAILED ❌: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
