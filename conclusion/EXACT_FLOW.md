# ESGenuine — Exact Flow

**Purpose.** A complete, no-shortcuts trace of what happens to a PDF from the moment it
arrives to the moment a number appears on the dashboard — with every threshold, constant,
and decision rule named, and every claim in this document traceable to a file and line.

**How to read this.** Sections 1–14 follow *execution order*. Section 15 is the evaluation
methodology (the part a report's Methods section is built from). Section 16 gives the data
contracts. Section 17 lists defects found while writing this — they are real and unfixed.

**Provenance rule for this document:** every constant below was read out of the source, not
recalled. Where behaviour is unverified, it says so.

---

## 1. The whole thing in one paragraph

A PDF is validated and profiled, then decomposed into typed layout blocks, a section tree,
sentences, structured table rows, and claim candidates — each carrying page and bounding-box
provenance. Text windows and table markdown are sent to an LLM which returns structured
claims. Those claims pass through a **deterministic repair layer** that maps free-text
aspects onto a controlled taxonomy, repairs fiscal-year misalignment, verifies each numeric
value against its own source, applies rule-based corrections, and drops form furniture. The
survivors are embedded, deduplicated by content hash, and written to a partitioned Postgres
table. Downstream, vector neighbourhoods feed an NLI contradiction engine, a greenwashing
taxonomy produces flags, and a count-weighted integrity score aggregates them. A React
dashboard reads claims directly from Supabase; everything else goes through FastAPI.

```
PDF ─► [0] triage ─► [1] blocks ─► [2] layout ─► [3] sections ─► [4] sentences
                                                                      │
                            [5] tables (Docling) ──────────┐          │
                                                           ▼          ▼
                                          [6] candidates ─► [7] chunks ─► [8] provenance
                                                                      │
                                                    ┌─────────────────┘
                                                    ▼
                                     [9] LLM extraction (2 paths)
                                                    │
                                     [10] validate + enrich
                                                    │
                          ┌─────────────────────────▼─────────────────────────┐
                          │  [11] DETERMINISTIC REPAIR LAYER  (S1 … S5)       │
                          └─────────────────────────┬─────────────────────────┘
                                                    ▼
                                     [12] embed + store (Supabase)
                                                    │
                    ┌───────────────────────────────┼───────────────────────────┐
                    ▼                               ▼                           ▼
        [13] contradictions            [13] greenwash + integrity      [14] satellite
                    └───────────────────────────────┼───────────────────────────┘
                                                    ▼
                                        [15] API + dashboard
```

---

## 2. Stage 0 — Ingest & triage

**File:** `backend/src/parsers/pdf_parser.py` · `Step0_IngestTriage`

Runs *before* any heavy parsing so a bad file fails fast and loudly.

| Check | Rule | On failure |
|---|---|---|
| Exists | `Path.exists()` | `PDFValidationError` |
| Openable | `fitz.open()` | `PDFValidationError` — "corrupt or unsupported" |
| Not encrypted | `doc.is_encrypted and not doc.authenticate("")` | `PDFValidationError` |
| Non-empty | `page_count == 0` | `PDFValidationError` |

**Profiling produced:**

- `file_hash` — full-file **SHA-256**, streamed in 8 KB chunks. This is the dedup key, and
  it is computed identically here and in `supabase_ingest.sha256_file`, so the same PDF
  hashes the same on either path.
- `extraction_path` — samples `min(5, page_count)` pages; `digital` if mean characters per
  page ≥ **100**, else `scanned`.
- `multi_column` flag — over the first 3 pages, if the spread of text-block x-origins
  exceeds **40% of page width**, the page is treated as multi-column.
- `warnings` — a scanned PDF gets an explicit advisory that extraction will be sparse
  without OCR.

**Why it matters for a report:** this is the stage that stops the system from silently
producing an empty result for a scanned document — the failure mode that makes naive
pipelines look like they "found nothing" when they never could have.

---

## 3. Stage 1 — Structural extraction

**Class:** `Step1_StructuralExtractor` · **Library:** PyMuPDF (`fitz`)

Iterates `page.get_text("dict", flags=TEXT_PRESERVE_WHITESPACE)`. For each block:

- **Image blocks are skipped** (`block["type"] != 0`).
- Spans are concatenated; the **largest span font size** wins for the block, and `is_bold`
  is true if any span's font name contains "bold".
- Text passes through **`ftfy.fix_text`** to repair double-encoded UTF-8
  (`"Indiaâ€™s"` → `"India's"`) — with a graceful no-op fallback if ftfy is absent.
- Blocks shorter than **3 characters** are dropped.
- `block_id = f"p{page+1}_b{block_idx}"` — stable and human-readable.

**Output:** `RawBlock(block_id, page_number, text, bbox, font_size, font_name, is_bold, line_count)`

---

## 4. Stage 2 — Layout classification

**Class:** `Step2_LayoutClassifier`

Purely rule-based, relative to the **median font size** of the document (default 10.0 if no
fonts resolve). Rules are applied in this order — first match wins:

| Class | Rule |
|---|---|
| `page_header` | `bbox.y0 < 60` |
| `page_footer` | `bbox.y1 > 750` |
| `footnote` | `font_size < 0.75 × median` **and** `bbox.y1 > 650` |
| `heading` | (`font_size > 1.2 × median` **or** `is_bold`) **and** `len(text) < 200` **and** `line_count ≤ 3` |
| `caption` | `font_size < 0.85 × median` **and** `len(text) < 150` **and** contains one of `figure / chart / graph / source: / note:` |
| `list` | matches `^[\s]*[•\-–—\*\d]+[\.\)]\s` |
| `paragraph` | default |

**Repeated furniture removal.** Headers and footers are keyed by their first 50 characters;
anything appearing on `max(3, 0.6 × total_pages)` pages or more is treated as a repeater and
filtered. This is what removes the company name and page number from every page.

---

## 5. Stages 3–4 — Section tree and sentences

- **Step 3** reconstructs a document hierarchy from heading levels into a `SectionNode` tree,
  using **NetworkX** where available and a dict fallback otherwise (the fallback prints a
  warning at import).
- **Step 4** segments blocks into `Sentence` records with **spaCy**, each carrying
  `sentence_id`, `block_id`, `page_number`, `section_id`, `section_title`, `bbox`, and its
  index within the block.

The design note at the top of the file is the point worth quoting in a report:

> `PDF → structured blocks → document graph → sentences → candidate claims → chunking`
> **NOT** `PDF → chunks`

Chunking happens *only* at Step 7, after structure is understood. Most RAG pipelines chunk
first and lose the layout signal permanently.

---

## 6. Stage 5 — Table extraction

**Files:** `parsers/docling_tables.py`, `parsers/_docling_worker.py`,
`extractors/table_parser.py`, `extractors/table_extractor.py`, `extractors/vlm_tables.py`

Tables are extracted as **markdown per page** by Docling, run in a **separate worker
process** (`_docling_worker.py`) — Docling pulls heavy model dependencies and isolating it
keeps the main process importable without them.

The resulting page markdown is cached to
`backend/tests/eval/fixtures/docling_<doc>.json` as
`[{page_number, markdown}, …]`. **This cache is the substrate the entire evaluation stack
runs on** — every offline harness reads it instead of re-parsing a PDF.

Switches: `USE_DOCLING_TABLES=1`, `USE_VLM_TABLES=1` (the ingest endpoint sets the latter
when `use_vlm_tables` is passed).

---

## 7. Stages 6–8 — Candidates, chunks, provenance

- **Step 6** scores each sentence for claim likelihood (rule-based, 0–1) into a
  `ClaimCandidate` with a `features` dict — the transparent pre-filter that keeps the LLM
  from being asked about every sentence in a 90-page document.
- **Step 7** builds a `SemanticChunk` per candidate:
  `context_before | target_sentence | context_after`, plus a concatenated `full_text` for
  model input. The context window is what lets the LLM resolve "it fell by 12%".
- **Step 8** emits a `ProvenanceRecord` binding
  `chunk_id → sentence_id → block_id → page → section → bbox (+ table_reference)`.

**This is the chain that makes every downstream number auditable back to a rectangle on a
page.** It is the single most defensible property of the system and should lead any Methods
section.

---

## 8. Stage 9 — LLM extraction

**File:** `backend/src/extractors/claim_extractor.py` (927 lines)

### 8.1 Two extraction paths

| Path | Entry | Unit of work | Prompt |
|---|---|---|---|
| **Text** | `extract_from_sections(...)` | char-budgeted section window (**3500 chars**, `build_section_windows`) | `SECTION_EXTRACTION_PROMPT` |
| **Table** | `extract_from_table_markdown(...)` | one **page** of Docling markdown, truncated to **8000 chars** | `TABLE_CLAIMS_PROMPT` |

There is also `AAMLT_EXTRACTION_PROMPT` for the per-chunk path.

### 8.2 The LLM client — `LLMClient`

**A round-robin pool, not a single provider.** `_build_pool()` constructs one endpoint per
key found in:

| Provider | Env vars | Default model | Endpoint |
|---|---|---|---|
| NVIDIA NIM | `NVIDIA_API_KEYS`, `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` | `integrate.api.nvidia.com/v1/chat/completions` |
| Groq | `GROQ_API_KEYS`, `GROQ_API_KEY` | `llama-3.1-8b-instant` | `api.groq.com/openai/v1/chat/completions` |
| HuggingFace | `HF_API_KEYS`, `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN` | `meta-llama/Llama-3.1-8B-Instruct` | `router.huggingface.co/v1/chat/completions` |

Comma-separated key lists are supported and de-duplicated.

**Critical control-flow fact:** if the pool is **non-empty**, `extract()` takes the pool path
and the OpenAI / Anthropic branches are **unreachable**. They are only consulted when the
pool is empty. This is the trap documented in
[`../docs/CROSSCHECK_FINDINGS.md`](../docs/CROSSCHECK_FINDINGS.md) §2 — setting
`OPENAI_API_KEY` on a machine that has an NVIDIA key never calls OpenAI.

**Reliability primitives:**

- `_next_endpoint()` — round-robin, **skipping keys in cooldown**; if every key is cooling
  down it picks the one whose cooldown expires soonest, so it can never deadlock.
- `COOLDOWN_S = 60` — a key that times out, 429s or 5xxs sits out a minute, shedding load
  onto healthy keys.
- **Streaming** (`stream=True`) — the read timeout applies to the *gap between chunks*, not
  the whole generation, so a slow-but-flowing 70B response survives where a non-streaming
  read of the full body would time out.
- `timeout=(15, LLM_STALL_TIMEOUT)` — connect 15 s, stall default **180 s**.
- `temperature=0.1`, `response_format={"type": "json_object"}`,
  `max_tokens=LLM_MAX_TOKENS` (default **3000**).

> **Reproducibility note for a report:** temperature is 0.1, not 0. Extraction is therefore
> *not* bit-reproducible end to end. Everything downstream is, because raw outputs are frozen
> as fixtures.

### 8.3 Checkpointing

**File:** `backend/src/extractors/checkpoint.py` · `ClaimCheckpoint`

When `checkpoint_path` is supplied, each **completed** work unit is recorded keyed
`tbl::<page>` or `sec::<index>`, with its claims. A re-run calls `cp.load()`, skips finished
units, and re-pays only for the rest.

**A failed unit is deliberately *not* recorded** (`claim_extractor.py:843`) so a resume
retries exactly what broke. Corrupt lines are dropped on scan with a printed count.

### 8.4 Concurrency

`max_workers` defaults from `_default_workers()`; overridable by `NVIDIA_CONCURRENCY`.
Failures increment `self.failed_units`, which is the authoritative count of pages lost —
distinct from pages that legitimately contained no numeric table.

---

## 9. Stage 10 — Validation & enrichment

**Function:** `_validate_and_enrich(raw, chunk, document_id)`

Every LLM object is coerced into the Pydantic `ExtractedClaim` (`extractors/models.py`).
Validation is **salvage-oriented**, not strict — e.g. `TimeField.baseline_year` accepts
`"2022-04-01"` or `"FY2022"` and regexes the year out rather than discarding the claim.

Assigned here, in order:

1. `claim_type` ← `ClaimAnalyzer.classify_type(action_verb, target_sentence)`
   - `TARGET_VERBS = {aim, plan, intend, commit, target, aspire, will, goal}`
   - `PERFORMANCE_VERBS = {reduced, increased, achieved, delivered, improved, generated, maintained}`
   - Action verb checked first, then the surrounding sentence; default `narrative`.
2. `normalized_aspect` ← `ESGOntology.normalize_aspect(raw_aspect)` (§10.1)
3. `metric_family` ← `SignatureGenerator.generate_metric_family(normalized_aspect)`
4. `metric_key` ← `generate_metric_key(normalized_aspect, unit)`
5. `time_bucket`, `location_scope`, `claim_signature`
6. `groundability_score` + `observability_type` ← `GroundabilityClassifier.score()`
7. `vagueness_score` ← `ClaimAnalyzer.compute_vagueness()`

### 9.1 Groundability scoring — exact

```
points  = 1.0  if a numeric metric is present
        + 1.0  if a start or end date is present
        + location bonus:  facility 1.0 | city/region 0.75 | country 0.5 | global 0.15
        + 1.0  if the aspect matches an OBSERVABLE_ASPECTS keyword

score   = min(points / 2.5, 1.0)
score  *= {performance: 1.0, target: 0.6, other: 0.5}      # claim-type multiplier
          (optical_possible floors the multiplier at 0.7)
```

The `global` bonus is only **0.15** because a "global" location is usually an NLP false
positive, not a real scope. The claim-type multiplier was added because forward-looking
targets were scoring as groundable purely for citing a number.

`observability_type` ∈ `directly_observable` (metric+location+time) | `reported_metric`
(metric only) | `optical_possible` (spatial aspect) | `not_observable`.

### 9.2 Vagueness scoring — exact

```
0.5  no metric   +   0.3  no time   +   0.2  no location
+0.2 if claim_type == narrative   |   +0.1 if target
capped at 1.0
```

### 9.3 Table path extras

For table claims only (`claim_extractor.py:862-868`), **before** the claim is returned:

1. `fix_fy_column(claim, page_markdown)` — the FY repair runs **at extraction time**.
2. `_value_in_source(value, markdown)` — failure appends `value_not_in_table`.

> **This is the single most important fact for interpreting the ablation.** Stages S2 and S3
> of the repair layer are *already applied* before a fixture is written, which is why
> replaying them measures ≈0. See §17.2.

---

## 10. Stage 11 — The deterministic repair layer

**File:** `backend/src/extractors/quality_gate.py` (493 lines) · replayed by
`backend/scripts/run_ablation.py` as stages S1–S5.

This is the project's actual contribution. It runs **after** the LLM, needs **no** model, and
costs **0.45 ms/claim**.

### 10.1 S1 — Ontology normalisation

`ESGOntology.normalize_aspect(raw)` maps free text onto a controlled taxonomy of ~50 nodes
across `emissions.* / energy.* / water.* / waste.* / biodiversity.* / social.* / governance.*`.

**Matching algorithm — word-boundary, with specificity tie-breaking:**

1. **Direct hit** — raw string is exactly a keyword → that node.
2. **Word-boundary match** (`\b…\b`, *not* substring) with two competing rules:
   - **Rule A** — a keyword phrase found *inside* the raw aspect ⇒ raw is specific ⇒
     the **longest** matching keyword wins (`"gender diversity"` beats `"diversity"`).
   - **Rule B** — the raw aspect found *inside* a keyword ⇒ raw is generic ⇒ the
     **shortest** containing keyword wins (raw `"emissions"` → `"total emissions"`,
     not `"value chain emissions"`).
   - **A beats B.**
3. Fallback → `uncategorized`.

**Why word boundaries matter:** the previous substring rule made raw `"diversity"` match the
keyword `"biodiversity"` — a systematic mislabel of workforce-diversity claims as
environmental ones. `\b` eliminates that class because *diversity* has no word boundary
inside *biodiversity*. This is a good concrete example for a Methods section: the failure was
found by evaluation, not by inspection.

**Deliberately keyword-free nodes.** `social.diversity.gender.female/.male`,
`social.workforce.permanent/.contractual` have **empty** keyword lists. A cohort keyword like
`"men employees"` would be Rule-B bait (generic raw `"employees"` → shortest containing
keyword → wrong cohort). Cohort routing happens **only** in the gate, from sentence text.

### 10.2 S2 — Fiscal-year column repair

`fix_fy_column(claim, markdown)`. Walks the page markdown maintaining the most recent
header's column→FY map (so multi-table pages work). Acts **only** when:

- the row label names **exactly one** FY (`\bfy\s*'?\s*(?:20)?(\d{2})\b`),
- the emitted value is found under a **different** FY's column, and
- the labelled FY's cell in the same row parses as a number.

Flag: `fy_column_fixed`.

### 10.3 S3 — Source-value verification

`_value_in_source(value, sentence)` tokenises numbers tolerating **both** Western
(`1,234,567`) and **Indian** (`3,86,71,851`) digit grouping, and accepts float equality
within a `1e-9` relative tolerance.

- Text claims failing this get `value_not_in_source`.
- Table claims are exempt here — their `source_sentence` is only the row label, so they are
  verified against the page markdown at extraction time instead.

### 10.4 S4 — Rule-based gate (`apply_gate`)

**Corrections** — mutate the claim, recompute derived keys, log a flag:

| Flag | Rule |
|---|---|
| `scope_fixed` | "Scope 1/2/3" in the row text beats a generic `emissions.*` label |
| `gender_fixed` | male/female/gender rows are workforce diversity, never biodiversity |
| `waste_water_fixed` | waste rows mislabelled `water.*` |
| `aspect_fixed` | ~35 regex backstops for taxonomy-gap classes |
| `type_fixed` | a table row carrying a value is `performance` (or `target` under future markers), not `narrative` |

**Suspicions** — flag only, **nothing is silently dropped**:

| Flag | Rule |
|---|---|
| `implausible_unit` | unit dimension impossible for the aspect (LTIFR in headcount, emissions in USD) |
| `value_not_in_source` | see S3 |

Every correction calls `_refresh_keys()` so `metric_family`, `metric_key` and
`claim_signature` follow the new aspect — otherwise partition routing and cross-report
blocking would silently disagree with the label.

**The backstop regexes are the bulk of the file** (~60 patterns): per-pollutant splits
(PM/SOx/NOx/VOC are *different substances* — one shared key made their rows pairwise
"contradict"), waste disposal routes (re-used / landfilled / incinerated are different
quantities, not restatements), and gender/employment cohorts.

### 10.5 S5 — Furniture filter (`is_furniture`)

Table claims are **exempt** (a label-only source is expected there). A text claim is
furniture if:

- the sentence is empty, **or**
- it ends in `?`, starts with `please specify | not applicable | if yes`, or contains
  `disclose`, **or**
- it contains **no digit** and either matches `^(no\.|number) of\b`, or is **< 80 chars**
  while the claim carries a numeric metric — i.e. the number cannot have come from this
  sentence (`"Permanent Employees"` + `22,372`).

**This is the precision lever and the recall cost.** It removes 34 claims on the statutory
filing, some of which are genuine facts — the −5.5 pp recall trade in §15.4.

---

## 11. Stage 12 — Embedding and storage

**File:** `backend/src/extractors/supabase_ingest.py`

1. `sha256_file(path)` → content hash.
2. `find_report_by_file_hash()` → if present, ingest **short-circuits** and returns the
   existing report rather than duplicating claims.
3. `_delete_existing_claims(report_id, doc_id)` → **delete-then-insert idempotency**. If the
   delete fails (e.g. RLS forbids it) the failure is printed loudly, because silently
   proceeding would double-write.
4. Embeddings via `model_config.load_embedder()` — **`bge-base-en-v1.5` pinned to commit
   `a5beb1e3`**.
5. `_upsert_report()` keyed on `report_id`, storing `file_hash` and `claim_count`.

**Credentials:** the write path prefers `SUPABASE_SERVICE_ROLE_KEY` (bypasses RLS, required
once `2026-08-09_enable_rls.sql` demotes anon to SELECT-only), falling back to the anon key
so local dev keeps working. Server-side only.

### 11.1 Schema

`claims` is **LIST-partitioned on `metric_family`** with five partitions plus DEFAULT, and
carries `pgvector` embeddings with HNSW indexes per partition.

> ⚠️ **The partitioning is ~50% inert.** See §17.1 — this is a real defect.

---

## 12. Stage 13 — Reasoning

### 12.1 Candidate retrieval — `reasoning/retrieval.py`

"Stanford metric-signature blocking": instead of O(N²) pairwise comparison, each claim is
compared only against claims sharing its **`metric_family`**, retrieved by vector similarity.

`match_claims` RPC parameters: `match_threshold=0.85`, `match_count=10`,
`filter_family=<metric_family>`, `exclude_claim_id=<self>`.

**Failure handling is deliberate.** One transient reconnect+retry (disconnect / timeout /
connection / reset), then `RetrievalError` is **raised, not swallowed**. The docstring is
explicit about why: the old `except: return []` made a dead RPC indistinguishable from "no
contradictions found".

### 12.2 Contradiction engine — `reasoning/nli_engine.py`

- **Numeric path first** — most pairs are decided by strict numeric comparison after
  canonical unit conversion (`UnitCanonicalizer`), never touching the model.
- **Textual path** — `distilbert-base-uncased-mnli`, **pinned to commit `cfa538a0`**, loaded
  **lazily** on first textual comparison (weights are ~250–350 MB and the numeric path
  usually suffices). The module is constructible without torch installed, so numeric
  reasoning is unit-testable in isolation.
- Fed as a genuine **premise/hypothesis pair** (`{"text": a, "text_pair": b}`).
  A previous version concatenated both into one string and ran single-sequence
  classification — every "textual" verdict was meaningless. Worth citing as a lesson.
- Contradiction iff `label == contradiction` **and** `score > 0.6`.
- **Subgroup catch-all guard:** one `metric_key` routinely holds sibling categories
  (male/female headcounts, waste disposal routes, PM/SOx/NOx). Comparing those pairwise
  exploded into C(n,2) false "value mismatch" flags — **307 on `tata_power_2024` alone**.
  The Round-3 taxonomy split plus this guard is the fix.

**Live state:** `contradictions` table holds **16** rows.

### 12.3 Greenwashing taxonomy — `reasoning/greenwash_taxonomy.py`

Emits typed flags with severity ∈ `Critical | High | Medium | Low | None`, e.g.
`DISCLOSURE_GAP` (High), `ASPIRATIONAL_HEAVY` (Medium), `CONTRADICTION` (severity derived).
Flags sort by `_SEV_RANK` descending.

### 12.4 Integrity score — `reasoning/integrity_report.py`

`build_report()` is **pure** (no I/O), so it is unit-testable; the API layer fetches inputs.

```
score = 100 − Σ over flags ( severity_weight × prevalence )

severity_weight = { Critical: 50, High: 30, Medium: 16, Low: 6, None: 0 }
prevalence      = claims_triggering_flag / total_claims
                  (structural flags with no per-claim count use a fixed 0.5)
score clamped to [0, 100]
```

**Grades:** A ≥ 85 · B ≥ 70 · C ≥ 55 · D ≥ 40 · F otherwise.
**Report version 2.3** (2.0 count-weighting, 2.1 honour human reviews, 2.2 fact-check, 2.3
satellite).

**Why count-weighting exists:** the original flat per-flag penalty gave *every* real report
an F, because every real report trips nearly all flag types — zero discriminating power.

Fact-check folds in additively: a bonus capped at **10 points**, gated on
`weighted_credibility ≥ 0.7` and `coverage ≥ 0.15`, so a trivially-checked report cannot buy
points.

> ⚠️ **The severity weights are hand-set and have never been validated against any external
> criterion.** The system's headline output is uncalibrated, and every document in the repo
> says so. Do not report it as an accuracy result.

### 12.5 The quarantined spec

`backend/docs/specs/integrity_formula.md` documents a *different*, per-claim formula
(`Integrity_Gap = w_C·contradiction + w_E·(1−evidence) + w_V·(1−CVE) + w_U·uncertainty`).
It carries a banner stating **"UNIMPLEMENTED DESIGN NOTE — Status: never built"** and names
what actually ships instead. This matters because it was the only written specification of
"the integrity score" and would otherwise have become a paper's Methods section describing a
system that does not exist.

---

## 13. Stage 14 — Satellite verification

**Files:** `verification/satellite_evidence.py`, `sentinel_ndvi.py`, `geocode.py`

```
claim → scale gate → geocode → before/after NDVI composites → deterministic verdict
      → SHA-256-committed evidence bundle
```

**Locked design rules (from the module docstring):**
- *The agent/LLM never judges* — the verdict is a pure function of committed numbers, and
  every input that produced it is hashed into the bundle.
- *Honesty first* — anything the 10 m optical signal cannot support returns `inconclusive`
  with a machine-readable reason, never a guessed verdict.

**Parameters (`PARAMS`, version `sat-ev-2.1`):**

| Key | Value | Meaning |
|---|---|---|
| `buffer_m` | 250 | AOI radius around the geocoded point |
| `min_abs_delta` | 0.05 | NDVI units below which the signal is noise |
| `min_z` | 2.0 | paired-pixel z threshold |
| `method` | `paired_pixel` | v2.0 used whole-composite means vs spatial std; heterogeneity (river + urban in one AOI) drowned real change |
| `n_eff_divisor` | 16 | spatial-autocorrelation discount — one independent sample per 4×4 block |
| `collection` | `sentinel-2-l2a` | Sentinel-2 Level-2A |

**Aspect expectations:** reforestation → NDVI **up**; solar build-out → NDVI **down**
(vegetation replaced by panels); everything else → no optical expectation → `inconclusive`.

**`check_key`** = `sha256(report_id | normalized_aspect | location_text | time_bucket)[:16]`
— stable across re-ingests, because `claim_id` is a fresh UUID on every delete-then-insert
and previously orphaned all stored evidence.

Heavy geospatial imports (`rasterio`, `pystac_client`, `planetary_computer`) are **lazy**, so
the module loads in CI without the geo stack.

**Live state:** `satellite_evidence` holds **82** rows — this genuinely ran.

---

## 14. Stage 15 — API and frontend

### 14.1 API surface — FastAPI

| Endpoint | Purpose |
|---|---|
| `POST /v1/upload` | parse only, returns the 8-step artifacts |
| `POST /v1/reports/ingest` | **the real path** — auth-gated, dedup, async job |
| `GET /v1/jobs/{id}` | job progress |
| `GET /v1/claims/{doc_id}` | memory → disk → Supabase fallback |
| `GET /v1/documents/{id}/…` | sections, sentences, candidates, chunks, tables, provenance |
| `GET /v1/reasoning/{doc}/contradictions` `/risk-score` `/greenwashing-flags` `/integrity-report` `/review-queue` `/fact-check` | reasoning layer |
| `POST /v1/reasoning/{doc}/reviews` | human verdict upsert (auth) |
| `GET /v1/reasoning/portfolio/integrity` | per-company scores via the same `build_report()` |
| `POST /auth/register` `/login` `/refresh` · `GET /auth/me` | JWT auth |
| `GET /health` | liveness + readiness (DB, disk headroom, embedder importable) |

**Ingest job lifecycle:** `queued → parsing → extracting → ingesting → done` (or `error`),
driven by `_run_ingest` as a `BackgroundTask`.

### 14.2 The dual data path — important and undocumented elsewhere

- **Claims** are read by the frontend **directly from Supabase** (`hooks/useClaims.ts` →
  `supabase.from(...)`).
- **Everything else** — ingest, reasoning, benchmark, auth — goes through **FastAPI**
  (`lib/api.ts`, `API_BASE` from `VITE_API_BASE`, default `http://localhost:8000`).

**Consequences worth stating in any architecture write-up:**
1. Row-level security is the **only** authorization on claim data; the API layer is bypassed.
2. Integrity scores are recomputed **client-side on every load**, not materialised.

---

## 15. Evaluation methodology

**This section is what a report's Methods and Results are built from.** Eight harnesses,
all offline, all reading committed fixtures.

### 15.1 The scoring unit — `run_evaluation.py`

Six per-field rates are computed against a hand-labelled gold set:

| Rate | Definition |
|---|---|
| `candidate_precision` | of emitted claims, the share that are genuine (not furniture/fabrication) |
| `aspect_node_acc` | exact match on the taxonomy **node** |
| `aspect_pillar_acc` | match on the top-level pillar only |
| `value_acc` | within **±5%** relative tolerance, unambiguous rows only |
| `unit_base_acc` | unit canonicalised to the correct **dimension family** |
| `type_acc` | `performance` / `target` / `narrative` |

> **`precision_composite` is the unweighted mean of FIVE of these — `aspect_pillar_acc` is
> excluded.** Verified: (74.0 + 37.8 + 91.7 + 100.0 + 73.0)/5 = 75.3, which is what the
> harness prints. Getting this wrong in a paper would be an easy reviewer catch.

**It is not accuracy and not F1.** All five terms are precision-family and there is **no
recall term** — the gold set is sampled from claims the extractor *emitted*, so anything it
missed cannot appear. `EXTRACTION_SCORE` was renamed `precision_composite` in `46364fd`
precisely to stop that misreading.

### 15.2 Ablation — `run_ablation.py`

Six cumulative stages replayed over frozen fixtures:

| Stage | Applies |
|---|---|
| S0 | nothing — `normalized_aspect` reset to the LLM's free text, flags and tags cleared |
| S1 | `+ ESGOntology.normalize_aspect` + `_refresh_keys` |
| S2 | `+ fix_fy_column` |
| S3 | `+ value-in-table` flagging |
| S4 | `+ apply_gate` |
| S5 | `+ is_furniture` drop — **the shipped configuration** |

Each stage deep-copies its input, because the gate mutates in place and sharing objects
would contaminate later stages.

**Two honesty constraints built into the harness itself:**
- `aspect_node_acc` is **0% at S0 by construction** — free text cannot exact-match a
  controlled vocabulary — so S0→S5 flatters the method. **Quote S1→S5.**
- Both gold sets are **development sets**. The harness prints this on every run.

### 15.3 Confidence intervals — `run_bootstrap.py`

Nonparametric bootstrap, **2,000 resamples**, **claim as the sampling unit**, percentile
intervals. Ablation deltas are **paired** — both stages scored on the *same* resample — which
is what makes them robust to the gold sets being development sets.

Reported caveat: a percentile bootstrap on all-correct data returns a degenerate [100, 100]
interval, which is a boundary artifact. Those are reported as "no errors observed in N", with
a one-sided **rule-of-three** bound (≈92% at n=37) instead.

### 15.4 Recall — `run_recall.py`

The system-independent half. Table cells are **mechanically enumerated** from the committed
Docling markdown (`_candidate_cells`), giving a denominator the system does not control.

- Duplicate `(row_label, value)` pairs are **collapsed**.
- **Governance-form cells are excluded** — they assert no quantity.
- Headline is **distinct-fact recall**; raw cell recall is reported as a conservative lower
  bound.

### 15.5 Cross-system baselines — `run_baselines.py`

Three scoring lanes, and the harness is explicit that the obvious one is the weakest:

| Lane | What | Comparable across systems? |
|---|---|---|
| **L1 fact recall** | distinct table facts recovered | ✅ mechanical denominator |
| **L2 grounding precision** | share of emitted values that occur in the source page | ✅ mechanical, taxonomy-free |
| **L3 gold composite** | scored against the committed gold | ❌ **structurally biased** |

**Why L3 is biased:** every gold set is sampled *from the shipped extractor's output* and
matches by `claim_id`, falling back to normalised `source_sentence`. A different system
phrases its sentence differently, fails to match, and goes unscored. Probing the rule-based
extractor found only **7 of 46** gold sentences reproducible by non-LLM composition. The
harness prints the match rate beside every L3 number and renders scores under a **50% match
as `n/a`** rather than as a number.

**The no-LLM floor (`R`) is suppressed on L1/L2 as tautological** — it is built from the same
enumerator that scores recall, so it recalls 100% by construction, and its values are copied
out of the markdown so grounding is 100% for the same reason. The harness tags it
`tautological=True` and prints `--`. What it *does* measure honestly is
**ontology coverage: 43.1%** of table rows are keyword-reachable; the remaining 57% is the
share of the surface that genuinely needs a model.

**Matched arms.** The A row must come from `baseline_incumbent_<case>.jsonl` — the incumbent
model driven through the *identical* code path, page set and token budget. The shipped
fixture is a full-document run and is **never differenced** against a table-only arm; it is
shown as a labelled context row. Without a matched arm the harness prints `[UNMATCHED ARMS]`
and **withholds** the interaction term.

**Generation safety.** `--provider` blanks every other provider's pool vars (blank, not pop —
imported modules re-run `load_dotenv()`, which repopulates a missing key but leaves an empty
one alone), applied *after* the import that triggers it. A heterogeneous pool is refused
outright. The meta records the endpoint's actual model, pool composition, token budget and
failed-page list.

