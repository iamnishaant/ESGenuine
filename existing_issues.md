# Existing Issues — ESGenuine

> Living log of **concrete defects found by actually running the system** (not theory). Each entry: what was tested, exact input, expected vs actual, root cause, impact. Newest batch on top. Append new findings; don't delete verified ones.

**Severity:** 🔴 Critical (broken/silently wrong) · 🟠 Major (wrong/noisy output) · 🟡 Minor (inconsistency/cosmetic) · ✅ Verified working.

---

## Batch 2026-06-25b — Tier-1: ingest dedup + idempotent writes

**What ran:** `POST /v1/reports/ingest` re-ingesting the same PDF (same `company_name`+`report_year` → same `report_id`) inserted a *fresh* set of `claims` rows each time (each row gets a new `uuid4()` `claim_id`, so nothing ever collided). Re-uploading a report silently doubled its claim count and corrupted every downstream count/score.

**Fixed this batch:**
- ✅ **Content-hash dedup.** The endpoint now hashes the uploaded PDF (full-file SHA-256, the same digest Step0 triage already computes) and, before spawning a job, looks it up in `reports.file_hash`. An exact-content re-upload returns `{"status": "duplicate", "report_id": …}` with no new job — no duplicate work, no duplicate claims. `find_report_by_file_hash` / `sha256_file` in [supabase_ingest.py](backend/src/extractors/supabase_ingest.py); short-circuit in [server.py `/v1/reports/ingest`](backend/src/api/server.py).
- ✅ **Idempotent claim writes (delete-then-insert).** `ingest_claims_to_db` now clears a report's existing claims (`DELETE … WHERE report_id=… OR doc_id=…`) before writing the new set, so a re-ingest of *changed* content (same identity, new bytes) **replaces** rather than appends. Empty extractions skip the delete (won't wipe a prior good ingest). Returns `replaced` in the result.
- ✅ **`reports` row now written by the ingest path.** Previously only the collector populated `reports`; the live ingest never did. `ingest_claims_to_db` upserts the report row (keyed by `report_id`, carrying `file_hash` + `claim_count`) — but only when `inserted > 0`, so a fully-failed insert stays retryable instead of being dedup-blocked.
- ✅ **Migration applied to live DB.** `backend/database/2026-06-25_reports_file_hash.sql` (`reports.file_hash` + `reports_file_hash_idx`) and the earlier `2026-06-25_observability_type.sql` both applied + verified against Supabase (columns + index present). Both are also folded into `schema.sql` for fresh setups.
- ✅ **RLS delete caveat resolved (verified live).** RLS is **disabled** on `claims`, all partitions, and `reports` (no policies); `has_table_privilege('anon','public.claims','DELETE')=True`. A live no-op delete via the publishable key was allowed, and a full **delete-then-insert round-trip on a sentinel report kept the claim count at 3 (not 6)** with a single upserted `reports` row carrying `file_hash` — i.e. idempotent re-ingest is proven against the real DB, not just in code.
- ⏭️ **Out of scope (next Tier-1 item):** persisting in-memory `ingest_jobs` to DB.

---

## Batch 2026-06-25 — Full issue sweep: reasoning spine + data quality + state (Tiers 1–3)

**What ran:** re-audited the 2026-06-23/24 batches against current code (the codebase had drifted ahead of the log) and fixed the reasoning chain end-to-end. Verified against the live DB.

**Already fixed by earlier Phase 1/2 work (confirmed in code, now closed):**
- ✅ **#4** Mojibake — `pdf_parser.py` uses `ftfy.fix_text` + a repair step (line ~291). Clean source sentences.
- ✅ **#10** `/sections` now returns `total` ([server.py:127](backend/src/api/server.py)).
- ✅ **#11** `/health` returns `app.version` (4.0.0), no longer hardcoded ([server.py:306](backend/src/api/server.py)).
- ✅ **#14** `metric_key` now built from a canonical unit **dimension**, not a raw-unit slug; implausible (aspect, dimension) pairs collapse to `.unspecified` ([ontology.py `generate_metric_key`](backend/src/extractors/ontology.py)).
- 🟠→🟡 **#15** Aspect/unit mis-assignment **mitigated** by the plausibility filter (`is_plausible_metric`), but the 8B extractor can still emit wrong values for a key (see residual below).

