# ESGenuine — repository audit

**Date:** 2026-08-12 · **Method:** direct inspection of the tree, the live database, and
execution artifacts. Claims below are checked, not inferred; where something is unverified
it says so.

---

## 1. What this actually is

**~25,000 lines** of working code across a Python backend and a React frontend, plus an
evaluation stack that is unusually rigorous for a project of this size.

| Area | LOC | Files |
|---|--:|--:|
| `backend/src` | 8,605 | 41 |
| `backend/scripts` (evaluation) | ~4,100 | 25 |
| `backend/tests` | 3,919 | 32 |
| `frontend/src` | 12,490 | 98 |

**The honest one-line description:** a competent ESG document pipeline wrapped in an
*exceptional* evaluation harness. The measurement infrastructure is the strongest thing here
and is stronger than the system it measures.

---

## 2. Is it real, or a demo?

Checked against the **live database**, not the code:

| Table | Rows | Verdict |
|---|--:|---|
| `claims` | **1,730** | ✅ real corpus, 6 reports, 461 pages |
| `reports` | **6** | ✅ content-hash dedup working |
| `contradictions` | **16** | ✅ NLI ran and persisted |
| `satellite_evidence` | **82** | ✅ Sentinel/NDVI genuinely executed |
| `claim_reviews` | **0** | ⚠️ review queue built, never used |
| `users` | **0** | ⚠️ auth built, never used |
| `jobs` | **0** | ⚠️ table exists; jobs actually live in-process |

Plus 3 geocode caches on disk, 12 parsed documents, 14 frozen fixtures. **This system has
genuinely been run end to end.** It is not a scaffold.

---

## 3. 🔴 Defects found

### 3.1 A partition that can never receive a row — `claims_environment` is dead

The partition bounds and the ontology disagree about naming:

```
PARTITION claims_environment FOR VALUES IN
  ('environment.emissions', 'environment.energy', 'environment.water', ...)

but the ontology emits metric_family = 'emissions.total', 'energy.renewable',
                                       'water.consumption', 'waste.total', ...
```

There is no `environment.` prefix anywhere in `SignatureGenerator.generate_metric_family`.
Consequence, measured live:

| Partition | Rows |
|---|--:|
| `claims_default` | **851** (49% of the table) |
| `claims_uncategorized` | 598 |
| `claims_social` | 281 |
| **`claims_environment`** | **0** ← 695 environment claims are in DEFAULT |
| **`claims_governance`** | **0** |

The largest real category — 695 emissions/energy/water/waste/biodiversity claims — is
entirely in the catch-all. `claims_governance` is dead for the same reason. 146 `social.*`
claims also miss because only 4 social families are enumerated in the bounds.

**Impact:** partition pruning does nothing for the biggest query class, and the per-partition
HNSW index on `claims_environment` indexes an empty table. It fails **silently** — no error,
just a partitioning strategy that is ~50% inert.

**Fix:** either prefix the ontology's families with the pillar, or restate the bounds to
match what the ontology actually emits. The second is safer (no data migration). Low
complexity, high value, and it should carry a test asserting no partition is empty after
ingest.

### 3.2 Live superuser credential (known, still open)

Documented in [`../docs/CROSSCHECK_FINDINGS.md`](../docs/CROSSCHECK_FINDINGS.md) §P0. The
plaintext Postgres **superuser** password was hardcoded in three tracked files since the
initial commit; the code is fixed but **the credential has not been rotated** and
authenticated successfully during this audit. Superuser bypasses RLS, so the RLS migration
constrains nothing against a holder of it.

### 3.3 Job state is in-process

`/v1/reports/ingest` returns a `job_id` and the UI polls `/v1/jobs/{id}`, but the `jobs`
table has 0 rows — state lives in the FastAPI process. A restart mid-ingest orphans the job
with no recovery path in the UI. On Render's free tier (which sleeps), this will happen.

---

## 4. Feature-by-feature status

| Feature | Status | Wired? | Evaluated? | Score |
|---|---|:--:|:--:|:--:|
| PDF parsing (Docling, 8-step + triage) | Complete | ✅ | indirectly | **8** |
| LLM extraction (pooled, N-key, checkpointed) | Complete | ✅ | ✅ | **9** |
| **Deterministic repair layer** | Complete | ✅ | ✅ CI-backed | **9** |
| **Evaluation harnesses (8 scripts)** | Complete | ✅ | self-validating | **10** |
| Supabase ingest (dedup, idempotent) | Complete | ✅ | partially | **7** |
| Contradiction detection (NLI) | Working | ✅ | ❌ | **6** |
| Greenwashing taxonomy | Working | ✅ | ❌ | **5** |
| Integrity score | Working | ✅ | ❌ uncalibrated | **4** |
| Fact-check vs reference figures | Working | ✅ | ❌ | **5** |
| Satellite (NDVI/Sentinel) | Working, n=2 | ✅ | ❌ | **4** |
| Frontend dashboard (10 pages) | Complete | ✅ | ❌ no FE tests | **7** |
| Ingest UI + job polling | Complete | ✅ | ❌ | **6** |
| Auth (JWT, register/login/refresh) | Complete | ✅ | ✅ unit | **6** |
| Review queue | Built | ✅ | ❌ 0 rows | **3** |

**Nothing is fake.** Everything listed executes. The gradient is *evaluated* → *works but
unmeasured* → *works but unused*.

**The pattern worth naming:** quality drops sharply as you move from the extraction/eval
core outward. The repair layer has bootstrap CIs; the integrity score has hand-set severity
weights (`Critical: 50, High: 30, Medium: 16, Low: 6`) that have never been validated against
any external criterion. The project knows this — `backend/docs/specs/integrity_formula.md`
carries a banner saying the documented formula was **never built** and naming what actually
ships. That self-quarantining is a strong signal, not a weak one.

