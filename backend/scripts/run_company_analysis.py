"""
Reusable company analysis driver (read-only over the app code).

Parses one or more ESG report PDFs, extracts claims via the configured LLM
(NVIDIA NIM by default), and reports a DEFENSIVE "evidence quality" summary:
  - groundability / vagueness distribution
  - share of claims lacking a metric / timeframe / location (i.e. unverifiable as written)
  - concrete low-evidence examples (verbatim source sentence)
  - year-over-year drift for metrics that appear in both reports

Framing rule: we never assert a report is "false" — only that specific claims
"lack verifiable evidence as stated".

Usage (from backend/):
  SAMPLE=40 ../.venv/Scripts/python.exe scripts/run_company_analysis.py "ESG_Reports/shell-*.pdf" ESGenuine_shell_analysis.md
"""
import sys, os, glob, re, json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]          # backend/
sys.path.insert(0, str(ROOT / "src"))
from parsers.pdf_parser import DocumentParsingPipeline
from extractors.claim_extractor import ClaimExtractor

SAMPLE = int(os.environ.get("SAMPLE", "40"))         # chunks per report (0 = all)
pattern = sys.argv[1] if len(sys.argv) > 1 else "ESG_Reports/shell-*.pdf"
out_md = sys.argv[2] if len(sys.argv) > 2 else str(ROOT.parent / "ESGenuine_analysis.md")

def year_of(name: str) -> str:
    m = re.search(r"(20\d{2})", name)
    return m.group(1) if m else name

_SUFFIX = {"sustainability", "report", "esg", "environmental", "social", "governance",
           "csv", "creating", "shared", "value", "responsibility", "and", "of", "plc",
           "company", "the", "annual", "impact", "en", "1", "2"}

def company_of(name: str) -> str:
    """Best-effort company name from the filename (e.g. 'shell-sustainability-report-2023' -> 'Shell')."""
    toks = [t for t in re.split(r"[-_\s]+", name) if t and not re.fullmatch(r"20\d{2}|\d{1,2}", t)]
    toks = [t for t in toks if t.lower() not in _SUFFIX]
    return " ".join(w.capitalize() for w in toks) if toks else name

extractor = ClaimExtractor()
print(f"[driver] LLM provider = {extractor.llm.provider} | sample/report = {SAMPLE or 'ALL'}")

def build_windows(sentences, max_chars=3500):
    """Group the document's sentences (reading order) into char-budgeted windows -> 1 LLM call each."""
    blocks, cur, size = [], [], 0
    def flush():
        if cur:
            titles = [x.get("section_title") for x in cur if x.get("section_title")]
            title = max(set(titles), key=titles.count) if titles else "Document"
            blocks.append({"section_title": title, "sentences": list(cur)})
    for s in sentences:
        t = s.get("text", "") or ""
        if cur and size + len(t) > max_chars:
            flush(); cur.clear(); size = 0
        cur.append(s); size += len(t) + 1
    flush()
    return blocks

per_year = {}     # year -> list[ExtractedClaim]
report_meta = {}  # year -> dict

