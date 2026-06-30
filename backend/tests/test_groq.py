import os
from dotenv import load_dotenv
load_dotenv()

import sys
from pathlib import Path
import json

import pytest

# Hits a live LLM provider (Groq/NVIDIA) over the network — deselected in CI via
# `-m "not live"`. Run locally with credentials present.
pytestmark = pytest.mark.live

backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from extractors.pipeline import ExtractionPipeline

def test_groq():
    print("API Key loaded:", "Yes" if os.environ.get("GROQ_API_KEY") else "No")
    
    # Load 5 chunks from the parsed output
    parsed_dir = Path(__file__).parent.parent / "ESG_Reports" / "test_output"
    with open(parsed_dir / "08dbf8224013_chunks.json", "r", encoding="utf-8") as f:
        all_chunks = json.load(f)
        
    test_chunks = all_chunks[:5]
    print(f"Testing on {len(test_chunks)} chunks using Groq...")
    
    pipeline = ExtractionPipeline()
    claims = pipeline.run(chunks=test_chunks, table_rows=[], document_id="test_doc")
    
    print(f"\nExtracted {len(claims)} claims:")
    for i, c in enumerate(claims):
        print(f"\nClaim {i+1}:")
        print(f"  Aspect: {c.aspect}")
        print(f"  Action: {c.action}")
        print(f"  Metric: {c.metric}")
        print(f"  Location: {c.location}")
        print(f"  Time: {c.time}")
        print(f"  Groundable Score: {c.groundability_score}")
        print(f"  Source: {c.provenance.source_sentence}")

if __name__ == "__main__":
    test_groq()
