# ESGenuine — Deep Engineering Audit & Step-Forward Plan

**Author:** Principal-architect-level review (read-only audit; no code changed)
**Date:** 2026-06-23
**Scope:** Full codebase — `frontend/`, `backend/`, `supabase/`, data, infra assumptions.
**Mandate:** Identify the *biggest* changes that would turn this from a student/demo project into a fully-backed, production-grade, research-grade, scalable system.

> **One-line verdict:** The system is a *well-structured demo with a real extraction core*, but it is **not a system yet** — there is no production ingestion path, the "orchestration layer" is mock data, the evaluation has no ground truth, the reasoning layer is partially broken, and there is zero operational infrastructure (no tests, CI, containers, migrations, observability, or auth). The good news: the hard parts (parsing, ontology, local embeddings/NLI) exist, so the path to "serious system" is mostly **wiring, hardening, and evaluation**, not greenfield research.

---

## ⚡ UPDATE 2026-06-25 — Production wiring + next-gen capabilities shipped

Much of Tier 1/2 below is now **done** (see [existing_issues.md](existing_issues.md) for the defect-level log). Summary of what changed:

**Production spine fixed:** async ingest path (`POST /v1/reports/ingest` → parse→extract→embed→Supabase); `match_claims` RPC applied + extended; contradiction engine rebuilt (metric_key+canonical-unit gating, zero-baseline & magnitude-outlier guards); `doc_id`/company data consistency; mojibake, table-noise, location-junk cleaned. 16/17 audited defects closed.

**Live data now multi-company:** Tata Power (181), Shell 2022 (527), Shell 2023 (727) — canonical metric_keys, real peers + a 2-year trajectory.

**Next-gen analysis layer (new modules under `backend/src/reasoning/`):**
| Capability | Module | Endpoint(s) |
|---|---|---|
| Greenwashing taxonomy (typed flags + EU/ESRS/SEC/BRSR mapping) | `greenwash_taxonomy.py` | `GET /reports/{id}/greenwashing-flags` |
| ESG Integrity Report (score/grade + flags + recs) | `integrity_report.py` | `GET /reports/{id}/integrity-report` |
| Peer benchmarking + target trajectory (canonical-unit, polarity-aware) | `benchmark.py` | `GET /benchmark/metric/{key}`, `/benchmark/company/{id}`, `/benchmark/trajectory/{id}/{key}` |
| External fact-checking (corpus + cross-report, cited verdicts) | `fact_check.py` + `data/evidence_corpus.json` | `GET /reports/{id}/fact-check` |
| Agentic auditor + conversational audit (cited RAG Q&A + exec summary) | `agent.py` + `search_claims` RPC | `POST /audit/ask`, `GET /audit/{id}/summary` |

**Frontend wired:** new `lib/api.ts` client + `Integrity Audit` page (`/integrity-audit`) showing integrity score/grade, greenwashing flags, external fact-check verdicts, peer benchmark scorecard, and a conversational audit box. Includes a **verification-method router** (`verificationMethod`) — only optically-observable aspects (reforestation/solar/land) are flagged satellite-verifiable; emissions/social/governance/financial claims route to data/document cross-check, never imagery.

**Still open / next:** 70B re-ingestion for cleaner extraction values; persisting canonical/observability fields to DB; a real external evidence corpus (replace illustrative `evidence_corpus.json`); auth/CI/containers/observability (Tier 3 below unchanged). #17 scorer calibration is **done** (re-scored live data).

---

## 0. How to read this report

Every recommendation carries reasoning, expected impact, tradeoffs, difficulty, and a realistic time estimate (for *one competent research/engineering student* working focused days — not a team). Sections 1–8 diagnose; Section 9 prioritizes (Tier 1/2/3) with the mandatory estimate tables; Section 10 is the roadmap; Section 11 is self-critique.

Time ranges used: `2–4h`, `1–2d`, `3–5d`, `1–2w`, `2–4w`, `1–2mo`.

---

## 1. System as actually built (ground truth)

This matters because **the diagrams in the code do not match the runtime**. The real data flow:

```
                 ┌─────────────── Supabase (Postgres + pgvector) ───────────────┐
                 │  tables: claims (partitioned), contradictions, reports        │
                 └───────▲──────────────────────────────────────────▲───────────┘
                         │ reads (anon key, direct)                   │ writes
   frontend/ (Vite/React)│                                            │ ONLY from
   - useClaims.ts ───────┘                          backend/tests/run_integration_test.py
   - DocumentViewer.tsx ──HTTP──► FastAPI (backend/src/api/server.py)  (manual script)
                                   - /v1/upload      → DocumentParsingPipeline (8 steps, SYNC)
                                   - /v1/claims/extract → ExtractionPipeline (Groq LLM, SYNC)
                                   - /reports/{id}/contradictions → NLI on the fly
   frontend SubmitReport ──► Supabase Edge Fn `analyze-claims` ──► Lovable AI gateway
```

**Critical structural facts (evidence):**

1. **There is no production path that writes claims to the database.** Ingestion + embedding + contradiction computation lives only in [`backend/tests/run_integration_test.py`](backend/tests/run_integration_test.py) and the standalone [`backend/src/extractors/ingest_claims.py`](backend/src/extractors/ingest_claims.py). The API (`server.py`) parses and extracts to **local JSON files** and **in-memory dicts** (`document_registry`, `claims_registry`, [server.py:44-54](backend/src/api/server.py)). The frontend reads the DB, but nothing in the app *fills* it. The DB was populated by hand.

2. **The LangGraph "pipeline DAG" is entirely mock data.** [`backend/src/pipeline/workflow_dag.py`](backend/src/pipeline/workflow_dag.py) hardcodes "Pune facility / 10,000 trees / NDVI z-score" outputs in every node (`parse_document`, `extract_claims`, `fetch_satellite`, …). It imports `langgraph` but is a disconnected dry-run demo. The "orchestration layer" therefore **does not exist** in any real sense.