### 15.6 Cost — `run_cost.py`

Times S1–S5 only. **Excluded on purpose:** the LLM call (the point of the measurement), PDF
parsing (upstream and cached), and the harness's own deep copies. Reports **best of N**
because the floor is the signal and anything above it is scheduler noise.

### 15.7 Page-matched comparison — `run_page_matched.py`

Recall and grounding restricted to pages **both** arms produced claims for. A page lost to a
transport failure would otherwise score as "the model found nothing here", penalising
whichever arm had the worse network conditions.

### 15.8 Gate workload — `run_gate_workload.py`

The only cross-model-comparable view of the repair layer: the **rate at which the gate
intervenes** (aspect changed, type changed, furniture dropped, flags raised).

> **An intervention is not evidence of an improvement.** This measures how much the layer
> finds to do, not how much it gets right. Stated in the module docstring and in the paper.

### 15.9 Ground-truth integrity — `test_gold_integrity.py`

`GOLD_HASHES.json` stores a per-claim hash of every gold label. CI **fails the build** if any
label changes without a documented version bump in `GOLD_CHANGELOG.md`. This exists because
ground truth must not drift toward the system it measures — 6 of 100 labels were revised
toward the system before the gate existed, and the limitation is disclosed rather than hidden.

---

## 16. Data contracts

