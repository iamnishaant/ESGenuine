"""
ESGenuine - semi-automated evidence-corpus curation (improve_rating A1).

The fact-check engine is starved: 4 illustrative records -> almost everything
UNVERIFIED. This replaces fully-manual JSON editing with a 3-step workflow:

  1) template  ->  rank the corpus's most-checkable metrics and emit a CSV a human
                   fills with verified reference values (one row per company x
                   metric_key x year, prefilled with the CLAIMED value for context)
  2) validate  ->  strict-check a filled CSV (schema, units, quality tier, source
                   citation present for any non-illustrative row)
  3) merge     ->  convert the CSV into evidence_corpus.json records (replacing
                   illustrative rows for the same key, never silently overwriting
                   verified ones)

No-fabricate rule: `merge` REFUSES any row with quality verified/self_reported
whose `source` doesn't cite a document + page/table. Illustrative rows are allowed
but keep their machine-readable "demo only" tier.

Usage:
  python backend/scripts/build_evidence_corpus.py template [--claims path.jsonl] [--out template.csv]
  python backend/scripts/build_evidence_corpus.py validate <filled.csv>
  python backend/scripts/build_evidence_corpus.py merge <filled.csv> [--corpus path.json] [--dry-run]
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]              # backend/
DEFAULT_CLAIMS = ROOT / "test_results" / "incremental_claims_backup.jsonl"
DEFAULT_CORPUS = ROOT / "data" / "evidence_corpus.json"

CSV_FIELDS = ["company_id", "metric_key", "year", "value", "unit",
              "statement", "source", "url", "quality", "claimed_value_context"]
QUALITIES = {"verified", "self_reported", "illustrative", "unverified"}
# a real citation names a document and a page/table locator
_CITATION = re.compile(r"(report|filing|cdp|brsr|annual|datasheet).*(p\.?\s*\d+|page\s*\d+|table)", re.I)


def _load_claims(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cmd_template(args):
    claims = _load_claims(args.claims)
    # rank (company_id, metric_key, year) triples by claim count - the most-claimed
    # metrics are the ones evidence unlocks the most coverage for
    triples = Counter()
    example_val = {}
    for c in claims:
        key = (c.get("company_id") or "unknown", c.get("metric_key") or "", str(c.get("time_bucket") or ""))
        mk = key[1]
        if not mk or mk == "uncategorized" or not key[2].isdigit():
            continue
        triples[key] += 1
        m = c.get("metric") or {}
        if key not in example_val and m.get("value") is not None:
            example_val[key] = f"{m.get('value')} {m.get('unit')}"

    out = Path(args.out)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for (cid, mk, yr), n in triples.most_common(args.top):
            w.writerow({
                "company_id": cid, "metric_key": mk, "year": yr,
                "value": "", "unit": "", "statement": "",
                "source": "", "url": "", "quality": "",
                "claimed_value_context": f"{n} claim(s); e.g. {example_val.get((cid, mk, yr), 'n/a')}",
            })
    print(f"[template] {min(args.top, len(triples))} rows -> {out}")
    print("Fill value/unit/statement/source/url/quality, then run: validate, merge.")


def _check_rows(path):
    """Return (valid_rows, errors)."""
    rows, errors = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):   # 1-based + header
            if not (row.get("value") or "").strip():
                continue                                       # unfilled template row
            e = []
            if not (row.get("company_id") or "").strip():
                e.append("company_id missing")
            if not re.fullmatch(r"[a-z0-9_.]+", (row.get("metric_key") or "")):
                e.append(f"bad metric_key {row.get('metric_key')!r}")
            try:
                row["year"] = int(row["year"])
            except (ValueError, TypeError, KeyError):
                e.append(f"bad year {row.get('year')!r}")
            try:
                row["value"] = float(str(row["value"]).replace(",", ""))
            except (ValueError, TypeError):
                e.append(f"bad value {row.get('value')!r}")
            if not (row.get("unit") or "").strip():
                e.append("unit missing")
            q = (row.get("quality") or "").strip() or "unverified"
            if q not in QUALITIES:
                e.append(f"bad quality {q!r} (want {sorted(QUALITIES)})")
            row["quality"] = q
            # the no-fabricate gate: trusted tiers must cite document + page/table
            if q in ("verified", "self_reported") and not _CITATION.search(row.get("source") or ""):
                e.append("quality is trusted but source doesn't cite a document + page/table")
            if e:
                errors.append(f"  line {i}: " + "; ".join(e))
            else:
                rows.append(row)
    return rows, errors


def cmd_validate(args):
    rows, errors = _check_rows(args.csv)
    print(f"[validate] {len(rows)} valid filled row(s), {len(errors)} error(s).")
    for e in errors:
        print(e)
    return 1 if errors else 0


def cmd_merge(args):
    rows, errors = _check_rows(args.csv)
    if errors:
        print(f"[merge] REFUSED - {len(errors)} invalid row(s); run validate for detail.")
        return 1

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    records = corpus.get("records", [])
    by_key = defaultdict(list)
    for idx, r in enumerate(records):
        by_key[(r.get("company_id"), r.get("metric_key"), r.get("year"))].append(idx)

    added = replaced = skipped = 0
    for row in rows:
        rec = {k: row[k] for k in ("company_id", "metric_key", "year", "value",
                                   "unit", "statement", "source", "url", "quality")}
        key = (rec["company_id"], rec["metric_key"], rec["year"])
        existing = by_key.get(key, [])
        blocked = False
        for idx in existing:
            old_q = records[idx].get("quality", "unverified")
            if old_q == "verified" and rec["quality"] != "verified":
                print(f"[merge] skip {key}: existing VERIFIED record not overwritten by {rec['quality']}")
                skipped += 1
                blocked = True
            else:
                records[idx] = rec                 # upgrade illustrative/unverified in place
                replaced += 1
                blocked = True
        if not blocked:
            records.append(rec)
            by_key[key].append(len(records) - 1)
            added += 1

    corpus["records"] = records
    print(f"[merge] +{added} added, {replaced} replaced, {skipped} skipped "
          f"-> {len(records)} total records")
    if args.dry_run:
        print("[merge] dry-run: corpus NOT written.")
        return 0
    Path(args.corpus).write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[merge] wrote {args.corpus}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="emit a fill-me CSV ranked by claim volume")
    t.add_argument("--claims", default=str(DEFAULT_CLAIMS))
    t.add_argument("--out", default=str(ROOT / "data" / "evidence_template.csv"))
    t.add_argument("--top", type=int, default=40)

    v = sub.add_parser("validate", help="strict-check a filled CSV")
    v.add_argument("csv")

    m = sub.add_parser("merge", help="merge a filled CSV into evidence_corpus.json")
    m.add_argument("csv")
    m.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    m.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "template":
        return cmd_template(args) or 0
    if args.cmd == "validate":
        return cmd_validate(args)
    return cmd_merge(args)


if __name__ == "__main__":
    sys.exit(main())
