"""
ESGenuine — SOURCE-ANCHORED annotation sampler (roadmap 6.1b / 6.3)
====================================================================

Builds the annotation worksheet for a gold set that is anchored to the SOURCE DOCUMENT
instead of to extractor output. This is the fix for the three structural defects the
2026-08-10 audit found in `tests/eval/gold_set*.json`.

WHAT WAS WRONG WITH THE OLD SAMPLING FRAME
------------------------------------------
Every existing gold set was sampled *from claims the extractor emitted*
(`_meta.source_extraction` points at an output JSONL). Three consequences, all fatal for
a research claim, and all of them properties of the FRAME rather than of the annotator:

  1. NO RECALL IS POSSIBLE. A claim the system missed never enters the sample, so it
     cannot be counted against the system. `precision_composite` is precision-only by
     construction, not by omission.
  2. THE ANNOTATOR IS ANCHORED. The old protocol reads "for each sampled extracted claim
     we read its source_sentence and record the CORRECT label" — i.e. the label is formed
     while looking at the prediction. That is textbook anchoring bias.
  3. THE GOLD ROTS WHEN THE SYSTEM CHANGES. Labels reference taxonomy nodes, so a new
     ontology node makes old labels look stale and invites editing ground truth to match
     the system. That is exactly what happened in `48555ea` and `95e1f20`.

THE FIX — three design decisions
--------------------------------
**(1) Enumerate units from the document, not claims from the output.** A "unit" is a
sentence or a table cell that *could* carry a claim. The frame is fixed before the system
runs, so recall has a denominator and a miss is visible.

**(2) Stratify, then reweight.** Most sentences in an ESG report assert nothing, so
uniform sampling would spend the whole annotation budget on negatives. Units are split
into three strata by claim density and sampled at different rates; every unit carries its
inclusion probability so estimates are reweighted back to the full document
(Horvitz–Thompson). You get unbiased document-level precision AND recall without
exhaustive annotation.

**(3) Record CONCEPT, not taxonomy node.** The worksheet asks for a free-text concept
plus a coarse pillar ("particulate matter emissions" / `emissions`). Mapping concept →
`emissions.air_pollutants.pm` is a SYSTEM artifact, versioned separately in
`tests/eval/concept_map.json`. When the ontology gains a node you update the MAPPING —
a system change, visible in the diff as such — and never the ground truth. This is what
structurally prevents the `48555ea` failure from recurring.

WHAT THIS SCRIPT DELIBERATELY DOES NOT DO
-----------------------------------------
It never reads, loads or looks at extractor output. The worksheet contains no predictions,
no claim_ids and no suggested labels — only source text. That is not an oversight to be
"improved" later: pre-filling labels from the system would reintroduce defect (2) and
silently invalidate every κ computed from the result.

HONEST LIMITS
-------------
* Recall is measured relative to the PARSER's units. A fact the PDF parser never surfaced
  (an unparsed figure, a scanned table, OCR failure) is outside the frame and will not be
  counted as a miss. Report this; do not let "recall" be read as "of everything in the PDF".
* Stratum C is sampled thinly, so its contribution to reweighted estimates carries the
  widest interval. Bootstrap over units, respecting strata.

Run:
    # table units only — works today off any committed Docling cache
    python backend/scripts/enumerate_units.py --docling tests/eval/fixtures/docling_tata.json \\
        --doc-id tata_power_2024 --n 400 --out tests/eval/worksheets/

    # text + table, from a parsed document
    python backend/scripts/enumerate_units.py --docling <cache.json> \\
        --sentences backend/parsed/<hash>_sentences.json --doc-id <id> --n 400 --out <dir>

    # inspect the frame without sampling
    python backend/scripts/enumerate_units.py --docling <cache.json> --doc-id x --describe
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_recall as rr                                            # noqa: E402

SEED = 42

# ── strata ────────────────────────────────────────────────────────────────────────────
# Claim density differs by an order of magnitude between these, so they are sampled at
# different rates and reweighted. Keep the definitions DUMB and auditable: a reviewer must
# be able to verify the frame without running anything, and a clever classifier here would
# make the sampling probabilities depend on a model.
_NUMERAL = re.compile(r"\d")
_ESG_TERMS = re.compile(
    r"\b(emission|ghg|greenhouse|carbon|co2|scope\s*[123]|methane|"
    r"energy|renewable|solar|wind|electricity|fuel|"
    r"water|effluent|discharge|withdrawal|"
    r"waste|recycl|landfill|hazardous|"
    r"safety|injur|ltifr|fatalit|"
    r"employee|worker|women|female|diversity|training|wage|"
    r"biodiversity|afforest|reforest|tree|"
    r"emission intensity|net zero|net-zero|target|baseline|"
    r"csr|community|governance|board|ethic|corruption|complaint|"
    r"supplier|supply chain|human rights|posh)\b", re.I)

STRATA = ("A_numeral_and_esg", "B_numeral_only", "C_other")

# Sampling weights: how the budget is split across strata. Not equal — A is where the
# claims are, C is sampled only enough to bound how much is being missed there.
DEFAULT_ALLOCATION = {"A_numeral_and_esg": 0.60, "B_numeral_only": 0.25, "C_other": 0.15}


def _stratum(text: str, *, has_number: bool = None) -> str:
    """Assign a unit to a stratum.

    `has_number` overrides the text test, and TABLE CELLS MUST PASS IT. A cell is only in
    the frame because it parsed as a number, so testing its *label* for a digit is
    meaningless — it sent rows like "National | Total | 136.0" to stratum C (the
    thinly-sampled "probably nothing here" bucket) purely because the row label had no
    digit in it. Numeric table rows are exactly what must not be under-sampled.
    """
    has_num = bool(_NUMERAL.search(text or "")) if has_number is None else has_number
    has_esg = bool(_ESG_TERMS.search(text or ""))
    if has_num and has_esg:
        return "A_numeral_and_esg"
    if has_num:
        return "B_numeral_only"
    return "C_other"


# ── frame construction ────────────────────────────────────────────────────────────────

def _unit_id(doc_id: str, kind: str, page, key: str) -> str:
    """Stable, content-derived id. Survives re-parsing and re-extraction, which is the
    entire point — a gold label keyed to this never needs rewriting when the system changes."""
    h = hashlib.sha1(f"{doc_id}|{kind}|{page}|{key}".encode("utf-8")).hexdigest()[:12]
    return f"{kind}_{h}"


def table_units(cache_path: Path, doc_id: str) -> list:
    """One unit per numeric table cell: (row label, column header, value)."""
    pages = {e["page_number"]: e["markdown"]
             for e in json.loads(cache_path.read_text(encoding="utf-8"))}
    units = []
    for pg, md in sorted(pages.items()):
        for cell in rr._candidate_cells(md):
            text = f"{cell['row_label']} | {cell['column']} | {cell['value']}"
            units.append({
                "unit_id": _unit_id(doc_id, "tbl", pg, text),
                "kind": "table_cell",
                "page": pg,
                "text": text,
                "row_label": cell["row_label"],
                "column_header": cell["column"],
                "cell_value": cell["value"],
                "is_governance_form": cell["is_form"],
                # has_number=True: the cell is in the frame *because* it parsed as a number.
                "stratum": _stratum(f"{cell['row_label']} {cell['column']}", has_number=True),
            })
    return units


def text_units(sentences_path: Path, doc_id: str, min_chars: int = 40) -> list:
    """One unit per parsed sentence. Very short fragments are dropped from the FRAME (not
    sampled and discarded) — they are parser debris, and leaving them in would inflate the
    denominator with things no system should extract."""
    rows = json.loads(sentences_path.read_text(encoding="utf-8"))
    units = []
    for s in rows:
        text = re.sub(r"\s+", " ", (s.get("text") or "")).strip()
        if len(text) < min_chars:
            continue
        units.append({
            "unit_id": _unit_id(doc_id, "txt", s.get("page_number"), s.get("sentence_id") or text),
            "kind": "sentence",
            "page": s.get("page_number"),
            "text": text,
            "section_title": s.get("section_title"),
            "stratum": _stratum(text),
        })
    return units


# ── sampling ──────────────────────────────────────────────────────────────────────────

def sample(units: list, n: int, allocation=None, seed: int = SEED) -> tuple:
    """Stratified sample WITH recorded inclusion probabilities.

    Returns (sampled_units, manifest). Every sampled unit carries `inclusion_prob` and
    `ipw_weight` = 1/p, so downstream estimators reweight to the full document instead of
    reporting a statistic about the sample.
    """
    allocation = allocation or DEFAULT_ALLOCATION
    rng = random.Random(seed)

    by_stratum = {s: [u for u in units if u["stratum"] == s] for s in STRATA}
    manifest = {"seed": seed, "target_n": n, "frame_total": len(units), "strata": {}}

    picked = []
    for s in STRATA:
        pool = by_stratum[s]
        want = min(len(pool), int(round(n * allocation[s])))
        chosen = rng.sample(pool, want) if want else []
        p = (want / len(pool)) if pool else 0.0
        for u in chosen:
            u = dict(u)
            u["inclusion_prob"] = round(p, 6)
            u["ipw_weight"] = round(1.0 / p, 4) if p else None
            picked.append(u)
        manifest["strata"][s] = {
            "frame_size": len(pool), "sampled": want,
            "inclusion_prob": round(p, 6),
            "ipw_weight": round(1.0 / p, 4) if p else None,
        }

    rng.shuffle(picked)   # so the annotator does not work through one stratum at a time
    manifest["sampled_total"] = len(picked)
    return picked, manifest


# ── worksheet emission ────────────────────────────────────────────────────────────────

# The annotator fills these. Deliberately NOT pre-filled from any system output.
ANNOTATION_FIELDS = [
    "is_esg_claim",        # yes | no
    "concept",             # FREE TEXT, e.g. "particulate matter emissions". NOT a taxonomy node.
    "pillar",              # emissions | energy | water | waste | social | governance | other
    "claim_type",          # performance | target | narrative
    "value",               # the number asserted, or blank
    "unit",                # as written in the source
    "value_ambiguous",     # yes | no  (row carries several values, none pinnable)
    "annotator_note",
]


def write_worksheet(units: list, manifest: dict, doc_id: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{doc_id}_units"

    csv_path = out_dir / f"{stem}.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_id", "kind", "page", "source_text"] + ANNOTATION_FIELDS)
        for u in units:
            w.writerow([u["unit_id"], u["kind"], u["page"], u["text"]] + [""] * len(ANNOTATION_FIELDS))

    jsonl_path = out_dir / f"{stem}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for u in units:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")

    manifest_path = out_dir / f"{stem}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {"csv": csv_path, "jsonl": jsonl_path, "manifest": manifest_path}


def _describe(units: list):
    print(f"\nFRAME — {len(units)} candidate units")
    print(f"{'stratum':<22}{'units':>8}{'share':>9}   {'example'}")
    print("-" * 100)
    for s in STRATA:
        pool = [u for u in units if u["stratum"] == s]
        share = len(pool) / len(units) if units else 0
        ex = (pool[0]["text"][:52] + "…") if pool else "—"
        print(f"{s:<22}{len(pool):>8}{100 * share:>8.1f}%   {ex}")
    kinds = {}
    for u in units:
        kinds[u["kind"]] = kinds.get(u["kind"], 0) + 1
    print("-" * 100)
    print("by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Sample source text units for annotation (no system output involved).")
    ap.add_argument("--docling", help="Docling page-markdown cache JSON (table units)")
    ap.add_argument("--sentences", help="parsed *_sentences.json (text units)")
    ap.add_argument("--doc-id", required=True, help="stable document id, used in unit ids")
    ap.add_argument("--n", type=int, default=400, help="annotation budget (default 400)")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", default="backend/tests/eval/worksheets", help="output directory")
    ap.add_argument("--describe", action="store_true", help="print the frame and exit (no sampling)")
    a = ap.parse_args()

    if not a.docling and not a.sentences:
        raise SystemExit("give --docling and/or --sentences: there is nothing to enumerate otherwise")

    units = []
    if a.docling:
        units += table_units(Path(a.docling), a.doc_id)
    if a.sentences:
        units += text_units(Path(a.sentences), a.doc_id)

    if not units:
        raise SystemExit("frame is empty — check the input paths")

    _describe(units)
    if a.describe:
        sys.exit(0)

    picked, manifest = sample(units, a.n, seed=a.seed)
    manifest["doc_id"] = a.doc_id
    manifest["sources"] = {"docling": a.docling, "sentences": a.sentences}

    paths = write_worksheet(picked, manifest, a.doc_id, Path(a.out))
    print(f"\nSAMPLED {len(picked)} units for annotation")
    for s in STRATA:
        m = manifest["strata"][s]
        print(f"  {s:<22}{m['sampled']:>5} of {m['frame_size']:<6} "
              f"p={m['inclusion_prob']:.4f}  weight={m['ipw_weight']}")
    print()
    for k, v in paths.items():
        print(f"  {k:<9} {v}")
    print("\nNEXT: annotate the CSV WITHOUT looking at any system output, then have a second")
    print("annotator label a >=150-unit overlap independently. See docs/ANNOTATION_PROTOCOL.md.")