### 16.1 `ExtractedClaim` — the spine

| Field | Type | Set by |
|---|---|---|
| `claim_id` | uuid[:12] | model default |
| `aspect` / `normalized_aspect` | str | LLM / ontology |
| `action`, `claim_type` | str | LLM / `ClaimAnalyzer` |
| `metric` | `{value, unit, direction, normalized_*}` | LLM + `UnitNormalizer` |
| `location` | `{raw_text, specificity∈facility/city/region/country/global}` | LLM + NER |
| `time` | `{start_date, end_date, baseline_year}` | LLM (salvage-validated) |
| `provenance` | `{source_sentence, page_number, chunk_id, block_id, section_label, bbox}` | parser |
| `confidence` | float 0–1 | LLM |
| `observability_type`, `groundability_score`, `vagueness_score` | | `GroundabilityClassifier`, `ClaimAnalyzer` |
| `metric_family`, `metric_key`, `time_bucket`, `location_scope`, `claim_signature` | str | `SignatureGenerator` |
| `quality_flags`, `framework_tags` | list[str] | quality gate |
| `company_id`, `company_name`, `report_year`, `report_id` | | ingest metadata |
| `source_type` | `text` \| `table` | extractor path |

### 16.2 Unit canonicalisation

`UnitNormalizer.UNIT_MAP` covers mass, emissions, energy, area, volume, percentage and count
families. Two design choices worth noting:

