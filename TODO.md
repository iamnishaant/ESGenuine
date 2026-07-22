# ESGenuine — Master TODO / Roadmap

> Durable backlog so work can resume across sessions. Companion docs:
> [`take_step_forward.md`](take_step_forward.md) (architecture rationale + estimates),
> [`existing_issues.md`](existing_issues.md) (runtime defects log).
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done. Priority: 🔴 critical · 🟠 high · 🟡 nice.

---

## ▶ Active now — SOTA program (extraction-first, full program)

> **Reconciliation 2026-07-13** — this file had drifted behind the code. Since the
> Phase-3 write, the 7-step improvement program shipped (eval harness → Docling tables
> → quality gate → evidence corpus → fact-check score v2.2 → framework tags → prod
> Docker), ontology **round 2** landed (gold v0.3: **89.7 OOS / 96.1 in-sample**),
> **Satellite Evidence v2.3** went live, and the Benchmark page + YoY drift shipped.
> Checkboxes below flipped to match. **In flight now:** corpus re-ingest on the round-2
> pipeline (tata/shell_2022/infosys_2023 done; infosys_2025/microsoft/shell_2023
> extracting) + the ⑥ regate sweep (re-apply round-2 gate to batch-written JSONLs).
> See memory `pharos-improvement-roadmap` / `pharos-corpus-scoring` for the live detail.

### Phase 1 — SOTA extraction redesign  `[~]`
- [x] Fix mojibake at source (`ftfy` in `pdf_parser.py` Step 1) 🔴
- [x] `SECTION_EXTRACTION_PROMPT` + `ClaimExtractor.extract_from_sections()` (1 call per section-window, full context) 🟠
- [x] Section pre-filter (skip boilerplate) + char-budget windowing + provenance fuzzy-map 🟠
- [x] Driver `scripts/run_company_analysis.py` switched to section-windows 🟠
- [x] **Verify on Shell pair** — DONE: 2022 (65 calls→527), 2023 (83 calls→779), 0 timeouts, mojibake clean. Findings in `ESGenuine_shell_analysis.md`. Defensive signal solid (~64% narrative/aspirational, ~38% no metric). 🟠
- [x] **Fix `metric_key` normalization** — canonical *dimensions* (co2e/mass/energy/volume/area/percent/count/rate/currency); implausible (aspect,dim) pairs collapse to `.unspecified`. Drift now honest (`water.consumption.volume 18M→17M m³`, `ltifr.rate 6.9→2.0`) — existing_issues #14–16 ✅
- [x] **Multi-key endpoint pool** — `LLMClient` round-robins NVIDIA + Groq (multi-key via `GROQ_API_KEYS`/`NVIDIA_API_KEYS`); Groq ~0.9s/call vs ~20s NVIDIA-70B 🟠
- [x] HF token in `.env` (kills unauthenticated HF Hub warning) 🟡
- [ ] Re-run final extraction on 70B (cached claims make this cheap) for max quality once table fixes land 🟡
- [ ] Local intra/cross-report contradiction pass on clean claims (no Supabase RPC needed) — partial Phase 4 🟠
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
- [~] Produce final Shell findings WITH table metrics (REUSE text + VLM tables) — running
- [x] Wire VLM tables into `ExtractionPipeline.run()` (production path; env `USE_VLM_TABLES`) ✅
- [ ] **Better table-page detection** — pdfplumber `find_tables` misses borderless perf tables (only 2/91 pages on Shell). Use digit-density or VLM page-classify so we don't under-select.
- [ ] Dedup table vs text claims; sub-dimension split for co2e absolute-vs-intensity

### Phase 3 — Verification layer  `[~]` 🟠
- [x] **Satellite Evidence v2 — ✅ SHIPPED (v2.3 live, commits →`68accff`, 2026-07-12).**
      Real Sentinel-2 NDVI verification wired into the integrity report: paired-pixel
      z-score verdicts, **Jarama reforestation SUPPORTED (z=12.8)**, Microsoft
      **North-Holland datacenter NOT_SUPPORTED** (score 48.2→50.1 + `SATELLITE_CONTRADICTION`
      flag), SHA-256 evidence bundles in a `satellite_evidence` table, REST-based runner
      (IPv4, survives IPv6 drop), Benchmark-page satellite panel. Original scope (delivered):
- [x] ~~replace the mocked `fetch_satellite` step~~
      (`pipeline/workflow_dag.py`) with real imagery verification. **Scope locked
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
- [ ] Self-consistency (sample extraction 2×, keep agreeing fields)
- [ ] LLM-judge pass for the greenwashing verdict + calibrated confidence
- [ ] Symbolic sanity checks (unit/temporal plausibility; Scope1+2 vs total)