3. **The product concept in the code (satellite/NDVI/SAR/vision) is not implemented** anywhere in the backend. The real backend is **text-only** ESG claim extraction + NLI. (The frontend's satellite UI was already de-fictioned in a prior pass.)

4. **In-memory server state** means a restart loses the document registry, and you cannot run more than one worker without divergent state.

5. **Embeddings and NLI are local** (`sentence-transformers` BAAI/bge-base-en-v1.5, `transformers` DistilBERT-MNLI). The *only* hard external APIs in the core are **Groq (LLM extraction)** and **Supabase (DB)**. The frontend separately depends on **Lovable AI** via the edge function.

---

## 2. Architecture assessment

### 2.1 Scale — **Not ready.** Blockers:

- **Synchronous long-running requests.** `/v1/upload` runs the full 8-step parse in the request thread; extraction sleeps `time.sleep(2.1)` *per chunk* ([claim_extractor.py:156](backend/src/extractors/claim_extractor.py)). The integration test reports **75.8 minutes to process 2 reports** ([PHAROS_INTEGRITY_TEST_REPORT.md](backend/test_results/PHAROS_INTEGRITY_TEST_REPORT.md)). Any real HTTP client times out; any concurrency multiplies CPU/RAM (spaCy + torch models loaded per process).
- **No job queue / async workers.** There is no Celery/RQ/Arq/Cloud Tasks. Uploads cannot be backgrounded, retried, or rate-limited centrally.
- **In-memory registries + local-disk artifacts** (`backend/parsed/*.json`) tie the system to a single machine and a single process.
- **Model loading on import** (DistilBERT loads at `server.py` import time via `api_reasoning.py`). Cold start is heavy; every worker re-loads. No model server / warm pool.
- **Partitioning is a no-op** (see §4.3) so the claimed "5–10× speedup" is fictional; at scale the DB will behave like a single unindexed-by-design table for the default partition.

### 2.2 Maintainability — **Mixed.**

- **Good:** clear module separation (`parsers/`, `extractors/`, `reasoning/`, `api/`), Pydantic models, a clean `LLMClient` provider abstraction ([claim_extractor.py:102-177](backend/src/extractors/claim_extractor.py)), shared frontend types after recent cleanup.
- **Bad:** dead/duplicated code (`workflow_dag.py` mock, `table_extractor.py` legacy vs `table_parser.py`, two Supabase client files in frontend). Configuration via scattered `load_dotenv()` calls and hardcoded constants (embedding model declared in 2+ files). No central `config`/settings object. No typed settings (`pydantic-settings`).

### 2.3 Extensibility — **Will not scale with complexity.**

- New stages must be threaded manually through `server.py` + `ExtractionPipeline.run()`; there is no real DAG/state machine driving production (the LangGraph one is fake). Adding "human review", "re-extraction", or "multi-model verification" today means bespoke glue.
- No event model, no message bus, no idempotency keys, no run/version IDs. Every reprocessing is a fresh, untracked run.

---

## 3. Hidden weaknesses & production blockers (brutally honest)

| # | Weakness | Evidence | Why it's dangerous |
|---|----------|----------|--------------------|
| 3.1 | **No DB ingest in the app** | `server.py` writes JSON only; ingest in test script | The product cannot actually onboard a new report end-to-end without manual scripts |
| 3.2 | **Mock orchestration shipped as code** | `workflow_dag.py` | Misleads future devs; LangGraph is "adopted" but unused |
| 3.3 | **NLI input format is wrong** | `f"{text_a} </s></body> {text_b}"` ([nli_engine.py:23](backend/src/reasoning/nli_engine.py)) | DistilBERT-MNLI is run as single-string `text-classification`, not premise/hypothesis pair → contradiction labels are unreliable/meaningless. The whole "Textual" contradiction path is suspect |
| 3.4 | **Table-dump "sentences"** | DB rows like `"1.\nPermanent (D)\n 22,372 …"` | LLM extracts numbers from garbled table text; provenance is noise; downstream metrics are fragile |
| 3.5 | **Partitioning mismatch** | schema partitions `environment.emissions` vs emitted `emissions.scope1` | All rows fall to `claims_default`; the design optimization is inert; re-running `schema.sql` `DROP TABLE`s live data |
| 3.6 | **Numeric contradiction heuristic is naive** | 5% abs-diff, same time_bucket/scope ([nli_engine.py:45](backend/src/reasoning/nli_engine.py)) | Unit-blind (compares values without confirming same unit/metric_key); `time_bucket="unknown_time"` collides everything; false contradictions like the observed `22372 → 9134` |
| 3.7 | **No ground-truth evaluation** | `PHAROS_INTEGRITY_TEST_REPORT.md` counts only | "PASS" = counts within ranges. No precision/recall/F1 for extraction, ontology mapping, or contradictions → **no research credibility** |
| 3.8 | **Secrets in `.env`, permissive DB** | live `GROQ_API_KEY`, `DATABASE_URL` password; anon key used to **insert** in `ingest_claims.py` | Anyone with the anon key can likely write `claims` (RLS appears open). Secret sprawl |
| 3.9 | **Unpinned deps** | `requirements.txt` all `>=`, 0 `==` | Non-reproducible builds; a torch/transformers minor bump can silently change model behavior or break |
| 3.10 | **No tests / CI / containers / migrations** | no `pytest.ini`, `.github/`, `Dockerfile`, `supabase/migrations/` | Every change is unverified; environment drift; schema drift (already happened F:→E: + partition) |
| 3.11 | **Silent failure swallowing** | `except Exception: pass` in incremental backup ([claim_extractor.py:375](backend/src/extractors/claim_extractor.py)); broad validation `except` | Errors vanish; debugging is guesswork |
| 3.12 | **Rate-limit handling via string parsing** | regex on error text ([claim_extractor.py:411](backend/src/extractors/claim_extractor.py)) | Brittle across provider/SDK changes; "used 49" magic string |
| 3.13 | **No observability** | only `print()` | No metrics, traces, structured logs, or run lineage; impossible to operate or debug at scale |
| 3.14 | **No auth/tenancy** | frontend uses anon key directly | Cannot multi-tenant; no per-user data isolation; data is effectively public |

---

## 4. Major step-forward improvements (architectural jumps)

These are the high-leverage changes, grouped. Each is justified and sized.

### 4.1 Introduce a real **job/run model + async workers** *(the single biggest unlock)*
**What:** Replace synchronous `/v1/upload` with an enqueue-and-poll pattern. Introduce a `runs` table (run_id, doc_id, status, stage, timings, errors) and a worker process (Arq/RQ/Celery, or a Supabase/pg-backed queue). The API enqueues; workers parse → extract → embed → ingest → detect contradictions; the frontend polls run status.
**Why:** Eliminates timeouts, enables concurrency, retries, idempotency, progress UI, and — crucially — **creates the missing production ingest path** (§3.1). Everything else (observability, recovery, scaling) hangs off this.
**Impact:** Transformative. Tradeoff: operational complexity (a worker to run). Risk: medium (state machine correctness).
**Effort:** `1–2w`.

### 4.2 Make the **pipeline a real DAG/state machine** (delete or rebuild the mock)
**What:** Either (a) delete `workflow_dag.py` and codify the real flow as an explicit pipeline object with typed stage I/O, persisted intermediate state, and resumability; or (b) repurpose LangGraph properly to wrap the *real* `DocumentParsingPipeline` + `ExtractionPipeline` + reasoning, with the `runs` table as backing store.
**Why:** Adds resumability ("re-run from extraction"), per-stage metrics, and clean extension points. Removes the most misleading code in the repo.
**Impact:** High (maintainability + extensibility). Risk: low–medium.
**Effort:** `3–5d` (delete+wrap) / `1–2w` (full LangGraph integration with persistence).

### 4.3 **Fix the data model**: drop fake partitioning, add real indexes, version everything
**What:** Replace LIST partitioning (broken) with either correct partitions that match `SignatureGenerator` output **or** a single table with proper B-tree indexes on `(metric_family, claim_signature, company_id, report_year)` + HNSW on `embedding`. Add `run_id`, `model_version`, `prompt_version`, `extractor_version`, `created_at` columns. Manage via versioned **Supabase migrations** (not `setup_db.py` with `DROP TABLE`).
**Why:** Correct performance, safe schema evolution (no data loss), and reproducibility lineage on every row.
**Impact:** High. Risk: medium (migrating live data — must be additive, never `DROP`).
**Effort:** `3–5d`.

### 4.4 **Rebuild the reasoning/verification layer** (it's the research heart and it's weak)
**What:** (1) Fix NLI to true pair classification (use a proper NLI/zero-shot model with premise+hypothesis API, e.g. `cross-encoder/nli-deberta-v3` via sentence-transformers `CrossEncoder`, or HF `pipeline("text-classification")` with `text`/`text_pair`). (2) Make numeric contradiction **unit-aware** (compare only same `metric_key` + normalized unit; require overlapping/known time + scope). (3) Add a **verification/confidence layer**: an LLM-judge or NLI ensemble that must agree before a contradiction is surfaced (reduces false positives like the `22372→9134` case). (4) Add **self-consistency** (sample extraction twice, keep agreeing fields).
**Why:** This is what separates a credible "greenwashing detector" from a regex demo. Current contradictions are not trustworthy.
**Impact:** Very high (research credibility + product trust). Risk: medium.
**Effort:** `1–2w`.

### 4.5 **Stand up a real evaluation harness with ground truth** *(non-negotiable for "research-grade")*
**What:** Build a small **gold-standard labeled set** (e.g., 100–300 hand-annotated claims across 3–5 reports: correct aspect, metric value/unit, time, location, plus a labeled contradiction set). Compute **precision/recall/F1** for extraction fields, ontology mapping accuracy, and contradiction detection (P/R, confusion matrix). Track per-version in a results store. Add regression gating (fail CI if F1 drops).
**Why:** Today "PASS" is a count check. Without labels, no claim about accuracy is defensible; you cannot tune prompts/models safely; you cannot publish.
**Impact:** Very high. Tradeoff: annotation labor. Risk: low (just effort).
**Effort:** `1–2w` (incl. annotation of a seed set).

### 4.6 **Context & extraction-quality redesign** (garbage-in problem)
**What:** Improve Step 1–7 parsing so table dumps don't become "sentences": route detected table regions to the structured table parser exclusively; pass clean, layout-aware context to the LLM; add a pre-extraction quality filter (drop sentences that are >X% numeric with no verb — logic already exists in `ingest_claims.validate_claim`, move it *upstream*). Consider a layout model (e.g., `unstructured`, `docling`, or LayoutLMv3) for robust table/figure separation.
**Why:** Extraction quality is capped by input quality; current sources are noisy ([§3.4]).
**Impact:** High (directly lifts F1). Risk: medium (parser changes).
**Effort:** `1–2w` (heuristics) / `3–5d` extra for a layout model.

### 4.7 **Observability + structured logging + run lineage**
**What:** Replace `print()` with structured logging (`structlog`/`loguru` + JSON), add OpenTelemetry traces around stages, emit metrics (claims/sec, tokens, cost, error rates, model latency) to Prometheus/Grafana or a hosted equivalent. Persist per-run logs to the `runs` table.
**Why:** You cannot operate, debug, or cost-control what you can't see.
**Impact:** High (ops + cost). Risk: low.
**Effort:** `3–5d`.

### 4.8 **Containerization + CI/CD + reproducibility**
**What:** `Dockerfile` for backend (pin Python, preload models), `docker-compose` (backend + worker + local Postgres+pgvector + frontend), pin `requirements.txt` (`pip-tools`/`uv` lockfile), add `pyproject.toml`, GitHub Actions (lint, typecheck, pytest, frontend build). Seed RNG and pin model revisions.
**Why:** Reproducible builds, environment parity, automated verification. Prevents the F:→E: / partition-drift class of bugs.
**Impact:** High (reliability + reproducibility). Risk: low.
**Effort:** `3–5d`.

### 4.9 **Security & multi-tenancy**
**What:** Enable Supabase **RLS** with per-row ownership; move all writes to a **service-role** key on the backend (never anon writes); add app auth (Supabase Auth) so the frontend reads scoped data; rotate the committed `GROQ_API_KEY`; move `DATABASE_URL`/secrets to a secret manager; restrict CORS.
**Why:** Today data is effectively public and writable; no tenant isolation.
**Impact:** High (table-stakes for production). Risk: medium (RLS can lock you out if misconfigured — test carefully).
**Effort:** `3–5d`.

### 4.10 **Caching + cost control for the LLM layer**
**What:** Content-hash cache for extraction (skip re-LLM on unchanged chunk text); dedup identical chunks before LLM; batch where the provider allows; token/cost budget per run with hard caps; prompt/version caching.
**Why:** The `sleep(2.1)`-per-chunk serial Groq path is the bottleneck and the main cost/risk; caching cuts cost and latency dramatically on re-runs.
**Impact:** High (cost + latency). Risk: low.
**Effort:** `2–4d`.

---

## 5. MCP (Model Context Protocol) opportunities

MCP is most valuable here for (a) giving an *agentic* extraction/verification loop clean tool access, and (b) standardizing how the backend and any dev-time agents talk to the DB, files, and vector store. Honest take: MCP is **not required** for the core batch pipeline, but it is a strong fit for the **verification agent**, **dev/ops tooling**, and **eval**.

| MCP server | Why it matters / problem solved | Expected impact | Adoption difficulty | Risks | Effort | Verdict |
|---|---|---|---|---|---|---|
| **Postgres/Supabase MCP** | Lets an agent (or Claude-in-the-loop) query `claims`/`contradictions` with guardrails; powers ad-hoc analysis, eval queries, and a future "ask your portfolio" feature | High | Low (servers exist) | SQL injection / over-broad grants → use read-only role | `2–4h` to wire, `1–2d` to harden | **Good-to-have** (Must-have if you build an analyst agent) |
| **Vector-DB MCP** (pgvector/Qdrant) | Standardizes semantic retrieval for a RAG/verification agent; decouples retrieval from `retrieval.py` glue | Medium–High | Low–Med | Stale index, dim mismatch (768) | `1–2d` | **Good-to-have** |
| **Filesystem MCP** | Agent access to `backend/parsed/*.json`, ESG PDFs, eval artifacts during dev | Medium | Low | Path traversal; scope to repo | `2–4h` | **Good-to-have (dev)** |
| **Memory MCP** | Persistent memory for a long-running verification/curation agent (decisions, analyst feedback, known-FPs) | Medium | Med | Memory drift/staleness | `1–2d` | **Future** |
| **GitHub MCP** | Automate eval-regression issues, changelog, PRs from agents; tie runs to commits | Medium | Low | Token scope | `2–4h` | **Good-to-have (ops)** |
| **Browser/Fetch MCP** | Fetch primary-source ESG PDFs / corroborate claims against company sites / regulators | High (capability expansion) | Med | Rate limits, legal/ToS, hallucinated sources | `3–5d` | **Future (high upside)** |
| **Observability MCP** (logs/metrics) | Let an agent triage failed runs, summarize errors, propose fixes | Medium | Med | Noise | `1–2d` | **Future** |
| **Evaluation MCP** | Expose the gold-set + scorers as tools so an agent can run/inspect evals and propose prompt changes | High (closes the tuning loop) | Med | Overfitting to eval | `2–4d` (after §4.5) | **Good-to-have** |
| **Knowledge-graph MCP** | Back a claims↔entities↔metrics graph for graph reasoning (see §6) | High (research) | High | Modeling complexity | `1–2w` | **Future** |

**Bottom line:** Start with **Postgres + Filesystem + GitHub MCP** (cheap, immediately useful for dev/ops and an analyst agent). Defer Browser/KG/Memory MCP until the core pipeline and eval exist — MCP on top of an unevaluated pipeline just accelerates shipping wrong answers.

---

## 6. Capability-expansion bets (research upside)

- **Knowledge graph + graph reasoning.** Model `Company → Report(year) → Claim → Metric` and `Claim –contradicts→ Claim`. Enables temporal drift detection, cross-company peer comparison, and explainable contradiction chains far beyond pairwise NLI. *(Effort `1–2w`; Impact high; Risk medium.)*
- **Hybrid neuro-symbolic checks.** Symbolic rules for unit/temporal consistency (e.g., Scope1+Scope2 vs total; YoY plausibility bounds) layered with the LLM/NLI. Cheap, deterministic, and a strong false-positive filter. *(Effort `3–5d`; Impact high.)*
- **Ensemble + self-correction.** Two-model extraction with reconciliation; an LLM-judge "verifier" pass; abstain when models disagree (confidence scoring). *(Effort `1–2w`; Impact high for trust.)*
- **Streaming UX.** Stream parse/extract progress to the frontend (SSE/WebSocket) once §4.1 exists. *(Effort `2–4d`; Impact medium UX.)*
- **Retrieval redesign (RAG).** Today retrieval is only used for contradiction blocking. A proper RAG layer (chunk store + reranker) would power "evidence for this claim", "similar claims across peers", and grounded Q&A. *(Effort `1–2w`; Impact medium–high.)*

---

## 7. API dependency reduction & vendor lock-in (critical)

### 7.1 Current hard external dependencies

| Dependency | Where | Why it exists | Risk | Failure modes | Lock-in |
|---|---|---|---|---|---|
| **Groq LLM** (`llama-3.1-8b-instant`) | `claim_extractor.LLMClient` | Claim extraction from chunks | **High** | 429 rate limits (free tier 500k tok/day, 30 RPM → `sleep(2.1)`), daily cap aborts runs mid-stream ([claim_extractor.py:419](backend/src/extractors/claim_extractor.py)), model deprecation | Low–Med (provider abstraction exists; OpenAI/Anthropic also supported) |
| **Supabase** (Postgres + pgvector + Edge + Auth) | DB of record, RPC, edge fn | Storage, vector search, frontend data | **High** | Project pause (free tier), key leak, RLS gaps, region/latency | **High** (RPC `match_claims`, edge functions, auth, anon key in client) |
| **Lovable AI gateway** | `supabase/functions/analyze-claims` | Frontend "Analyze claims" | **Medium** | `LOVABLE_API_KEY` unset → feature dead; opaque model/SLA | High (proprietary gateway) |
| **HF Hub (model download)** | sentence-transformers / transformers at runtime | Pulls model weights | Medium | Unauthenticated rate limits (warning already seen), offline failure | Low (can vendor weights) |

**Already local (good):** embeddings (`bge-base-en-v1.5`), NLI (`distilbert-mnli`), parsing (PyMuPDF/pdfplumber/spaCy). So the system is **closer to local-first than it looks** — the LLM extractor is the main external dependency.

### 7.2 Alternatives & migration

**LLM extraction (highest leverage):**
- **Local-first option:** run a quantized instruct model via **Ollama / llama.cpp** (e.g., Llama-3.1-8B-Instruct Q4/Q5, Qwen2.5-7B-Instruct) behind the *existing* `LLMClient` abstraction (add a `local`/`ollama` provider). For batch/server, **vLLM** for throughput.
- **Tradeoffs:** accuracy ~ comparable for this structured-JSON task at 7–8B with a good prompt; latency depends on GPU (CPU is slow); removes rate limits and per-token cost; adds infra/ops burden and a GPU requirement for speed.
- **Hybrid/redundancy:** model router with fallback order (local → Groq → OpenAI), per-provider health checks, and graceful degradation to the **rule-based extractor** (already present) when all LLMs fail. Cache (§4.10) makes re-runs provider-free.

**Vector search / DB:**
- Self-host **Postgres + pgvector** (compose) to drop Supabase lock-in for the data plane; or **Qdrant**/**LanceDB** if you want a dedicated vector store. Keep the `match_claims` logic as SQL/migration so it ports. Supabase Auth can be replaced later with self-hosted GoTrue or app-level auth.

**Lovable AI edge function:** re-point `analyze-claims` to the same model router (local/Groq) so the frontend feature doesn't depend on a proprietary gateway.

**HF Hub:** vendor model weights into the image / a model cache volume; set `HF_HOME` + `TRANSFORMERS_OFFLINE=1` in prod for deterministic, offline-capable startup.

### 7.3 Recommended roadmap (dependency reduction)

- **Short-term (`1w`):** add `local`/`ollama` provider to `LLMClient`; add a provider-router with fallback + rule-based degradation; vendor/cache HF weights; cache extractions. → removes hard Groq dependency for dev and gives runtime redundancy.
- **Medium-term (`2–4w`):** docker-compose local Postgres+pgvector; port `match_claims` + schema via migrations; make Supabase *optional* (env-switch between hosted and self-hosted DB); re-point edge function to the router.
- **Long-term (`1–2mo`):** GPU-served vLLM for throughput; full self-host profile (DB + inference) for air-gapped/private deployments; evaluate fine-tuning a small model on the gold set to beat the 8B baseline at lower cost.

---

## 8. Benchmark vs "what good looks like"

| Dimension | This system | Mature system | Gap |
|---|---|---|---|
| Ingestion | Manual script | Idempotent API + queue + workers | **Large** |
| Orchestration | Mock LangGraph | Real DAG with persisted state + resume | **Large** |
| Reasoning | Pairwise NLI (broken input) + naive numeric | Ensemble + symbolic checks + verifier + confidence | **Large** |
| Evaluation | Count-based "PASS" | Labeled gold set, P/R/F1, regression gates | **Large (research-blocking)** |
| Reproducibility | Unpinned, no seeds, no versions | Lockfiles, pinned models, run/version lineage | **Large** |
| Observability | `print()` | Structured logs, metrics, traces, cost | **Large** |
| Infra | None | Docker, CI, migrations, IaC | **Large** |
| Security | Anon key, secrets in `.env` | RLS, service role, secret mgr, auth | **Large** |
| Frontend | Solid, now de-fictioned | + streaming, auth, scoped data | Medium |
| Core extraction | **Real and decent** | + quality gating + self-consistency | Medium |

**What separates this from a mature system:** it has a credible *core* but lacks the *systemic spine* — ingestion, orchestration, evaluation, reproducibility, observability, security. Those are the difference between "a notebook that worked once" and "a system."

---

## 9. Highest-ROI prioritization

### Tier 1 — Major impact, low–medium effort (do first)

| Improvement | Complexity | Estimated Time | Dependencies | Risk | Expected Impact |
|---|---|---|---|---|---|
| Pin deps + lockfile + `pyproject` + seeds | Low | `2–4h` | — | Low | Reproducibility baseline |
| Containerize (backend+worker+pg) + compose | Medium | `3–5d` | deps pinned | Low | Env parity, local self-host |
| CI (lint/typecheck/pytest/build) | Low–Med | `2–4d` | Docker, a few tests | Low | Stops regressions |
| Structured logging + basic metrics | Low–Med | `3–5d` | — | Low | Operability, cost visibility |
| LLM cache + chunk dedup + cost caps | Medium | `2–4d` | — | Low | Big cost/latency cut |
| Add `local`/router provider + rule-based fallback | Medium | `3–5d` | LLMClient | Low–Med | Removes Groq hard-dep, redundancy |
| Fix NLI pairing + unit-aware numeric checks | Medium | `3–5d` | — | Med | Trustworthy contradictions |
| Enable RLS + service-role writes + rotate key | Medium | `3–5d` | Supabase | Med | Closes security hole |
| Delete/clearly-quarantine mock `workflow_dag.py` | Low | `2–4h` | — | Low | Removes misleading code |

### Tier 2 — Major impact, high effort (game-changing)

| Improvement | Complexity | Estimated Time | Dependencies | Risk | Expected Impact |
|---|---|---|---|---|---|
| **Async job/run model + workers (production ingest)** | High | `1–2w` | queue, runs table | Med | The core unlock; real end-to-end |
| **Real orchestration DAG w/ persistence + resume** | High | `3–5d`–`2w` | runs table | Med | Extensibility, recovery |
| **Gold-set evaluation harness (P/R/F1) + gating** | High | `1–2w` | labeled data | Low (effort) | Research credibility |
| **Data-model fix: indexes/partitions + migrations + versioning** | Medium–High | `3–5d` | Supabase migrations | Med | Perf + safe evolution + lineage |
| **Extraction-quality redesign (table/layout routing)** | High | `1–2w` | parser | Med | Lifts every downstream metric |
| **Verification/ensemble/confidence layer** | High | `1–2w` | NLI fix, eval | Med | Trust, fewer false positives |
| Self-hosted Postgres+pgvector profile (de-lock Supabase) | Medium–High | `2–4w` | migrations | Med | Vendor independence |

### Tier 3 — Nice-to-have / future

| Improvement | Complexity | Estimated Time | Dependencies | Risk | Expected Impact |
|---|---|---|---|---|---|
| Knowledge graph + graph reasoning | High | `1–2w` | data model | Med | Research depth |
| Browser/Fetch MCP for source corroboration | High | `3–5d`+ | router, eval | Med–High | Capability expansion |
| Streaming progress UI (SSE/WebSocket) | Medium | `2–4d` | job model | Low | UX |
| RAG layer for evidence/Q&A | Medium–High | `1–2w` | vector store | Med | Product surface |
| Analyst agent over MCP (DB/eval/memory) | High | `1–2w`+ | MCP, eval | Med | Power-user capability |
| GPU vLLM serving | Medium | `3–5d` | GPU | Med | Throughput |
| Fine-tune small extractor on gold set | High | `2–4w` | gold set | Med | Cost/accuracy |

---

## 10. Recommended sequencing (roadmap)

1. **Weeks 1–2 (Foundation & honesty):** pin deps, Docker+compose, CI, structured logging, delete mock DAG, LLM cache, local provider+fallback, rotate secret + enable RLS. *(All Tier 1.)* — makes the system reproducible, observable, cheaper, and not a security liability.
2. **Weeks 3–5 (The spine):** async job/run model + workers → **real end-to-end ingest via API**; data-model fix with migrations + versioning; fix reasoning (NLI + numeric). — turns it into an actual system.
3. **Weeks 6–8 (Credibility):** gold-set eval harness + regression gating; extraction-quality redesign; verification/confidence layer. — makes results *trustworthy and defensible*.
4. **Months 2–3 (Independence & depth):** self-hosted DB/inference profile; knowledge graph + graph reasoning; RAG + analyst agent over MCP; optional fine-tune. — research-grade + vendor-independent + scalable.

---

## 11. Self-critique — what I might be wrong about / missed

- **I did not run the live pipeline end-to-end with a fresh PDF through the API + ingest**, so some "broken" claims (e.g., NLI quality, contradiction FP rate) are inferred from code + the existing test report, not measured. The eval harness (§4.5) is exactly what would replace this inference with numbers — which is itself the strongest evidence that §4.5 is the right priority.
- **RLS status is inferred** (anon key used for inserts ⇒ likely permissive) but not directly confirmed; verify policies before assuming the hole exists.
- **Local-LLM accuracy parity is a claim, not a measurement.** Whether a quantized 7–8B matches Groq's 8B on this structured task must be validated on the gold set before committing to local-first in production.
- **I may be over-indexing on "production-grade."** If the actual goal is a *research paper/demo*, then Tier-1 reproducibility + the eval harness (§4.5) + reasoning fixes (§4.4) matter most, and the heavy infra (queues, multi-tenancy, self-hosting) can wait. If the goal is a *product*, the async ingest spine (§4.1) is the gate.
- **Possible over-engineering risks I'm flagging on myself:** full LangGraph adoption, knowledge graph, and MCP agents are genuinely valuable but should *follow* a working eval loop — building them first would just produce confident wrong answers faster.
- **Things I deliberately downweighted:** bundle splitting / minor lint / micro-perf — real but low-ROI versus the systemic gaps above.

> **If you do only five things:** (1) async job/run model + real DB ingest, (2) gold-set evaluation with P/R/F1, (3) fix NLI + unit-aware numeric reasoning + a verifier, (4) pin/containerize/CI for reproducibility, (5) add a local LLM provider with fallback. Those five convert this from a demo into a serious, defensible system.