- The miss value is the string **`"unspecified"`**, not `None`, because the eval harness's
  `unit_to_base` treats `"unspecified"` as the null family.
- A value in `(0, 1)` with a `%` unit is multiplied by 100 — `0.4 reduction` → `40%`.

### 16.3 Live database state (verified)

| Table | Rows |
|---|--:|
| `claims` | 1,730 |
| `reports` | 6 |
| `contradictions` | 16 |
| `satellite_evidence` | 82 |
| `claim_reviews` | 0 |
| `jobs` | 0 |
| `users` | 0 |

---

## 17. Defects found while tracing this flow

### 17.1 🔴 `claims_environment` is a dead partition

`claims` is LIST-partitioned on `metric_family`. The bounds expect a pillar prefix the
ontology never emits:

```
PARTITION claims_environment FOR VALUES IN
  ('environment.emissions', 'environment.energy', 'environment.water', ...)

but  generate_metric_family("emissions.scope1")  ->  "emissions.scope1"
     generate_metric_family("energy.renewable")  ->  "energy.renewable"
```

`generate_metric_family` takes the **first two dot-segments of `normalized_aspect`**, and no
taxonomy node begins with `environment.`. **No row can ever match.**

Measured live: `claims_default` holds **851 of 1,730 rows (49%)**, including all **695**
emissions/energy/water/waste/biodiversity claims. `claims_environment` and
`claims_governance` hold **zero**. 146 `social.*` claims also miss, because only four social
families are enumerated in the bounds.