### Phase 4 — Fix retrieval & reasoning  `[~]` 🔴
- [x] Apply `database/match_claims_rpc.sql` to live DB — DONE 2026-06-25 (was PGRST202; RPC now callable, returns the full field set) — existing_issues #1
- [ ] Remove the silent `except Exception: return []` in `retrieval.py` (still swallows → `[]`; now prints the error but the swallow remains at `retrieval.py:85-87`) — existing_issues #1
- [x] Fix `doc_id` = chunk-id bug; use a real per-report document id — DONE (all ingest paths write real `report_id`; live rows relabeled) — existing_issues #3
- [x] Fix NLI input format — DONE (`_textual_entailment` feeds a real premise/hypothesis pair via `{"text", "text_pair"}`; the `</s></body>` hack is gone) — existing_issues #3/#7
- [x] Make numeric contradiction unit/metric_key-aware — DONE (`_numeric_conflict` compares same `metric_key`+canonical unit; cross-year series no longer flagged; unit-canonicalizer) — existing_issues #7/#18/#19
- [ ] (optional) Swap embeddings to NVIDIA `llama-nemotron-embed` for SOTA retrieval

### Phase 5 — Evaluation harness  `[~]` 🟠
- [x] Hand-label a gold set — DONE: v0.1 (46 claims, 4 companies), v0.2 (`gold_set_docling_tata.json`, 50 table-verified), v0.3 (Shell 2022, 50, out-of-sample) — `backend/tests/eval/`
- [x] Precision/Recall/F1 for extraction fields + ontology mapping — DONE (`run_evaluation.py` → EXTRACTION_SCORE: precision/value/pillar/node/type). **63.6 → 96.1 in-sample, 89.7 OOS.** (contradiction-eval still TODO)
- [x] Regression gate — **CI-ENFORCED (2026-07-19)**: `test_gold_regression.py` regates frozen raw extractions (`tests/eval/fixtures/`) through the CURRENT deterministic stack and asserts gold floors (Tata ≥96.0, Shell ≥89.5) on every push — the manual re-score-both-golds protocol, automated. Proven live: the round-3 subgroup split initially scored 94.0 (keyword-steal bug) before the fix; this gate would have failed CI.

---

## 🔴 Critical runtime defects (from existing_issues.md) — **all #1–#13 resolved & verified 2026-06-26**
- [x] #1/#2 reasoning endpoints return real conflicts (RPC applied) — residual: `retrieval.py` still swallows RPC errors → `[]` (tracked in Phase 4)
- [x] #3 `claims.doc_id` holds a real per-report id (was chunk IDs)
- [x] #4 mojibake — parser runs `ftfy`; live corpus **0/2385** mojibake markers (DB re-ingested clean)
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
- [ ] Async job/run model + workers → **real production ingest path** (today ingest is a manual script)
- [ ] Pin deps / lockfile + `pyproject.toml`; seed RNG; pin model revisions
- [x] Dockerfile + docker-compose — DONE + verified live 2026-07-06 (`a09691c`): backend multi-stage + frontend nginx + compose (Supabase-only by design, no local PG); container healthy. 3 deploy-blocking bugs fixed.
- [x] CI — was ALREADY live (`.github/workflows/ci.yml` since 2026-07-01, unbroken green streak): backend offline pytest + advisory ruff + frontend tsc/build; now also runs the gold-floor regression gate
- [~] Structured logging — JSON request-log middleware shipped (`981a13f`, request_id/status/duration); full `print()`→structlog sweep still TODO
- [ ] Security: enable Supabase RLS, service-role for writes, restrict CORS
- [ ] Versioned Supabase migrations (stop `setup_db.py` DROP TABLE); fix dead LIST partitioning

## 🟡 Data / corpus
- [x] Shell 2022 + 2023 downloaded & validated → `backend/ESG_Reports/`
- [ ] Coca-Cola / Nestlé / Shein reports — sites are JS/WAF-gated; **user to drop PDFs into `backend/ESG_Reports/`**, then run `scripts/run_company_analysis.py`
- [~] Re-ingest a clean corpus on the round-2 (96.1) pipeline — IN PROGRESS: tata/shell_2022/infosys_2023 done; infosys_2025/microsoft/shell_2023 extracting (`reingest_corpus.py`); ⑥ regate sweep re-applies round-2 gate to batch JSONLs (`regate_ingest.py`)

## 🟡 Housekeeping / decisions
- [x] Commit the uncommitted stack — DONE (repo fully committed; the whole 7-step program + round-2 + satellite + benchmark landed as split commits through `68accff`)
- [ ] Rotate exposed keys when convenient (GROQ, NVIDIA, DB password) — all in gitignored `.env`; deferred by user
- [ ] Optional: rename the top-level folder to `ESGenuine` (manual; breaks IDE/cwd if done mid-session)
- [ ] Repoint frontend `analyze-claims` edge function off Lovable AI → NVIDIA (needs Supabase secret + redeploy)

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
