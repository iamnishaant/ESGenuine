# ESGenuine

> Corporate sustainability reports are written to be read by humans and audited by nobody. This makes them machine-checkable.

An **evidence-grounded ESG claim extraction and integrity system**. It turns a 90-page
sustainability PDF into structured, provenance-carrying claims, then measures how much of
that extraction you can actually trust — with a deterministic post-correction layer that
repairs what the language model gets wrong at **0.45 ms per claim and zero inference cost**.

Unlike typical LLM document pipelines, this system:

- **Measures itself.** Six evaluation harnesses, bootstrap confidence intervals, a
  mechanically-enumerated recall denominator, and a CI gate that fails the build if ground
  truth is edited.
- **Refuses to flatter itself.** Circular metrics are suppressed, thin-sample scores are
  withheld rather than printed, and the harnesses decline to emit an interaction term when
  the experimental arms aren't comparable.
- **Recomputes offline.** Every number below regenerates from committed fixtures in
  seconds, with no API key and no network.

---

## 🧭 TL;DR

- **Problem:** ESG disclosures are unstructured, unverified, and inconsistent between
  documents — and LLM extraction from them fails quietly.
- **Solution:** Parse → extract → **deterministically repair** → ground against the source
  page → store with provenance.
- **Core Innovation:** The repair layer is *post-hoc, rule-based and free*, and **which
  repair matters is determined by the disclosure format** — a statutory filing and a
  narrative report need different corrections.