**Impact:** partition pruning does nothing for the largest query class, and the per-partition
HNSW index on `claims_environment` indexes an empty table. It fails **silently**.

**Corroboration:** `reasoning/retrieval.py:115` still uses `"metric_family":
"environment.emissions"` in its `__main__` test stub — the `environment.` prefix is a
superseded design that the ontology moved away from, leaving the partitions and this stub
behind.

**Fix:** restate the bounds to match what the ontology emits (safer than renaming the
ontology — no data migration), plus a test asserting no partition is empty after ingest.

### 17.2 🟠 The frozen fixtures are not raw LLM output

`claim_extractor.py:862-868` applies `fix_fy_column` (S2) and the value-in-table check (S3)
**before** anything is written. The committed fixtures additionally carry `apply_gate` flags
(`type_fixed` ×157 on Tata) from an earlier layer revision.

**Consequence:** the ablation's S0 is a **reconstruction** (three fields reset, current stack
replayed), and the S2/S3 deltas measure the residual between layer revisions, not the value
of those stages. Reported gains are therefore a **lower bound**. Full detail in
[`../docs/CROSSCHECK_FINDINGS.md`](../docs/CROSSCHECK_FINDINGS.md) §1.

### 17.3 🟠 Job state is in-process

`/v1/reports/ingest` returns a `job_id` and the UI polls `/v1/jobs/{id}`, but the `jobs` table
holds 0 rows — state lives in the FastAPI process. A restart mid-ingest orphans the job with
no UI recovery. On a sleeping free-tier host this will happen.