**Fixed this batch:**
- ✅ **#3** `doc_id` = real document id across **all three** ingest paths: `supabase_ingest.py` (already correct), [ingest_claims.py](backend/src/extractors/ingest_claims.py) (was `chunk_id[:12]`), [run_integration_test.py:265](backend/tests/run_integration_test.py). Old DB rows still hold chunk-ids (historical; new ingests are correct).
- ✅ **#1** `match_claims` RPC **applied to live DB** (was never applied → PGRST202). Rewrote it to also return `metric_key, metric_value, metric_unit, metric_direction, time_bucket, location_scope` — the previous return set starved the engine. Verified via PostgREST (anon key) with a real embedding: returns matches with all fields. SQL: [match_claims_rpc.sql](backend/database/match_claims_rpc.sql).
- ✅ **#7** Contradiction engine rewritten ([nli_engine.py `_numeric_conflict`](backend/src/reasoning/nli_engine.py)): now (a) only compares claims with the **same meaningful `metric_key` + same unit** (family-level blocking was too coarse), (b) ignores placeholder time buckets (`unknown_time`/null), (c) guards **zero baselines** (`0.0 -> 2.8` no longer flags), (d) restricts Hard direction-conflict to same metric/time/scope. Unit-tested all gates.
- ✅ **#2** Reasoning endpoints verified live: chain was dead only because of #1. Corpus scan now yields **47 typed conflicts (34 Temporal, 13 Scope)**, all same-`metric_key`, no zero/unknown-time noise (vs the old 20 cross-metric false positives). `/reports/{chunk}/contradictions` returns 0 for 6-claim chunk docs — correct (no same-metric pairs); real grouping arrives once reports are ingested via the fixed `doc_id` path.