- **Impact (all measured, see [Results](#-results)):**
  - Precision composite **67.7 → 96.1** (statutory), **72.1 → 89.7** (narrative)
  - Repair layer worth **+24.6** and **+7.0** points at **zero LLM cost**
  - **0.45 ms/claim** — 168 ms for a 373-claim report, single-threaded, no network

---

## 🎯 Problem Statement

Existing approaches suffer from:

- **Unstructured disclosure.** The same metric appears as a table cell in one report, a
  sentence in another, and a footnote in a third. There is no schema.
- **Silent LLM failure.** An extractor asked for "Scope 1 emissions" returns a number that
  looks plausible. We measure **31.7%** of a 70B model's emitted values as *not present on
  the page it cites*.
- **Unfalsifiable evaluation.** Most pipelines report a precision figure against a gold set
  sampled from their own output — which structurally cannot count what they missed.

This leads to:

- ESG ratings that **disagree with each other** at correlation ~0.5 across major providers
  (the "aggregate confusion" problem), because the underlying data extraction is unaudited.
- Greenwashing that is **invisible to automation**: a target restated three ways across two
  reports reads as three supporting claims, not one unverified commitment.

---

## 🎯 Design Goals

- **Provenance or nothing** — every claim carries document, page, and source sentence.
- **Cheap correction** — repairs must be deterministic and free relative to a second LLM pass.
- **Honest measurement** — no metric that cannot be recomputed from a committed artifact.
- **Format-aware** — a statutory form and a narrative report are different problems.

---

## 💡 Key Innovations

1. **Deterministic post-correction layer**
   → Six cumulative stages (taxonomy normalisation, fiscal-year repair, source-value
   verification, rule-based gate, furniture filter) applied *after* the LLM. Worth +24.6
   points on a statutory filing at no inference cost.

2. **Regime-dependent repair — the central finding**
   → The dominant repair differs by disclosure format: the rule-based gate carries the
   statutory filing (**+20.5**), taxonomy mapping carries the narrative report (**+10.6**),
   and **the two confidence intervals do not overlap**.

3. **Mechanically-grounded evaluation, not self-report**
   → Recall is measured against table cells *enumerated from the parsed document*, giving a
   system-independent denominator. Grounding precision checks whether an emitted number
   literally occurs on its cited page — no annotation, comparable across any system.

4. **Adversarial harness design**
   → The rule-based baseline is built from the same enumerator that scores recall, so its
   100% is tautological — the harness detects this and prints `--` instead. Gold scores
   computed on <50% sample match render as `n/a`, not as a number.

---

## 🧠 Why This Works

Traditional approaches fail because:

- They treat extraction as a **single LLM call** and accept whatever comes back.
- They evaluate on **precision only**, which cannot see what was dropped.

This system succeeds because it separates:

- **What the model produced** (probabilistic, expensive, variable)
- **What is structurally repairable** (deterministic, free, auditable)
- **What is verifiable against the source** (mechanical, model-independent)

→ **Result:** the expensive component shrinks to the part that genuinely needs a model, and
everything downstream is inspectable.

---

## 🏗️ System Architecture

```text
             PDF (sustainability / BRSR / ESG report)
                              │
                    ┌─────────▼─────────┐
                    │  Parsing (Docling) │  8-step: triage → layout → sections →
                    │  + table extraction│  sentences → candidates → chunks → tables
                    └─────────┬─────────┘
                              │  page markdown + semantic chunks
                    ┌─────────▼─────────┐
                    │  LLM extraction    │  llama-3.3-70b via NVIDIA NIM
                    │  (pooled, N keys)  │  round-robin + failure cooldown + checkpoint
                    └─────────┬─────────┘
                              │  raw claims (aspect, metric, provenance)
        ┌─────────────────────▼─────────────────────┐
        │      DETERMINISTIC REPAIR LAYER            │   ← the contribution
        │  S1 ontology → S2 FY repair → S3 value-in- │      0.45 ms/claim
        │  source → S4 quality gate → S5 furniture   │      zero API cost
        └─────────────────────┬─────────────────────┘
                              │  repaired + flagged claims
                    ┌─────────▼─────────┐
                    │  Supabase Postgres │  pgvector HNSW, 5 LIST partitions,
                    │  + embeddings      │  content-hash dedup, idempotent ingest
                    └─────────┬─────────┘
                              │
      ┌───────────────────────┼───────────────────────┐
      ▼                       ▼                       ▼
 Contradiction          Greenwashing            Integrity report
 (NLI, DistilBERT)      taxonomy                (count-weighted score)
      │                       │                       │
      └───────────────────────┼───────────────────────┘
                              ▼
                   React + Vite dashboard
              (globe, claim explorer, audit trail)
```

---

## 🧩 System Components

### 1. Parsing (`backend/src/parsers/`)
- **What:** PDF → sections, sentences, claim candidates, structured tables.
- **How:** Docling for layout-aware table extraction; a Step-0 triage rejects
  non-machine-readable PDFs with a 422 rather than producing silent garbage.

### 2. LLM extraction (`backend/src/extractors/claim_extractor.py`)
- **What:** Markdown tables and text windows → structured claims.
- **How:** An OpenAI-compatible **round-robin pool** across N NVIDIA/Groq/HF keys with
  per-key failure cooldown, streaming reads, bounded retry, and a **resumable checkpoint**
  so a network failure re-pays only for the pages that broke.

### 3. Deterministic repair (`backend/src/extractors/quality_gate.py`, `ontology.py`)
- **What:** The correction layer this project is actually about.
- **How:** Taxonomy normalisation to a controlled vocabulary; fiscal-year column repair;
  value-in-source verification; rule-based repairs (scope inference, waste/water confusion,
  diversity/biodiversity confusion, implausible unit–aspect pairs); form-furniture removal.

### 4. Storage (`backend/src/extractors/supabase_ingest.py`)
- **What:** Idempotent, content-hash-deduplicated ingest into Supabase Postgres.
- **How:** `pgvector` embeddings (`bge-base-en-v1.5`, pinned by commit SHA), HNSW indexes,
  LIST partitioning on `metric_family`.

### 5. Reasoning (`backend/src/reasoning/`)
- Contradiction detection via NLI over vector neighbourhoods, a greenwashing-signal
  taxonomy, fact-checking against reference figures, and a document-level integrity score.
- ⚠️ **Not evaluated.** See [Limitations](#️-limitations--what-is-not-evaluated).

---

## 🧠 Models

| Role | Model | Pinning |
|---|---|---|
| Claim extraction | `meta/llama-3.3-70b-instruct` (NVIDIA NIM) | hosted, temperature 0.1 |
| Comparison arm | `openai/gpt-oss-120b` (NVIDIA NIM) | hosted, temperature 0.1 |
| Embeddings | `bge-base-en-v1.5` | commit `a5beb1e3` |
| Contradiction (NLI) | `distilbert-base-uncased-mnli` | commit `cfa538a0` |

**There is no training.** This is an extraction-and-repair system, not a learned model — the
contribution is the deterministic layer and the evaluation, and all RNGs are seeded (42).
Local weights are pinned by commit SHA so the offline results are bit-reproducible.

---

## 📊 Results

> Every figure below is rendered by `backend/scripts/make_readme_figures.py`, which computes
> its values from the committed fixtures **at render time**. A plot cannot drift from the
> table beside it.

### Corpus

| | |
|---|---|
| Companies / reports | **4 / 6** |
| Source pages | **461** |
| Extracted claims | **1,730** (1,394 carrying a numeric value) |
| Annotated claims | 100 (2 × 50) |
| Regimes | 1 statutory BRSR filing, 5 narrative/IR reports |

### 1. Extraction quality — the repair layer

Nonparametric bootstrap over annotated claims, 2,000 resamples, claim as sampling unit.

| Metric | BRSR statutory | 95% CI | IR narrative | 95% CI |
|---|--:|:--:|--:|:--:|
| candidate precision | 86.0% | [75.0, 95.5] | 98.0% | [94.0, 100.0] |
| aspect node | 94.6% | [85.7, 100.0] | 79.6% | [68.0, 90.0] |
| unit family | † | — | 77.3% | [64.4, 89.1] |
| claim type | † | — | 95.9% | [89.8, 100.0] |
| **precision composite** | **96.1** | **[93.5, 98.5]** | **89.7** | **[85.3, 94.0]** |

† No errors observed in the annotated sample. Reported this way rather than as 100%: a
percentile bootstrap on all-correct data returns a degenerate interval.

![Ablation by regime](images/fig_readme_1_ablation.png)

**The central finding.** The dominant repair stage is set by the disclosure format — the
rule-based gate carries the statutory filing (**+20.5** [16.3, 25.2]), taxonomy mapping
carries the narrative report (**+10.6** [7.8, 13.5]), **and the intervals do not overlap**.
A single pipeline tuned on one regime will under-serve the other.

| Δ | BRSR | IR |
|---|:--:|:--:|
| S0→S1 ontology | +3.8 [1.5, 6.5] | **+10.6** [7.8, 13.5] |
| S3→S4 gate | **+20.5** [16.3, 25.2] | +7.0 [4.0, 10.2] |
| S4→S5 furniture | +2.4 [0.8, 4.3] | +0.0 *n.s.* |
| **S1→S5 repair layer** | **+24.6** [19.6, 30.4] | **+7.0** [4.0, 10.2] |

### 2. What precision costs — the honesty figure

![Precision–recall trade-off](images/fig_readme_2_tradeoff.png)

Across S0→S5 the composite rises **67.7 → 96.1** while table-fact recall **falls
59.5% → 54.0%**. The furniture filter removes 34 claims, and some of them are genuine facts.
**A precision-only evaluation cannot see this.** Recall is measured against 482 table cells
enumerated mechanically from the parsed document — a denominator the system does not control.

### 3. Extractor choice vs. repair — the matched comparison

![Matched extractor comparison](images/fig_readme_3_extractor.png)

Identical committed markdown, identical code path, identical token budget; only the model
differs. Page-matched, so a page lost to a network failure cannot read as a model finding
nothing.

| Document | Extractor | Fact recall | Grounding |
|---|---|--:|--:|
| BRSR | llama-3.3-70b | 41.2% | 68.3% |
| BRSR | **gpt-oss-120b** | **97.2%** | **99.1%** |
| IR | llama-3.3-70b | 44.1% | 100% |
| IR | **gpt-oss-120b** | **89.8%** | 100% |

**Extractor choice dominates the tabular surface.** **31.7%** of the 70B model's emitted
values do not occur on the page they cite, against **0.9%** for the 120B model — the exact
misattribution class the repair layer's source-value check exists to catch.

> ⚠️ **This comparison does *not* establish whether the repair layer survives a model
> upgrade, and we do not claim that it does.** Recall and grounding read only a claim's value
> and page, so they observe the layer solely where it *adds, removes or rewrites* a claim —
> and its one such action here removes nothing at either tier. The gold composite, where
> aspect/type/unit corrections would register, matches 2% and 0% of the two arms and is
> unusable across models. The question is open. See
> [`docs/CROSSCHECK_FINDINGS.md`](docs/CROSSCHECK_FINDINGS.md) §P1.

### 4. Cost, and the no-model floor

| | |
|---|--:|
| Repair layer | **0.45 ms/claim** (168 ms for 373 claims, single-threaded) |
| Rule-based extraction, no LLM | names only **43.1%** of table rows |
| Offline test suite | **178 passed** |

The 57% of table rows a keyword taxonomy *cannot* name is the share of the surface that
genuinely requires a model.

---

## 🧪 Experimental Insights

- **The dominant repair is a property of the document, not the pipeline.** Non-overlapping
  intervals across two regimes.
- **Precision-oriented repair is a trade.** +28.4 composite costs −5.5pp recall.
- **A better extractor is worth more than repair, on the table surface.** ~2× the recall and
  ~30× fewer misattributions.
- **But repair does not become redundant.** The gate's intervention rate *rises* with the
  stronger model (15.4% → 37.7%). Intervention is not improvement, so this settles nothing —
  it only rules out the convenient conclusion.

**Conclusion:** → *Deterministic repair and model capability are not interchangeable, and the
evidence to declare a winner does not exist yet.*

---

## ⚠️ Limitations — what is *not* evaluated

Stating these is what makes the rest credible.

1. **Development sets, not held-out.** Both annotated sets were tuned against; 6 of 100
   labels were revised toward the system. **No untouched test set exists.** The paired
   ablation deltas are unaffected (identical claims at both stages) — which is why they are
   the primary result and the absolute scores are context.
2. **Single annotator.** No inter-annotator agreement statistic.
3. **Precision-only composite.** No recall term; narrative-claim recall is unmeasured.
4. **Two documents in depth**, and they are the corpus's *easiest* — 23–25% of their claims
   fall outside the taxonomy, against 52–53% for two reports not evaluated.
5. **The frozen fixtures are not raw model output.** They carry repair flags from an earlier
   layer revision, so S0 is a *reconstruction* and the reported gains are a **lower bound**.
6. **Extraction is not end-to-end reproducible** — hosted LLM at non-zero temperature. Frozen
   fixtures make every *reported* number recomputable.
7. **Out of scope and unevaluated:** contradiction detection, the greenwashing taxonomy, the
   document integrity score (severity weights are hand-set and uncalibrated), and satellite
   verification. These ship as components; **no accuracy is claimed for any of them.**

### Failure case

**Input:** a governance form row — `"Whether the entity has a policy on..."` with the cell `2`

**Issue:** the extractor reads `2` as a metric value. The furniture filter removes it — but
the same filter also deletes genuine sparse table facts, which is the −5.5pp recall cost
above. Precision and recall are traded here, not jointly optimised.

---

## 🔁 Reproducibility

All offline, no credentials, seconds:

```bash
python backend/scripts/run_ablation.py   --markdown   # repair-layer ablation
python backend/scripts/run_bootstrap.py  --markdown   # confidence intervals
python backend/scripts/run_recall.py                  # table-fact recall
python backend/scripts/run_baselines.py  --markdown   # 2×2 + no-LLM floor
python backend/scripts/run_cost.py       --markdown   # latency
python backend/scripts/run_page_matched.py            # page-matched model comparison
python backend/scripts/run_gate_workload.py           # gate intervention rate
python backend/scripts/make_readme_figures.py         # the plots above
cd backend && python -m pytest -m "not live"          # 178 passed
```

Raw LLM outputs and parsed page markdown are committed as frozen fixtures; local weights are
pinned by commit SHA; all RNGs seeded. **A gold-set tamper gate fails CI if any ground-truth
label changes without a documented version bump.**

---

## 📁 Repository Structure

```text
backend/
├── src/
│   ├── parsers/          Docling PDF → sections/sentences/tables  (~1.1k LOC)
│   ├── extractors/       LLM extraction, ontology, quality gate   (~3.5k LOC)
│   ├── reasoning/        NLI contradictions, greenwash, integrity (~2.3k LOC)
│   ├── verification/     geocoding + Sentinel NDVI satellite      (~0.4k LOC)
│   └── api/              FastAPI: ingest, claims, jobs, auth      (~0.6k LOC)
├── scripts/              evaluation harnesses (the science)       (~4.1k LOC)
├── tests/                27 test modules, 178 offline tests
│   └── eval/             gold sets, frozen fixtures, hash locks
└── database/             schema + migrations (partitions, RLS, HNSW)
frontend/src/             React + Vite dashboard                   (~12.5k LOC)
docs/                     paper, findings, protocols, results, figures
```

---

## ⚙️ Quick Start

```bash
# 1. Backend
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# 2. Verify the evaluation reproduces (no keys needed)
cd backend && python -m pytest -m "not live"          # expect 178 passed

# 3. Configure (see .env.example)
cp .env.example .env                                   # DATABASE_URL, NVIDIA_API_KEY(S), Supabase

# 4. Run
uvicorn src.api.server:app --reload --port 8000        # backend
cd frontend && npm install && npm run dev              # dashboard
```

### Example: ingest a report

```bash
curl -X POST http://localhost:8000/v1/reports/ingest \
  -F "file=@report.pdf" -F "company_name=Tata Power" -F "report_year=2024"
# → { "job_id": "..." }   then poll GET /v1/jobs/{job_id}
```

**Example claim:**

```json
{
  "aspect": "renewable energy share",
  "normalized_aspect": "energy.renewable",
  "metric": { "value": 42.5, "unit": "%" },
  "claim_type": "performance",
  "provenance": { "page_number": 17, "source_sentence": "Renewable capacity (%)" },
  "framework_tags": ["GRI 302-1"],
  "quality_flags": ["type_fixed"]
}
```

---

## 🌍 Impact & Vision

- **For analysts:** a claim store with page-level provenance, so a number can be traced to
  the sentence that produced it.
- **For researchers:** a fully offline, reproducible evaluation harness for ESG claim
  extraction — including the negative results.
- **Vision:** make sustainability disclosure *falsifiable* — where every claim carries the
  evidence that supports it and the measurement of how much that evidence is worth.

---

## 📄 License & Citation

Licensed under the terms in [`LICENSE`](LICENSE). If you use this work, see
[`CITATION.cff`](CITATION.cff).