### 17.4 🔴 Live superuser credential

Documented in [`../docs/CROSSCHECK_FINDINGS.md`](../docs/CROSSCHECK_FINDINGS.md) §P0. Code
fixed; **rotation still outstanding**.

---

## 18. Reproducing everything

```bash
python backend/scripts/run_ablation.py   --markdown   # repair-layer ablation
python backend/scripts/run_bootstrap.py  --markdown   # bootstrap CIs, B=2000
python backend/scripts/run_recall.py                  # table-fact recall
python backend/scripts/run_baselines.py  --markdown   # 2×2 + no-LLM floor
python backend/scripts/run_cost.py       --markdown   # latency
python backend/scripts/run_page_matched.py            # page-matched model comparison
python backend/scripts/run_gate_workload.py           # gate intervention rate
python backend/scripts/make_readme_figures.py         # figures
cd backend && python -m pytest -m "not live"          # 178 passed
```

**Reproducibility substrate:** raw LLM outputs and parsed page markdown are committed as
frozen fixtures; `bge-base-en-v1.5` pinned at `a5beb1e3` and `distilbert-base-uncased-mnli`
at `cfa538a0`; all RNGs seeded (42). Extraction itself is **not** bit-reproducible — hosted
model at temperature 0.1 — but every *reported* number recomputes exactly, offline, at zero
cost.
