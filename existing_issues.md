# Existing Issues — ESGenuine

> Living log of **concrete defects found by actually running the system** (not theory). Each entry: what was tested, exact input, expected vs actual, root cause, impact. Newest batch on top. Append new findings; don't delete verified ones.

**Severity:** 🔴 Critical (broken/silently wrong) · 🟠 Major (wrong/noisy output) · 🟡 Minor (inconsistency/cosmetic) · ✅ Verified working.

---

## Batch 2026-08-10 — #21–#27: frontend UX defects (globe focus, dead controls, failure-vs-empty)

Found by reading the render paths and reproducing the math/data, not by theory. All fixed in this batch.

#### 21. 🔴 Globe rotated the selected company to the FAR side of the Earth
- **Test:** `Globe.tsx` `focusYaw = Math.PI / 2 - alpha`, where `alpha = atan2(local.z, local.x)`.
- **Root cause:** rotating the group by `y` maps a point's local yaw `a` to world yaw `a - y`. Facing a camera at azimuth `beta` therefore requires `y = alpha - beta`. The old formula gives world yaw `2*alpha - PI/2`, which equals `beta` for exactly **one** longitude.
- **Reproduced numerically** on the real HQ registry, camera at (0,0,5) — `visible` is the horizon test `P·C > r²`:

  | Company | old facing | old visible | fixed facing | fixed visible |
  |---|---|---|---|---|
  | Shell | −0.622 | **false** | 0.622 | true |
  | Microsoft | 0.293 | **false** | 0.673 | true |
  | Infosys | 0.886 | true | 0.975 | true |
  | Tata Power | 0.781 | true | 0.946 | true |

- **Impact:** clicking Shell or Microsoft spun their own pin behind the globe. It looked intermittent because Infosys/Tata sit near `alpha ≈ PI/2`, where the wrong formula happens to be right.
- **Fix:** target `alpha - cameraAzimuth`, derived from the live camera (so it also survives the user having orbited first), and stop steering once settled so the globe doesn't counter-rotate against a drag.

#### 22. 🟠 Far-side pins drew labels and stole clicks through the Earth
- **Root cause:** drei `<Html>` is a DOM overlay with no depth test, and an invisible raycast mesh is still hit on the back hemisphere.
- **Fix:** per-pin horizon test (`P·C > r²`) gates both the label and the pointer handlers.

#### 23. 🟠 Risk Dashboard's narrative counter was permanently 0
- **Test:** `claims.filter(c => c.verifiabilityClass === 'Narrative')`.
- **Root cause:** `claims.claim_type` is stored **lowercase** (`performance` 1263 / `narrative` 370 / `target` 97). The comparison never matched.
- **Fix:** case-insensitive compare; the type is now documented as lowercase on the `Claim` interface and centralised in `lib/claimFacets.ts`.

#### 24. 🟠 Backend failure was rendered as "you have no data"
- **Benchmark:** a failed `getCrossCompany` fell through to *"No two companies share this metric on a common canonical unit yet"* — blaming the corpus for a connection failure.
- **Audit Trail:** any missing claim rendered *"No Claims Available — could not find any claims"*, including a stale claim URL while 1730 claims were loaded.
- **Header:** the status light was a hardcoded green dot reading **"Connected"** regardless of backend state — it said Connected while every score on the page showed "—".
- **Fix:** all three now distinguish *request failed* / *corpus empty* / *id not found*, and the header light reads the same probe (`useBackendScores.availability`) the scores use.

#### 25. 🟠 Selecting a company anywhere threw the selection away
- **Test:** Portfolio Overview rows had `cursor-pointer` + hover styling, but only the 20px chevron was a `<Link>`, and it pointed at the unscoped `/claims`.
- **Fix:** the Claim Directory now takes `?view=&company=&report=` from the URL; the whole Portfolio row links to that company's drill-down, and the globe's CompanyPanel links there too. Back/forward and deep links work.

#### 26. 🟡 Controls that animated but did nothing
- `Filter Portfolio` (Portfolio Overview) and the Header's bell / settings / user buttons had **no `onClick` at all** while carrying `whileHover`/`whileTap` press animations.
- **Fix:** the portfolio filter is a real search + risk filter; settings and the user chip are links (the chip shows the actually signed-in email via `/v1/auth/me`); the bell is removed rather than faked.

#### 27. 🟡 Sidebar "Evidence Analysis" was a dead end
- **Test:** the sidebar links to `/evidence` with **no** `claimId`, so the find-by-id returned undefined and a top-level nav item rendered *"Claim Not Found — the requested claim ID does not exist in the database."*
- **Fix:** with no id there is nothing to fail — it defaults to the first integrity-gap claim, matching what Audit Trail already did.

#### 28. 🟡 ClaimExplorer duplicated the corpus fetch
- **Root cause:** the page ran its own copy of `fetchAllClaimRows` + the contradiction join instead of `useClaims()`, so every visit re-downloaded all 1730 rows and the page never observed `invalidateClaimsCache()` after an ingest.
- **Fix:** switched to the shared hook.

> Verified: `tsc --noEmit` clean, `vite build` clean, and the new grouping/facet logic run against all 1730 live rows — 4 companies / 6 report cells, cell totals reconcile to 1730 exactly, drill-down count matches the cell, and no filter leakage on a 3-facet combination.

---

## Status rollup — 2026-06-26

All 🔴 Critical and 🟠 major data defects are **resolved & verified on live data**. #1–#19 are closed except the items explicitly listed below. Verified this date:
- **#1** `match_claims` vector RPC exists & is callable (no longer PGRST202). **#2** reasoning endpoints return real conflicts (was a consequence of #1+#3).
- **#3** `doc_id` is a real document id (`tata_power_2024`), not a chunk id. **#6** companies labeled correctly (Tata Power / Shell / Microsoft / Infosys — not "Business").
- **#13** all 6 reports carry accurate `claim_count` (181 / 527 / 727 / 369 / 249 / 332) — no empty shells (Microsoft + Infosys ingested with 70B).
- **#7** contradiction noise addressed (#18 cross-year fix + unit-guard + #19 dimension split). **#18** count over-fire fixed. **#19** deterministic layer fixed + backfilled (top batch).
- Score saturation fixed (count-weighted v2.0) + human-in-the-loop review (v2.1).

