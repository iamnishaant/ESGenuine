"""
ESGenuine — table-cell RECALL harness (roadmap Phase 6.1)
=========================================================

Closes the single biggest methodological hole in the project's evaluation.

THE PROBLEM
-----------
`run_evaluation.py` computes EXTRACTION_SCORE from five precision-family rates and
has no recall term. That is not an oversight that a formula fixes — it is structural:
every gold set is built by *sampling claims the extractor already emitted*
(`_meta.source_extraction` points at a JSONL of output), so a claim the system MISSED
is invisible to it. A system that emitted one perfect claim and dropped the other 372
would score ~100.

THE APPROACH
------------
For TABLE data we do not need human annotation to get a denominator. Docling already
returns each page as GFM markdown with row labels and column headers intact, so the
set of numeric facts on a page is mechanically enumerable:

    (row_label, column_header, value)   for every numeric cell

We then ask: of those ground-truth cells, how many did the pipeline actually emit as a
claim on that page? That is a real, reproducible recall number, computed with zero LLM
cost, over exactly the surface Docling was adopted to fix.

WHAT THIS IS AND IS NOT
-----------------------
IS:     recall over numeric TABLE cells — the half of the corpus where the Docling
        table-parsing contribution lives, measured objectively.
IS NOT: full-document claim recall. Narrative/text claims ("we aim to be net zero by
        2040") cannot be enumerated mechanically and still need human annotation —
        that remains open (Phase 6.1b).

CONSERVATIVE BY CONSTRUCTION: not every numeric cell is an ESG claim (some are counts
of offices, index numbers, footnote markers). Those inflate the denominator, so the
TRUE recall is at least what this reports. We prefer a defensible lower bound to a
hand-tuned denominator — a reviewer can audit the cell filter in `_candidate_cells`.

Run:
    python backend/scripts/run_recall.py
    python backend/scripts/run_recall.py --misses 25     # show what was missed
    python backend/scripts/run_recall.py --json out.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))

from extractors.models import ExtractedClaim                       # noqa: E402

_FIX = _REPO / "backend" / "tests" / "eval" / "fixtures"

# (label, fixture jsonl, docling cache, coverage)
#
# `coverage` matters enormously for interpretation. The Docling caches were built for
# different purposes: Tata's covers essentially the whole BRSR (pages 2-42 contiguous),
# so its denominator approximates every table in the document. Shell's covers only 5
# TARGETED pages (2, 33, 34, 73, 81) captured for spot-checks — so a Shell recall figure
# describes those pages, NOT the 91-page report. Quoting it as document-level recall
# would be wrong in both directions (the sample is small and deliberately table-dense).
CASES = [
    ("Tata Power BRSR FY24", "tata_docling_full.jsonl", "docling_tata.json",
     "near-full document (40 pages cached, 2-42 contiguous) — treat as document-level"),
    ("Shell SR2022", "shell_2022_raw.jsonl", "docling_shell2022.json",
     "PARTIAL: 5 targeted pages only — NOT document-level, do not quote as such"),
]

# A cell value is only comparable if it parses as a number. Strip thousands
# separators, currency/percent decoration and footnote markers.
_NUM = re.compile(r"^[^\d\-+]*([-+]?\d[\d,]*\.?\d*)\s*[%a-zA-Z°/³²]*\s*[*†‡]?$")
# Row labels must look like prose, not a stray marker — at least 3 letters.
_HAS_WORD = re.compile(r"[A-Za-z]{3,}")
# Cells that are years, not measurements: a bare 4-digit 19xx/20xx is a column
# header value or a date, never the quantity being claimed.
_YEARISH = re.compile(r"^(19|20)\d{2}$")

# BRSR compliance FORM tables ("was this reviewed by the Board? / how often?") carry
# numbers (principle indices, Yes/No coded as counts) but assert no ESG quantity. The
# extractor is RIGHT to ignore them, so counting them as recall targets penalises correct
# behaviour. Detected off the column header / row label, which are distinctive.
_FORM_COL = re.compile(r"indicate whether|frequency \(annually|subject for review", re.I)
_FORM_ROW = re.compile(r"^subject for review", re.I)


def _parse_number(cell: str):
    s = (cell or "").strip()
    if not s or s in {"-", "--", "n/a", "N/A", "NA"}:
        return None
    m = _NUM.match(s)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    if _YEARISH.match(raw):
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v


def _tables(markdown: str):
    """Yield GFM tables as lists of cell-lists. A table is a run of pipe rows; the
    second row is the |---| separator, which we skip."""
    rows, cur = [], []
    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells if c):   # separator row
                continue
            cur.append(cells)
        else:
            if len(cur) >= 2:
                rows.append(cur)
            cur = []
    if len(cur) >= 2:
        rows.append(cur)
    return rows


def _candidate_cells(markdown: str):
    """Ground-truth numeric facts on one page: (row_label, col_header, value).

    Filter (deliberately simple + auditable):
      * first column is the row label and must contain a >=3-letter word
      * the cell must parse as a number and not be a bare year
      * header row is the table's first row
    """
    out = []
    for tbl in _tables(markdown):
        header, *body = tbl
        for row in body:
            if not row:
                continue
            label = row[0]
            if not _HAS_WORD.search(label):
                continue
            for i, cell in enumerate(row[1:], start=1):
                v = _parse_number(cell)
                if v is None:
                    continue
                col = header[i] if i < len(header) else f"col{i}"
                out.append({"row_label": label, "column": col, "value": v,
                            "is_form": bool(_FORM_COL.search(col) or _FORM_ROW.search(label))})
    return out


def _close(a: float, b: float, rel: float = 0.01) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) / scale <= rel


def run(show_misses: int = 0):
    results = {}
    for label, fixture, cache, coverage in CASES:
        pages = {e["page_number"]: e["markdown"]
                 for e in json.loads((_FIX / cache).read_text(encoding="utf-8"))}

        # extracted values, grouped by page
        by_page = {}
        n_claims = n_table = 0
        with open(_FIX / fixture, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                c = ExtractedClaim.model_validate(json.loads(line))
                n_claims += 1
                if c.source_type == "table":
                    n_table += 1
                if c.metric is None or c.metric.value is None:
                    continue
                pg = c.provenance.page_number if c.provenance else None
                if pg is None:
                    continue
                try:
                    by_page.setdefault(pg, []).append(float(c.metric.value))
                except (TypeError, ValueError):
                    continue

        # CONFOUND GUARD. A fixture produced by a text-dominant run barely exercised the
        # table pipeline, so its table-cell recall measures THAT RUN'S CONFIGURATION, not
        # the shipped Docling table path — and a "page produced no claims" miss must NOT
        # then be attributed to table-page detection. Surfaced so the number can't be
        # read as a verdict on detection when the table path never really ran.
        table_share = (n_table / n_claims) if n_claims else 0.0

        total = hit = 0
        d_total = d_hit = 0          # stricter denominator: distinct facts, forms excluded
        n_dupes = n_form = 0
        att_total = att_hit = 0      # restricted to pages the pipeline actually touched
        untouched_pages, untouched_cells = 0, 0
        misses, per_page = [], []
        for pg, md in sorted(pages.items()):
            cells = _candidate_cells(md)
            if not cells:
                continue
            got = by_page.get(pg, [])
            attempted = bool(got)    # emitted >=1 valued claim here => page was processed
            if not attempted:
                untouched_pages += 1
                untouched_cells += len(cells)

            # Stricter view: one row label + value is ONE fact even when a wide matrix
            # table repeats it across several column groups (21% of the raw Tata
            # denominator was such repeats), and governance-form cells are dropped
            # entirely because they assert no ESG quantity.
            seen = set()
            p_hit = 0
            for cell in cells:
                matched = any(_close(cell["value"], v) for v in got)
                if matched:
                    hit += 1
                    p_hit += 1
                else:
                    misses.append({"page": pg, **cell})
                total += 1

                if cell["is_form"]:
                    n_form += 1
                    continue
                key = (cell["row_label"].strip().lower(), cell["value"])
                if key in seen:
                    n_dupes += 1
                    continue
                seen.add(key)
                d_total += 1
                if matched:
                    d_hit += 1

            if attempted:
                att_total += len(cells)
                att_hit += p_hit
            per_page.append({"page": pg, "cells": len(cells), "recalled": p_hit,
                             "attempted": attempted,
                             "recall": round(p_hit / len(cells), 3)})

        results[label] = {
            "fixture": fixture,
            "cache_coverage": coverage,
            "pages_cached": sorted(pages),
            "claims_total": n_claims,
            "claims_from_tables": n_table,
            "table_claim_share": round(table_share, 3),
            "table_path_exercised": table_share >= 0.15,
            "pages_with_tables": len(per_page),
            "ground_truth_cells": total,
            "recalled": hit,
            # End-to-end: what the system delivers vs what is on the page. The number
            # that matters to a user, and the one to report as "recall".
            "table_cell_recall": round(hit / total, 4) if total else None,
            # Stricter + truer: distinct (row_label, value) facts, governance-form cells
            # excluded. Report this as the headline; keep the raw one as the lower bound.
            "distinct_facts": d_total,
            "distinct_fact_recall": round(d_hit / d_total, 4) if d_total else None,
            "duplicate_cells_collapsed": n_dupes,
            "form_cells_excluded": n_form,
            # Diagnostic split — separates the two very different failure modes:
            #   detection  = page never processed at all (table-page detection missed it)
            #   extraction = page processed but the LLM did not emit that fact
            "pages_never_processed": untouched_pages,
            "cells_lost_to_detection": untouched_cells,
            "recall_on_processed_pages": round(att_hit / att_total, 4) if att_total else None,
            "per_page": per_page,
            "misses_sample": misses[:show_misses] if show_misses else [],
            "n_misses": len(misses),
        }
    return results


def _print(res, show_misses):
    for label, d in res.items():
        r = d["table_cell_recall"]
        print(f"\n{'=' * 78}\n{label}\n{'=' * 78}")
        print(f"  cache coverage         : {d['cache_coverage']}")
        print(f"  pages with tables      : {d['pages_with_tables']}")
        print(f"  ground-truth cells     : {d['ground_truth_cells']}")
        print(f"  recalled by pipeline   : {d['recalled']}")
        dr = d["distinct_fact_recall"]
        print(f"  raw cell recall        : {'n/a' if r is None else f'{100 * r:.1f}%'}"
              f"   ({d['recalled']}/{d['ground_truth_cells']} — conservative lower bound)")
        print(f"  DISTINCT-FACT RECALL   : {'n/a' if dr is None else f'{100 * dr:.1f}%'}"
              f"   (headline: {d['duplicate_cells_collapsed']} duplicate cells collapsed, "
              f"{d['form_cells_excluded']} governance-form cells excluded)")
        rp = d["recall_on_processed_pages"]
        print(f"  table claims in fixture: {d['claims_from_tables']}/{d['claims_total']}"
              f"  ({100 * d['table_claim_share']:.0f}% of claims)")
        print(f"  ---- failure split ----")
        print(f"  pages producing 0 claims: {d['pages_never_processed']}"
              f"  -> {d['cells_lost_to_detection']} cells")
        print(f"  recall on other pages   : {'n/a' if rp is None else f'{100 * rp:.1f}%'}")
        if not d["table_path_exercised"]:
            print("  ** CONFOUND: this fixture is TEXT-DOMINANT — the table pipeline barely ran.")
            print("     Its table-cell recall reflects THAT RUN'S CONFIG, not the shipped Docling")
            print("     path, and the zero-claim pages must NOT be blamed on table-page detection.")

        worst = sorted([p for p in d["per_page"] if p["cells"] >= 5],
                       key=lambda p: p["recall"])[:5]
        if worst:
            print("  weakest pages (>=5 cells):")
            for p in worst:
                print(f"     p{p['page']:<4} {p['recalled']:>3}/{p['cells']:<3} "
                      f"= {100 * p['recall']:5.1f}%")
        if show_misses and d["misses_sample"]:
            print(f"  sample of {len(d['misses_sample'])} of {d['n_misses']} missed cells:")
            for m in d["misses_sample"]:
                lab = m["row_label"][:46]
                print(f"     p{m['page']:<4} {lab:<48} {m['column'][:18]:<20} {m['value']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--misses", type=int, default=0, help="show N missed cells per case")
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()

    res = run(show_misses=a.misses)
    _print(res, a.misses)
    print("\nNOTE: this is recall over numeric TABLE cells only. Narrative/text-claim "
          "recall still requires human annotation (Phase 6.1b) — do not quote this as "
          "whole-document recall.")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"wrote {a.json_out}")