**New residual found (extends #15/#16):** the engine correctly flags `social.workforce.total.count shifted 20255 -> 74.445` — but `74.445` is a ratio mislabeled as a *count* at extraction time. The numeric reasoning is now sound; the remaining noise is **upstream value/unit mis-assignment** (needs 70B extraction + a unit normalizer, per #16). Tracked, not an engine defect.

**Tier 2/3 — data quality, state, contract (also fixed this batch):**
- ✅ **#6** Company mislabel. The production path (`POST /v1/reports/ingest`) already takes an explicit `company_name` (no fragile filename inference). Corrected the live data: all **181** claims relabeled `Business` → **Tata Power** (`company_id=tata_power`, `report_id=tata_power_2024`), and their `doc_id` consolidated from per-chunk ids to `tata_power_2024` (this also completes #3 for the existing rows, so the `/reports/{doc}/contradictions` endpoint now groups them as one document). Affected rows backed up to scratchpad first.
- ✅ **#13** `reports` table refreshed: `business_2024` → `tata_power_2024`/Tata Power, `claim_count` recomputed from actual claims (214 → 181; the 3 empty shells stay at 0), all dead `F:\` `file_path`s set NULL.
- ✅ **#5** Table extractor ([pdf_parser.py `Step5_TableExtractor`](backend/src/parsers/pdf_parser.py)) now (a) skips fragment-tables whose header row has <2 non-empty headers, (b) drops cells under empty headers, (c) de-dupes colliding header names, (d) rejects near-empty rows (≤2 chars). Validated against the audit's own 163-row artifact: removes exactly the documented noise (74 empty-header + 42 short → 99 dropped, 64 clean rows kept). Note: single-column datasheets that pdfplumber mis-extracts without row labels (e.g. bp datasheet) now correctly yield 0 — those were always label-less noise.
- ✅ **#9** `location_text` junk: 10 live rows holding the literal `"null"`/`"none"` set to NULL; write paths now guard via `_clean_str` ([supabase_ingest.py](backend/src/extractors/supabase_ingest.py)) + inline guard in [ingest_claims.py](backend/src/extractors/ingest_claims.py). The 51 NULL `time_start` rows are inherent (no date to fabricate) and are now safely handled by #7's unknown-time gating.
- ✅ **#12** Document filename persisted across restart: startup now reads `filename`/`statistics`/`sections` back from each `*_full.json` ([server.py startup](backend/src/api/server.py)) instead of the `"Discovered: {id}"` placeholder.
- ✅ **#8** Empty disk claims artifact: `GET /v1/claims/{doc_id}` now falls back to the canonical **Supabase** store (keyed by `doc_id` or `report_id`) when the disk artifact is empty/missing — so async-ingested reports surface their claims (verified: `tata_power_2024` → 181). Legacy pre-migration file-hash ids (e.g. `08dbf8224013`) honestly 404 instead of returning a misleading `total: 0`.

**Tier 4 — extraction trust (#15/#16 closed in code):**
- ✅ **#16** Cross-year drift. New [`UnitCanonicalizer`](backend/src/extractors/ontology.py) converts (value, unit) to a canonical base per dimension (ktCO2e→tCO2e, GWh→MWh, ML→m³, acres→hectares, …). The engine now compares **canonical** values, so unit-scale differences no longer read as contradictions (1.2 ktCO2e == 1200 tCO2e). Added a **magnitude-outlier guard**: an extreme YoY ratio (>100×) on an absolute quantity (count/mass/energy/volume/area/co2e) is treated as a unit/extraction error, not a real change — directly kills the "`scope1 10 → 100000`" class. Same-year large mismatches (real contradictions like 12.3M vs 453K) are preserved. Corpus contradictions 47 → **39** (8 untrustworthy drift pairs removed).
- ✅ **#15** Value mislabels. `UnitCanonicalizer.is_value_plausible` rejects values that contradict the shape their `metric_key` implies (a `.count` of 74.445, a negative `.percent`); the engine drops such pairs before reasoning.
- ⚙️ **Operational remainder:** raw value/unit *accuracy* at the source still benefits from 70B extraction (`NVIDIA_MODEL=meta/llama-3.3-70b-instruct`) — the code is now robust to the noise, but cleaner extraction is the upstream win. Persisting canonical_value/_unit to the DB (vs. computing at compare time) is a future optimization.

- ✅ **#17** Scorer recalibrated ([models.py `GroundabilityClassifier`](backend/src/extractors/models.py) + [ontology.py `compute_vagueness`](backend/src/extractors/ontology.py)): groundability now respects `claim_type` (performance ×1.0, target ×0.6, narrative ×0.5; optical aspects floored at 0.7) and de-weights noisy "global" locations; vagueness adds a forward-looking/narrative penalty. Re-scored all **1435** live rows (no-LLM): groundability avg 0.706→0.480, "groundable (≥0.75)" 879→368 (fixes the 57%-high-yet-64%-narrative mismatch), vagueness now flags 430 claims so the taxonomy `VAGUE`/`NON_GROUNDABLE` flags fire correctly.

**Status: all 17 original issues resolved or mitigated.** Live data consistent + re-scored; reasoning surface alive and trustworthy. Remaining work is operational (70B ingestion for cleaner extraction values) + future optimizations (persist canonical values), not defects.

---

## Batch 2026-06-24 — Phase 1 SOTA extraction run (Shell 2022/2023)

**What ran:** section-level extraction (NVIDIA `llama-3.1-8b-instruct`, 4-way concurrent, `skip_tables`) on real Shell reports. 2022: 65 calls→527 claims · 2023: 83 calls→779 claims · **0 timeouts** · mojibake fixed (clean source sentences). Headline defensive signal is solid: **~64% narrative/aspirational, ~38% no metric → lack of disclosed evidence.** New defects found:

| # | Sev | Area | Symptom |
|---|-----|------|---------|
| 14 | 🟠 | Extraction | **`metric_key` normalization is garbage** — keys like `emissions.scope1.litres`, `emissions.scope1.usd`, `social.health_safety.ltifr.cages`, `ltifr.km` (`500,000,000 km → 54 km`). Built as `aspect.<raw-unit-slug>` → unrelated figures collide. |
| 15 | 🟠 | Extraction | **Aspect/unit mis-assignment** — Scope-1 emissions reported in `litres`/`cages`/`km`/`USD`; LTIFR in `cages`/`km`. 8B model + topic-mixed windows produce wrong (aspect, unit) pairs. Use 70B for final + tighter windows. |
| 16 | 🟠 | Reasoning input | **Cross-year drift untrustworthy** — because of #14/#15, YoY matching compares nonsense (`scope1.tonnes 10 → 100000`). Needs canonical units + clean metric_keys (Phase 2 tables + a unit normalizer). |
| 17 | 🟡 | Scoring | **Groundability vs claim_type disagree** — 57% "high groundability" yet 64% "narrative/aspirational". Narrative claims scoring high groundability ⇒ the rule-based scorer is lenient/miscalibrated. |

---

## Batch 2026-06-23 — End-to-end runtime audit

**How tested:** booted `uvicorn src.api.server:app` (port 8031), hit every endpoint with curl against the on-disk parsed doc `08dbf8224013`, and queried the live Supabase REST API directly (anon key) for the data the frontend renders. The LLM provider is now NVIDIA NIM (verified separately).

### Summary table

| # | Sev | Area | Endpoint / Source | Symptom |
|---|-----|------|-------------------|---------|
| 1 | 🔴 | Reasoning | `POST /rest/v1/rpc/match_claims` | RPC **does not exist** in live DB → contradiction retrieval silently returns `[]` |
| 2 | 🔴 | Reasoning | `GET /reports/{id}/contradictions`, `/risk-score` | Always return **0 conflicts** (consequence of #1 + #3); failure swallowed |
| 3 | 🔴 | Data model | Supabase `claims.doc_id` | `doc_id` holds **chunk IDs** (`chunk_0013`), not document IDs → reasoning groups by chunk |
| 4 | 🟠 | Parsing | `GET /v1/documents/{id}/sentences` | **Mojibake** in 194/1213 (16%) sentences (`India's`→`Indiaâ€™s`) |
| 5 | 🟠 | Parsing | `GET /v1/documents/{id}/tables` | **45% of table rows are noise** (empty headers, ≤2 chars) |
| 6 | 🟠 | Data quality | Supabase `claims.company_name` | All 181 claims labeled generic **`"Business"`** (actually Tata Power) |
| 7 | 🟠 | Reasoning quality | Supabase `contradictions` | **False/noisy contradictions** (cross-metric, zero-baseline, null time buckets) |
| 8 | 🟠 | Data state | `GET /v1/claims/08dbf8224013` | Returns `total: 0` — on-disk `..._claims.json` is an empty list |
| 9 | 🟡 | Data quality | Supabase `claims` | 10 rows have `location_text` == string `"null"`; 51/181 (28%) `time_start` NULL |
| 10 | 🟡 | API contract | `GET /v1/documents/{id}/sections` | Missing the `total` field that every other list endpoint returns |
| 11 | 🟡 | API contract | `GET /health` | Reports `version: "3.0.0"`; app/openapi version is `"4.0.0"` |
| 12 | 🟡 | State | `GET /v1/documents` | Filename is placeholder `"Discovered: {id}"` after restart (in-memory registry) |
| 13 | 🟡 | Data state | Supabase `reports` | `claim_count` stale (214 vs 181 actual); 3/4 reports have 0 claims; `file_path` on dead **F:** drive |

---

### Detailed findings

#### 1. 🔴 `match_claims` vector-search RPC is missing from the live database
- **Test:** `POST https://<proj>.supabase.co/rest/v1/rpc/match_claims` with a 768-d zero vector + `filter_family`.
- **Expected:** rows of similar claims.
- **Actual:** `HTTP 404`, `{"code":"PGRST202", "message":"Could not find the function public.match_claims ..."}`.
- **Root cause:** [backend/database/match_claims_rpc.sql](backend/database/match_claims_rpc.sql) exists in the repo but was **never applied** to the live DB (schema drift, same class as the partition mismatch).
- **Impact:** [retrieval.py `find_candidate_pairs`](backend/src/reasoning/retrieval.py) calls the RPC inside a `try/except Exception: return []` ([retrieval.py:85-87](backend/src/reasoning/retrieval.py)). The exception is **swallowed**, so semantic retrieval silently yields nothing. The contradiction engine has no candidate pairs to evaluate. **This is the single most important runtime defect.**

#### 2. 🔴 Reasoning endpoints always return zero
- **Test:** `GET /reports/chunk_0013/contradictions` → `{"total_conflicts":0,...,"conflicts":[]}`. `GET /reports/chunk_0013/risk-score` → `greenwashing_risk: 0.0`, all sub-counts 0.
- **Expected:** real contradiction analysis (chunk_0013 has 6 claims in the DB).
- **Actual:** zeros, every time.
- **Root cause:** combination of #1 (no candidate pairs) and #3 (per-chunk grouping). Even if the RPC existed, #3 caps comparisons to a single chunk.
- **Note:** the populated `contradictions` table (20 rows) was **not** produced by these endpoints — it was written by the offline integration-test runner via a different path. The live API reasoning surface is effectively dead.

#### 3. 🔴 `doc_id` is polluted with chunk IDs
- **Test:** distinct `doc_id` values in `claims` = `chunk_0013`, `chunk_0023`, `chunk_0017`, … (one per chunk).
- **Expected:** a single document identifier per report (e.g., `08dbf8224013` or `business_2024`).
- **Root cause:** ingestion sets `"doc_id": prob.get("chunk_id", "doc")[:12]` ([ingest_claims.py:154](backend/src/extractors/ingest_claims.py), mirrored in [run_integration_test.py:265](backend/tests/run_integration_test.py)).
- **Impact:** there is no document-level grouping in the DB; `/reports/{doc_id}/*` can only ever see the handful of claims sharing one chunk-id prefix. Cross-document and intra-document contradiction detection is structurally impossible as wired.

#### 4. 🟠 Mojibake (double-encoded UTF-8) in parsed text
- **Test:** `GET /v1/documents/08dbf8224013/sentences` → `"...one of Indiaâ€™s largest..."`. Count: **194/1213 (16%)** sentences contain `â€`/`Ã`. In Supabase claims: 8/181 `source_sentence` affected.
- **Expected:** `India's` (U+2019 apostrophe).
- **Root cause:** smart-quote/UTF-8 bytes from PyMuPDF being decoded as Latin-1 then re-encoded somewhere in [pdf_parser.py Step 1](backend/src/parsers/pdf_parser.py) extraction/serialization.
- **Impact:** corrupts source sentences → feeds garbled text to the LLM extractor, embeddings, and NLI; degrades every downstream signal and looks unprofessional in the UI.

#### 5. 🟠 Table extraction emits mostly-noise rows
- **Test:** `GET /v1/documents/08dbf8224013/tables` → 163 rows; sample `{"table_id":"tbl_007","cells":{"":"7"}}`. **74/163 (45%)** rows have an empty-string column header; **42/163 (26%)** have ≤2 chars of total content.
- **Expected:** structured rows with real headers→values.
- **Root cause:** [Step5_TableExtractor](backend/src/parsers/pdf_parser.py) accepts any `pdfplumber` table with ≥2 rows and blindly maps `table[0]` as headers; layout fragments and page furniture become "tables".
- **Impact:** pollutes the table claim pipeline and any table-derived metrics with junk.

#### 6. 🟠 Company is mislabeled "Business"
- **Test:** distinct `company_name` across all 181 claims = `{"Business"}`. The report is Tata Power's BRSR.
- **Root cause:** metadata inferred from filename `business-responsibility-and-sustainability-report...` → company token "Business" ([populate_reports.py infer_metadata](backend/scripts/populate_reports.py)).
- **Impact:** Portfolio/Claim views attribute everything to a non-existent company "Business"; cross-company analysis is meaningless.

#### 7. 🟠 Contradictions are noisy / false positives
- **Test:** sample of `contradictions.reasoning`:
  - `Value shifted 22372.0->9134.0 between null and unknown_time` (Temporal)
  - `Value mismatch: 12319000.0 vs 453608.0 for same time/scope` (Metric)
  - `Value shifted 0.0->2.8 between unknown_time and 2024` (Temporal)
- **Why these are wrong:** the numeric engine ([nli_engine.py `_numeric_conflict`](backend/src/reasoning/nli_engine.py)) compares `metric_value`s that share a **coarse `metric_family`** but are almost certainly **different `metric_key`s/units** (e.g., 12.3M vs 453K), treats `time_bucket="unknown_time"`/`null` as comparable, and flags `0.0 -> 2.8` (zero baseline). It is **unit- and metric-key-blind**.
- **Impact:** the headline "contradictions/greenwashing" output is untrustworthy.

#### 8. 🟠 Discovered doc has zero claims on disk
- **Test:** `GET /v1/claims/08dbf8224013` → `total: 0`. File [`backend/parsed/08dbf8224013_claims.json`](backend/parsed) is an empty `[]`.
- **Root cause:** parse artifacts (sentences/chunks/tables) were saved, but the claims file is empty (extraction not persisted here, or emptied by `clean_json.py`). A duplicate copy also lives in `backend/ESG_Reports/test_output/`.
- **Impact:** the only "discovered" document surfaces no claims through the API.

#### 9. 🟡 `"null"`-string and missing temporal data in claims
- **Test:** 10/181 claims have `location_text` equal to the literal string `"null"`; 51/181 (28%) have `time_start = NULL`.
- **Impact:** the `"null"` string is a data smell (now defended in the frontend `realOrNull`, but the DB is still dirty); missing `time_start` collapses time buckets and feeds #7.

#### 10. 🟡 `/sections` breaks the list-endpoint contract
- **Test:** `/v1/documents/{id}/sections` returns `{document_id, sections}` with **no `total`**; `/sentences`, `/candidates`, `/chunks`, `/tables`, `/provenance` all return `total`.
- **Impact:** inconsistent contract; a client iterating `total` gets `undefined` for sections.

#### 11. 🟡 `/health` version is stale
- **Test:** `/health` → `"version":"3.0.0"`; OpenAPI/app version is `"4.0.0"` ([server.py health route](backend/src/api/server.py)). Hardcoded string, drifts from the app version.

#### 12. 🟡 Document filename lost on restart
- **Test:** `/v1/documents` → `"filename":"Discovered: 08dbf8224013"`.
- **Root cause:** `document_registry` is an in-memory dict rebuilt from disk globbing on startup ([server.py:44-52](backend/src/api/server.py)); the real PDF filename isn't persisted.
- **Impact:** UI shows a placeholder name; no durable document metadata.

#### 13. 🟡 `reports` table is stale/misleading
- **Test:** `business_2024` `claim_count = 214` but only **181** claims exist; `infosys_2023`, `infosys_2025`, `microsoft_2024` all have `claim_count = 0`; every `file_path` points to `F:\AMRITA ALL SEMESTER\...` (project now lives on `E:`).
- **Impact:** stale aggregates; 3 of 4 reports are empty shells; dead file paths.

---

### ✅ Verified working (so they aren't re-investigated)

| Area | Test | Result |
|------|------|--------|
| Health/liveness | `GET /health` | 200 ok (version string aside) |
| Document listing | `GET /v1/documents` | 200, returns discovered doc |
| Retrieval endpoints | `/sections /sentences /candidates /chunks /tables /provenance` | 200, correct structure & consistent counts (1445 raw blocks → 205 chunks/candidates/provenance) |
| Missing-doc handling | `/v1/documents/NOPE/sections`, `/v1/claims/NOPE` | **404** (correct) |
| Reasoning no-data path | `/reports/NOPE/contradictions` | **404** "No claims found" (correct) |
| Extract guard | `POST /v1/claims/extract {NOPE}` | **404** (correct) |
| Upload — corrupt PDF | `POST /v1/upload` (non-PDF bytes, `.pdf`) | **422** "Invalid PDF" (triage fix works) |
| Upload — wrong type | `POST /v1/upload` (`.txt`) | **400** (correct) |
| Sentence section filter | `/sentences?section=Environmental%20Performance` | 200, filtered 172 (works) |
| Contradiction integrity | orphan check | 20 rows, 29 refs, **0 orphaned** |
| LLM extraction (NVIDIA) | `LLMClient` → `meta/llama-3.3-70b-instruct` | 200, well-formed AAMLT JSON |

---

### Not exhaustively exercised (flagged, needs follow-up)
- **`POST /v1/claims/extract` full run** was *not* executed end-to-end: it issues **one LLM call per chunk serially** (205 calls for this doc). Functionally wired, but heavy/slow and unbatched — confirm output quality + cost on a small doc before relying on it.
- **`POST /v1/upload` full parse** (valid PDF) was validated for triage/202 paths in a prior session; not re-run here to avoid a multi-minute synchronous parse.

> Cross-reference: architectural remedies for #1–#3, #7 and the heavy/serial paths are detailed in [take_step_forward.md](take_step_forward.md) (async ingest spine, data-model fix, reasoning rebuild, migrations).
