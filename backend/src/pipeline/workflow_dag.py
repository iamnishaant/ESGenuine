"""
Pharos Integrity — Pipeline DAG (Production)
=============================================

Full pipeline flow:

  PDF
   ↓ Layout parsing
   ↓ Sentence segmentation
   ↓ Claim extraction
   ↓ Claim graph construction    ← NEW: builds contradiction edges
   ↓ CVE scoring
   ↓ Evidence gate
   ↓ Geospatial resolution
   ↓ Satellite fetch
   ↓ Vision analysis
   ↓ Integrity scoring
"""

from typing import Dict, List, Any, TypedDict
from langgraph.graph import StateGraph, START, END


class PipelineState(TypedDict):
    document_id: str
    raw_text: str
    blocks: List[Dict[str, Any]]
    sentences: List[Dict[str, Any]]
    claims: List[Dict[str, Any]]
    claim_graph: Dict[str, Any]  # nodes + edges for contradiction detection
    cve_scores: Dict[str, float]
    observability_types: Dict[str, str]
    satellite_evidence: Dict[str, Any]
    integrity_scores: Dict[str, float]
    audit_trail: List[Dict[str, Any]]
    errors: List[str]


# ── Step Nodes ──

def parse_document(state: PipelineState) -> PipelineState:
    """Step 1-2: PDF structural extraction + layout classification."""
    print(f"[1] Parsing document {state['document_id']}...")
    state["blocks"] = [
        {"block_id": "p1_b0", "type": "heading", "text": "Environmental Performance"},
        {"block_id": "p1_b1", "type": "paragraph", "text": "We reduced emissions by 40% at our Pune facility between 2021 and 2023."},
        {"block_id": "p2_b0", "type": "paragraph", "text": "Total emissions increased from 50,000 to 70,000 tonnes CO2e."},
        {"block_id": "p3_b0", "type": "paragraph", "text": "We planted 10,000 trees in Rajasthan under our conservation programme."},
    ]
    state["audit_trail"].append({"step": "parse", "status": "success", "blocks": len(state["blocks"])})
    return state


def segment_sentences(state: PipelineState) -> PipelineState:
    """Step 3-4: Section hierarchy + sentence segmentation."""
    print("[2] Segmenting sentences...")
    state["sentences"] = [
        {"sentence_id": "s1", "text": b["text"], "block_id": b["block_id"]}
        for b in state["blocks"] if b["type"] == "paragraph"
    ]
    state["audit_trail"].append({"step": "segment", "status": "success", "sentences": len(state["sentences"])})
    return state


def extract_claims(state: PipelineState) -> PipelineState:
    """Step 5: LLM-based AAMLT extraction."""
    print("[3] Extracting claims...")
    if not state.get("sentences"):
        state["errors"].append("No sentences to extract from.")
        return state

    state["claims"] = [
        {"id": "clm-1", "text": "Reduced emissions by 40%", "aspect": "emissions",
         "location": {"raw_text": "Pune facility", "specificity": "facility"},
         "observability_type": "not_observable"},
        {"id": "clm-2", "text": "Emissions increased from 50k to 70k tonnes",
         "aspect": "emissions", "observability_type": "not_observable"},
        {"id": "clm-3", "text": "Planted 10,000 trees in Rajasthan",
         "aspect": "reforestation",
         "location": {"raw_text": "Rajasthan", "specificity": "region"},
         "observability_type": "optical_possible"},
    ]
    state["audit_trail"].append({"step": "extract", "status": "success", "claims": len(state["claims"])})
    return state


def build_claim_graph(state: PipelineState) -> PipelineState:
    """Step 6: Build claim contradiction graph."""
    print("[4] Building claim graph...")
    if state["errors"]:
        return state

    # Detect contradiction: clm-1 says "reduced 40%" but clm-2 says "increased"
    state["claim_graph"] = {
        "nodes": [c["id"] for c in state["claims"]],
        "edges": [
            {
                "source": "clm-1", "target": "clm-2",
                "edge_type": "contradicts",
                "severity": 0.9,
                "reason": "clm-1 claims reduction, clm-2 shows increase"
            }
        ]
    }
    state["audit_trail"].append({"step": "claim_graph", "status": "success",
                                  "edges": len(state["claim_graph"]["edges"])})
    return state