for pdf in sorted(glob.glob(pattern)):
    name = Path(pdf).stem
    yr = year_of(name)
    print(f"\n[driver] ==== {name} (year {yr}) ====")
    res = DocumentParsingPipeline(pdf).run(skip_tables=True)  # section mode needs sentences, not tables
    sents = [{"text": s.get("text", ""), "page_number": s.get("page_number", 0),
              "sentence_id": s.get("sentence_id", ""), "section_title": s.get("section_title"),
              "bbox": s.get("bbox")} for s in res["sentences"]]
    blocks = build_windows(sents)
    if SAMPLE:                       # cap windows for a fast proof; SAMPLE=0 -> all
        blocks = blocks[:SAMPLE]
    print(f"[driver] {len(sents)} sentences -> {len(blocks)} section-windows (~1 LLM call each)")

    # Persist/reuse so a crash (or re-analysis) never loses extraction work.
    cache = ROOT / "parsed" / f"{name}_sota_claims.json"
    if os.environ.get("REUSE") == "1" and cache.exists():
        from extractors.models import ExtractedClaim
        claims = [ExtractedClaim.model_validate(d) for d in json.loads(cache.read_text(encoding="utf-8"))]
        print(f"[driver] reused {len(claims)} cached claims from {cache.name}")
    else:
        claims = extractor.extract_from_sections(blocks, document_id=name)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([c.model_dump() for c in claims], default=str, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print(f"[driver] saved {len(claims)} claims -> {cache.name}")

    # Phase 2: VLM-extracted table metrics (env VLM_TABLES=1). Merged with text claims.
    n_table = 0
    if os.environ.get("VLM_TABLES") == "1":
        tcache = ROOT / "parsed" / f"{name}_table_claims.json"
        if os.environ.get("REUSE") == "1" and tcache.exists():
            from extractors.models import ExtractedClaim
            tclaims = [ExtractedClaim.model_validate(d) for d in json.loads(tcache.read_text(encoding="utf-8"))]
        else:
            from extractors.vlm_tables import VLMTableExtractor
            tables = VLMTableExtractor(max_pages=int(os.environ.get("VLM_MAX_PAGES", "0"))).extract(pdf)
            tclaims = extractor.extract_from_table_markdown(tables, document_id=name)
            tcache.write_text(json.dumps([c.model_dump() for c in tclaims], default=str, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        n_table = len(tclaims)
        claims = claims + tclaims
        print(f"[driver] + {n_table} table claims (VLM)")

    per_year[yr] = claims
    report_meta[yr] = {"file": Path(pdf).name, "company": company_of(name),
                       "pages": res["triage"]["page_count"],
                       "sentences": len(sents), "windows": len(blocks), "table_claims": n_table}

def bucket(claims):
    g = [c.groundability_score for c in claims]
    high = sum(1 for x in g if x >= 0.75); mid = sum(1 for x in g if 0.5 <= x < 0.75); low = sum(1 for x in g if x < 0.5)
    return high, mid, low

def pct(n, d): return round(100 * n / d, 1) if d else 0.0

lines = []
def w(s=""): lines.append(s)

_company = next((m.get("company") for m in report_meta.values() if m.get("company")), "")
w(f"# ESGenuine — Evidence-Quality Analysis: {_company}".rstrip(": "))
w()
w(f"_Company: **{_company or 'Unknown'}** · reports analyzed: {', '.join(sorted(report_meta))}_")
w()
w("> **Defensive framing:** findings describe whether individual claims are *verifiable as written* "
  "(do they carry a number, a timeframe, a location, a source?). Low scores indicate **lack of disclosed "
  "evidence**, not that a statement is false.")
w()
for yr in sorted(per_year):
    claims = per_year[yr]
    meta = report_meta[yr]
    n = len(claims)
    if n == 0:
        w(f"## {yr} — {meta['file']}\n\n_No claims extracted from the sample._\n")
        continue
    high, mid, low = bucket(claims)
    with_metric = sum(1 for c in claims if c.metric is not None)
    with_time = sum(1 for c in claims if c.time is not None and (c.time.start_date or c.time.end_date))
    with_loc = sum(1 for c in claims if c.location is not None and c.location.raw_text)
    avg_vague = round(sum(c.vagueness_score for c in claims) / n, 3)
    narrative = sum(1 for c in claims if (c.claim_type or "").lower() == "narrative")
    w(f"## {yr} — {meta['file']} ({meta['pages']} pp, {meta.get('windows','?')} section-windows over {meta.get('sentences','?')} sentences)")
    w()
    w(f"- Claims analyzed: **{n}**")
    w(f"- Groundability: high(≥0.75) **{high} ({pct(high,n)}%)** · medium **{mid} ({pct(mid,n)}%)** · low(<0.5) **{low} ({pct(low,n)}%)**")
    w(f"- **Lack-of-evidence indicators:** no metric **{pct(n-with_metric,n)}%** · no timeframe **{pct(n-with_time,n)}%** · no location **{pct(n-with_loc,n)}%**")
    w(f"- Avg vagueness: **{avg_vague}** · narrative/aspirational claims: **{narrative} ({pct(narrative,n)}%)**")
    w()
    weak = sorted(claims, key=lambda c: c.groundability_score)[:6]
    w("**Lowest-evidence examples (unverifiable as written):**")
    for c in weak:
        src = (c.provenance.source_sentence or "").strip().replace("\n", " ")[:160]
        w(f"  - _g={c.groundability_score:.2f}, vague={c.vagueness_score:.2f}_ — \"{src}\"")
    w()

# Year-over-year drift on metrics present in both reports
if len(per_year) >= 2:
    yrs = sorted(per_year)
    w(f"## Year-over-year drift ({yrs[0]} → {yrs[-1]})")
    w()
    from extractors.ontology import SignatureGenerator
    def metric_map(claims):
        m = defaultdict(list)
        for c in claims:
            if not (c.metric and c.metric.value is not None and c.normalized_aspect):
                continue
            # Recompute the key with the current normalizer (works on cached claims too),
            # and skip collapsed/uncategorized keys — they aren't trustworthy to compare.
            key = SignatureGenerator.generate_metric_key(c.normalized_aspect, c.metric.unit)
            if key == "uncategorized" or key.endswith(".unspecified"):
                continue
            m[key].append((c.metric.value, c.metric.unit, c.provenance.source_sentence))
        return m
    a, b = metric_map(per_year[yrs[0]]), metric_map(per_year[yrs[-1]])
    common = sorted(set(a) & set(b))
    if not common:
        w("_No metric keys appeared in both sampled years — increase SAMPLE or fix metric_key normalization "
          "to enable robust cross-year comparison (see existing_issues.md)._")
    else:
        for k in common:
            va = a[k][0]; vb = b[k][0]
            w(f"- `{k}`: {va[0]} {va[1] or ''} ({yrs[0]}) → {vb[0]} {vb[1] or ''} ({yrs[-1]})")
    w()

w("---")
w(f"_Provider: {extractor.llm.provider}. Representative even-spaced sample per report (not cherry-picked). "
  "Contradiction engine intentionally not used (see existing_issues.md #1–#3)._")

Path(out_md).write_text("\n".join(lines), encoding="utf-8")
print(f"\n[driver] wrote findings -> {out_md}")
print("\n".join(lines))
