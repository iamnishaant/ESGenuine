"""
ESGenuine — EXTERNAL BASELINE harness (roadmap Phase 6.2c)
==========================================================

Closes the gap `run_ablation.py` cannot close: the ablation compares the system to
*itself with the contribution removed*. That is a necessary control, not a baseline.
A reviewer's first question is different and sharper:

    Does the deterministic repair layer still earn its keep when the LLM underneath
    it is a FRONTIER model — or is it just patching a mid-tier model's mistakes?

Every committed fixture was produced by `llama-3.3-70b`. Until that question has a
number attached, the project's headline finding ("cheap deterministic repair beats
model scale") is an assertion.

THE DESIGN — a 2x2 factorial, not four unrelated runs
-----------------------------------------------------
                        no repair        + repair       delta(repair)
    llama-3.3-70b         A0               A1              A1 - A0
    frontier              B0               B1              B1 - B0
    delta(model)        B0 - A0          B1 - A1        >> INTERACTION <<

The interaction term is the whole experiment. Three outcomes, all publishable:

  * delta(repair) holds at both model tiers -> "repair is complementary to scale".
    The strongest result, and the one the current framing assumes.
  * delta(repair) shrinks as the model improves -> reframe to COST. "A $0.02/report
    deterministic layer buys what a 10x more expensive model buys." Still a real
    finding; report tokens/latency/dollars per report as the headline instead.
  * delta(repair) is noise at both tiers -> the contribution is not what we thought.
    Better to learn this from a harness than from a reviewer.

`R` (rule-based, no LLM at all) sits outside the 2x2 as the floor: it says how much
of the table surface is reachable with no model spend whatsoever.

THE THREE SCORING LANES — and why the obvious one is the weakest
----------------------------------------------------------------
L1  fact recall        MECHANICAL, FAIR. Distinct numeric table facts enumerated from
                       the committed Docling markdown (`run_recall._candidate_cells`),
                       then checked against what each system emitted. System-independent
                       denominator, so every system is measured against the same target.

L2  grounding precision MECHANICAL, FAIR. Of the numeric values a system emits on a page,
                       what fraction actually APPEAR in that page's source markdown?
                       Values that do not are fabrications. No annotation, no gold set,
                       no taxonomy — so it is comparable across systems by construction.

L3  gold composite     *** BIASED. READ THE WARNING. *** Scores against the committed
                       gold sets via `run_evaluation.evaluate`.

L3's bias is structural and was measured, not guessed. Every gold set is sampled FROM
THE SHIPPED EXTRACTOR'S OUTPUT (`_meta.source_extraction` points at a JSONL of output)
and matches by `claim_id`, falling back to exact normalized `source_sentence`. A
different system phrases its `source_sentence` differently, so it simply fails to match
and goes unscored. Probing the rule-based extractor against the Tata gold found only
**7 of 46** gold sentences reproducible by non-LLM composition.

So L3 measures a system on the subset of sentences where the SHIPPED extractor already
fired. It is a paired read on a common subset, never an unbiased quality comparison, and
it structurally cannot credit a baseline for finding something the shipped system missed.
This harness prints the match rate next to every L3 number and shouts when it is thin.

**The fix is not in this file.** It is `docs/ANNOTATION_PROTOCOL.md` — a gold set
anchored to SOURCE TEXT UNITS rather than to extractor output. Until that exists, quote
L1 and L2 across systems and treat L3 as directional only.

REPRODUCIBILITY
---------------
Scoring is fully offline and free: it reads committed fixtures and Docling caches. Only
`--generate` spends money, and it writes its output back into `tests/eval/fixtures/` so
every later run is offline again — the same frozen-fixture discipline the rest of the
eval stack uses.

Generation extracts from the COMMITTED page markdown (not a fresh PDF parse), so the
input is byte-identical across systems and the only variable is the model. That confines
the comparison to the TABLE surface, which is exactly where L1 and L2 are valid.

Run:
    python backend/scripts/run_baselines.py                       # score what exists
    python backend/scripts/run_baselines.py --markdown            # paper-ready table
    python backend/scripts/run_baselines.py --json out.json

    # the metered step (needs a key); writes a fixture, then never needs re-running
    OPENAI_MODEL=... OPENAI_API_KEY=... \
      python backend/scripts/run_baselines.py --generate frontier --case tata
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend" / "src"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

import run_evaluation as ev                                       # noqa: E402
import run_recall as rr                                           # noqa: E402
from run_ablation import _run_stage                               # noqa: E402
from extractors.models import ExtractedClaim, MetricField, ProvenanceField   # noqa: E402
from extractors.ontology import ESGOntology                       # noqa: E402
from extractors.quality_gate import _value_in_source              # noqa: E402

_FIX = _REPO / "backend" / "tests" / "eval" / "fixtures"
_GOLD = _REPO / "backend" / "tests" / "eval"

# (key, label, shipped fixture, docling cache, gold set)
CASES = {
    "tata": ("Tata Power BRSR FY24", "tata_docling_full.jsonl",
             "docling_tata.json", "gold_set_docling_tata.json"),
    "shell": ("Shell SR2022", "shell_2022_raw.jsonl",
              "docling_shell2022.json", "gold_set_shell_v03.json"),
}

# A generated frontier fixture lands here. Absent => that cell of the 2x2 is reported
# as NOT RUN rather than silently skipped, so a half-finished experiment cannot read
# as a complete one.
def _frontier_fixture(case: str) -> Path:
    return _FIX / f"baseline_frontier_{case}.jsonl"


# The A row must come from the SAME code path as the B row or the 2x2 is not an
# experiment. See `run()` — generate with `--generate incumbent --case <case>`.
def _incumbent_fixture(case: str) -> Path:
    return _FIX / f"baseline_incumbent_{case}.jsonl"


# ─────────────────────────────────────────────────────────── loading

def _load_pages(cache: str) -> dict:
    return {e["page_number"]: e["markdown"]
            for e in json.loads((_FIX / cache).read_text(encoding="utf-8"))}


def _load_claims(path: Path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(ExtractedClaim.model_validate(json.loads(line)))
    return out


# ─────────────────────────────────────────────────── R: the no-LLM floor

def _rule_extract(pages: dict) -> list:
    """Rule-based table extraction: every numeric cell becomes a claim, aspect assigned
    by ontology keyword match on the row label. No model, no network, no cost.

    This is the FLOOR — how much of the table surface is reachable with no model spend?

    *** ITS L1/L2 SCORES ARE TAUTOLOGICAL AND ARE SUPPRESSED IN THE REPORT. ***
    This extractor is built from `rr._candidate_cells`, which is the very enumeration L1
    uses as its recall denominator, so it recalls 100% of it by construction; and its
    values are copied out of the page markdown, so L2 grounding is 100% for the same
    reason. Neither number says anything about the world. They are the circularity this
    harness exists to avoid elsewhere, so `run()` tags this system `tautological=True`
    and the printers render "--" rather than a flattering 100%.

    What R *does* measure honestly:
      * `ontology_coverage` — the share of table rows a keyword taxonomy can even name.
        Rows resolving to `uncategorized` are the ones that genuinely need a model.
      * its L3 gold composite, subject to the usual (here, severe) match-rate caveat.
    """
    claims = []
    for pg, md in sorted(pages.items()):
        for cell in rr._candidate_cells(md):
            if cell["is_form"]:
                continue                      # governance-form cells assert no quantity
            label = cell["row_label"]
            aspect = ESGOntology.normalize_aspect(label)
            # Column header often carries the unit ("... (GJ) FY 23"); row label carries
            # it more often. Concatenate for the unit sniff, keep the label as provenance.
            claims.append(ExtractedClaim(
                aspect=label[:120],
                normalized_aspect=aspect,
                action="reported",
                claim_type="performance",
                metric=MetricField(value=cell["value"],
                                   unit=_sniff_unit(f"{label} {cell['column']}")),
                provenance=ProvenanceField(source_sentence=label, page_number=pg,
                                           chunk_id=f"tbl_p{pg}", block_id=f"tbl_p{pg}"),
                confidence=0.3,
                source_type="table",
            ))
    return claims


_UNIT_HINTS = [
    ("%", "%"), ("percent", "%"), ("gj", "GJ"), ("tj", "TJ"), ("kwh", "kWh"),
    ("mwh", "MWh"), ("gwh", "GWh"), ("kcal/kwh", "kcal/kWh"), ("kilolitre", "kilolitres"),
    ("kl", "kilolitres"), ("m3", "m3"), ("tco2", "tCO2e"), ("co2", "tCO2e"),
    ("tonne", "tonnes"), ("mt", "tonnes"), ("kg", "kg"), ("inr", "INR"), ("crore", "INR crore"),
]


def _sniff_unit(text: str) -> str:
    """MetricField.unit is a required str, and the eval harness's `unit_to_base` already
    treats "unspecified" as the null family — so that, not None, is the right miss value."""
    t = (text or "").lower()
    for needle, unit in _UNIT_HINTS:
        if needle in t:
            return unit
    return "unspecified"


# ─────────────────────────────────────────────────────────── scoring lanes

def _lane_recall(claims: list, pages: dict) -> dict:
    """L1 — distinct-fact recall against the mechanically enumerated cell set.

    Mirrors run_recall's headline definition exactly (duplicate (row_label, value) pairs
    collapsed, governance-form cells excluded) so the two harnesses cannot drift apart
    and report different 'recall' for the same run.
    """
    by_page = {}
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        pg = c.provenance.page_number
        if pg is None:
            continue
        try:
            by_page.setdefault(pg, []).append(float(c.metric.value))
        except (TypeError, ValueError):
            continue

    total = hit = 0
    for pg, md in sorted(pages.items()):
        got = by_page.get(pg, [])
        seen = set()
        for cell in rr._candidate_cells(md):
            if cell["is_form"]:
                continue
            key = (cell["row_label"].strip().lower(), cell["value"])
            if key in seen:
                continue
            seen.add(key)
            total += 1
            if any(rr._close(cell["value"], v) for v in got):
                hit += 1
    return {"distinct_facts": total, "recalled": hit,
            "recall": (hit / total) if total else None}


def _lane_grounding(claims: list, pages: dict) -> dict:
    """L2 — of the numeric values emitted, how many actually occur in the source page?

    A value absent from its own source page is a fabrication (or a mis-attributed page).
    Fully mechanical and taxonomy-free, so it compares systems on equal terms.

    Claims whose page is not in the cache are EXCLUDED from the denominator rather than
    counted as failures — a cache covering 5 pages of a 91-page report would otherwise
    make any system look like it hallucinates constantly.
    """
    checked = grounded = skipped = 0
    for c in claims:
        if c.metric is None or c.metric.value is None or c.provenance is None:
            continue
        md = pages.get(c.provenance.page_number)
        if md is None:
            skipped += 1
            continue
        try:
            v = float(c.metric.value)
        except (TypeError, ValueError):
            continue
        checked += 1
        if _value_in_source(v, md):
            grounded += 1
    return {"checked": checked, "grounded": grounded, "skipped_uncached": skipped,
            "grounding_precision": (grounded / checked) if checked else None}


def _lane_gold(claims: list, gold: dict) -> dict:
    """L3 — the committed gold composite. BIASED across systems; see module docstring."""
    rows = [json.loads(json.dumps(c.model_dump(), default=str)) for c in claims]
    res = ev.evaluate(gold, rows)
    t = res["tallies"]
    m = dict(res["metrics"])
    m["matched"] = t["matched"]
    m["gold_total"] = t["gold_total"]
    m["match_rate"] = (t["matched"] / t["gold_total"]) if t["gold_total"] else None
    return m


# ─────────────────────────────────────────────────────────── the 2x2

def _repair(claims: list, pages: dict) -> list:
    """Full shipped deterministic stack — reuses the ablation's S5 so the two harnesses
    can never disagree about what 'the repair layer' means."""
    return _run_stage(5, claims, pages)


def _no_repair(claims: list) -> list:
    """Ablation S0: strip the deterministic taxonomy mapping, leaving the LLM's own
    free-text aspect. The honest 'what did the model alone produce' condition."""
    cs = copy.deepcopy(claims)
    for c in cs:
        c.quality_flags = []
        c.framework_tags = []
        c.normalized_aspect = c.aspect
    return cs


def run(case_keys=None) -> dict:
    out = {}
    for key in (case_keys or CASES):
        label, fixture, cache, gold_file = CASES[key]
        pages = _load_pages(cache)
        gold = json.loads((_GOLD / gold_file).read_text(encoding="utf-8"))
        shipped_raw = _load_claims(_FIX / fixture)

        systems = {"R  rule-based (no LLM)": _rule_extract(pages)}

        # ── the A row ────────────────────────────────────────────────────────────
        # The SHIPPED fixture is not a valid A row. It came from a full-document run
        # (text + tables, its own page coverage) while a generated B row comes from
        # extract_from_table_markdown over the cached pages. Measured composition:
        #
        #   tata  shipped 373 = 179 table + 194 text, 29 pages | frontier 451 = 451 table, 27 pages
        #   shell shipped 247 =  13 table + 234 text, 50 pages | frontier 191 = 191 table,  4 pages
        #
        # Scoring those against a table-cell denominator compares fixture composition,
        # not models — on shell, 13 table claims against 191. The shipped fixture also
        # carries 178/174 gate flags (an older apply_gate ran before it was frozen)
        # where a generated fixture carries none, so even "no repair" is not the same
        # condition on both rows.
        #
        # So A comes from `baseline_incumbent_<case>.jsonl`: the incumbent model driven
        # through the identical code path, pages and token budget as the frontier run,
        # leaving the model as the only variable. Without it there is no interaction
        # term, and the shipped fixture is reported as context only.
        ipath = _incumbent_fixture(key)
        matched = ipath.exists()
        if matched:
            incumbent_raw = _load_claims(ipath)
            systems["A0 llama, no repair"] = _no_repair(incumbent_raw)
            systems["A1 llama + repair"] = _repair(incumbent_raw, pages)
            systems["S  shipped (full-doc)"] = _repair(shipped_raw, pages)
        else:
            systems["A0 llama, no repair"] = _no_repair(shipped_raw)
            systems["A1 llama + repair"] = _repair(shipped_raw, pages)

        fpath = _frontier_fixture(key)
        if fpath.exists():
            frontier_raw = _load_claims(fpath)
            systems["B0 frontier, no repair"] = _no_repair(frontier_raw)
            systems["B1 frontier + repair"] = _repair(frontier_raw, pages)

        # Systems built FROM the L1 enumerator cannot be scored BY it — see _rule_extract.
        _TAUTOLOGICAL = {"R  rule-based (no LLM)"}
        # Different code path from the A/B rows; shown for context, never differenced.
        _UNMATCHED = {"S  shipped (full-doc)"}

        scored = {}
        for name, claims in systems.items():
            taut = name in _TAUTOLOGICAL
            rec = _lane_recall(claims, pages)
            grd = _lane_grounding(claims, pages)
            if taut:
                # Keep the raw values for the JSON dump (auditable), but null the headline
                # rates so no report can quote a self-referential 100%.
                rec = {**rec, "recall": None, "recall_raw_circular": rec["recall"]}
                grd = {**grd, "grounding_precision": None,
                       "grounding_precision_raw_circular": grd["grounding_precision"]}
            entry = {"claims": len(claims), "tautological": taut,
                     "unmatched": name in _UNMATCHED, **rec, **grd,
                     "gold": _lane_gold(claims, gold)}
            if taut:
                named = sum(1 for c in claims
                            if c.normalized_aspect and c.normalized_aspect != "uncategorized")
                entry["ontology_coverage"] = (named / len(claims)) if claims else None
            scored[name] = entry

        out[key] = {
            "label": label, "gold": gold_file, "cache": cache,
            "pages_cached": len(pages),
            "frontier_available": fpath.exists(),
            "frontier_fixture": str(fpath.relative_to(_REPO)) if fpath.exists() else None,
            "matched_arms": matched,
            "incumbent_fixture": str(ipath.relative_to(_REPO)) if matched else None,
            "systems": scored,
        }
    return out


# ─────────────────────────────────────────────────────────── generation (metered)

# Which env vars feed each provider's slot in LLMClient's round-robin pool. Used to
# BLANK every provider except the one under test — see `_isolate_provider`.
_POOL_VARS = {
    "nvidia": ("NVIDIA_API_KEYS", "NVIDIA_API_KEY"),
    "groq":   ("GROQ_API_KEYS", "GROQ_API_KEY"),
    "hf":     ("HF_API_KEYS", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
}


def _isolate_provider(provider: str) -> None:
    """Force a SINGLE-provider, single-model pool.

    Two traps this defuses, both of which silently corrupt a 'frontier' fixture:

    1. `LLMClient.__init__` builds a round-robin pool from *every* NVIDIA/Groq/HF key it
       finds, and `extract()` takes the pool path whenever that pool is non-empty. With a
       populated `.env` the pool is heterogeneous — NVIDIA 70B *and* Groq 8B *and* an HF
       8B — so the claims in one fixture come from a mix of models. `reingest_corpus.py`
       already blanks the small ones for exactly this reason ("8B = quality pollution");
       the baseline harness needs the same discipline, more so, because its whole purpose
       is attributing a difference to the model.
    2. The pool ALSO short-circuits the OpenAI/Anthropic branches: they are only reached
       when the pool is empty. So `OPENAI_API_KEY=... OPENAI_MODEL=gpt-4o` on a machine
       that has an NVIDIA key in `.env` never calls OpenAI at all — it calls llama and
       writes `"model": "gpt-4o"` into the meta, which is worse than failing.

    Blank rather than pop: imported modules re-run `load_dotenv()`, which repopulates a
    missing key from `.env` but leaves an empty one alone.
    """
    for names in (v for k, v in _POOL_VARS.items() if k != provider):
        for n in names:
            if n in os.environ:
                os.environ[n] = ""
    # OpenAI/Anthropic are only reachable with an EMPTY pool, so blank every pool var.
    if provider in ("openai", "anthropic"):
        for names in _POOL_VARS.values():
            for n in names:
                if n in os.environ:
                    os.environ[n] = ""


def generate(case: str, tag: str = "frontier", limit: int = 0, provider: str = "") -> Path:
    """Re-extract table claims from the COMMITTED page markdown with a different model.

    Input is the cached markdown, so the only variable versus the shipped fixture is the
    model. Writes a JSONL fixture; after this runs once, scoring is offline forever.
    """
    # Import FIRST: claim_extractor runs load_dotenv() at import time, so isolating
    # before the import would just be undone by it.
    from extractors.claim_extractor import ClaimExtractor, LLMClient

    if provider:
        _isolate_provider(provider)

    label, _fixture, cache, _gold = CASES[case]
    pages = _load_pages(cache)
    tables = [{"page_number": pg, "markdown": md} for pg, md in sorted(pages.items())]
    if limit:
        tables = tables[:limit]

    probe = LLMClient()
    if not probe.endpoints and probe.provider == "fallback":
        raise SystemExit(
            "No LLM credentials found — generation would silently fall back to the\n"
            "rule-based extractor and produce a fixture labelled 'frontier' that is\n"
            "nothing of the sort. Set one of NVIDIA_API_KEY / GROQ_API_KEY /\n"
            "OPENAI_API_KEY / ANTHROPIC_API_KEY (plus the matching *_MODEL) and retry.")

    # A fixture whose claims came from more than one model is not a measurement of any
    # model. Refuse rather than produce one — the failure this guards is silent.
    pool_models = sorted({e["model"] for e in probe.endpoints})
    pool_providers = sorted({e["provider"] for e in probe.endpoints})
    if len(pool_models) > 1:
        raise SystemExit(
            f"HETEROGENEOUS POOL — refusing to generate.\n"
            f"  providers: {', '.join(pool_providers)}\n"
            f"  models   : {', '.join(pool_models)}\n"
            f"LLMClient round-robins across all of these, so the fixture would be a blend "
            f"of models\nand could not be attributed to any one of them. Re-run with "
            f"--provider <{'|'.join(sorted(_POOL_VARS))}> to isolate a single provider.")

    if probe.endpoints:
        # Authoritative: what the pool will ACTUALLY call. The env-precedence guess below
        # is only a fallback for the pool-less OpenAI/Anthropic path.
        model = pool_models[0]
    else:
        model = (os.environ.get("OPENAI_MODEL") or os.environ.get("ANTHROPIC_MODEL")
                 or os.environ.get("NVIDIA_MODEL") or os.environ.get("GROQ_MODEL") or "?")
    print(f"[baseline] case={case} ({label})  pages={len(tables)}  provider={probe.provider}  model={model}")

    # Resume across runs. extract_from_table_markdown records each COMPLETED page and
    # deliberately does not record a failed one, so a re-run re-pays only for what broke.
    # Without this a late failure discards every page that already succeeded: a DNS drop
    # on 2026-08-11 threw away 26 good pages of 40 to save none, twice. Metered work
    # should never be lost to an unrelated failure at the end of it.
    ckpt = _FIX / f".ckpt_{tag}_{case}.jsonl"
    extractor = ClaimExtractor()
    claims = extractor.extract_from_table_markdown(
        tables, document_id=f"baseline_{case}", checkpoint_path=str(ckpt))

    # A page the extractor could not parse contributes zero claims, and once the fixture is
    # on disk that is indistinguishable from "the model found nothing here". A run
    # interrupted by a network failure therefore writes a file that looks like a measurement
    # and is not one: an incumbent run on 2026-08-11 lost 14/40 pages to DNS failure on one
    # document and 5/5 on the other, and this function wrote a 0-claim fixture without
    # complaint. Scored, that reads as "the model recalled 0% of table facts".
    #
    # `failed_units` counts pages whose LLM call exhausted its retries — the precise signal.
    # Counting zero-claim pages instead would conflate failures with pages that genuinely
    # hold no numeric table: on the frontier Tata run 13/40 pages were empty but only 2 had
    # failed, so a heuristic tuned to catch the bad run would have rejected the good one.
    failed = getattr(extractor, "failed_units", 0)
    loss = failed / len(tables) if tables else 0.0
    ceiling = float(os.environ.get("BASELINE_MAX_PAGE_LOSS", "0.10"))
    if not claims or loss > ceiling:
        raise SystemExit(
            f"REFUSING TO WRITE — {failed}/{len(tables)} pages ({100 * loss:.0f}%) failed "
            f"after retries,\nover the {100 * ceiling:.0f}% ceiling. See the [Failed] lines "
            f"above.\nA fixture missing this much of the document cannot be compared against "
            f"a complete\none. The checkpoint at {ckpt.name} retains every page that "
            f"succeeded, so re-running\nwhen the endpoint is healthy re-pays only for the "
            f"failures. Set BASELINE_MAX_PAGE_LOSS\nto accept the gap deliberately.")
    if failed:
        print(f"[baseline] NOTE: {failed}/{len(tables)} pages failed after retries — "
              f"recorded in the meta so the gap is visible to anything scoring this fixture.")

    covered = {c.provenance.page_number for c in claims
               if c.provenance and c.provenance.page_number is not None}
    missing = sorted({t["page_number"] for t in tables} - covered)

    out = _FIX / f"baseline_{tag}_{case}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for c in claims:
            f.write(json.dumps(c.model_dump(), default=str) + "\n")

    meta = out.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "case": case, "tag": tag, "provider": probe.provider, "model": model,
        "pool_providers": pool_providers, "pool_models": pool_models,
        "pool_size": len(probe.endpoints), "isolated_provider": provider or None,
        # Reasoning-style models spend completion tokens before emitting JSON, so the
        # 3000 default truncates them mid-object and the page is lost. Recorded because
        # it differs from the shipped fixture's run and a reader must be able to see that.
        "llm_max_tokens": int(os.environ.get("LLM_MAX_TOKENS", "3000")),
        "temperature": 0.1,
        "pages": len(tables), "claims": len(claims), "source_cache": cache,
        # A page lost to a failed call scores as "the model found nothing here" unless the
        # gap is recorded. Anything comparing two fixtures must be able to see how much of
        # each document was actually reached — hence both counts, and the page list.
        "failed_pages": failed,
        "pages_with_claims": len(covered),
        "pages_without_claims": missing,
        "note": "Generated from committed Docling page markdown, so the input is "
                "byte-identical to the shipped fixture's table surface and the model is "
                "the only variable. TABLE SURFACE ONLY — no text/narrative claims.",
    }, indent=2), encoding="utf-8")
    print(f"[baseline] wrote {out.relative_to(_REPO)}  ({len(claims)} claims)")
    print(f"[baseline] wrote {meta.relative_to(_REPO)}")
    return out


# ─────────────────────────────────────────────────────────── reporting

def _pct(v, width=6):
    # +1 because the numeric branch appends a literal "%" after the width-padded number.
    return f"{'--':>{width + 1}}" if v is None else f"{100 * v:{width}.1f}%"


def _print(res):
    for key, d in res.items():
        print(f"\n{'=' * 100}\n{d['label']}   [{d['pages_cached']} cached pages -> {d['gold']}]\n{'=' * 100}")
        print(f"{'system':<26}{'claims':>7}{'RECALL':>10}{'GROUND':>9}"
              f"{'gold':>8}{'match':>8}   interpretation")
        print("-" * 100)
        for name, s in d["systems"].items():
            g = s["gold"]
            mr = g["match_rate"]
            notes = []
            if s.get("unmatched"):
                notes.append("different code path (full-doc) — context only, never differenced")
            if s.get("tautological"):
                notes.append("L1/L2 circular (built from the L1 enumerator) — suppressed")
            if mr is not None and mr < 0.5:
                notes.append("gold match thin")
            print(f"{name:<26}{s['claims']:>7}{_pct(s['recall'], 9)}"
                  f"{_pct(s['grounding_precision'], 8)}"
                  f"{(g['extraction_score'] if g['extraction_score'] is not None else 0):>8.1f}"
                  f"{_pct(mr, 7)}"
                  + ("  << " + "; ".join(notes) if notes else ""))
            if s.get("ontology_coverage") is not None:
                print(f"{'':<26}{'':>7}{'':>9}{'':>8}{'':>8}{'':>7}"
                      f"     keyword-reachable rows: {100 * s['ontology_coverage']:.1f}%"
                      f"  (the rest is what needs a model)")

        print("-" * 100)
        if not d.get("matched_arms"):
            print("  [UNMATCHED ARMS] The A row is the SHIPPED fixture, which came from a")
            print("            full-document run (text + tables) while any B row comes from the")
            print("            table-only path. Their compositions differ, so a difference between")
            print("            them is not attributable to the model. Generate a matched A row:")
            print(f"              python backend/scripts/run_baselines.py --generate incumbent "
                  f"--case {key} --provider <p>")
        _print_tradeoff(d["systems"])
        if not d["frontier_available"]:
            print("  [NOT RUN] frontier cells B0/B1 are missing — the 2x2 is HALF EMPTY, so no")
            print("            interaction term can be computed and the headline question")
            print("            ('does repair survive a better model?') is still UNANSWERED.")
            print(f"            Generate with:  python backend/scripts/run_baselines.py "
                  f"--generate frontier --case {key}")
        elif not d.get("matched_arms"):
            # Both rows exist but are not comparable. Printing the interaction anyway is
            # how a reader ends up quoting it; withholding it is the whole point of the
            # check above.
            print("  2x2 INTERACTION — WITHHELD. Both rows exist, but the A row is not")
            print("            comparable to the B row (see [UNMATCHED ARMS]), so any")
            print("            interaction term would be attributing a code-path difference")
            print("            to the model. Generate the matched incumbent arm first.")
        else:
            _print_interaction(d["systems"])

        print("\n  LANE NOTES")
        print("    RECALL  L1 distinct table facts recovered — mechanical denominator, FAIR across systems.")
        print("    GROUND  L2 emitted values that occur in the source page — mechanical, FAIR across systems.")
        print("    gold    L3 committed-gold composite — BIASED: the gold was sampled from the SHIPPED")
        print("            extractor's own output, so another system is only scored where its sentences")
        print("            happen to match. 'match' is that coverage. Directional only.")


def _print_tradeoff(systems: dict):
    """What the repair layer COSTS, which run_ablation.py structurally cannot show.

    The ablation reports the repair layer as monotone gain because every stage is scored
    on a precision-family composite with no recall term. Add a recall lane and the
    furniture drop turns out to be a TRADE, not a free win: it deletes claims, and some
    of what it deletes were real table facts. A paper that reports the gain without the
    cost is reporting half a result.
    """
    pairs = [("llama", "A0 llama, no repair", "A1 llama + repair"),
             ("frontier", "B0 frontier, no repair", "B1 frontier + repair")]
    shown = False
    for tier, raw_name, rep_name in pairs:
        if raw_name not in systems or rep_name not in systems:
            continue
        raw, rep = systems[raw_name], systems[rep_name]
        if raw["recall"] is None or rep["recall"] is None:
            continue
        d_recall = rep["recall"] - raw["recall"]
        d_gold = (rep["gold"]["extraction_score"] or 0) - (raw["gold"]["extraction_score"] or 0)
        dropped = raw["claims"] - rep["claims"]
        if not shown:
            print("  REPAIR-LAYER TRADE-OFF — the cost side, invisible to run_ablation.py")
            shown = True
        note = ("free win — no recall lost" if d_recall >= -0.005
                else f"PAID FOR: {abs(100 * d_recall):.1f}pp of table-fact recall")
        print(f"    {tier:<9} gold {d_gold:+6.1f}   recall {100 * d_recall:+6.1f}pp   "
              f"claims dropped {dropped:>4}   -> {note}")


def _verdict(d_llama: float, d_frontier: float, eps: float = 0.005) -> str:
    """Read the two repair deltas, not just their difference.

    The previous rule was `interaction > -0.02 -> "repair SURVIVES"`, which is wrong in
    the case that actually occurred: repair COST llama 5.5pp of recall and did nothing
    for the frontier model (-5.5, 0.0). That is a positive interaction (+5.5pp) and the
    old rule printed "repair SURVIVES the model upgrade" — a conclusion the numbers
    contradict. What survives has to be judged from d_frontier's own sign, with the
    interaction describing only how the two tiers differ.
    """
    helps_f, helps_l = d_frontier > eps, d_llama > eps
    hurts_f, hurts_l = d_frontier < -eps, d_llama < -eps
    if helps_f and helps_l:
        return ("repair helps at BOTH tiers -> complementary to scale"
                if d_frontier >= d_llama - eps
                else "repair helps at both tiers but SHRINKS with scale")
    if helps_f and not helps_l:
        return "repair helps ONLY the stronger model"
    if helps_l and not helps_f:
        return "repair helps the weaker model ONLY -> gain is absorbed by scale; reframe to cost"
    if hurts_f or hurts_l:
        return "repair COSTS on this lane at " + ("both tiers" if hurts_f and hurts_l
                                                  else ("the frontier tier" if hurts_f else "the llama tier"))
    return "repair is INERT on this lane at both tiers"


def _print_interaction(systems: dict):
    """The point of the whole harness: does the repair delta survive a better model?"""
    def rec(n):
        return systems[n]["recall"]

    def grd(n):
        return systems[n]["grounding_precision"]

    rows = [("recall", rec), ("grounding", grd)]
    print("  2x2 INTERACTION — delta(repair) at each model tier")
    for metric, fn in rows:
        a = fn("A1 llama + repair"), fn("A0 llama, no repair")
        b = fn("B1 frontier + repair"), fn("B0 frontier, no repair")
        if None in a or None in b:
            continue
        d_llama, d_frontier = a[0] - a[1], b[0] - b[1]
        inter = d_frontier - d_llama
        print(f"    {metric:<11} llama {100 * d_llama:+6.1f}pp   "
              f"frontier {100 * d_frontier:+6.1f}pp   interaction {100 * inter:+6.1f}pp"
              f"   -> {_verdict(d_llama, d_frontier)}")
    print("    NOTE  these lanes see the repair layer only where it ADDS OR REMOVES a claim")
    print("          or changes a value. Aspect/type/unit corrections are invisible here by")
    print("          construction — L1/L2 read metric.value and page only. A zero delta on")
    print("          this table is not evidence that the gate did nothing; it is evidence")
    print("          that it did nothing THESE LANES CAN SEE. The gold composite is where")
    print("          those corrections land, and it is not comparable across models.")


_THIN_MATCH = 0.5   # below this the gold composite is computed on too few claims to mean anything


def _gold_cell(g: dict) -> str:
    """Never render a bare gold score off a thin match.

    A1 on the matched Tata arm scores 100.0 from a 2% match rate — ONE gold claim. In a
    markdown table that reads as a perfect score, and markdown is what gets pasted into a
    paper. The text printer flags this in a side note; the table has to carry it inline or
    the warning does not travel with the number.
    """
    score, mr = g["extraction_score"], g["match_rate"]
    if score is None or mr is None:
        return "n/a"
    if mr < _THIN_MATCH:
        return f"n/a *(match {100 * mr:.0f}%)*"
    return f"{score:.1f}"


def _print_markdown(res):
    print("\n<!-- generated by backend/scripts/run_baselines.py — do not hand-edit -->")
    for key, d in res.items():
        print(f"\n**{d['label']}** — {d['pages_cached']} cached pages\n")
        print("| system | claims | fact recall | grounding precision | gold composite | gold match |")
        print("|---|--:|--:|--:|--:|--:|")
        for name, s in d["systems"].items():
            g = s["gold"]
            note = " ⚠︎" if s.get("unmatched") else ""
            print(f"| {name}{note} | {s['claims']} | {_pct(s['recall']).strip()} | "
                  f"{_pct(s['grounding_precision']).strip()} | "
                  f"{_gold_cell(g)} | {_pct(g['match_rate']).strip()} |")

        if not d["frontier_available"]:
            print("\n> **Incomplete.** The frontier rows are not generated, so the 2×2 has no "
                  "interaction term and the central question is unanswered.")
        elif not d.get("matched_arms"):
            print("\n> **Not comparable.** The A row is the shipped fixture (full-document "
                  "run) and the B row is table-only, so a difference between them is not "
                  "attributable to the model. Generate the matched incumbent arm.")
        else:
            print()
            _print_interaction_markdown(d["systems"])

        if any(s.get("unmatched") for s in d["systems"].values()):
            print("\n> ⚠︎ marks a row from a **different code path** (full-document run, text "
                  "and tables). It is shown for context and must never be differenced against "
                  "the matched A/B rows.")
        print("\n> Fact recall and grounding precision use mechanical, system-independent "
              "denominators and are comparable across rows. The gold composite is **not** — "
              "the gold set was sampled from the shipped extractor's output, so another system "
              "is scored only where its source sentences coincide. Where that match is under "
              f"{100 * _THIN_MATCH:.0f}% the score is withheld as `n/a`: it would be computed "
              "on a handful of claims and reads as a real number.")


def _print_interaction_markdown(systems: dict):
    """The interaction, plus the reason a zero here is not a verdict on the layer."""
    print("| Δ(repair) | fact recall | grounding |")
    print("|---|--:|--:|")
    rows = []
    for tier, raw, rep in (("llama-3.3-70b", "A0 llama, no repair", "A1 llama + repair"),
                           ("frontier", "B0 frontier, no repair", "B1 frontier + repair")):
        if raw not in systems or rep not in systems:
            return
        r = systems[rep]["recall"], systems[raw]["recall"]
        g = systems[rep]["grounding_precision"], systems[raw]["grounding_precision"]
        if None in r or None in g:
            return
        rows.append((tier, r[0] - r[1], g[0] - g[1]))
        print(f"| {tier} | {100 * (r[0] - r[1]):+.1f}pp | {100 * (g[0] - g[1]):+.1f}pp |")
    if len(rows) == 2:
        print(f"| **interaction** | {100 * (rows[1][1] - rows[0][1]):+.1f}pp | "
              f"{100 * (rows[1][2] - rows[0][2]):+.1f}pp |")
    print("\n> These two lanes read only a claim's value and page, so they observe the "
          "deterministic layer **solely where it adds, removes or rewrites a claim**. "
          "Aspect, type and unit corrections cannot appear here. A zero is therefore not "
          "evidence that the layer does nothing — only that it does nothing these lanes can "
          "see, and the gold lane that would see it is not comparable across models.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="External baselines: 2x2 model x repair, plus a no-LLM floor.")
    ap.add_argument("--case", choices=sorted(CASES), help="restrict to one document")
    ap.add_argument("--generate", metavar="TAG", nargs="?", const="frontier",
                    help="METERED: re-extract table claims with the configured model and "
                         "write a fixture (requires --case)")
    ap.add_argument("--limit", type=int, default=0, help="generate: cap pages (smoke test)")
    ap.add_argument("--provider", choices=["nvidia", "groq", "hf", "openai", "anthropic"],
                    help="generate: isolate ONE provider by blanking every other pool key. "
                         "Required in practice — LLMClient otherwise round-robins across "
                         "every NVIDIA/Groq/HF key in .env and blends models into one fixture.")
    ap.add_argument("--markdown", action="store_true", help="paper-ready markdown table")
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()

    if a.generate:
        if not a.case:
            raise SystemExit("--generate requires --case (it spends money; be explicit)")
        generate(a.case, tag=a.generate, limit=a.limit, provider=a.provider or "")
        sys.exit(0)

    res = run([a.case] if a.case else None)
    _print_markdown(res) if a.markdown else _print(res)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {a.json_out}")