---

## 5. Architecture notes

**Dual data path, and it's undocumented.** The frontend reads claims **directly from
Supabase** (`useClaims.ts` → `supabase.from(...)`) while ingest, reasoning, benchmark and
auth go through **FastAPI**. Both are legitimate, but it means:
- Row-level security is the *only* authorization on the claim data — the API layer is bypassed.
- Scores are recomputed client-side on every load rather than materialized.

**Good decisions worth crediting:**
- Round-robin LLM pool with per-key failure cooldown — a genuinely thoughtful reliability primitive.
- Resumable checkpoint keyed by work unit, where failures are deliberately *not* recorded so a resume retries only them.
- `unit_to_base` canonicalisation with an "unspecified" null family rather than `None`.
- Frozen fixtures as the reproducibility substrate — the entire eval stack runs offline at zero cost.

---

## 6. Premium-vs-free assessment

**Capabilities replicated for free:** layout-aware table extraction (Docling vs. AWS
Textract), vector search (self-hosted pgvector vs. Pinecone), NLI contradiction detection
(DistilBERT vs. GPT-4 judging), multi-key LLM throughput (pooling vs. paid rate limits),
satellite verification (Sentinel-2 open data vs. Planet Labs).

**Where paid systems still win:** no human-in-the-loop labeling; no calibrated risk model;
no entity resolution across corporate structures; single-annotator ground truth.

**Realistic category:** **strong research prototype / near-MVP.** Someone would pay for the
*evaluation harness* today. They would not yet pay for the integrity score, because it is
uncalibrated and the README correctly declines to claim otherwise.

---

## 7. Scores

| Dimension | Score | Justification |
|---|:--:|---|
| Engineering | **8/10** | Clean modules, real error handling, 178 tests. Loses points for the dead partition and in-process job state |
| Product | **6/10** | Real dashboard, real ingest. But the headline output (integrity score) is uncalibrated |
| Innovation | **7/10** | The regime-dependence finding and the harness discipline are genuinely novel-ish; the pipeline itself is standard |
| Architecture | **7/10** | Sensible separation; the undocumented dual data path and dead partition cost it |
| Production readiness | **5/10** | Live credential, in-process jobs, no observability, no rate limiting |
| Research rigor | **9/10** | Bootstrap CIs, tamper gate, frozen fixtures, retracted findings, reported nulls |
| Resume / placement | **9/10** | Very few student projects can show a negative result they chose to report |
| Startup potential | **5/10** | Real problem, real market — but 6 reports and no calibration is not a product |
| Investor demo | **6/10** | The globe and dashboard demo well; the numbers behind them are honest but small |

**True completion: ~70%.** Extraction + evaluation ~90%; reasoning ~60% (works, unmeasured);
product surface ~65%; ops ~35%.

---

## 8. Improvements, by ROI

### Quick wins
1. **Fix the dead partition** — restate bounds to match the ontology. *Files:* a new
   migration + a test. *Impact:* makes half the partitioning strategy real. *Risk:* low.
2. **Rotate the credential** + add `gitleaks` to CI. *Impact:* removes the only live security
   issue. *Risk:* none.
3. **Persist job state** to the `jobs` table that already exists. *Impact:* ingest survives a
   restart. *Complexity:* low.
4. **Resolve HQ at ingest** and persist lat/lng — new companies currently don't plot on the
   globe without a code change. `geocode.py` already exists.

### Medium
5. **A held-out annotated set** on a document never tuned on — **Infosys**, which is the
   corpus's hardest (52–53% uncategorized) and already ingested. This retires the largest
   limitation and is the single highest-fan-out task available.
6. **Ingest the 3 idle PDFs** (2 bp datasheets + 1 BRSR) → 5 companies / 9 reports, and it
   makes the "three disclosure formats" claim true, which it currently isn't.
7. **`reproduce.py` + a CI diff gate** — regenerate every number and figure and fail if any
   drifts. This is the exact failure that was caught manually.

### Major
8. **Calibrate the integrity score** against *something* — analyst ratings, restatements,
   controversy datasets. Until then it is a number with no referent, and it is the system's
   headline output.
9. **Source-anchored gold** per `docs/ANNOTATION_PROTOCOL.md`. Unlocks cross-model scoring,
   which is currently impossible (2% / 0% match rates) and is what blocked the P1 conclusion.

### Research-level
10. **Sector diversity.** 4 companies across 3 sectors is the real cap on generalisation. A
    bank, a retailer and a cement/steel firm would change the claim distribution meaningfully.

---

## 9. Verdict

**Would this impress?**

- **Professors / research labs:** Yes. Bootstrap CIs, a tamper gate on ground truth, a
  retracted finding and a reported null put it above most MSc work.
- **ML engineers:** Yes — the pool, the checkpoint, and the adversarial harness design read
  as someone who has been burned by silent failure.
- **Recruiters:** Yes, strongly, *if led with the evaluation* rather than the dashboard.
- **VCs:** Not yet. 6 reports and an uncalibrated score is a research artifact.

**Brutally honest:** this is **very good** student work with **exceptional** evaluation
methodology attached to a **good, not exceptional** system.

What separates it from a top-tier project is not engineering — it's *scope of evidence*.
Four companies, two annotated documents, both tuned against, one unanswered headline
question. Every conclusion is correctly hedged, which is admirable, but hedging is not the
same as having the data.

The single thing that would move it from "very good" to "exceptional" is **one untouched
held-out document, annotated and frozen before anyone looks at model output.** That converts
a careful internal evaluation into evidence about the world. It is one day of work, and it
would be worth more than everything else on this list combined.