**Minor cosmetics #4/#5/#10/#11/#12 — ✅ all resolved & verified 2026-06-26** (were already fixed in code; entries below predate the fixes):
- **#4** mojibake: Step 1 runs `fix_text` (ftfy) per block ([pdf_parser.py:292](backend/src/parsers/pdf_parser.py)); `fix_text("Indiaâ€™s")` → `"India's"`, and the live corpus has **0/2385** claims with mojibake markers.
- **#5** table noise: Step 5 drops empty-header columns and rows with ≤2 chars of content ([pdf_parser.py:670-705](backend/src/parsers/pdf_parser.py)).
- **#10** `/sections` now returns `total` ([server.py:141](backend/src/api/server.py)). **#11** `/health` returns `app.version` (4.0.0), not a hardcoded string ([server.py:371](backend/src/api/server.py)). **#12** filename is read back from the parse artifact instead of a "Discovered: {id}" placeholder ([server.py:55-62](backend/src/api/server.py)).

**Still open — externally blocked / accepted ceiling (the remaining gap):**
- **LLM extraction ceiling** (residual of #7/#19): aspect/scope *mislabels* (diversity claims tagged `biodiversity`; 58Mt vs 305Mt both tagged `scope1` same year). Not deterministically fixable — needs 70B re-extraction with tighter aspect derivation. The product's standing data-quality remainder.
  - **Being closed (2026-07-13, in progress):** the 96.1/round-2 pipeline (Docling tables + quality gate + ontology round 2 + FY-column repair) is re-extracting the full corpus on 70B — this directly attacks the mislabel residual. tata/shell_2022/infosys_2023 landed; infosys_2025/microsoft/shell_2023 extracting. Fresh extraction score is the honest re-measure once the batch completes.
- **Evidence-corpus depth** (fact-check coverage 4–46%): needs *sourced* real reference figures (no-fabricate rule) — not an engine defect; blocked on external data. *(Partially addressed: corpus grew 4→24 page-cited records with the power/energy dimension split.)*

---

## Batch 2026-08-09c — #24: RLS APPLIED to production; anon write primitive closed

> First session with live DB access. The vulnerability was **demonstrated, not inferred**,
> and auditing the real grants revealed the migration would not have closed it.

### ✅ #24a 🔴 — anonymous write access to score-bearing tables — CLOSED
**Pre-migration, verified live** (project `fpxgspimlsgiuvalwcmx`, 1730 claims):
RLS `false` on all 12 public tables, **0 policies**, and anon holding
`DELETE,INSERT,TRUNCATE,UPDATE` on 11 tables. Proof it was live, not theoretical: using the
publishable key that ships in the JS bundle, `POST /rest/v1/jobs` returned **201** (sentinel
deleted immediately after). Any visitor could forge `claim_reviews` — which move the
published integrity score — or delete `contradictions`.

**Applied 2026-08-09** via Supabase SQL Editor (the agent's DDL execution was correctly
blocked by the permission classifier; self-granting production write access is exactly what
that guard is for). **Post-apply, verified:**
| check | result |
|---|---|
| RLS on 6 tables + all 5 `claims` partitions | ✅ true |
| policies | ✅ 11, all `SELECT`-only |
| anon / authenticated privileges | ✅ `SELECT` only (TRUNCATE gone) |
| corpus | ✅ 1730 claims intact |
| anon READ claims / contradictions / reports | ✅ 200 |
| anon INSERT jobs | ✅ **401 `42501` permission denied** (was 201) |
| anon DELETE contradictions | ✅ 401 |
| service_role INSERT / cleanup | ✅ 201 / 204 |
| offline suite | ✅ 173/173 |

### ✅ #24b 🔴 — the migration itself would have left the corpus wipeable
See `927fcc4`. Two bypasses caught by auditing the live grants *before* applying:
1. **TRUNCATE is not subject to RLS.** Policies filter SELECT/INSERT/UPDATE/DELETE only;
   TRUNCATE is a table-level privilege checked before any policy. Revoking just I/U/D would
   have left the public key able to wipe all 1730 claims **while the verify query reported
   `RLS=true`** — a fix that looks correct and isn't. Now `REVOKE ALL PRIVILEGES` + re-`GRANT
   SELECT` (also catches REFERENCES/TRIGGER).
2. **Partition grants do not cascade.** All five partitions independently held
   `DELETE,INSERT,TRUNCATE,UPDATE`; the parent REVOKE missed them. Now revoked in the same
   `pg_inherits` loop that enables RLS.

*Lesson: verify a security fix against the live object, not the migration's intent — and
remember RLS has a TRUNCATE-shaped hole in it.*

### ⚠️ #24c — follow-ups
- **Rotate `SUPABASE_SERVICE_ROLE_KEY`** — it was pasted into a chat transcript. It bypasses
  RLS entirely, so it is the one credential worth being strict about.
- `.env` still holds a legacy `eyJ…` publishable key while the dashboard now issues
  `sb_publishable_…`; both work today, they diverge when legacy keys are retired.
- Supabase migration history is still empty ("No migrations") — everything has been applied
  by hand. Versioned `supabase/migrations/` remains an open TODO item.

---

## Batch 2026-08-09b — measurement gaps closed: ablation + recall (#23)

> Not runtime defects — **measurement** defects. The system was being judged by a number
> that could not fall for the two most important reasons. Both harnesses are LLM-free and
> run off the frozen fixtures already committed, so they re-run in seconds on any change.

### ✅ #23a 🔴 — the extraction score had no recall term, and could not have one
`EXTRACTION_SCORE` averaged five precision-family rates. Structural, not a missing formula:
every gold set is sampled *from claims the extractor already emitted*, so a missed claim was
invisible. A pipeline that emitted 1 perfect claim and dropped 372 would have scored ~100.
**Fix:** `backend/scripts/run_recall.py`. Docling returns each page as GFM markdown with row
labels and column headers intact, so numeric table facts are **mechanically enumerable** — a
real recall denominator with no human annotation. **Measured: Tata 54.4%** (262/482 cells).
Deliberately conservative (the denominator includes non-claim cells like office counts), so
true recall is ≥ reported; the cell filter is small and auditable in `_candidate_cells`.

### ✅ #23g 🔴 (reproducibility) — every local model floated on `main`; name duplicated 4×
`SentenceTransformer("BAAI/bge-base-en-v1.5")` and the NLI `pipeline(...)` loaded by **bare
name**, i.e. whatever is currently on that HF repo's `main`. An upstream re-upload would
change embeddings → retrieval → contradictions → **every published score**, with no code
change, no version bump and nothing in git to explain the drift. Fatal for a reproducible
result. The model name was also duplicated across `ingest_claims`, `supabase_ingest`,
`reasoning.agent` and `reasoning.retrieval`, so the embedder that *built* the vectors could
silently diverge from the one that *queries* them.

**Fix:** new `backend/src/model_config.py` — one definition of model + pinned commit +
loader, env-overridable (`EMBED_MODEL`/`EMBED_REVISION`/`NLI_MODEL`/`NLI_REVISION`/`SEED`).
Pinned to the SHAs **already in the local HF cache**, i.e. the exact weights that produced
the currently reported numbers, so this makes existing results reproducible rather than
freezing an arbitrary new version:
- `BAAI/bge-base-en-v1.5` → `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`
- `typeform/distilbert-base-uncased-mnli` → `cfa538a0fddbbd978fefe8966c1aeff7ad409c90`

All 5 load sites now call `load_embedder()` / `load_nli()`; `seed_everything()` (python +
numpy + torch, SEED=42) runs at process start and the server logs `model_provenance()` so
every run states which weights and seed produced its numbers. **Verified:** both models load
offline from cache at the pinned revision, embedder 768-dim (matches `VECTOR(768)`), NLI
returns CONTRADICTION 0.999, process-level caching holds. Gold floors unchanged (96.1/89.7).
`test_model_config.py` (5 tests) asserts the revisions are **40-char SHAs** (a tag or `main`
would still float), that the embedder stays 768-dim, and that seeding is deterministic.

### ✅ #23f 🟠 — recall denominator refined, and the real extraction gap identified
Diagnosing the 220 Tata misses showed the raw denominator was penalising correct behaviour:
- **90 cells (21%) were the SAME fact repeated** across column groups of a wide matrix table
  (p15 lists `Male | 20255` four times under one benefits matrix).
- **27 cells sat on BRSR governance FORM tables** ("was this reviewed by the Board?",
  "Frequency (Annually/Half-yearly)"). They carry numbers but assert no ESG quantity — the
  extractor is RIGHT to skip them, and p10 scoring 0/27 was correct behaviour, not a miss.

`run_recall.py` now reports **distinct-fact recall** as the headline (one `(row_label, value)`
per page = one fact, form cells dropped) and keeps raw cell recall as the conservative bound:
**Tata 54.4% raw → 59.5% distinct-fact.**

**The residual gap is real and now localised: wide matrix tables are under-extracted.** Not a
pillar bias (social is the largest table pillar at 41 claims) but a density problem — the LLM
summarises a big matrix into a handful of claims instead of one per row×period:
| page | table | GT cells | claims emitted |
|---|---|---|---|
| p15 | benefits coverage (Male/Female/Total × benefit) | ~34 | **3** |
| p23 | permanent vs other-than-permanent workforce | ~46 | **10** |
| p17 | employee demographics by gender | 92 | 21 |
Next lever is therefore **prompt/chunking for wide tables** (emit one claim per row×period),
not table-page detection. Locked by 2 new gates (distinct-fact floor + a guard that the
duplicate/form filters keep firing). Suite **168/168**.

### ⚠️ #23b — RETRACTED SAME DAY: "detection is the main recall loss" was over-attributed
The harness splits misses into *page produced no claims* vs *processed but not emitted*:
| report | overall recall | pages w/ 0 claims | recall elsewhere | table claims |
|---|---|---|---|---|
| Tata BRSR FY24 | **54.4%** | 29 cells / 2 pages | **57.8%** | 179/373 (48%) |
| Shell SR2022 | 8.0% | 162 cells / 3 pages | **33.3%** | **13/247 (5%)** |

**First reading (WRONG):** "~76% of Shell's table facts were never looked at → pdfplumber
table-page detection is the top recall bug", and the Phase-2 detection item was promoted 🟠→🔴.

**Re-check the same day retracted that.** Two independent reasons the attribution fails:
1. **The Shell fixture is text-dominant — 13 table claims out of 247 (5%).** That run barely
   exercised the table pipeline, so its table-cell recall measures the run's configuration,
   not the shipped table path.
2. **Production Docling doesn't use pdfplumber detection at all.** `pipeline.py` calls
   `DoclingTableExtractor().extract(pdf_path)` with **no `pages` argument** → it converts
   every page. `find_table_pages` gates only the **VLM** path.

**What survives:** the Tata figure (**54.4%**, 48% table claims, near-full-document cache) is
sound and is the real recall number. The Shell figure is not evidence about detection.
**Guard added so this cannot recur:** `run_recall.py` now reports `table_claim_share` and
prints an explicit CONFOUND warning when it is <15%. Detection cost on the VLM path remains
**unmeasured** — measure before prioritising. Detection item restored to 🟠.

*Lesson for the paper: a recall denominator is only interpretable against a fixture that
actually ran the pipeline being judged.*

### ✅ #23c 🟠 — the 63.6→96.1 headline was never attributed to a component
No ablation existed, so "the deterministic layer is the contribution" was an assertion.
**Fix:** `backend/scripts/run_ablation.py` — 6 cumulative stages scored against both golds.
**Deterministic repair layer = +24.6 (Tata 71.5→96.1) and +7.0 (Shell 82.7→89.7)** over an
LLM-plus-vocabulary baseline, at zero LLM cost. The dominant lever depends on document type:
form-heavy BRSR → gate fixes **+20.5** (node 18.9%→94.6%) + furniture drop +2.4 (precision
74%→86%); narrative IR report → ontology mapping **+10.6** (node 0%→53.1%), furniture drop 0.
**Honesty guard:** the S0→S5 totals (+28.4/+17.6) are inflated because S0 node accuracy is 0%
*by construction* (free LLM text vs controlled vocabulary); the script prints S1→S5 as the
number to quote and says why. Also surfaced that S3 (`value_not_in_table`) contributes **+0.0**
to the composite — it flags rather than drops, feeding downstream fabrication analysis only.

### ✅ #23d 🟠 (security) — deployed API trusted localhost origins with credentials
`_DEV_ORIGINS` (localhost:8080/5173/3000) was in the CORS allowlist unconditionally, and
`allow_credentials=True`. A page on any developer's machine — or anything a user ran locally
on those ports — could make credentialed cross-origin calls against production. **Fix:** dev
origins are added only when `ENVIRONMENT` is not production (same flag `auth.py` uses for its
JWT fail-closed check), plus a loud warning if prod sets neither `ALLOWED_ORIGINS` nor
`ALLOWED_ORIGIN_REGEX`. Verified in both modes.

### ✅ #23e — both measurements locked as CI gates
`backend/tests/test_ablation_recall.py` (5 tests): the S1→S5 deterministic gain must stay
≥20.0 / ≥5.0; ablation S5 must still reproduce the shipped gold score (proves the ablation
mirrors the real stack rather than drifting into its own path); no stage may drop the score
>1.0; table-cell recall floors 50% / 6%; the detection split must stay populated. **Why this
matters:** a refactor that silently stopped the gate firing would still pass the gold floors
(the LLM fixture is frozen and already decent) while the project's actual contribution went
to zero. Suite now **166/166** offline.

---

## Batch 2026-08-09 — full-depth frontend↔backend cross-check (#22)

> Method: enumerated all 32 backend routes and every frontend call site, ran the offline
> suite, `tsc` under both the CI command and the real project config, `vite build`, and
> read the migration set for the security posture. Live DB was NOT reachable from the
> audit environment, so #22d's grant/RLS state is derived from migrations + code, not a
> live probe — **verify with the queries at the bottom of the migration after applying.**

### ✅ #22a 🔴 — landing page hard-coded `http://localhost:8000`, breaking every deploy
`DocumentViewer.tsx` declared its own `const API_BASE = 'http://localhost:8000'` instead of
importing the scheme-tolerant one from `lib/api.ts`. `DocumentViewer` renders on `Index.tsx`
(**the landing page**), so all 6 of its calls (`/v1/upload`, `/v1/documents`, `/v1/claims/*`)
pointed at localhost in a deployed build — and an HTTPS origin blocks them outright as mixed
content. `render.yaml` injects `VITE_API_BASE`, but that only reaches `lib/api.ts`; the local
constant was invisible to it, so the Blueprint's own stated fix did not cover the landing page.
**Fix:** import `API_BASE` from `@/lib/api`; the local declaration is gone. Only remaining
`localhost` is the intentional dev fallback inside `resolveApiBase()`.

### ✅ #22b 🔴 (CI) — the frontend type-check job checked *nothing* and hid 10 real errors
`.github/workflows/ci.yml` ran `npx tsc --noEmit`, which resolves `frontend/tsconfig.json` —
a solution-style config (`"files": []` + project references). Without build mode, tsc compiles
no files and **always exits 0**. Measured: `npx tsc --noEmit` → exit 0 / 0 errors, while
`npx tsc --noEmit -p tsconfig.app.json` → **exit 2 / 10 errors**. The job's long green streak
was vacuous.
**Root cause of the 10 errors (#22c).** **Fix:** CI now runs `npx tsc -b --force`. Proven with a
canary file containing a bogus column: old command exit 0 (missed), new command exit 2 (caught).
`*.tsbuildinfo` gitignored.

### ✅ #22c 🟠 — generated Supabase types were an empty stub; the whole read path was untyped
`frontend/src/integrations/supabase/types.ts` declared `Tables: { [_ in never]: never }` — an
empty `Database`. So `.from('claims')` / `.from('contradictions')` typed as `never`, and every
downstream field access errored (`useClaims.ts`, `ClaimExplorer.tsx`). Runtime was unaffected
(PostgREST ignores TS), but the frontend's **primary data source had zero compile-time safety**,
and calling it "the typed generated client" was inaccurate.
**Fix:** hand-written from the authoritative DDL (`schema.sql` + all 7 migrations, kept in step
with `_row()` in `supabase_ingest.py`): `claims` (28 cols), `contradictions`, `reports`,
`claim_reviews`, `jobs`, `satellite_evidence`, plus the `match_claims` / `search_claims` RPCs.
`users` deliberately omitted — anon is REVOKED on it. All 10 errors cleared with no source edits.

### ✅ #22d 🔴 (security) — public anon key had write access to score-bearing tables
No `ENABLE ROW LEVEL SECURITY` existed anywhere in `backend/database/`, while migrations granted
**anon** `INSERT/UPDATE/DELETE` on `claim_reviews` and `jobs`, `INSERT/DELETE` on `contradictions`,
and `INSERT` on `satellite_evidence`. The anon key ships inside the JS bundle (and is in git
history at `9338e89`), so any visitor could delete every contradiction or forge review rows —
and reviews **move the published integrity score** (`build_report()` honours `dismissed`; live
example: Microsoft 44.0 D → 59.4 C). An anonymous score-editing primitive is fatal for a product
whose deliverable *is* the score.
**Compounding factor found while fixing:** the backend authenticated with that *same anon key*
for all writes — there was no service-role key anywhere — so naive RLS would have broken ingest.
**Fix (two parts):** (1) all write paths now prefer `SUPABASE_SERVICE_ROLE_KEY`, falling back to
anon so pre-migration/local/CI use is unchanged — `supabase_ingest.py`, `ingest_claims.py`,
`retrieval.py`, `run_satellite_checks.py`. `agent.py` stays anon (read-only: least privilege).
(2) `backend/database/2026-08-09_enable_rls.sql` — revokes anon writes, enables RLS on all six
tables **and every `claims` partition** (RLS does not cascade to partitions; enabling only the
parent would have been cosmetic), adds SELECT-only policies, ships verify + rollback blocks.
**⚠️ NOT YET APPLIED** — needs `SUPABASE_SERVICE_ROLE_KEY` set in the backend env first.

### ✅ #22e 🟠 — the production ingest pipeline had no UI at all
`POST /v1/reports/ingest` + `GET /v1/jobs/{id}` had **zero frontend call sites**, so the entire
Docling→70B→quality-gate→ontology→embed→Supabase pipeline was reachable only from
`backend/scripts/`. Meanwhile the page named *"Submit New Report"* took typed-in claim **text**,
called an unrelated Supabase edge function (`analyze-claims`), and "submitted" by downloading a
JSON file — nothing persisted. Two independent LLM analysis paths that could disagree, with the
weaker one occupying the product's front door.
**Fix:** new `components/ReportIngestPanel.tsx` — PDF upload → auth (endpoint is
`Depends(get_current_user)`) → `ingestReport()` → 3s job polling with a stage bar
(queued→parsing→extracting→ingesting→done) → cache invalidation (`invalidateClaimsCache` +
`invalidateBackendScores`) → link to Integrity Audit. Handles the `status:"duplicate"`
content-hash response distinctly from a queued job. `SubmitReport` is now two tabs with the
ingest path as default; the text tool is retained, relabelled **"Quick claim check"**, and
carries an explicit banner that it does not touch the corpus or any score.

### ✅ #22f 🟡 — mock "production" orchestration + dead API surface
`src/pipeline/workflow_dag.py` was imported by nothing, hardcoded mock outputs in every node
(incl. `ndvi_delta_zscore: -1.5`, `"doc-mock-tata-2024"`), and its docstring claimed
**"(Production)"** — exactly the misleading artifact `take_step_forward.md` §3.2 flagged and
prescribed deleting. The real flow (`DocumentParsingPipeline` → `ExtractionPipeline` →
`ingest_claims_to_db`, resumable via `checkpoint.py`) is what §3.2 asked for and now exists.
**Fix:** deleted `src/pipeline/` (its only other file was `__init__.py`); dropped `langgraph`
from `requirements.txt` (sole consumer). Also pruned dead `lib/api.ts` exports —
`getGreenwashingFlags`, `getAuditSummary`, the unused `getTrajectory` variant (the surviving
`getTrajectory2` was renamed back to `getTrajectory`), and `setToken` demoted to module-private.

### ✅ #22g 🟠 — `start.bat` launched the backend with the wrong interpreter
The first cut of the new `start.bat` launcher invoked a bare `uvicorn` (venv prepended to
PATH). Smoke-testing it end-to-end exposed two independent failures:
1. the venv's `uvicorn.exe` console-script shim exits **rc=1 with no output** — those shims
   hardcode an absolute interpreter path at install time, so they break whenever the venv or
   repo folder moves or is renamed (a live risk here: renaming the top folder to `ESGenuine`
   is an open TODO item);
2. bare `python` on PATH resolved to a **different interpreter** (uvicorn **0.40.0**) than the
   venv (**0.41.0**, the pinned version) — i.e. the app would have run against the wrong
   environment even with the venv prepended to PATH.
**Fix:** launch as `..\.venv\Scripts\python.exe -m uvicorn ...`. The *relative* path from
`backend\` contains no spaces even though the absolute repo path does ("Pharos Integrity"),
so it needs no quoting — which also keeps the `cmd /k` argument free of the nested quotes cmd
parses inconsistently. PATH is still prepended, but only for interactive convenience in the
spawned window; the launch no longer depends on it.
**Verified:** `/health` → **HTTP 200 in 5s** (`embedding_model: ok`, `disk: ok`; `database`
errored only because the audit sandbox has no network to Supabase). All 4 launcher modes
dry-run correctly; port-warning helper fires on a listening port and stays silent on a free one.

**Verified after all of the above:** offline suite **161/161 pass**; `npx tsc -b --force`
**0 errors**; `vite build` **succeeds**; FastAPI app imports with **36 routes** (ingest + jobs
present) after the `src/pipeline` deletion.

**Still open from this batch:** apply `2026-08-09_enable_rls.sql` (needs live DB + service-role
key); `_DEV_ORIGINS` (localhost:8080/5173/3000) remains unconditionally in the CORS allowlist
including production; `.env` at `9338e89` still carries the anon key in git history (publishable,
but rotate when convenient); bundle is a single 2.3 MB chunk (no code splitting).

---

## Batch 2026-07-22 — live-run verification: perf, retrieval surfacing, methane mislabel

### ✅ #21a 🔴 (perf) — `/reports/{doc}/integrity-report` took 100–235s
- **What ran:** booted uvicorn, timed the endpoint live. shell_2023 **235s**, infosys_2025 **106s** — a multi-minute spinner on the Integrity Audit page.
- **Root cause:** it sourced contradictions from `get_contradictions()`, which fires one Supabase vector-search RPC **per claim** (379 round-trips on shell_2023, many "Server disconnected") + an NLI model pass. Every other endpoint (review-queue / greenwashing-flags / audit) uses the in-memory `_numeric_contradictions()` scan — the same source that now populates the persisted `contradictions` table.
- **✅ Fixed (`59d8ff8`):** integrity-report uses `_numeric_contradictions()`. **235→2.6s, 106→1.7s, microsoft 1.3s**, identical scores/flags/satellite, contradiction counts match the persisted table. Semantic/NLI retrieval stays on `GET /{doc}/contradictions`.

### ✅ #21b 🟠 — `retrieval.py` swallowed RPC failures into a false "0 conflicts"
- **What ran:** the live run logged `Error executing vector search RPC: Server disconnected` — the `except Exception: return []` (existing_issues #1's residual) made a dead RPC indistinguishable from "no contradictions found."
- **✅ Fixed:** `find_candidate_pairs` now raises `RetrievalError` on persistent failure (one reconnect+retry for transient drops), and `GET /{doc}/contradictions` reports `retrieval_available: false` + `retrieval_error` instead of a misleading 0. Also fails fast (no 379 failing round-trips). +1 test. The persisted table + integrity score are unaffected (they don't use this RPC).

### ✅ #21c 🟠 (extraction) — methane figures mislabeled as `emissions.total.co2e`
- **What ran:** probed `emissions.total.co2e` on shell_2023: found Methane (CH4) rows (p80, 1–2.3 Mt) and net-zero narrative zeros tagged as total emissions — the total-emissions key was polluted, and a Scope1+2-vs-total sanity check would fire on *our* mislabels, not greenwashing.
- **Root cause:** the gate's methane backstop fired only on `asp == "uncategorized"`, so a CH4 row the LLM labeled emissions-generic (→ normalized to `emissions.total`) was never rescued — even though the round-2 comment says methane should be split *from* total.
- **✅ Fixed:** methane backstop now fires on `emissions.*` too (guarded — the scope-from-row-text rule runs first, so real Scope-1/2/3 rows are untouched). +2 tests. Regated+re-ingested all 6 reports: shell_2023 **11** methane claims recovered from total (was 0), shell_2022 **3**; 0 methane rows remain mislabeled. Gold gate held (Tata 96.1 / Shell 89.7).
- **Deferred (documented):** the **Scope1+2-vs-total symbolic score check** (roadmap Phase 3) stays OUT of the integrity score — even after the methane fix, `emissions.total` still holds table segment-breakdown rows ("Total Scope 1 and Scope 2" per business line: 0.1/0.9/5.7/22.9 Mt), so an arithmetic check would penalize the score for extraction granularity, not disclosure quality. Root fix = split emissions.total by segment (a future ontology round), then the check becomes trustworthy.

### ✅ #21d 🟠 — geocoder matched a place name to a POI on the wrong continent
- **What ran:** live end-to-end satellite check on a current claim — `verify_claim` on `biodiversity.conservation @ "Lake Xochimilco"` (the Mexico City wetland/UNESCO site). It geocoded to **"Xochimilco Mexican Restaurant, West Montrose Avenue, Ravenswood" — a restaurant in Chicago** (class=amenity), then computed NDVI (z=7.21, 2500 px) around the wrong location. The engine works; the *geographic* input was garbage.
- **Root cause:** `geocode._query` used Nominatim `limit=1` and took `hits[0]` with **no class filter**, so an exact-name POI outranked the real geographic feature.
- **✅ Fixed:** fetch `limit=10`, keep only real ground features (`_acceptable`: place / natural / water / waterway / boundary / landuse + park-like leisure), pick the highest-importance one; POI-only matches now return None (honest miss). Cache bumped v2→v3 to drop old unfiltered hits. **Verified live:** "Lake Xochimilco" → honest miss (was a restaurant); **"Jarama riverbed, Madrid" → the real Río Jarama (waterway/river)**; "Kenyan fishing village" → miss. +4 offline tests (`test_geocode_filter.py`). Correctness-over-recall is the right trade for a verification tool (a wrong geocode = a false verdict).

### ✅ #21f 🔴 (CI) — satellite test broke the offline suite (rasterio not in CI)
- **What ran:** CI run #32 — `Backend — pytest (offline suites)` failed with **exit code 2** (collection error, not a test failure). `test_satellite_check_key.py` imports `satellite_evidence`, which imported `sentinel_ndvi` at module top → `rasterio` / `pystac_client` / `planetary_computer`, **none of which are in requirements.txt** (they're needed only to fetch imagery). A single un-importable module aborts the whole pytest collection.
- **✅ Fixed:** made the `sentinel_ndvi` import LAZY (inside `verify_claim`, the only user) so `check_key` / expectations / stored-evidence reading load without the geo stack. Verified: `import satellite_evidence` no longer pulls `sentinel_ndvi` (sys.modules check); `api_reasoning` clean too. Full `pytest -m "not live"` = 161 green locally. Root of the class: heavy optional deps must never sit at module top of a widely-imported module.

### ✅ #21e 🟠 — stored satellite evidence was orphaned by every re-ingest
- **What ran:** checked `satellite_evidence.claim_id` against the (round-3 re-ingested) `claims` table: **0/50 still match.** `ingest_claims_to_db` assigns a fresh `uuid4()` claim_id on every ingest, but `satellite_evidence` keyed on it — so each re-ingest broke the per-claim link. The report panel still showed counts (joined by `report_id`) but they were **stale 2026-07-11 numbers on claims that no longer exist**, plus 141 rows with `report_id = NULL`.
- **✅ Fixed (root cause):** added a stable `check_key = sha256(report_id|normalized_aspect|location_text|time_bucket)[:16]` — invariant for the same semantic claim across re-ingests. The runner writes it; `_satellite_for` re-links stored rows to the CURRENT claim_id via `check_key` and drops rows whose claim is gone, so the panel **self-heals after any future re-ingest**. Migration `2026-07-22_satellite_check_key.sql` applied (pooler/IPv4): column + index added, **141 NULL-report orphans purged** (200→61 rows). Re-ran `run_satellite_checks.py` on the current corpus with the fixed geocoder — North-Holland datacenter reproduced as `not_supported`, Lake Xochimilco now `geocode_failed` (was the Chicago restaurant). +4 tests (`test_satellite_check_key.py`). Mostly-inconclusive verdicts remain by honest-first design.

---

## Batch 2026-07-19 — #20: contradictions table was dead + same-key subgroup explosion

### ✅ #20a 🔴 — UI `contradictions` table was a 3-month-old orphaned artifact
- **What ran:** probed the live `contradictions` table the frontend reasoning views (ContradictionExplorer / ClaimGraph / RiskScorePanel via `useClaims`) read directly from Supabase: **20 rows, all created 2026-04-08** by the offline integration-test runner — nothing has written the table since. Rows were pre-#18 noise (`Value shifted 22372.0->9134.0 between null and unknown_time`) referencing **long-deleted claim ids**.
- **Root cause:** no production path ever wrote `contradictions` — the backend computes conflicts on demand per request; the table (never in `schema.sql`) silently rotted while the UI kept rendering it.
- **✅ Fixed:** contradictions are now a **maintained per-document artifact**. `reasoning/persist_contradictions.py` runs the deterministic numeric scan (no NLI model load) and replaces a doc's rows (delete-then-insert by `doc_id` — same idempotency pattern as claims), wired into `ingest_claims_to_db` (guarded; can never fail an ingest). Migration `2026-07-19_contradictions_doc_id.sql` applied live (adds `doc_id` + index + anon grants; table folded into `schema.sql` as #11); 20 legacy rows purged; tata/shell_2022/infosys_2023 backfilled.
- **NOTE (infra):** the direct `db.*` host was unreachable (IPv6-only, router drops IPv6) — migration applied via the IPv4 **session pooler** `aws-1-ap-southeast-1.pooler.supabase.com:5432`, user `postgres.<project-ref>`, same password as DATABASE_URL.

### ✅ #20b 🟠 — same-metric_key subgroup rows exploded into C(n,2) false "Value mismatch" flags
- **Test:** the first backfill persisted **325 contradictions for tata_power_2024 alone** (307 Metric/High). Breakdown: `waste.total.mass` 209 pairs ("Re-used waste" vs "C&D waste" vs "Landfilling waste"…), `social.diversity.gender.headcount` (male/female/permanent/contract rows), `emissions.air_pollutants.mass` (PM vs SOx vs NOx). All same-year "mismatches" between **different subgroup rows sharing one catch-all metric_key** — categories, not double-reporting. This same inflated count feeds the CONTRADICTION flag in `build_report` (score side), so it wasn't just a UI artifact.
- **Root cause:** the #19 metric_key-conflation residual, now at score-relevant scale on the round-2 corpus. Per #19's own verdict, the contradiction layer cannot deterministically distinguish conflated quantities.
- **✅ Fixed (precision-first gate):** `_numeric_conflict` now trusts a same-year Metric/Scope mismatch only when the two claims are **literally the same statement with different numbers** (source sentences equal after stripping digits/punctuation — `_same_reported_quantity`). Different statements under one key = subgroup/conflation → suppressed. Sentence-less rows keep the old behavior (conservative fallback). Hard direction conflicts unaffected. **tata 325→2, shell_2022 85→7, infosys_2023 29→1 — survivors verified real** (e.g. `Hard/Critical: Direction conflict for emissions.total.percent in 2021: decrease vs increase`). +3 tests (16/16 nli, 37 report-suite green).
- **Trade-off (documented, deliberate):** recall for cross-context double-reports (table vs narrative restating the same figure differently) is sacrificed for precision — acceptable because every observed cross-context pair in this corpus was conflation, not signal. **Root fix stays ontology round 3** (split waste by disposal route, air_pollutants per pollutant, gender by cohort) which re-enables per-key cross-context comparison.

---

## Batch 2026-06-26 — #19 deterministic layer RESOLVED + test-leak fix

### ✅ #19 metric_key conflation — deterministic layer fixed (split dimensions) + backfilled
- **What ran:** probed live units under the conflated keys. `social.health_safety.ltifr.count` (n=51) actually held `employees`(10)/`people`(4)/`fatalities`(1)/`events`+`incidents`(7)/`hours`(rate denominators); `emissions.scope1.co2e` (n=106) mixed ~96 absolutes with ~10 intensities (`gco2e/mj`, `co2e/kwh`, `co2e per inr`).
- **Fix (deterministic, no LLM):** in [ontology.py](backend/src/extractors/ontology.py) `_DIM_RULES` — added an `intensity` dimension (physical denominators only, matched before co2e/energy/mass; a time denominator like `tCO2e/year` stays absolute) and split the `count` catch-all into `headcount`/`fatalities`/`injuries`/`incidents` (+ generic `count`). `_PLAUSIBLE` updated per family; `is_value_plausible` integer-gate extended to the new count-family suffixes; dropped the dangerous bare `men`/`women` keyword (substring-matched `assessments`, `management`, …).
- **Backfill:** recomputed `metric_key` + `claim_signature` over all 2385 live claims (via `DATABASE_URL`) — **97 rows updated** (41 headcount, 31 intensity, 11 incidents, 4 rate, 1 fatalities; 9 mislabeled diversity-as-biodiversity rows collapsed to `.unspecified`, acceptable). Now `emissions.scope1.intensity` benchmarks separately from `.co2e`; `ltifr` splits into `.rate`/`.headcount`/`.incidents`/`.fatalities`. Test `test_metric_key_dimension_routing` updated to lock the new routing; 72 tests green.
- **Scores unchanged** (Tata B84 / MS D44 / Shell F26 / Infosys D42) and **contradiction counts unchanged** — expected: the contradiction `_comparable` gate already required identical canonical units, so cross-quantity pairs were never compared. The win here is **benchmark/grouping precision**, not contradiction reduction.
- **Residual (accepted ceiling):** the LLM *aspect/scope* mislabels (diversity claims tagged `biodiversity.conservation`; 58Mt vs 305Mt both tagged `scope1` same year) are NOT deterministically fixable — they need 70B re-extraction with tighter aspect derivation. Tracked as the standing extraction-quality remainder, not an engine defect.

### ✅ test_db_constraints leaked `test_corp` rows into the live corpus
- **Test:** `scripts/test_db_constraints.py` inserts two sentinel claims (`company_id='test_corp'`) into the **live** `claims` table on every run, with the cleanup commented out — so a bogus 2-claim "test_corp" company (grade A/100) appeared in the portfolio after each test run.
- **Fixed:** enabled the delete-by-`company_id` cleanup at the end of the test; purged the lingering rows (corpus back to 2385 claims, 4 companies).

---

## Batch 2026-06-25d — score saturation RESOLVED: count-weighted scoring

### ✅ Score saturation fixed — the integrity metric now discriminates (closes the #18 ⚠️ result)
- **What ran:** replaced the flat per-flag-type penalty in [integrity_report.py](backend/src/reasoning/integrity_report.py) with **count-weighting**: `penalty = sev_weight × prevalence`, `prevalence = count / total_claims` (weights `{Critical:50, High:30, Medium:16, Low:6}`; structural count=0 flags fixed at 0.5). `_REPORT_VERSION` → `"2.0"`; `penalty_breakdown` carries `prevalence`.
- **Root cause it fixes:** the flat model deducted a fixed penalty per *distinct flag type* regardless of how many claims triggered it, so a flag hitting **4%** of claims cost the same −8 as one hitting **90%**. Every real ESG report trips ~all flag types → everyone saturated to **F** (the #18 ⚠️ finding). Prevalence-weighting makes pervasiveness the driver.
- **Verified on live data (calibration):** **OLD all F** — Shell'22 13, Shell'23 6, Tata'24 28 (range 22, one grade). **NEW** — Shell'22 **34.5 (F)**, Shell'23 **25.7 (F)**, Tata'24 **84.2 (B)** (range 58, grades {B, F}). The clean metric-dense report (Tata) now separates from the greenwash-heavy ones (Shell). 71 tests green incl. new `test_score_is_count_weighted_by_prevalence`.
- **#19 now has direct score impact:** Critical×prevalence makes `CONTRADICTION` the biggest single lever, so the metric_key conflation in #19 (inflating Metric contradictions) now feeds the headline score — fixing it upstream sharpens the score further. Still the right next move; not regressed by this change.

---

## Batch 2026-06-25c — live-data run: contradiction over-fire + score saturation

**What ran:** ran the full reasoning pipeline against the **live Supabase corpus** (1435 claims; docs `tata_power_2024`/`shell_2022`/`shell_2023`) and `verify_search_claims_index.sql` against the live DB. Two new defects + one schema fix.

### 18 🟠 — "Internally inconsistent figures" is massively over-counted by normal time series
- **Test:** `_numeric_contradictions(shell_2022 claims)` → **956 conflicts** → fed straight into the `CONTRADICTION` greenwashing flag as `count=956`, severity **Critical** (−25 pts).
- **Breakdown:** `{Temporal: 569, Metric: 350, Scope: 32, Hard: 5}`.
- **Root cause:** the **Temporal rule** ([nli_engine.py:160-169](backend/src/reasoning/nli_engine.py)) returns a contradiction for *any* two same-`metric_key`/same-scope claims whose values differ >5% across **different real years**. But a multi-year disclosure of one KPI is a **time series, not an inconsistency** — e.g. `social.health_safety.ltifr.rate shifted 0.4->1.7 between 2022 and 2021` is just the year-over-year trend. ~60% of the count (the 569 Temporal pairs) are this false-positive class. The genuinely-contradictory **same-year** mismatches are already the separate `Metric` type (`Value mismatch: 0.4 vs 0.7 ... in 2022/global`) and are kept.
- **Impact:** inflates the contradiction count, which feeds the `CONTRADICTION` greenwashing flag. This is issue #7's noise re-emerging at the *report* level: the per-pair engine was de-noised, but treating a cross-year series as pairwise contradictions was not.
- **✅ Fixed (this batch):** dropped the cross-year value-shift branch from [`_numeric_conflict`](backend/src/reasoning/nli_engine.py) — a value differing across *different real years* is a time series, not a contradiction. Same-year `Metric` mismatches, cross-scope `Scope`, and `Hard` direction conflicts are kept. The `Temporal` type is gone; the now-dead extreme-YoY guard (`_is_absolute`/`_MAX_YOY_RATIO`) was removed. `test_nli_engine.py` updated (the intentional Temporal cases now assert `None`); 69 tests green. **Verified on live data:** shell_2022 **956 → 387** conflicts, shell_2023 **→ 493**, tata_power **→ 25** — the 569 cross-year false positives are gone.
- **⚠️ Honest result — the fix corrects the count but does NOT move the grade.** All three reports stay at **F** (28/13/6 unchanged), because score saturation has *other* drivers: (a) the flat per-flag penalty makes the `CONTRADICTION` flag Critical whenever *any* same-year `Metric`/`Hard` conflict exists (severity unchanged), and (b) the `VAGUE` + `TARGETS_NO_BASELINE` flags alone already sum past the F threshold. **Levers that would actually move grades: count-weighted penalties (deferred) + fixing #19 metric_key conflation** (a chunk of the remaining 350 `Metric` "mismatches" are unrelated quantities sharing a key, e.g. fatalities vs employees under `ltifr.count` — upstream extraction, not engine logic).

### 19 🟠 — metric_key granularity conflates unrelated quantities (extends #14/#15/#16)
- **Test:** within `shell_2022`, one `metric_key` groups physically different things:
  - `social.health_safety.ltifr.count` (21 claims): units = `{employees, fatalities, hours, incidents, events, assessments, people, …}` — comparing a fatality count to an employee headcount.
  - `emissions.scope1.co2e` (49 claims): units mix an **intensity** (`gCO2e/MJ`) with absolutes (`Mt CO2e`, `million tonnes CO2e`, `tCO2e`).
- **Root cause:** upstream — the 8B extractor + the `.count`/`.co2e` dimension being a catch-all (the #14/#15/#16 family). The canonicalizer correctly keeps incomparable units apart at compare time, so these mostly don't *numerically* conflict, but they share a key and pollute grouping/benchmarking.
- **Impact:** feeds spurious pairs into #18 and muddies per-metric benchmarks. Tracked as the existing operational remainder (needs 70B extraction + tighter metric_key derivation), not a new engine defect.
- **✅ Verified (2026-06-25d) — the contradiction layer is NOT the place to fix this; it's pure extraction quality.** Checked shell_2022's 350 `Metric` contradictions on live data: only 63 pair claims with differing raw units, and `_comparable` already blocks the clean conflation (e.g. `fatalities` vs `employees` canonicalize to distinct non-empty units → guard rejects). The 63 are **same-canonical-unit genuine magnitude differences** — canonicalization is correct (`51 'million tonnes co2e'` → `51,000,000 tCO2e`; `58000000 'tco2e'` → `58,000,000 tCO2e`), so they read as `58Mt vs 51Mt vs 305Mt vs 1.1Mt` of "Scope 1" in the **same year/global**. That spread is the **8B extractor mislabeling different entities/scopes/contexts all as `emissions.scope1.co2e`** — an aspect/scope-assignment error upstream, with **no deterministic guard** that distinguishes them (they're physically the same dimension). Realizing any score benefit requires re-extraction (70B / tighter aspect+scope derivation) **and a re-ingest/backfill** of the stored `metric_key`/`location_scope` — not a pure-logic patch. Conclusion stands: this is the extraction ceiling, deferred pending model/source work.
- **✅ Deterministic layer RESOLVED (2026-06-26) — see top batch.** The conflation's tractable half (coarse `count` catch-all + intensity colliding with absolute `co2e`) is fixed in the ontology + backfilled over live claims. Only the LLM aspect/scope-mislabel residual remains (needs 70B re-extraction).

### ✅ Schema fix — `claims_default` partition had no HNSW index
- **Test:** `verify_search_claims_index.sql` on the live DB → only 4 of 5 claims partitions had an embedding index; `claims_default` (the catch-all holding `emissions.scope1`, currently the **largest** partition at 746 rows) had none.
- **Fixed + applied to live DB:** `CREATE INDEX … claims_default_embedding_idx … hnsw (embedding vector_cosine_ops)` — folded into [schema.sql](backend/database/schema.sql), shipped as migration `2026-06-25_claims_default_hnsw.sql`, verified (5 HNSW indexes now). Note: at current scale all 5 are **dormant** — a literal-vector seq scan (8.9 ms) beats a forced HNSW scan (194 ms), so the planner correctly skips them; the index is insurance that activates as partitions grow.

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
