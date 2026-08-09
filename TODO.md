# ESGenuine — Master TODO / Roadmap

> Durable backlog so work can resume across sessions. Companion docs:
> [`take_step_forward.md`](take_step_forward.md) (architecture rationale + estimates),
> [`existing_issues.md`](existing_issues.md) (runtime defects log).
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done. Priority: 🔴 critical · 🟠 high · 🟡 nice.

---

## ▶ Active now — SOTA program (extraction-first, full program)

> **Reconciliation 2026-08-09** — re-audited line by line against the code; the
> 2026-07-13 header below had gone stale (it still described the corpus re-ingest as
> "in flight" when it completed 2026-07-22, and two items contradicted each other).
> Corrected this pass:
> - **Phase 5's "Precision/Recall/F1 — DONE" was wrong.** The harness is
>   **precision-only**; there is no recall or F1 term anywhere in `run_evaluation.py`
>   (verified by grep). Re-opened as the headline research gap — see **Phase 6**.
> - Corpus count fixed (2385 → **1730**, the round-3 figure), the resolved
>   `retrieval.py` residual removed from the #1/#2 line, and the deleted
>   `pipeline/workflow_dag.py` reference annotated.
> - CI's "unbroken green streak" qualified: the **frontend type-check job was a no-op**
>   until 2026-08-09 (existing_issues #22b).
> - New **Phase 6 — research/paper readiness** captures the agreed path to a publishable
>   result, and the 🔵 batch-#22 hardening work is recorded below.
>
> **Prior state (2026-07-13, still accurate):** the 7-step improvement program shipped
> (eval harness → Docling tables → quality gate → evidence corpus → fact-check score
> v2.2 → framework tags → prod Docker), ontology **round 2** landed (gold v0.3:
> **89.7 OOS / 96.1 in-sample**), **Satellite Evidence v2.3** went live, and the
> Benchmark page + YoY drift shipped. Corpus re-ingest + the ⑥ regate sweep then
> completed 2026-07-22 (all 6 reports on round-3).
> See memory `pharos-improvement-roadmap` / `pharos-corpus-scoring` / `pharos-audit-2026-08`.
>
> **Run it locally:** `start.bat` at the repo root (backend :8000 + frontend :8080,
> each in its own window; `start.bat backend|frontend` for one, `/nobrowser` to skip
> the browser). Preflights the venv, `.env`, `node_modules` and both ports.

### Phase 1 — SOTA extraction redesign  `[~]`
- [x] Fix mojibake at source (`ftfy` in `pdf_parser.py` Step 1) 🔴
- [x] `SECTION_EXTRACTION_PROMPT` + `ClaimExtractor.extract_from_sections()` (1 call per section-window, full context) 🟠
- [x] Section pre-filter (skip boilerplate) + char-budget windowing + provenance fuzzy-map 🟠
- [x] Driver `scripts/run_company_analysis.py` switched to section-windows 🟠
- [x] **Verify on Shell pair** — DONE: 2022 (65 calls→527), 2023 (83 calls→779), 0 timeouts, mojibake clean. Findings in `ESGenuine_shell_analysis.md`. Defensive signal solid (~64% narrative/aspirational, ~38% no metric). 🟠
- [x] **Fix `metric_key` normalization** — canonical *dimensions* (co2e/mass/energy/volume/area/percent/count/rate/currency); implausible (aspect,dim) pairs collapse to `.unspecified`. Drift now honest (`water.consumption.volume 18M→17M m³`, `ltifr.rate 6.9→2.0`) — existing_issues #14–16 ✅
- [x] **Multi-key endpoint pool** — `LLMClient` round-robins NVIDIA + Groq (multi-key via `GROQ_API_KEYS`/`NVIDIA_API_KEYS`); Groq ~0.9s/call vs ~20s NVIDIA-70B 🟠
- [x] HF token in `.env` (kills unauthenticated HF Hub warning) 🟡
- [x] Re-run final extraction on 70B — DONE via the round-3 corpus re-ingest (all 6 reports live on the 96.1/round-3 pipeline, 2026-07-22)
- [x] Local intra/cross-report contradiction pass on clean claims (no Supabase RPC) — DONE: `reasoning/persist_contradictions.py` runs the deterministic numeric scan at ingest and maintains the `contradictions` table (existing_issues #20)
- [x] Wire section mode into `ExtractionPipeline.run()` (accept `sentences`, prefer sections, keep chunk path as fallback) 🟠
- [x] Wire `/v1/claims/extract` to load `sentences` and use section mode 🟠
- [x] Harden NVIDIA call (read-timeout 300s + `max_tokens` cap); driver persists/REUSEs claims 🟠
- [x] `skip_tables` parse flag (section mode needs sentences only → fast parse) 🟠
- [x] Concurrent extraction (`NVIDIA_CONCURRENCY`, default 6-way) — minutes not tens of minutes 🟠
- [x] Live progress bar in `extract_from_sections` (TTY bar + periodic log lines) 🟠
- [ ] Add response caching (content-hash per window) to the production pipeline to avoid re-LLM on re-runs 🟡

### Phase 2 — Document-AI tables  `[~]` 🟠
- [x] `VLMTableExtractor` (`vlm_tables.py`): detect table pages → render → NVIDIA VLM (`nemotron-nano-12b-v2-vl`) → clean markdown. Validated on Shell. ✅
- [x] `TABLE_CLAIMS_PROMPT` + `extract_from_table_markdown` → structured table claims (e.g. `emissions.scope1.co2e 57/58/83 million tonnes CO2e`). ✅
- [x] Wired into driver (`VLM_TABLES=1`, cached to `_table_claims.json`). Unit-inference prompt fixed (no more `"number"`). ✅
- [x] Produce final Shell findings WITH table metrics (REUSE text + VLM tables) — delivered by the
      round-3 corpus re-ingest (shell_2022 247 / shell_2023 379 claims, Docling table path live).
- [x] Wire VLM tables into `ExtractionPipeline.run()` (production path; env `USE_VLM_TABLES`) ✅
- [ ] 🔴 **Better table-page detection** — pdfplumber `find_tables` misses borderless perf tables
      (only 2/91 pages on Shell). Use digit-density or VLM page-classify so we don't under-select.
      ⚠️ **Do NOT cite the Shell recall figure as evidence for this.** An earlier pass claimed
      162 lost cells proved a detection failure and raised this to 🔴; **that attribution was
      withdrawn on re-check the same day.** Two reasons it doesn't hold: (1) the Shell fixture
      is **text-dominant — 13 table claims out of 247 (5%)**, so that run barely exercised the
      table pipeline; (2) the production Docling path (`pipeline.py`) calls
      `DoclingTableExtractor().extract(pdf_path)` with **no page filter** — it converts every
      page, so pdfplumber detection is not even in that code path. `run_recall.py` now prints a
      CONFOUND warning when a fixture's table share is <15%. Detection does still gate the
      **VLM** path (`vlm_tables.find_table_pages`), but its cost is **unmeasured** — measure
      before prioritising. Priority stays 🟠.
- [x] Sub-dimension split for co2e absolute-vs-intensity — DONE (`emissions.*.co2e` vs `.intensity` via the metric_key dimension split; existing_issues #19). Table-vs-text dedup: deferred (low value — furniture gate already drops most table noise).

### Phase 3 — Verification layer  `[~]` 🟠
- [x] **Satellite Evidence v2 — ✅ SHIPPED (v2.3 live, commits →`68accff`, 2026-07-12).**
      Real Sentinel-2 NDVI verification wired into the integrity report: paired-pixel
      z-score verdicts, **Jarama reforestation SUPPORTED (z=12.8)**, Microsoft
      **North-Holland datacenter NOT_SUPPORTED** (score 48.2→50.1 + `SATELLITE_CONTRADICTION`
      flag), SHA-256 evidence bundles in a `satellite_evidence` table, REST-based runner
      (IPv4, survives IPv6 drop), Benchmark-page satellite panel. Original scope (delivered):
- [x] ~~replace the mocked `fetch_satellite` step~~
      (~~`pipeline/workflow_dag.py`~~ — that whole mock DAG was **deleted 2026-08-09**,
      existing_issues #22f; real verification lives in `src/verification/`)
      with real imagery verification. **Scope locked
      2026-07-11** (per the VeriGreen→CellPass split in
      `E:\Completed_Less_Looked_at_Projects\Sustainability-BlockChain\DECISIONS.md`:
      the satellite CV front-half was explicitly sized as a feature FOR THIS REPO;
      the crypto/chain back-half went to CellPass — do NOT let it creep back in).
      - Pipeline: `optical_possible` claims (95 live) ∩ geocodable place name →
        geocode (Nominatim) → Sentinel-2 L2A before/after composites (free:
        Copernicus / Planetary Computer STAC) → NDVI delta + z-score → verdict
        `supported / not_supported / inconclusive` + `SATELLITE_*` flag into the
        integrity report.
      - Evidence commitment (cheap VeriGreen carry-over, no blockchain): store
        SHA-256 bundle per check (tile IDs+hashes, date windows, cloud mask %,
        params, verdict) in a `satellite_evidence` table → reproducible verdicts.
      - Expected surface: ~20–40 verifiable claims (reforestation / solar build-out);
        cloud cover fallback = widen compositing window, mark `inconclusive`.
      - OUT (rejected for this repo): geospatial FM fine-tuning (Prithvi/Clay),
        on-chain anchoring, VCs/DIDs, challenge contracts, carbon/biomass MRV.
      - Prereq: corpus re-ingest done (location fields only trustworthy on the
        96.1 pipeline) + gold v0.3 sanity on extraction.
- [ ] Self-consistency (sample extraction 2×, keep agreeing fields) — deferred (metered LLM)
- [ ] LLM-judge pass for the greenwashing verdict + calibrated confidence — deferred (metered LLM)
- [~] Symbolic sanity checks (Scope1+2 vs total) — **investigated 2026-07-22, deferred with reason** (existing_issues #21c): the check would fire on extraction granularity, not greenwashing — `emissions.total` still holds per-segment "Total Scope 1 and Scope 2" table rows. The methane-mislabel half was FIXED (CH4 no longer pollutes total-emissions). Unlocks once emissions.total is split by segment. Unit/value plausibility already enforced (`UnitCanonicalizer.is_value_plausible`).

### Phase 4 — Fix retrieval & reasoning  `[~]` 🔴
- [x] Apply `database/match_claims_rpc.sql` to live DB — DONE 2026-06-25 (was PGRST202; RPC now callable, returns the full field set) — existing_issues #1
- [x] Remove the silent `except Exception: return []` in `retrieval.py` — DONE 2026-07-22 (`RetrievalError` raised on persistent RPC failure + one reconnect/retry; `GET /{doc}/contradictions` reports `retrieval_available:false` instead of a false 0; fails fast) — existing_issues #1/#21b
- [x] Fix `doc_id` = chunk-id bug; use a real per-report document id — DONE (all ingest paths write real `report_id`; live rows relabeled) — existing_issues #3
- [x] Fix NLI input format — DONE (`_textual_entailment` feeds a real premise/hypothesis pair via `{"text", "text_pair"}`; the `</s></body>` hack is gone) — existing_issues #3/#7
- [x] Make numeric contradiction unit/metric_key-aware — DONE (`_numeric_conflict` compares same `metric_key`+canonical unit; cross-year series no longer flagged; unit-canonicalizer) — existing_issues #7/#18/#19
- [ ] (optional) Swap embeddings to NVIDIA `llama-nemotron-embed` for SOTA retrieval

### Phase 5 — Evaluation harness  `[~]` 🟠
- [x] Hand-label a gold set — DONE: v0.1 (46 claims, 4 companies), v0.2 (`gold_set_docling_tata.json`, 50 table-verified), v0.3 (Shell 2022, 50, out-of-sample) — `backend/tests/eval/`
- [x] **Precision** for extraction fields + ontology mapping — DONE (`run_evaluation.py` →
      EXTRACTION_SCORE = mean of candidate_precision / aspect_node / value / unit_base / type).
      **63.6 → 96.1 in-sample, 89.7 OOS.**
- [~] 🔴 **RECALL + F1 — table half DONE 2026-08-09 (Phase 6.1a: Tata 54.4% table-cell recall);
      text half still open (6.1b).** Was previously mis-recorded here as fully done. There is no
      recall, F1 or false-negative term anywhere in `run_evaluation.py` or the eval README
      (verified 2026-08-09). This is **structural, not a missing formula**: every gold set is
      sampled *from claims the extractor already emitted* (`_meta.source_extraction` points at
      a `*.jsonl` of output), so a claim the system **missed is invisible to the harness**.
      The headline "96.1/100" is therefore a precision-family composite wearing the shape of an
      F1. Fixing it requires a different annotation protocol — see **Phase 6.1**. Until then,
      quote the number as *extraction precision*, never as accuracy or F1.
- [ ] 🟠 **Contradiction eval set** — the contradiction engine has never been scored. No gold
      pairs, so `_numeric_conflict`'s precision/recall are unknown; the #20 subgroup gate was
      tuned by inspection. (Was parenthetically noted as "still TODO" — promoted to its own item.)
- [x] Regression gate — **CI-ENFORCED (2026-07-19)**: `test_gold_regression.py` regates frozen raw extractions (`tests/eval/fixtures/`) through the CURRENT deterministic stack and asserts gold floors (Tata ≥96.0, Shell ≥89.5) on every push — the manual re-score-both-golds protocol, automated. Proven live: the round-3 subgroup split initially scored 94.0 (keyword-steal bug) before the fix; this gate would have failed CI.

### Phase 6 — Research / paper readiness  `[ ]` 🟠  *(new 2026-08-09)*

> Verdict from the 2026-08-09 audit: **not publishable as a research paper yet; viable now as
> a demo/system-track or domain-workshop paper.** The engineering is strong; the *evaluation*
> is what a reviewer rejects on. Ordered by what unblocks the most.
>
> **The contribution to build the paper around** is not the LLM extraction (standard) — it is
> the **deterministic post-correction layer**: `quality_gate.py` + ontology expansion moved
> extraction **63.6 → 96.1 at zero LLM cost**. "Cheap deterministic repair beats a bigger
> model" is a genuinely publishable finding, and `scripts/regate_claims.py` can produce the
> whole ablation table with **no inference spend**.

- [x] ✅ **6.1a Recall — table-cell recall SHIPPED 2026-08-09.** `backend/scripts/run_recall.py`.
      Docling returns each page as GFM markdown with row labels + headers intact, so numeric
      table facts are **mechanically enumerable** — no human annotation needed for a real recall
      denominator. **Measured: Tata 54.4%** (482 ground-truth cells, near-full-document cache).
      Conservative by construction (the denominator includes non-claim cells like office
      counts), so true recall is **≥** reported; the cell filter is auditable in
      `_candidate_cells`. Also reports a split of misses into *pages that produced no claims*
      vs *processed but not emitted* — on Tata only 29 cells fall in the former, so **57.8%
      recall on the pages it did read** is the extraction-quality number.
      ⚠️ **Trust the Tata figure only.** Shell reads 8.0% but its fixture is **text-dominant
      (13 table claims of 247)** and its Docling cache covers just **5 targeted pages** — it
      measures that run's config, not the shipped table path. An earlier version of this entry
      read Shell's number as proof of a table-page-detection failure; **that was retracted**
      (existing_issues #23b). `run_recall.py` now prints a CONFOUND warning below 15% table
      share so the mistake can't repeat.
- [ ] 🟠 **6.1b Text-claim recall** — still open, still needs humans. Narrative claims ("net zero
      by 2040") can't be enumerated mechanically. Annotate 3–5 complete sections exhaustively.
      Only after this can a whole-document precision/recall/F1 be quoted.
- [x] ✅ **6.2 Ablation SHIPPED 2026-08-09.** `backend/scripts/run_ablation.py` — 6 cumulative
      stages (S0 raw LLM → S1 ontology → S2 FY repair → S3 value-in-table → S4 gate fixes →
      S5 furniture drop) scored against both golds off the frozen fixtures. **Zero LLM cost,
      runs in seconds.** Result — the deterministic repair layer is worth
      **+24.6 (Tata 71.5→96.1)** and **+7.0 (Shell 82.7→89.7)** over an LLM-plus-vocabulary
      baseline. Dominant lever differs by document type: form-heavy BRSR → **gate fixes +20.5**
      (node 18.9%→94.6%) plus furniture drop +2.4 (precision 74%→86%); narrative IR report →
      **ontology mapping +10.6** (node 0%→53.1%), furniture drop 0 (no form furniture present).
      **Honesty guard built in:** the S0→S5 totals (+28.4/+17.6) are inflated because S0's node
      accuracy is 0% *by construction* (free text vs controlled vocabulary); the script prints
      **S1→S5 as the defensible number to quote**.
      *Still open:* (b) a pdfplumber-vs-Docling table-path comparison, and (c) a raw
      single-prompt extraction baseline — both need metered LLM calls.
- [ ] 🟠 **6.3 Second annotator + agreement** — all 146 gold labels (46 + 50 + 50) are
      single-annotator, self-labelled. Get a second annotator on a ~100-claim subset and report
      Cohen's κ. Without it the ground truth is an opinion.
- [ ] 🟠 **6.4 External validity for the integrity score** — weights `{Critical:50, High:30,
      Medium:16, Low:6}` in `integrity_report.py` are hand-set and never calibrated against
      anything. Correlate scores against an independent signal (MSCI / Sustainalytics / CDP
      ratings, or regulatory greenwashing enforcement) across a wider company set.
- [ ] 🟠 **6.5 Corpus scale** — 6 reports / 4 companies is too small for a research claim.
      Target **30–50 reports**. Now much cheaper: ingest is reachable from the UI (`start.bat`
      → Submit Report) and is checkpointed + idempotent.
- [ ] 🟡 **6.6 Satellite validation at n≥30** — currently **n=2** (Jarama SUPPORTED z=12.8,
      North-Holland NOT_SUPPORTED). Two anecdotes cannot support a claim; needs a control group.
- [ ] 🟡 **6.7 Stats** — no significance tests or confidence intervals anywhere.

**Venue read (2026-08-09):** top-tier NLP main track — no (rejected on evaluation).
**Demo / system track** (ACL/EMNLP/SIGIR) — viable now. **Domain workshop** (ClimateNLP,
NLP4Sustainability, FinNLP) — viable with 6.1 + 6.2 + 6.3 (~3 weeks). **Full research paper** —
~3 months (6.1–6.5).

---

## 🔴 Critical runtime defects (from existing_issues.md) — **all #1–#13 resolved & verified 2026-06-26**
- [x] #1/#2 reasoning endpoints return real conflicts (RPC applied). ~~residual: `retrieval.py` still swallows RPC errors~~ — that residual was **closed 2026-07-22** (`RetrievalError`; see Phase 4), this line had not been updated.
- [x] #3 `claims.doc_id` holds a real per-report id (was chunk IDs)
- [x] #4 mojibake — parser runs `ftfy`; live corpus **0** mojibake markers (DB re-ingested clean). *(The old "0/2385" denominator was the pre-round-3 corpus; it is **~1730** claims as of the 2026-07-22 re-ingest.)*
- [x] #5 table rows ~45% noise — Step5 drops empty-header/short rows (Docling tables now primary path)
- [x] #6 company mislabel — all rows relabeled Tata Power; prod path takes explicit `company_name`
- [x] #7 noisy/false contradictions — engine unit/metric_key-aware, cross-year series dropped
- [x] #8 empty on-disk claims artifact — `/v1/claims/{id}` falls back to Supabase
- [x] #9 `"null"` strings / null `time_start` — cleaned + write-path guards; null-time gated in reasoning
- [x] #10 `/v1/documents/{id}/sections` now returns `total`
- [x] #11 `/health` version now reads `app.version`
- [x] #12 document filename persisted across restart (read back from parse artifact)
- [x] #13 `reports` table refreshed (accurate `claim_count`, dead `F:` paths nulled)

---

## 🟠 Production hardening (from take_step_forward.md, Tier 1)
- [x] **Hostable deployment** — DONE 2026-07-22 (`cb90eeb`): `render.yaml` Blueprint (Docker backend + static frontend) + `DEPLOY.md`; `$PORT`-aware Dockerfile; env-driven CORS; scheme-tolerant `VITE_API_BASE`. Not yet deployed (needs user's Render account + secrets). Closes the "backend has no deployment" gap that capped the frontend at localhost.
- [x] **Real production ingest path reachable from the UI** — DONE 2026-08-09 (existing_issues #22e).
      `components/ReportIngestPanel.tsx` drives `POST /v1/reports/ingest` → `GET /v1/jobs/{id}`
      polling (stage bar, duplicate handling, cache invalidation) from the Submit Report page;
      the pipeline previously had **zero** frontend call sites. Job state is already DB-backed
      (`jobs` table) so it survives restart. *Remaining:* dedicated worker process — ingest still
      runs in a FastAPI `BackgroundTask`, so a long ingest is tied to the web dyno's lifetime.
- [~] Pin deps / lockfile + `pyproject.toml`; seed RNG; pin model revisions — **mostly done.**
      `backend/pyproject.toml` exists (testpaths + `live` marker, deps from requirements.txt);
      frontend has `package-lock.json`. `requirements.txt` is **14 pinned / 2 floating**
      (`beautifulsoup4>=4.12.0`, `spacy-transformers>=1.3.4` — re-pin on next freeze; `langgraph`
      was dropped 2026-08-09 with its only consumer).
      ✅ **RNG seeding + HF model pinning DONE 2026-08-09** (existing_issues #23g):
      `src/model_config.py` is now the single source of truth — `bge-base-en-v1.5` pinned to
      `a5beb1e3…` and `distilbert-base-uncased-mnli` to `cfa538a0…` (the SHAs already in the
      local cache, so current results become reproducible), all 5 load sites routed through
      `load_embedder()`/`load_nli()`, `seed_everything()` (SEED=42) at process start, and the
      server logs `model_provenance()` every boot. Locked by `test_model_config.py`.
      *Still open:* re-pin the 2 floating pip deps (`beautifulsoup4`, `spacy-transformers`).
- [x] Dockerfile + docker-compose — DONE + verified live 2026-07-06 (`a09691c`): backend multi-stage + frontend nginx + compose (Supabase-only by design, no local PG); container healthy. 3 deploy-blocking bugs fixed.
- [x] CI — live since 2026-07-01 (`.github/workflows/ci.yml`): backend offline pytest (**161/161**,
      162 collected, 1 `live`-marked) + advisory ruff + frontend type-check/build + the gold-floor
      regression gate. ⚠️ **The "unbroken green streak" was partly illusory:** the frontend
      type-check ran `npx tsc --noEmit`, which resolves the solution-style `tsconfig.json`
      (`"files": []` + references) and therefore **compiled nothing and always exited 0**, hiding
      10 real errors. Fixed 2026-08-09 → `npx tsc -b --force` (existing_issues #22b; proven with a
      canary: old command exit 0, new exit 2). Backend pytest was always genuine.
- [~] Structured logging — JSON request-log middleware shipped (`981a13f`, request_id/status/duration); full `print()`→structlog sweep still TODO
- [x] ✅ Security: enable Supabase RLS, service-role for writes, restrict CORS — **APPLIED TO
      PRODUCTION 2026-08-09** (existing_issues #22d/#24). All backend write paths
      now prefer `SUPABASE_SERVICE_ROLE_KEY` (anon fallback preserved);
      `database/2026-08-09_enable_rls.sql` revokes anon writes and enables RLS on all six tables
      **plus every `claims` partition** with SELECT-only policies.
      **Was genuinely exploitable, and that was PROVEN not assumed:** using the actual
      bundle-embedded publishable key, an INSERT via PostgREST returned **201** pre-migration
      (sentinel removed immediately). anon also held **TRUNCATE** on all 11 tables — and
      TRUNCATE is *not* subject to RLS, so the first draft of the migration would have left
      the corpus wipeable while reporting `RLS=true`. Fixed before applying (`927fcc4`), along
      with partition grants, which do not cascade from the parent.
      **Post-apply verification:** RLS=true on all 6 tables + all 5 partitions · 11 SELECT-only
      policies · anon holds SELECT and nothing else · 1730 claims intact · anon READ 200 ·
      anon INSERT **401 42501** (was 201) · anon DELETE 401 · service_role INSERT 201.
      Offline suite 173/173 after.
      *Follow-up:* rotate the service-role key (it was pasted into a chat transcript), and
      `.env` still carries a legacy `eyJ…` publishable key while the dashboard issues
      `sb_publishable_…`.
      ✅ **CORS FIXED 2026-08-09:** `_DEV_ORIGINS` (localhost:8080/5173/3000) is now added only
      when `ENVIRONMENT` is not production — combined with `allow_credentials=True` it previously
      let a page on any developer's machine make credentialed cross-origin calls against a
      deployed API. Warns loudly if prod has neither `ALLOWED_ORIGINS` nor `ALLOWED_ORIGIN_REGEX`.
      Verified in both modes.
- [ ] Versioned Supabase migrations (stop `setup_db.py` DROP TABLE); fix dead LIST partitioning

## 🟡 Data / corpus
- [x] Shell 2022 + 2023 downloaded & validated → `backend/ESG_Reports/`
- [ ] Coca-Cola / Nestlé / Shein reports — sites are JS/WAF-gated; **user to drop PDFs into `backend/ESG_Reports/`**, then run `scripts/run_company_analysis.py`
- [x] Re-ingest a clean corpus on the round-3 (96.1) pipeline — **DONE 2026-07-22: all 6 reports live** (tata 335 / shell_2022 247 / shell_2023 379 / infosys_2023 249 / infosys_2025 242 / microsoft_2024 278). Old-pipeline garbage gone (0 huge-scope1 rows); contradictions persisted per report. Small gap: microsoft + shell_2023 miss their congestion-failed 'Environmental Performance' section (targeted resume when NVIDIA is calm).

## 🟡 Housekeeping / decisions
- [x] Commit the 7-step / round-2 / satellite / benchmark stack — DONE (split commits through `68accff`)
- [ ] 🟠 **Commit the 2026-08-09 batch-#22 stack — 21 files uncommitted right now.**
      Modified: `ci.yml`, `.gitignore`, `.env.example`, `render.yaml`, `requirements.txt`,
      `TODO.md`, `existing_issues.md`, 4 backend credential paths, 5 frontend files.
      New: `database/2026-08-09_enable_rls.sql`, `components/ReportIngestPanel.tsx`, `start.bat`.
      Deleted: `src/pipeline/` (2 files). Current branch is `ESG_V1` (the default) — **branch first.**
- [ ] Rotate exposed keys when convenient (GROQ, NVIDIA, DB password) — all in gitignored `.env`; deferred by user
- [ ] Optional: rename the top-level folder to `ESGenuine` (manual; breaks IDE/cwd if done mid-session)
- [x] Repoint `analyze-claim(s)` edge functions off Lovable AI → NVIDIA — DONE 2026-07-22 (both functions now call `integrate.api.nvidia.com` OpenAI-compatible with `NVIDIA_API_KEY`; JSON-mode + max_tokens). **To activate:** set `NVIDIA_API_KEY` as a Supabase function secret + `supabase functions deploy` (code done; inert until redeploy).

---

## ✅ Recently completed
- [x] Frontend de-fiction (removed satellite/NDVI/SAR mocks; wired to real Supabase fields)
- [x] Monorepo restructure (`frontend/` + `backend/` + `docs/`, single root `.env` via Vite `envDir`)
- [x] NVIDIA NIM as preferred LLM provider (`claim_extractor.LLMClient`)
- [x] Project rename Pharos Integrity → **ESGenuine** (code + docs)
- [x] Backend portability (relative paths), date-null sanitize, 3 TS errors fixed
- [x] Audit docs written: `take_step_forward.md`, `existing_issues.md`
- [x] git init at root + hardened `.gitignore`
- [x] **7-step improvement program** (2026-07-03, `9917b69`→`981a13f`): eval harness + gold set → Docling layout-aware tables → quality gate → evidence corpus → fact-check integrity score v2.2 → framework tags (GRI/ESRS/TCFD) → prod Docker
- [x] **Extraction score 63.6 → 96.1** (in-sample) via Docling + quality gate + ontology **round 2**; **89.7 out-of-sample** (Shell 2022, gold v0.3)
- [x] **Count-weighted integrity score** (v2.0→2.3) + human-in-the-loop flag review; **Satellite Evidence v2.3** (Sentinel-2 NDVI); **Benchmark page** + YoY drift + satellite panel
- [x] **Resumable metered extraction** (`ClaimCheckpoint`) + `reingest_corpus.py` / `regate_claims.py` / `regate_ingest.py` corpus-refresh tooling
- [x] **Frontend↔backend cross-check + hardening — batch #22, 2026-08-09** (existing_issues #22a–f).
      Six defects found by enumerating all 32 routes against every call site: landing page
      hard-coded `localhost:8000` (broke every deploy + mixed-content on HTTPS); the CI
      type-check job compiled nothing; `supabase/types.ts` was an empty stub so the whole
      frontend read path was untyped; the public anon key held write access to score-bearing
      tables; the ingest pipeline had **no UI at all**; and a mock "(Production)" LangGraph DAG
      shipped as dead code. All fixed. Gates: pytest 161/161, `tsc -b --force` 0 errors,
      `vite build` OK, app imports 36 routes.
- [x] **`start.bat` local launcher** — backend :8000 + frontend :8080 in separate windows;
      `backend`/`frontend` args, `/nobrowser`; preflights venv, `.env`, `node_modules`, ports.
