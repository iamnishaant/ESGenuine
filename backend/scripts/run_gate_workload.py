"""How much work does the repair layer FIND TO DO on each model's output?

The 2x2's L1/L2 lanes report the layer as zero at both tiers. That is not because the
layer is idle - it is because those lanes read only metric.value and page_number, so
they can see the layer solely where it ADDS, REMOVES or REWRITES a claim. Aspect, type
and unit corrections are invisible to them, and the gold lane cannot compare models
(match rates of 2% and 0%).

This measures the one thing that IS mechanically comparable across models: the RATE at
which the deterministic gate intervenes. It counts claims the gate modifies, by flag.

IMPORTANT: an intervention is not evidence of an improvement. This says how much the
layer finds wrong, not how much it gets right. But the rate is model-independent and
therefore a fair cross-model comparison, which is exactly what the L3 gold lane is not.
"""
import collections, copy, json, sys
from pathlib import Path

sys.path.insert(0, "backend/src")
sys.path.insert(0, "backend/scripts")
from extractors.models import ExtractedClaim
from extractors.ontology import ESGOntology
from extractors.quality_gate import apply_gate, is_furniture, _refresh_keys

FIX = Path("backend/tests/eval/fixtures")


def load(name):
    p = FIX / name
    if not p.exists():
        return None
    return [ExtractedClaim.model_validate(json.loads(l))
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def workload(claims):
    """Replay S1..S5 and record what the gate changed. Mirrors run_ablation's stages."""
    cs = copy.deepcopy(claims)
    for c in cs:
        c.quality_flags, c.framework_tags = [], []
        c.normalized_aspect = c.aspect
    before_aspect = [c.normalized_aspect for c in cs]
    before_type = [c.claim_type for c in cs]

    for c in cs:                                   # S1 taxonomy
        c.normalized_aspect = ESGOntology.normalize_aspect(c.aspect)
        _refresh_keys(c)
    after_s1 = [c.normalized_aspect for c in cs]

    for c in cs:                                   # S4 gate
        apply_gate(c)

    flags = collections.Counter(f for c in cs for f in (c.quality_flags or []))
    aspect_changed = sum(1 for a, c in zip(after_s1, cs) if c.normalized_aspect != a)
    type_changed = sum(1 for t, c in zip(before_type, cs) if c.claim_type != t)
    mapped = sum(1 for b, a in zip(before_aspect, after_s1) if a != b and a != "uncategorized")
    uncat = sum(1 for c in cs if (c.normalized_aspect or "") == "uncategorized")
    dropped = sum(1 for c in cs if is_furniture(c))               # S5
    touched = sum(1 for c in cs if c.quality_flags)
    n = len(cs) or 1
    return {
        "n": len(cs), "mapped_to_taxonomy": mapped, "uncategorized_after": uncat,
        "gate_aspect_changed": aspect_changed, "gate_type_changed": type_changed,
        "furniture_dropped": dropped, "claims_flagged": touched,
        "flag_rate": touched / n, "flags": flags,
    }


for case in ("tata", "shell"):
    print(f"=== {case}")
    for label, name in (("incumbent llama-3.3-70b", f"baseline_incumbent_{case}.jsonl"),
                        ("frontier  gpt-oss-120b ", f"baseline_frontier_{case}.jsonl")):
        cl = load(name)
        if cl is None:
            print(f"    {label}  (absent)")
            continue
        w = workload(cl)
        print(f"    {label}  n={w['n']}")
        print(f"        mapped to a taxonomy node : {w['mapped_to_taxonomy']:>4} "
              f"({100*w['mapped_to_taxonomy']/w['n']:.1f}%)   still uncategorized: {w['uncategorized_after']}")
        print(f"        gate CHANGED aspect       : {w['gate_aspect_changed']:>4} "
              f"({100*w['gate_aspect_changed']/w['n']:.1f}%)")
        print(f"        gate CHANGED claim_type   : {w['gate_type_changed']:>4} "
              f"({100*w['gate_type_changed']/w['n']:.1f}%)")
        print(f"        dropped as furniture      : {w['furniture_dropped']:>4} "
              f"({100*w['furniture_dropped']/w['n']:.1f}%)")
        print(f"        claims carrying any flag  : {w['claims_flagged']:>4} "
              f"({100*w['flag_rate']:.1f}%)")
        print(f"        flags: {dict(w['flags'])}")
    print()
