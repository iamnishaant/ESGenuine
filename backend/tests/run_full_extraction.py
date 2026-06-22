import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from extractors.pipeline import ExtractionPipeline

def run_targeted_extraction():
    parsed_dir = Path(__file__).parent.parent / "ESG_Reports" / "test_output"
    doc_id = "08dbf8224013"
    
    with open(parsed_dir / f"{doc_id}_chunks.json", "r", encoding="utf-8") as f:
        all_chunks = json.load(f)
        
    # Process clumps of chunks that usually contain high-value environmental data in BRSR reports
    # (Pages 20-50 usually cover emissions, energy, etc.)
    test_chunks = all_chunks[30:70] 
    print(f"Loaded {len(test_chunks)} targeted chunks to extract rich ESG claims for the UI.")
    print("Using model: llama-3.1-8b-instant (Higher rate limits)")
    
    pipeline = ExtractionPipeline()
    t0 = time.time()
    
    # Run the pipeline
    claims = pipeline.run(chunks=test_chunks, table_rows=[], document_id=doc_id)
    
    # Save results
    pipeline.save(claims, str(parsed_dir), doc_id)
    
    t1 = time.time()
    print(f"\nExtraction complete in {t1 - t0:.1f}s")
    print(f"Extracted {len(claims)} claims.")
    
    # Verify we got some groundable claims
    groundable = [c for c in claims if c.groundability_score >= 0.5]
    print(f"Groundable claims for UI: {len(groundable)}")
    for c in groundable[:3]:
        print(f" - {c.aspect}: {c.metric.value if c.metric else 'N/A'} in {c.location.raw_text if c.location else 'N/A'}")

if __name__ == "__main__":
    run_targeted_extraction()
