# External Evaluation — Notes & Prioritized Response

**Date:** 2026-07-01
**Source:** External "principal-architect" evaluation (competitor-landscape framing, enterprise-SaaS bar).
**Status:** Notes only — captures the eval verbatim-in-summary + this repo's prioritized verdict. Roadmap lives in [take_step_forward.md](take_step_forward.md); runtime defects in [existing_issues.md](existing_issues.md).

---

## 1. The eval's scorecard (against production-grade enterprise SaaS, not student bar)

| Metric | Score | Core reason |
|---|---|---|
| AI/ML sophistication & reasoning | **8.5/10** | Real reasoning layer — NLI contradiction engine, unit-aware numeric compare, greenwashing taxonomy, external fact-check. Semantic cross-examination, not summarization. |
| Product vision & UX | **8/10** | "Integrity Audit" breaks macro ESG fluff into sentence-level verifiable claims w/ vagueness + greenwash flags. Attacks the black-box rating problem. |
| Extraction quality & data processing | **6/10** | "Garbage-in" ceiling. Multi-col tables / complex PDF layouts flatten to garbled sentences pre-LLM → downstream NLI throws false positives. |
| Architecture, infra & scalability | **4.5/10** | Functionally a synchronous script. `/v1/upload` runs 8-step pipeline in one thread → times out / crashes under load. No async queue, weak CI/CD, no container orchestration. |

## 2. Competitor landscape

Space is crowded with **reporting** tools, thin on **auditing** tools.

- **Traditional raters** (MSCI ESG, Sustainalytics, Clarity AI) — ingest thousands of reports → one letter grade (black box).
- **AI reg-techs** (Briink, Manifest Climate, Greenomy) — map messy disclosures to regs (CSRD, TCFD).
- **Carbon/asset verifiers** (Sylvera, BeZero) — deep satellite + AI, but carbon-offset projects only.

**What we do better:**
1. **Micro-level transparency** — accountability to the exact sentence/claim; expose claim vagueness (groundability); show the contradictory sentences between 2022 vs 2023.
2. **Adversarial / anti-greenwashing posture** — built like a forensic auditor (greenwash taxonomy + contradiction engine), not a company-flattering compliance helper. Audience: investigative journalists, short-sellers, activist investors.
3. **Agentic interrogation** — chat agent w/ tool access to canonical metrics, evidence corpus, contradiction flags. Beyond static PDF dashboards.

## 3. Learn/add items the eval proposed

1. **Visual grounding (bounding boxes)** — layout-aware parser (Docling / Unstructured.io); store `[x0,y0,x1,y1,page_num]` per claim; render PDF w/ highlight for human verification.
2. **Multi-modal chart/table extraction** — detect table/image regions, pass raw image to a VLM → structured JSON (reports are ~40% charts/tables; text parsers butcher them).
3. **Strict regulatory mapping** — tag each claim to ESRS / TCFD clause IDs, not just internal `metric_key`. Makes it legally useful to compliance officers.
4. **Async ingestion pipeline** — rip out synchronous `/v1/upload`; return `job_id` instantly, process in background, push progress via WebSocket/SSE.

**Eval's verdict:** to go from research prototype → SaaS, the gap is **Data Engineering** (layout parsing / VLM tables) + **DevOps** (async queues, caching, containers) — NOT more AI features.

---

## 4. This repo's prioritized response (what's actually worth doing)

**Root-cause framing:** the four scores are not independent. Extraction (6/10) is the upstream driver — noisy text → false NLI contradictions → an integrity score that lies. Fix extraction and three downstream scores rise for free. Everything else is cosmetic until that's fixed.

### MUST
1. **Layout-aware table parsing — the real ceiling.** PyMuPDF flattens multi-column tables into word-soup → LLM extracts ghosts. Swap to **Docling** (free, local, strong tables, emits provenance coords). Single change lifts extraction, cuts NLI false-positives, makes the score trustworthy. Highest leverage on the list. *(Directly attacks the standing "LLM extraction ceiling" residual logged in [existing_issues.md](existing_issues.md).)*
2. **Regulatory mapping (ESRS / TCFD / GRI tags).** Cheapest high-value add — ontology + prompt expansion, no new infra. Claims already carry `metric_key`; add `framework_id`. Turns "cool demo" into "compliance-officer usable" and gives the adversarial angle standard anchors so accusations stick. Do alongside #1. *(Note: greenwash taxonomy already maps EU/ESRS/SEC/BRSR per take_step_forward.md — extend that to per-claim, not just per-flag.)*

### SHOULD
3. **Visual grounding (bbox) — only AFTER #1.** Not a separate project: Docling already emits `[x0,y0,x1,y1,page]`. Once #1 lands, storing bbox is near-free; render PDF + highlight = large trust payoff. A free-rider on #1.

### DEPRIORITIZE (eval is partly stale here)
4. **Async queue.** Eval says rip out sync `/v1/upload`, add Celery/Redis/RabbitMQ. But job state already persists to DB (survives restart, multi-worker — commit `e67b323`) and write endpoints are auth-gated (`cce42f9`). The hard part is done. For 4 companies a broker is over-engineering — just add a background worker loop pulling the existing job table; return `job_id`, poll endpoint. ~80% of the value at ~10% of the effort. Medium priority, not the crisis the eval paints.

### SKIP (premature)
- **Full-document VLM** (eval #2). Per-page VLM calls are expensive; Docling gets most tables. Reserve VLM only for table regions that fail structured parse — hybrid fallback, not default.
- **K8s / container orchestration.** Enterprise-SaaS framing. Corpus is ~2385 claims / 4 companies. Single container + worker is enough.

### Order
```
1. Docling swap       → fixes extraction + NLI (root cause)
2. + bbox storage     → free with Docling, trust UX
3. Framework tags     → cheap, legal credibility
4. Background worker  → reuse existing job table, no broker
   (skip: full-doc VLM, k8s)
```

**One-line:** eval is right that the answer is *data engineering, not more AI* — but wrong on target. **Docling table parsing** is the real unlock, async is already half-built, and per-claim regulatory tags are the cheap differentiator the eval underweights.
