# ESGenuine — Master TODO / Roadmap

> Durable backlog so work can resume across sessions. Companion docs:
> [`take_step_forward.md`](take_step_forward.md) (architecture rationale + estimates),
> [`existing_issues.md`](existing_issues.md) (runtime defects log).
> Legend: `[ ]` todo · `[~]` in progress · `[x]` done. Priority: 🔴 critical · 🟠 high · 🟡 nice.

---

## ▶ Active now — SOTA program (extraction-first, full program)

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

### Phase 3 — Verification layer  `[ ]` 🟠
- [ ] Self-consistency (sample extraction 2×, keep agreeing fields)
- [ ] LLM-judge pass for the greenwashing verdict + calibrated confidence
- [ ] Symbolic sanity checks (unit/temporal plausibility; Scope1+2 vs total)

### Phase 4 — Fix retrieval & reasoning  `[ ]` 🔴
- [ ] Apply `database/match_claims_rpc.sql` to live DB (RPC currently missing → contradictions silently 0) — existing_issues #1
- [ ] Remove the silent `except Exception: return []` in `retrieval.py` (surface failures) — existing_issues #1
- [ ] Fix `doc_id` = chunk-id bug; use a real per-report document id — existing_issues #3
- [ ] Fix NLI input format (`</s></body>` hack → proper premise/hypothesis pair) — existing_issues #3/#7
- [ ] Make numeric contradiction unit/metric_key-aware (stop cross-metric false positives) — existing_issues #7
- [ ] (optional) Swap embeddings to NVIDIA `llama-nemotron-embed` for SOTA retrieval

### Phase 5 — Evaluation harness  `[ ]` 🟠
- [ ] Hand-label a gold set (~100–300 claims across 3–5 reports)
- [ ] Precision/Recall/F1 for extraction fields, ontology mapping, contradictions
- [ ] Regression gate (fail CI if F1 drops); track per model/prompt version

---

## 🔴 Critical runtime defects (from existing_issues.md)
- [ ] #1/#2 reasoning endpoints always return 0 (missing RPC + silent except) → Phase 4
- [ ] #3 `claims.doc_id` holds chunk IDs → Phase 4
- [x] #4 mojibake in parsed text → fixed in parser (NOTE: existing DB rows still dirty — re-ingest to clean)
- [ ] #5 table rows ~45% noise → Phase 2
- [ ] #6 company mislabeled "Business" (it's Tata Power) — fix metadata inference in `populate_reports.py`
- [ ] #7 noisy/false contradictions → Phase 3/4
- [ ] #8 on-disk `08dbf8224013_claims.json` empty → re-run extraction/ingest
- [ ] #9 `"null"` strings + 28% null `time_start` in DB → re-ingest after fixes
- [x] #10 `/v1/documents/{id}/sections` now returns `total` (API contract fixed)
- [x] #11 `/health` version now reads `app.version` (no longer stale)
- [ ] #12 in-memory `document_registry` loses filename on restart → persist
- [ ] #13 `reports` table stale (claim_count 214 vs 181; 3/4 empty; F: paths)

---

## 🟠 Production hardening (from take_step_forward.md, Tier 1)
- [ ] Async job/run model + workers → **real production ingest path** (today ingest is a manual script)
- [ ] Pin deps / lockfile + `pyproject.toml`; seed RNG; pin model revisions
- [ ] Dockerfile + docker-compose (backend + worker + local pg+pgvector + frontend)
- [ ] CI (lint, typecheck, pytest, frontend build)
- [ ] Structured logging + metrics + per-run lineage (replace `print()`)
- [ ] Security: enable Supabase RLS, service-role for writes, restrict CORS
- [ ] Versioned Supabase migrations (stop `setup_db.py` DROP TABLE); fix dead LIST partitioning

## 🟡 Data / corpus
- [x] Shell 2022 + 2023 downloaded & validated → `backend/ESG_Reports/`
- [ ] Coca-Cola / Nestlé / Shein reports — sites are JS/WAF-gated; **user to drop PDFs into `backend/ESG_Reports/`**, then run `scripts/run_company_analysis.py`
- [ ] Re-ingest a clean corpus once Phase 1–4 land (fixes mojibake/company/doc_id in DB)

## 🟡 Housekeeping / decisions
- [ ] Commit the uncommitted stack (de-fiction, restructure, NVIDIA, rename, Phase 1) — suggest split commits
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
