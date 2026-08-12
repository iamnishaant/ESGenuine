"""Recall restricted to pages BOTH arms actually produced claims for.

A page that failed JSON parsing contributes zero recall to the arm that lost it, which
is a property of that run's luck with the endpoint, not of the model's extraction
quality. Reporting raw recall alone therefore penalises whichever arm had the worse
network night. This computes both:

  raw          - every cached page in the denominator (what run_baselines reports)
  page-matched - only pages where BOTH arms emitted at least one claim

The gap between them is the size of the failed-page confound.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, "backend/src")
sys.path.insert(0, "backend/scripts")
import run_recall as rr
from extractors.models import ExtractedClaim

FIX = Path("backend/tests/eval/fixtures")


def load(name):
    p = FIX / name
    if not p.exists():
        return None
    return [ExtractedClaim.model_validate(json.loads(l))
            for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def values_by_page(claims):
    out = {}
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        pg = c.provenance.page_number
        if pg is None:
            continue
        try:
            out.setdefault(pg, []).append(float(c.metric.value))
        except (TypeError, ValueError):
            pass
    return out


def recall(claims, pages, only=None):
    got = values_by_page(claims)
    total = hit = 0
    for pg, md in sorted(pages.items()):
        if only is not None and pg not in only:
            continue
        seen = set()
        for cell in rr._candidate_cells(md):
            if cell["is_form"]:
                continue
            key = (cell["row_label"].strip().lower(), cell["value"])
            if key in seen:
                continue
            seen.add(key)
            total += 1
            if any(rr._close(cell["value"], v) for v in got.get(pg, [])):
                hit += 1
    return hit, total, (hit / total if total else None)


def grounding(claims, pages, only=None):
    """L2: of the numeric values emitted, how many occur in that page's source markdown?"""
    from extractors.quality_gate import _value_in_source
    checked = ok = 0
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        pg = c.provenance.page_number
        if only is not None and pg not in only:
            continue
        md = pages.get(pg)
        if md is None:
            continue
        try:
            v = float(c.metric.value)
        except (TypeError, ValueError):
            continue
        checked += 1
        if _value_in_source(v, md):
            ok += 1
    return ok, checked, (ok / checked if checked else 0.0)


for case, cache in [("tata", "docling_tata.json"), ("shell", "docling_shell2022.json")]:
    pages = {e["page_number"]: e["markdown"]
             for e in json.loads((FIX / cache).read_text(encoding="utf-8"))}
    inc = load(f"baseline_incumbent_{case}.jsonl")
    fro = load(f"baseline_frontier_{case}.jsonl")
    print(f"=== {case}  cached pages={len(pages)}")
    if inc is None or fro is None:
        print(f"    incumbent={'present' if inc else 'ABSENT'}  frontier={'present' if fro else 'ABSENT'}\n")
        continue

    pi, pf = set(values_by_page(inc)), set(values_by_page(fro))
    both = pi & pf
    print(f"    pages with claims: incumbent={len(pi)}  frontier={len(pf)}  both={len(both)}")
    print(f"    incumbent-only pages: {sorted(pi - pf)}")
    print(f"    frontier-only  pages: {sorted(pf - pi)}")
    for name, claims in (("incumbent (llama-3.3-70b)", inc), ("frontier  (gpt-oss-120b)", fro)):
        h1, t1, r1 = recall(claims, pages)
        h2, t2, r2 = recall(claims, pages, only=both)
        g1 = grounding(claims, pages)
        g2 = grounding(claims, pages, only=both)
        print(f"    {name:<26} recall raw {h1:>4}/{t1:<4} = {100*r1:5.1f}%   "
              f"matched {h2:>4}/{t2:<4} = {100*r2:5.1f}%")
        print(f"    {'':<26} ground raw {g1[0]:>4}/{g1[1]:<4} = {100*g1[2]:5.1f}%   "
              f"matched {g2[0]:>4}/{g2[1]:<4} = {100*g2[2]:5.1f}%   claims={len(claims)}")
    print()