def compute_cve(state: PipelineState) -> PipelineState:
    """Step 7: CVE scoring with observability type."""
    print("[5] Computing CVE scores...")
    if state["errors"]:
        return state

    state["cve_scores"] = {
        "clm-1": 0.35,  # No satellite for emissions
        "clm-2": 0.25,  # No satellite for emissions
        "clm-3": 0.825  # Reforestation in Rajasthan, observable
    }
    state["observability_types"] = {
        "clm-1": "not_observable",
        "clm-2": "not_observable",
        "clm-3": "optical_possible",
    }
    state["audit_trail"].append({"step": "cve", "status": "success"})
    return state


def fetch_satellite(state: PipelineState) -> PipelineState:
    """Step 8-9: Evidence gate → satellite fetch for high-CVE optical claims."""
    print("[6] Fetching satellite evidence for eligible claims...")
    state["satellite_evidence"] = {
        "clm-3": {"ndvi_delta_zscore": -1.5, "quality": "valid", "cloud_cover": 0.12}
    }
    state["audit_trail"].append({"step": "satellite", "status": "success"})
    return state


def compute_integrity(state: PipelineState) -> PipelineState:
    """Step 10: Integrity Gap scoring with uncertainty."""
    print("[7] Computing Integrity Gap scores...")
    if state["errors"]:
        print(f"  Errors encountered: {state['errors']}")
        return state

    state["integrity_scores"] = {
        "clm-1": 0.72,  # High gap: contradicted by clm-2
        "clm-2": 0.68,  # High gap: contradicts clm-1
        "clm-3": 0.55,  # Moderate: NDVI shows some decline
    }
    state["audit_trail"].append({"step": "integrity", "status": "success"})
    return state


# ── Routing ──

def route_after_cve(state: PipelineState) -> str:
    if state["errors"]:
        return "compute_integrity"
    has_observable = any(
        state["cve_scores"].get(c["id"], 0) >= 0.6
        and state["observability_types"].get(c["id"]) == "optical_possible"
        for c in state["claims"]
    )
    return "fetch_satellite" if has_observable else "compute_integrity"


# ── Build Graph ──

builder = StateGraph(PipelineState)

builder.add_node("parse", parse_document)
builder.add_node("segment", segment_sentences)
builder.add_node("extract", extract_claims)
builder.add_node("claim_graph", build_claim_graph)
builder.add_node("cve", compute_cve)
builder.add_node("satellite", fetch_satellite)
builder.add_node("score", compute_integrity)

builder.add_edge(START, "parse")
builder.add_edge("parse", "segment")
builder.add_edge("segment", "extract")
builder.add_edge("extract", "claim_graph")
builder.add_edge("claim_graph", "cve")
builder.add_conditional_edges("cve", route_after_cve, {
    "fetch_satellite": "satellite",
    "compute_integrity": "score",
})
builder.add_edge("satellite", "score")
builder.add_edge("score", END)

pipeline_dag = builder.compile()


# ── CLI ──

if __name__ == "__main__":
    print("=" * 60)
    print("PHAROS INTEGRITY — Pipeline Integration Dry Run")
    print("=" * 60)

    result = pipeline_dag.invoke({
        "document_id": "doc-mock-tata-2024",
        "raw_text": "",
        "blocks": [],
        "sentences": [],
        "claims": [],
        "claim_graph": {},
        "cve_scores": {},
        "observability_types": {},
        "satellite_evidence": {},
        "integrity_scores": {},
        "audit_trail": [],
        "errors": [],
    })

    print("\n" + "=" * 60)
    print("Pipeline Complete ✓")
    print(f"  Claims found: {len(result['claims'])}")
    print(f"  Contradictions: {len(result['claim_graph'].get('edges', []))}")
    print(f"  Integrity Scores: {result['integrity_scores']}")
    print(f"  Audit Trail: {len(result['audit_trail'])} events")
    print("=" * 60)
