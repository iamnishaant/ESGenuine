# ESGenuine — Product Self-Improvement Journal

---

# Review 2026-06-25

## Scope

Full-product review across all shipped features as of this session's `ESG_V1` branch work (pre-push). Reviewed every backend reasoning module, the Integrity Audit frontend, the Portfolio Overview, the ingest pipeline, sidebar navigation, and all support files. This is the first entry in the journal. **A correction & verification pass (against the actual code) is appended at the end — read it alongside each section; a few claims below were overstated and are corrected there.**

---

## Feature Reviewed: Integrity Report & Greenwashing Taxonomy

### Current Purpose

Synthesize claim statistics, greenwashing flags, and contradiction findings into a single scored, graded report per document — the "ESG Integrity Report" — so an analyst or investor can judge a company's disclosure quality at a glance.

### Current Strengths

- **Score → Grade → Risk mapping is intuitive.** The 0–100 score, letter grade (A–F), and risk label ("Low"/"Moderate"/"High") form a hierarchy that any audience can grasp immediately.
- **Taxonomy is grounded in real regulation.** Flag types map explicitly to EU Green Claims Directive, ISO 14021, ESRS E1, SEC Climate Disclosure Rule, GHG Protocol, and BRSR. This is not vaporware — the references are real and citable.
- **Severity-ordered, deduped recommendations** are a strong design choice. The user sees the most urgent fix first.
- **Pure function design** (`build_report(claims, contradictions)` is I/O-free). Unit-testable, composable, and resilient.
- **Evidence snippets per flag** create auditability — the user can trace every flag to a specific claim.

### Hidden Weaknesses

1. **The integrity score is a simple subtraction, not diminishing.** The docstring says "diminishing" but the code is `score -= penalty` in a loop. Ten "Low" flags subtract 30 points total — identical cost to two "High" flags. This is punitive for noisy-but-harmless portfolios and lenient for concentrated risk. A well-run company with 200 claims that triggers 12 "Low" flags scores 64; a company with 2 "Critical" flags scores 50. The ordinal ranking is correct but the **distance between grades is misleading**.
2. **Penalty weights are hard-coded constants with no calibration data behind them.** The values 25/15/8/3 were eyeballed. They need at minimum a sensitivity analysis (how do real reports distribute?) and ideally calibration against analyst-labeled examples.
3. **No per-flag weighting by count.** A flag with `count: 47` subtracts the same penalty as one with `count: 1`. This means the score is insensitive to magnitude — a company with 1 vague claim and a company with 47 vague claims both lose the same 15 points (one "High" flag).
4. **Flag evidence is capped at 5.** For a "Vague" flag that applies to 47 claims, the user sees 5 and loses the rest. The count is shown, but there's no way to drill into the full list.
5. **No version/timestamp on the report.** When was this score computed? What model/prompt version was the extraction? The report is a snapshot but carries no provenance.

### User Pain Points

- **The score feels static and opaque.** Users cannot see *why* the score is 42 vs 67. A breakdown chart ("this flag cost you X points") is missing.
- **No comparison.** A score of 55 is meaningless without context. Is that good for this sector? For this year? The Integrity Report doesn't cross-reference the benchmark — even though the data exists in `benchmark.py`.

### Missing Considerations

- **Score normalization by report size.** A 50-page report with 180 claims will mechanically trigger more flags than a 10-page report with 30 claims. The score doesn't account for portfolio scale.
- **Historical trajectory of the score.** When you ingest a 2022 and 2023 report from the same company, there's no "your integrity improved from D to B" narrative. The trajectory module exists but isn't connected to the Integrity Report.

### Improvement Opportunities

1. **Introduce count-weighted penalties.** Instead of a flat penalty per flag, `penalty = base * min(log2(count + 1), cap)`. This makes magnitude matter without letting a single flag type dominate. ✅ **Shipped (this session)** — but with **prevalence**, not `log2(count)`: `penalty = sev_weight × (count / total_claims)` (weights `{Critical:50, High:30, Medium:16, Low:6}`; structural count=0 flags use a fixed 0.5 prevalence). Prevalence normalizes across report sizes — `log2(count)` would punish a 727-claim report just for being bigger than a 181-claim one. `_REPORT_VERSION` → `"2.0"`; `penalty_breakdown` now carries `prevalence`. Live result below.
2. **Score decomposition in the response.** Return `penalty_breakdown: [{flag_type, severity, count, points_deducted}]`. The frontend can render a stacked bar showing where points were lost. ✅ **Done (this session)** — `build_report` returns `penalty_breakdown` (`type/title/severity/count/points_deducted`, sorted most-impactful first). Score formula unchanged; field is additive. Test asserts `score == 100 − Σ(points)`.
3. **Sector-normalized scoring.** Use the benchmark data to show "your score relative to the median of companies in this sector/peer-group." Even a simple percentile rank transforms the score from abstract to actionable.
4. **Add `computed_at`, `extraction_version`, `model_version` fields** to the report payload. This is trivial to add and critical for auditability. ✅ **Partly done (this session)** — added `computed_at` (UTC ISO) + `report_version` (`"1.0"`, bump on formula change). `extraction_version`/`model_version` not yet wired (the extractor doesn't surface them to `build_report` — needs threading through ingest first).
5. **Score sensitivity analysis.** Run the scorer across all 3 current reports and document the distribution. If all three cluster in the same narrow band, the formula needs recalibration.

### UX Improvements

- **"What would improve my score?" affordance.** The recommendations exist but aren't framed as "do X and your score would rise by ~Y points." This is the single highest-value UX improvement for the Integrity Report.
- **Expandable evidence.** When a flag shows `count: 47` but only 5 snippets, add an "Expand" affordance that queries the full list (an endpoint already exists to support this via claim filtering).

### AI Enhancements (if applicable)

- **LLM-generated executive summary is already wired** via `synthesize_audit()`. However, the non-LLM fallback just returns the template string from `build_report`. The fallback should be richer — a structured bullet list of the top 3 findings, not a single sentence. ✅ **Done (this session)** — `_key_findings(report, factcheck, scorecard)` builds a structured bullet list (score/grade/risk, top flag, fact-check credibility+coverage, peer-lagging); `synthesize_audit` returns it as `key_findings` always and uses it as the structured-fallback `executive_summary`.

### Differentiation Opportunities

- **Regulatory mapping is the moat.** No competitor auto-maps greenwashing patterns to specific EU/SEC/BRSR clauses. This should be promoted more aggressively in the UI — not buried as a tiny `text-[11px]` line.
- **Temporal integrity trend** (score over time for the same company) is a feature competitors cannot easily replicate without the same ingestion + canonical-unit spine. Building a "report card over years" view from the existing data would be a strong differentiator.

### Product Synergies

- The Integrity Report should **consume** the benchmark scorecard (`benchmark.py`) to contextualize the score: "Your integrity score is 55 (grade C). Among 3 companies in this corpus, this ranks 2nd."
- The fact-check credibility percentage should feed into the integrity score as a positive signal (high external agreement = higher score). Currently the two systems are isolated.

### Edge Cases

- **Zero claims:** Handled (returns `{status: "No Data"}`). Good.
- **All claims are narrative (no metrics):** The score is dominated by `ASPIRATIONAL_HEAVY` and `VAGUE` flags. This is correct but the user needs context — "this report is primarily qualitative; quantitative integrity scoring is not applicable."
- **One very large report swamping peer comparison:** If Shell has 727 claims and Tata Power has 181, any "cross-company" aggregate is volume-biased. Not directly the Integrity Report's problem, but it affects the benchmark data that should feed into it.

### Trust & Reliability Improvements

- **Explain the formula.** The score computation is not described anywhere in the API response or UI. A "How is this calculated?" tooltip or section would dramatically increase trust.
- **Confidence interval on the score.** The score is deterministic given the claims, but the claims themselves have extraction uncertainty. Reporting "55 ± 8 (based on extraction confidence)" would be more honest.

### Scalability Considerations

- Pure function, no I/O — scales trivially. No concerns.
- The `_fetch_doc_claims` helper makes a Supabase query per report; if this is called frequently, add a lightweight cache (30–60s TTL). The data barely changes.

### Technical Debt to Avoid

- **Don't hardcode the penalty table.** Move it to a config file or environment variable so it can be tuned without code changes.
- **Don't add more flag types without a severity calibration pass.** Each new flag type shifts the score range; adding them ad-hoc will create inconsistency.

### Risks Introduced by These Changes

- Changing the scoring formula will change existing scores. Any published or demoed scores become stale. This is manageable if the report carries a version field (recommendation above).

### Priority: High
### Estimated Impact: High
### Estimated Implementation Effort: Medium (scoring formula + decomposition: 1–2 days; sector normalization: 3–5 days)

---

## Feature Reviewed: External Fact-Check Engine

### Current Purpose

Move verification beyond "report vs itself" to "claim vs ground truth." Each metric claim is checked against an external evidence corpus (reference figures from CDP/filings) and cross-report self-consistency, yielding SUPPORTED / CONTRADICTED / UNVERIFIED verdicts.

### Current Strengths

- **Three-verdict model is clean and intuitive.** Users immediately understand Supported/Contradicted/Unverified.
- **Canonical-unit comparison** means 1.2 ktCO₂e correctly matches 1200 tCO₂e. This is quietly excellent engineering.
- **Pluggable corpus design.** The JSON file can be swapped without code changes. The evidence schema is simple and extensible.
- **Cross-report self-consistency** is a genuinely novel feature. Comparing a company's 2022 report against its 2023 report catches self-contradictions that external data alone would miss.

### Hidden Weaknesses

1. **The evidence corpus is effectively a stub.** 3 records covering only Scope 1 emissions for Shell and Tata Power. The fact-check engine is architecturally sound but operationally starved. For any metric not in `evidence_corpus.json`, the verdict is always UNVERIFIED — which looks like "we can't check anything" to the user.
2. **Credibility = SUPPORTED / checked.** If 10/10 checked claims are all Scope 1 (same metric), the credibility reads 100% but only covers one dimension. The metric is misleading — it measures "consistency of what we *could* check" not "how credible is this report."
3. **No weighting by materiality.** A SUPPORTED claim about tree planting and a SUPPORTED claim about total emissions count equally toward credibility. Emissions are vastly more material.
4. **Cross-report matching requires `company_id` equality.** If company_id varies across reports (e.g., "tata_power" vs "tata_power_company"), no cross-checking occurs. There's no fuzzy matching or company alias resolution.
5. **No temporal proximity logic.** A claim about 2024 emissions is checked against a 2024 reference figure — but what if the reference is from a filing dated January 2024 and the claim is from a report dated December 2024? The year match is coarse.

### User Pain Points

- **Most claims will show UNVERIFIED** because the corpus is thin. This creates a "dead feature" impression — the engine works perfectly, but the fuel tank is empty.
- **No explanation of *why* a claim is unverified.** "No comparable evidence" is honest but not helpful. "No CDP Scope 3 data available for Tata Power 2024" would be much more useful.

### Missing Considerations

- **Evidence freshness / staleness.** The corpus has no `last_updated` field. A reference figure from 2019 used to check a 2024 claim is technically a match but practically stale. ⚠️ **Investigated, N/A as stated (this session)** — started adding a `stale` flag, but a smoke test showed `find_evidence` matches on **exact year** (`str(e.year) == claim_year`), so evidence year *always* equals the claim year — no staleness gap can arise and the flag would be dead code (always False). Reverted it. Becomes real only if matching is loosened to a year window; deferred until then.
- **Evidence sourcing automation.** The corpus is manually maintained. There's no pipeline to pull CDP, GRI, or public filings into it. This is the bottleneck that will determine whether the feature is real or decorative.

### Improvement Opportunities

1. **Weighted credibility.** `credibility = Σ(weight_i × supported_i) / Σ(weight_i)` where weight is proportional to materiality (emissions > governance > social sentiment). Even a simple 3-tier weighting (critical/important/informational) would be a meaningful improvement. ✅ **Done (this session, additive)** — `fact_check_document` adds `weighted_credibility` (emissions 3 / energy·water·waste·biodiversity 2 / governance 1.5 / else 1) and each verdict carries its `materiality`. Plain `credibility` is **unchanged** (both reported, so nothing silently shifts).
2. **Enriched UNVERIFIED explanations.** When a claim has no evidence, explain what *would* be needed: "No external reference for `water.consumption.volume` at year 2024 for tata_power. Add a CDP Water Security response or official annual report figure." ✅ **Done (this session)** — `check_claim`'s UNVERIFIED branch now names the metric/year/company and the remedy ("Add a CDP/official-filing figure or a prior-year report value in the same unit"), and distinguishes the *incomparable-unit* case ("evidence exists but in an incomparable unit").
3. **Coverage metric alongside credibility.** Report `checked / total_checkable` as a separate metric. A report with 80% credibility but only 5% coverage is not the same as one with 80% credibility and 60% coverage. ✅ **Done (this session)** — `fact_check_document` returns `checkable` + `coverage` (`checked/checkable`), independent of `credibility`. Test pins coverage 0.5 with credibility 1.0.
4. **Automate corpus ingestion.** A script that fetches CDP responses, BRSR filings, or official sustainability data sheets and writes them into the corpus schema would transform this from a demo to a product.

### AI Enhancements (if applicable)

- The `llm_verdict()` function exists but is **never called** in the fact-check pipeline. Wiring it for narrative claims (where numeric comparison doesn't apply) would increase coverage significantly. However, this needs careful prompting to avoid hallucinated verdicts.

  > **✅ Resolved 2026-06-25 (this session) — wired with grounding guards.** `llm_verdict` now has three guards against fabricated verdicts: (1) **no evidence ⇒ no LLM call** (returns UNVERIFIED, `engine="guard"` — nothing to ground a judgement); (2) a **confident verdict with no rationale is downgraded** to UNVERIFIED (ungrounded); (3) confidence is **clamped to [0,1]**; the prompt also says "use ONLY the evidence" and "answer UNVERIFIED if the evidence doesn't address the claim." It is wired into `fact_check_document(..., llm=...)` as an **opt-in fallback** that fires *only* on claims the numeric pass left UNVERIFIED but which have evidence (e.g. incomparable units) — it **never overrides a deterministic numeric verdict**, and `llm=None` (the default) leaves behaviour unchanged. The API routes pass the LLM only when one is configured (`_optional_llm()`), and the response carries an `llm_assisted` count. Locked by `backend/tests/test_fact_check_llm.py` (8 tests, fake LLM — guards, clamp, malformed JSON, fallback fires/does-not-override). *Honest scope note: this recovers "evidenced-but-numerically-incomparable" metric claims; pure narrative claims still rarely get evidence because `find_evidence` keys on metric_key+year, so coverage gain is real but bounded by corpus shape, not by the LLM.*

### Differentiation Opportunities

- **Cited verdicts are rare in ESG tooling.** Most competitors say "this claim is suspicious" without citing counter-evidence. ESGenuine's "diverges by 14% from CDP filing" with a source URL is a strong trust signal. Make the citation more prominent in the UI.
- **Cross-report self-consistency** is not offered by any ESG rating agency. It catches the common pattern of "our 2022 report said X, our 2023 report said Y about the same year." This should be named and marketed as a distinct capability.

### Product Synergies

- **Fact-check credibility should feed the Integrity Score.** A report with 90% external consistency should score higher than one with 20%. Currently isolated.
- **The evidence corpus should be shared with the agentic auditor.** When a user asks "What were Shell's Scope 1 emissions in 2022?", the agent should cite the evidence corpus alongside the claim data.

### Edge Cases

- **Company with only one report:** Cross-report self-consistency returns nothing (no other report to compare against). The user sees only external checks. This is correct but should be communicated.
- **Metric key mismatch across years:** If the 2022 report used `emissions.scope1.tonnes` and the 2023 report uses `emissions.scope1.co2e`, no cross-check occurs even though they measure the same thing. The canonical unit layer handles unit conversion but not key aliasing.

### Trust & Reliability Improvements

- **Surface evidence source quality.** "Reference figure (illustrative sample)" is currently the source string. When real data is added, distinguish "CDP verified filing" from "self-reported in another document" from "illustrative placeholder." The trust hierarchy matters.

### Scalability Considerations

- The engine is O(n × m) where n = doc claims and m = evidence records. With a thin corpus this is fine; with 10,000 evidence records, consider indexing by (company_id, metric_key, year) for O(1) lookup instead of linear scan.

### Technical Debt to Avoid

- **Don't ship the illustrative corpus to production.** The 3 placeholder records should be clearly marked as dev-only or replaced before any demo. A user seeing "Reference figure (illustrative sample)" will lose trust.

### Risks Introduced by These Changes

- Automating corpus ingestion introduces a data quality dependency. Bad reference figures will generate false CONTRADICTED verdicts, which is worse than UNVERIFIED. Any automation needs a human review gate.

### Priority: High
### Estimated Impact: High (but dependent on corpus quality)
### Estimated Implementation Effort: Medium (weighted credibility + coverage: 1 day; corpus automation: 1–2 weeks)

---

## Feature Reviewed: Peer Benchmarking & Trajectory

### Current Purpose

Cross-company comparison on shared metrics (ranked, percentiled) and per-company time-series trajectories with trend direction and gap-to-target analysis.

### Current Strengths

- **Polarity-aware.** The system knows emissions are "lower is better" and renewables are "higher is better." Rankings flip accordingly. This is not trivial and most quick implementations get it wrong.
- **Canonical-unit comparison.** Compares ktCO₂e vs tCO₂e correctly. Modal-unit selection ensures no cross-unit averaging.
- **Gap-to-target analysis** is a real value-add. "At current CAGR, you will miss your 2030 target by X" is actionable intelligence.
- **Median as the central tendency** (not mean) is robust to outliers — correct for small peer sets.

### Hidden Weaknesses

1. **With only 3 companies, percentiles are meaningless.** Percentile 0, 50, or 100 — there's no middle ground. The "leading/mid-pack/lagging" verdict is a coin flip with 3 data points. This isn't a code problem; it's a data-depth problem that the UI should acknowledge.
2. **No sector grouping.** Shell (energy) and Tata Power (power) are compared on emissions as though they're peers. In reality, their emission profiles are fundamentally different. The benchmark is technically correct but analytically misleading without sector context.
3. **Trajectory requires ≥2 data points.** A company with only one report year gets no trend analysis. This is correct mathematically but means most new users see "no trajectory data" — a cold-start problem.
4. **CAGR is linear.** `cagr_per_year = (last - first) / span`. This is a linear rate of change, not a compound annual growth rate. The variable name is misleading; actual CAGR would be `(last/first)^(1/span) - 1`.
5. **No confidence or sample-size indicator.** A benchmark based on 3 claims per company looks identical to one based on 300. The user can't distinguish signal from noise.

### User Pain Points

- **The metric keys are raw and technical.** `social.workforce.total.count` is shown verbatim in the UI. Users want "Total Workforce" not a dot-separated internal key.

> **✅ Resolved 2026-06-25 — human-readable metric labels.** New `frontend/src/lib/metricLabels.ts` maps a canonical key (`{aspect_node}.{dimension}`) to an analyst-facing label: it strips the trailing dimension, looks the node up in a curated table mirroring `ontology.py`'s taxonomy, falls back to a generic humanizer for unknown keys, and appends a dimension qualifier only where it disambiguates. Examples: `social.workforce.total.count` → "Total Workforce", `emissions.scope1.co2e` → "Scope 1 Emissions (CO₂e)", `social.diversity.gender.percent` → "Gender Diversity (%)". Applied at every render site that previously showed a raw key (raw key kept in a `title=` tooltip / JSON exports): IntegrityAudit scorecard + fact-check verdicts, ClaimIntelligence, EvidenceAnalysis, SystemTransparency aspect breakdown, AuditTrail, ClaimGraph tooltip (via ClaimExplorer), and the MetricTimeline series labels (which were previously showing just the dimension, e.g. "count").
- **No visual trajectory chart.** The data is returned as a JSON array; the UI renders it as a flat list. A sparkline or line chart would transform understanding.

### Missing Considerations

- **Sector-specific benchmarks.** Energy companies should be benchmarked against energy peers, not all companies. Add a sector/industry field to claims metadata and filter accordingly.
- **Benchmark confidence threshold.** With < 3 companies, benchmarks should be withheld or clearly labeled "insufficient peer data."

### Improvement Opportunities

1. **Human-readable metric labels.** Maintain a mapping `metric_key → {label, unit_label, description}`. `emissions.scope1.co2e` → "Scope 1 Emissions (CO₂e)". This is a small effort with outsized UX impact.
2. **Fix the CAGR calculation** to be actual CAGR, not linear average. This affects gap-to-target accuracy.
3. **Surface peer count + add a confidence signal.** *(Correction: per-metric peer count already exists in the API as the `of` field — `cross_company` sets it to `n`. The real gaps are (a) the **UI doesn't display** the denominator, and (b) there's no top-level `confidence`/`peer_count` summarising data depth.)* Let the UI gray out or caveat metrics with `of` < 3. ✅ **Done (this session)** — `cross_company` returns `confidence: "low"|"ok"` (n<3), `company_scorecard` adds per-metric `low_confidence` + top-level `low_confidence_metrics`. UI display of `of`/gray-out is the remaining (frontend) piece.
4. **Sector-filtered benchmarks.** Add a `sector` field and filter `cross_company()` to same-sector peers when available, falling back to all-company when the sector pool is too small.

### UX Improvements

- **Trajectory sparklines.** A simple SVG sparkline inline with each metric in the scorecard would make trends instantly visible.
- **"Compared with N peers" label.** Show how many companies contributed to each percentile. "Rank 2 of 3" is honest; hiding the denominator is not.

### AI Enhancements (if applicable)

- Not applicable at this stage. The benchmark is purely numeric and doesn't benefit from LLM processing.

### Differentiation Opportunities

- **Target-gap tracking is rare.** Most ESG tools show snapshots, not "are you on track for your 2030 pledge?" This is a strong story for investor-facing use cases.
- **Canonical-unit peer comparison** across reports that use different units is a real technical strength (not a "moat" — it's replicable, just non-trivial). It's only as good as the canonicalizer's coverage, which is currently partial (CO₂e/mass/energy/volume/area; verbose and compound units still pass through).

### Product Synergies

- **Benchmark data should enrich the Integrity Report.** "Your emissions rank 3rd of 3 companies (lagging)" should appear alongside the integrity score. Currently these are separate API calls with no cross-reference.
- **Trajectory data could enhance the fact-check engine.** If a company's trajectory shows a 50% emissions drop in one year, flag it as implausible (or celebrate it as remarkable). The data exists; the connection doesn't.

### Edge Cases

- **Same metric_key, different canonical units (after canonicalization).** Example: an intensity metric (tCO₂e/MWh) vs an absolute metric (tCO₂e). The code drops incomparable units via modal-unit filtering (`incomparable_dropped`), which is correct. But the user gets no explanation of why some companies were dropped.
- **Zero values.** A company reporting zero emissions on a metric (legitimate for some narrow scopes) would break the CAGR calculation (division by zero). Currently handled? Partially — `if first["value"]` guards against it but `0.0` is falsy in Python, so a legitimate zero would suppress the CAGR.

### Trust & Reliability Improvements

- **Show the methodology.** "Percentile calculated across N companies using the most recent report year. Values canonicalized to [unit]. Polarity: lower is better." A tooltip or methodology page would prevent misinterpretation.

### Scalability Considerations

- `_fetch_all_claims()` paginates through the entire claims table for every benchmark request. With 10,000+ claims this is O(n) per request. Consider materialized views or a dedicated benchmark table that's recomputed on ingest, not on read.

### Technical Debt to Avoid

- **Don't add sector filtering by hardcoding sector lists.** Make it data-driven from a `companies` or `reports` metadata table.
- **Don't let the linear "CAGR" propagate.** Fix it now before any reporting or publication references the number.

### Risks Introduced by These Changes

- Adding sector filtering with a small dataset (3 companies) could result in sectors with only 1 company, making benchmarks meaningless. Gate on minimum peer count.

### Priority: Medium
### Estimated Impact: High (particularly metric labels + CAGR fix)
### Estimated Implementation Effort: Low–Medium (labels: 2–4h; CAGR fix: 1h; sector filter: 1–2 days)

---

## Feature Reviewed: Agentic Auditor ("Ask the Auditor")

### Current Purpose

Natural-language Q&A over the claim corpus with page-cited answers (RAG via `search_claims` RPC + LLM synthesis), plus an executive summary that fuses the Integrity Report, fact-check, and benchmark into one narrative.

### Current Strengths

- **Citations with company/year/page.** Every answer traces back to a specific claim, a specific page in a specific report. This is table-stakes for trust in an audit context and it's done well.
- **Graceful degradation.** If no LLM key is available, the system returns raw evidence instead of failing. This is excellent resilience design.
- **Executive summary fusion** (`synthesize_audit`) combines three analysis modules into one narrative. The concept is strong — a one-call "give me the full picture" endpoint.

### Hidden Weaknesses

1. **No conversation memory.** Each `ask()` call is stateless. "What about their Scope 3?" has no idea what "their" refers to. The conversational framing in the UI implies statefulness that doesn't exist.
2. **k=8 is hardcoded as the retrieval window.** For broad questions ("summarize all environmental claims") 8 results is insufficient. For narrow questions ("what is the LTIFR for 2023?") 8 is overkill. There's no adaptive retrieval.
3. **The LLM prompt requests JSON output but has no structured output enforcement.** If the LLM returns malformed JSON (which happens ~5% of the time with 8B models), the entire answer fails. The error message ("LLM error: …") is unhelpful.
4. **No answer quality signal.** There's no way for the user to know if the answer is high-confidence or scraped from marginal evidence. The similarity scores exist in citations but aren't surfaced as an overall confidence.
5. **The executive summary is expensive.** It calls `_fetch_all_claims()` (paginated full-table scan) + `fact_check_document()` + `build_report()` + `company_scorecard()` synchronously. For a large corpus this could take 10+ seconds.

### User Pain Points

- **No suggested questions.** A new user staring at "Ask the Auditor" has no idea what to type. Suggested prompts ("What emissions targets has this company set?", "Are there any contradictions in the social data?") would dramatically improve engagement.
- **Chat history is client-only.** Refresh the page and all Q&A is lost. If this is a real audit tool, the conversation should persist.

### Missing Considerations

- **Answer grounding verification.** The LLM is told to use "ONLY the numbered EVIDENCE claims" — but there's no post-hoc check that it actually did. The model can hallucinate outside the evidence window and the system has no guardrail.
- **Multi-document questions.** "How do Shell and Tata Power compare on emissions?" requires cross-document retrieval. The current `doc_id` filter scopes to one document. Omitting `doc_id` searches globally, but the UI hardcodes a doc selector.

### Improvement Opportunities

1. **Suggested questions based on the selected report.** Analyze the report's flags and surface 3–5 relevant questions: "This report has 6 VAGUE flags — ask: 'Which environmental claims lack measurable metrics?'" ✅ **Done (this session)** — pure `agent.suggest_questions(report)` derives questions from flags + stats (vague/contradiction/aspirational/metric-pct), deduped & capped; exposed at `GET /audit/{doc_id}/suggested-questions` (no LLM).
2. **Structured output parsing with fallback.** Use a regex extractor to pull JSON from the LLM response even when it's wrapped in markdown fences or preamble. This is a common pattern that would eliminate ~80% of parse failures. ✅ **Done (this session)** — new `json_utils.loads_lenient` (strip ```fences```, else extract outermost `{…}`; raises so callers keep their fallback). Wired into `agent.ask`, `agent.synthesize_audit`, and `fact_check.llm_verdict`. 5 tests.
3. **Streaming answers.** For longer synthesis, stream the LLM response to the UI via SSE. The current fetch-and-wait pattern leaves the user staring at a spinner.
4. **Conversation context.** Maintain the last 3–5 Q&A pairs in the prompt as context. This is simple to implement (prepend to the prompt) and would make follow-up questions work.

### UX Improvements

- **Show similarity scores as a "relevance" indicator** next to each citation. A claim with 0.95 similarity is much more relevant than one with 0.75.
- **Allow clicking a citation to jump to that claim in the Claim Explorer.** The data (claim_id, doc_id) is already in the response.

### Differentiation Opportunities

- **Cited, auditable AI answers** are rare in ESG tools. Most either don't use AI or use it without citations. The citation model is a genuine trust differentiator.
- **Fused executive summary** (integrity + fact-check + benchmark in one narrative) is a strong, demo-able concept. *(Correction: dropped the "even expensive ESG rating agencies don't automate this" line — that's an unverifiable competitive claim. Pitch the capability on its own merits, not on assumptions about competitors.)*

### Product Synergies

- The auditor should be able to reference **fact-check verdicts** in its answers. "Shell's Scope 1 emissions claim is CONTRADICTED by CDP data [1]" — connecting the Q&A to the fact-check engine.
- The executive summary should link to the Integrity Report page. "See the full integrity report →"

### Edge Cases

- **Adversarial/off-topic questions.** "What is the weather today?" — the LLM will try to answer using ESG claims as context. Need a scope guard or graceful "I can only answer questions about ESG claims" response. ✅ **Soft signal added (this session)** — `ask` returns `top_similarity` + `low_relevance` (best match < 0.25) so the UI can caveat off-topic answers. Chose a soft flag over a hard refusal to avoid suppressing valid-but-low-similarity questions.
- **Empty retrieval.** If `search_claims` returns nothing (no relevant claims), the answer is "No relevant claims found" — correct, but the user might be asking a valid question with slightly different terminology.

### Trust & Reliability Improvements

- **Post-generation citation verification.** After the LLM generates an answer citing [1], [3], [5], verify that those citations exist and are semantically relevant. Flag hallucinated citations. ✅ **Done (existence check, this session)** — `ask` returns `unsupported_citations`: any `[n]` in the model's `used` list not present in the evidence set. (Semantic-relevance check still TODO.)

### Scalability Considerations

- The `synthesize_audit` endpoint does 4 cascading Supabase queries + LLM call synchronously. This will be the slowest endpoint in the system. Consider caching the report/factcheck/scorecard components (they change only on ingest, not on read).

### Technical Debt to Avoid

- **Don't build full conversation history on the server.** Keep Q&A stateless with client-side context injection. Server-side conversation state adds complexity without proportional value at this stage.

### Risks Introduced by These Changes

- Adding conversation context to the prompt increases token usage per call. Monitor cost.
- Suggested questions based on report analysis could themselves be misleading if the analysis has errors. Keep suggestions generic until the analysis is well-calibrated.

### Priority: Medium
### Estimated Impact: High (suggested questions + structured parsing fix: immediate user engagement improvement)
### Estimated Implementation Effort: Low–Medium (suggested questions: 2–4h; context injection: 1 day; structured parsing fix: 2h)

---

## Feature Reviewed: Verification Method Router (Frontend)

### Current Purpose

Correctly classify claims by *how* they can be verified: satellite imagery (optical environmental claims), data cross-check (metric claims), or document review (narrative claims). Prevents the UI from implying satellite verification for non-verifiable claims (emissions, governance, financial).

### Current Strengths

- **Intellectually honest.** This is one of the most important design decisions in the product. It prevents the product from claiming it can verify emissions via satellite imagery — a claim that would immediately discredit the platform with any expert audience.
- **Clean implementation.** A simple keyword-match function with a clear hierarchy. Easy to extend.

### Hidden Weaknesses

1. **Keyword matching is brittle.** A claim about "solar panel manufacturing efficiency" would match `solar` and be routed to imagery verification — but manufacturing efficiency is not optically observable.
2. **The OPTICAL list is English-only.** Internationalized claims (even in English reports, Hindi/local-language terms appear) will fall through to the wrong category.
3. **No "satellite + data" combination.** Some claims could benefit from both — e.g., "We planted 10,000 trees across 500 hectares." The area is satellite-verifiable, the count is a data claim. The router picks one.

### Improvement Opportunities

1. **Context-aware routing.** Instead of matching on the metric key alone, consider the full claim: aspect + metric_unit + claim_type. A "solar" claim with unit "USD" is financial, not optical.
2. **Surface the verification method in the Integrity Report**, not just the Fact-Check detail. "12 of your claims are imagery-verifiable, 45 are data-checkable, 120 require document review" is a useful disclosure profile. ✅ **Done (this session)** — `build_report` → `statistics.verification_profile` = `{imagery, data_crosscheck, document_review}` counts, using a backend `_verification_method` that **mirrors** the frontend `verificationMethod()` observability→method mapping (kept in sync).

### UX Improvements

- **Color-code by verification method consistently.** Currently the badge is `outline` with a tiny icon. Make imagery=green, data=blue, document=gray for faster scanning.

### Priority: Low
### Estimated Impact: Medium
### Estimated Implementation Effort: Low (context-aware routing: 1 day)

---

## Feature Reviewed: Frontend Navigation & Information Architecture

### Current Purpose

The sidebar navigates across 9 pages: Live Dashboard, Claim Explorer, Evidence Analysis, Audit Trail, Portfolio Overview, Integrity Audit, System Transparency, Submit Report, Settings.

### Current Strengths

- **Rich, animated sidebar** with collapse, tooltips, active indicators. Feels premium.
- **Logical grouping** from monitoring (Dashboard → Claims → Evidence → Audit Trail) to analysis (Portfolio → Integrity Audit) to admin (Transparency → Submit → Settings).
- **Consistent AppLayout wrapper** shared across pages.

### Hidden Weaknesses

1. **Nine top-level pages is a lot for a product with 3 reports.** The navigation implies breadth that the data doesn't yet support. This creates a "hollow product" impression when users click through and find thin data.
2. **The relationship between pages is unclear.** How does "Evidence Analysis" differ from "Claim Explorer"? How does "Audit Trail" relate to "Integrity Audit"? The names overlap in mental model.
3. **No primary action hierarchy.** The sidebar treats all pages equally. But the product's value chain has a clear flow: Submit Report → (processing) → Integrity Audit → Claim Explorer → Portfolio. This flow isn't guided.
4. **The "Live Dashboard" (Index page) is the most visually impressive but least functionally useful page.** The 3D Globe is a showpiece but the DashboardCards and ClaimIntelligence panels are not connected to the real analysis engines (Integrity Report, Fact-Check, Benchmark). Users land on spectacle, not substance.

### User Pain Points

- **Where do I start?** A first-time user with no reports sees an impressive but empty dashboard. There's no onboarding flow — "Upload your first ESG report to get started."
- **Page names use internal vocabulary.** "Evidence Analysis" is analyst jargon. "System Transparency" means nothing to a business user. Plain language ("How We Verify", "Upload & Analyze") would reduce cognitive load.

### Missing Considerations

- **Progressive disclosure.** Hide pages that have no data (e.g., don't show "Integrity Audit" until at least one report has been ingested and analyzed). Show them as locked/coming-soon with a "Submit a report to unlock" CTA.
- **Contextual navigation.** From the Integrity Report, clicking a greenwashing flag should deep-link to the relevant claims in Claim Explorer, pre-filtered. Currently pages are disconnected silos.

### Improvement Opportunities

1. **Consolidate or rename.** Consider merging "Evidence Analysis" and "Claim Explorer" — or at minimum, rename to make the distinction clear: "All Claims" vs "Claim Details."
2. **Add a guided flow.** "Upload → Analyze → Review → Benchmark" as a wizard or progress bar for new users. Power users still have full sidebar access.
3. **Make the Dashboard substantive.** Replace or augment the Globe with a "Portfolio health at a glance" card that shows the Integrity Score, top 3 flags, and fact-check credibility for the most recent report. The data is available via existing APIs.
4. **Deep-link between pages.** From Integrity Audit → click a flag → jump to Claim Explorer filtered to that flag type. From Portfolio → click a company → jump to Integrity Audit for that company's report.

### Differentiation Opportunities

- **Guided audit workflow** (Upload → Analyze → Review → Report) is something that differentiates a product from a dashboard. Dashboards show data; products guide action.

### Priority: Medium
### Estimated Impact: High (onboarding + deep-linking = retention)
### Estimated Implementation Effort: Medium (deep-links: 1–2 days; guided flow: 3–5 days; page consolidation: 2–3 days)

---

## Feature Reviewed: NLI Contradiction Engine

### Current Purpose

Detect contradictions between ESG claims using (1) strict numeric rules (metric-key-gated, canonical-unit-aware, zero-baseline-guarded) and (2) DistilBERT-MNLI textual entailment.

### Current Strengths

- **The numeric reasoning is genuinely robust.** Metric-key gating, canonical unit comparison, zero-baseline guards, magnitude-outlier rejection, and real-time-bucket requirements. This is not a naive diff — it's a carefully layered set of guards that reflect real-world data quality issues.
- **Tiered severity model** (Hard > Metric > Temporal > Scope) correctly prioritizes the most damning contradictions.
- **Validated** via inline `__main__` checks and ad-hoc live-corpus scans (47 → 39 contradictions after the magnitude-outlier guard). *(Correction: there is no formal pytest suite yet — "extensively tested" would overstate it; the numeric gates are spot-checked, not regression-locked.)*

### Hidden Weaknesses

1. **The textual NLI path is architecturally broken.** `_textual_entailment` formats input as `f"{text_a} </s></body> {text_b}"` — a single-string submission to a model expecting premise/hypothesis pair input. DistilBERT-MNLI's `text-classification` pipeline treats this as single-sequence classification, not NLI pair classification. The contradiction labels from this path are **unreliable** (the `take_step_forward.md` audit explicitly flags this as §3.3). Every "Textual" contradiction is suspect.
2. **The NLI model runs on every pair** even when numeric comparison already decided. This wastes compute. The `evaluate_pair` method runs both paths and only uses NLI as a fallback, but the compute cost is paid unconditionally.
3. **No deduplication of contradictions.** If claim A contradicts claim B, and claim B contradicts claim A, two contradictions are reported. The `evaluate_pair` is symmetric but the caller iterates directed pairs from retrieval.
4. **The engine loads on import.** `engine = ContradictionEngine()` at module scope in `api_reasoning.py` loads the DistilBERT-MNLI model at server startup. *(Correction: figures were overstated — DistilBERT-base is ~265 MB on disk, roughly 250–350 MB resident, and cold-start cost is dominated by importing torch/transformers, not the weights. The point stands — it loads eagerly even if contradictions are never requested — but quantify before optimizing.)*

### Improvement Opportunities

1. **Fix the NLI pairing.** Use `pipeline("zero-shot-classification")` or `CrossEncoder("cross-encoder/nli-deberta-v3-base")` with proper premise/hypothesis pairs. This is the single most impactful reasoning fix.
2. **Lazy-load the NLI model.** Only load when the first contradiction request arrives. Use a module-level singleton pattern with a lock.
3. **Short-circuit NLI when numeric conflict is found.** If the numeric rules already found a conflict, skip the expensive NLI inference.
4. **Deduplicate.** Sort claim pairs by ID and only evaluate (min_id, max_id) pairs.

> **✅ Resolved 2026-06-25 (across sessions): #1, #2, #3.** **#1 pairing** fixed in `bbc1a54` (real `{"text","text_pair"}` pair). **#3 short-circuit** also in `bbc1a54` — `evaluate_pair` skips NLI when a numeric rule fires. **#2 lazy-load** done this session: the DistilBERT pipeline (and even the `transformers` import) now load on first textual comparison via an `nli_model` property, not in `__init__` — verified `ContradictionEngine()` builds in ~0.02s with `_nli_model is None`, and the numeric path never triggers a load. This unblocked the **contradiction-path regression suite** (`backend/tests/test_nli_engine.py`, 13 tests: Hard/Metric/Temporal/Scope rules, canonical-unit no-false-positive, incomparable-unit + mislabel + zero-baseline + extreme-YoY gating, the evaluate_pair short-circuit, and the textual branch via an injected fake model — no torch needed). **#4 dedup** ✅ done this session: the `get_contradictions` endpoint previously iterated *directed* pairs with no dedup, so within one document both (A,B) and (B,A) were reported and severity-counted twice (the batch script `run_nli_batch.py` already deduped; the endpoint did not). The per-document loop was extracted into a pure, I/O-injected `contradiction_scan.scan_contradictions(doc_claims, retrieve_fn, engine_obj)` that dedups unordered claim-id pairs (`frozenset`), skips self-pairs, and leaves cross-report matches (which appear once anyway) intact. Locked by `backend/tests/test_contradiction_scan.py` (6 tests, fake engine + fake retrieval — symmetric-pair-once, self-pair-skip, cross-report, numeric-vs-textual confidence, missing-id, empty).

### Trust & Reliability Improvements

- **Label NLI-sourced contradictions differently from numeric-sourced ones.** The numeric path is high-confidence; the textual path is low-confidence. Users should see this distinction.
- **Confidence calibration.** The NLI confidence score is the raw model logit, not a calibrated probability. Report it as "model confidence" not "confidence."

### Priority: High (the NLI fix is a correctness issue, not just an improvement)
### Estimated Impact: Very High
### Estimated Implementation Effort: Medium (NLI fix: 1–2 days; lazy loading: 2h; dedup: 1h)

---

## Feature Reviewed: Production Ingest Pipeline (`/v1/reports/ingest`)

### Current Purpose

Upload an ESG PDF → parse → extract claims → embed → write to Supabase. The endpoint that actually populates the dashboard.

### Current Strengths

- **Background task execution.** Uses FastAPI's `BackgroundTasks` so the upload returns immediately with a job_id.
- **Job status polling** via `GET /v1/jobs/{job_id}`.
- **Metadata-driven.** Company name and year are explicit form fields, not inferred from filenames (fixing issue #6 structurally).
- **Calls through real modules** — not a separate script or manual process.

### Hidden Weaknesses

1. **In-memory job tracking.** `ingest_jobs` is a dict in the server process. Server restart loses all job state. Two workers would have independent job registries.
2. **No progress granularity.** Status goes from "queued" → "parsing" → "extracting" → "ingesting" → "done." The user can't see "extracting claim 47 of 181" or an ETA.
3. **No retry or idempotency.** If the server crashes mid-ingest, the job is lost. Re-submitting the same PDF creates duplicate claims in Supabase (no upsert or dedup guard).
4. **No file deduplication.** Uploading the same PDF twice creates two jobs, two sets of claims, two report entries. There's no content-hash check to say "this report is already ingested."
5. **Synchronous pipeline inside the background task.** The background task itself is CPU-bound (PDF parsing, LLM calls, embedding). In a single-worker uvicorn, this blocks the event loop. With `--workers 2`, it's better but still fragile.

### Improvement Opportunities

1. **Persist job state to Supabase.** A `jobs` table with job_id, status, stage, timestamps, error. Survives restarts, visible to multiple workers.
2. **Content-hash dedup.** Hash the uploaded PDF. Before starting a new job, check if that hash has already been processed. Return the existing report_id if so.
3. **Idempotent ingest.** Use `ON CONFLICT (claim_id) DO UPDATE` or a composite unique key in Supabase to prevent duplicate claims on re-ingest.
4. **Progress events.** Add a `progress` field to the job (e.g., `{stage: "extracting", current: 47, total: 181}`). The frontend can poll and show a progress bar.

### Priority: High
### Estimated Impact: High (dedup + idempotency prevent data corruption; job persistence prevents data loss)
### Estimated Implementation Effort: Medium (job persistence: 1 day; dedup: 1 day; idempotent ingest: 1 day)

---

## Cross-Cutting Observations (Product-Level)

### The "Two Products" Problem

ESGenuine currently has **two disconnected experiences:**

1. **The original Lovable-era frontend** (Index/Dashboard, Claim Explorer, Evidence Analysis, Audit Trail, Portfolio, Submit Report) — reads directly from Supabase, uses the `useClaims` hook, and renders company cards, globe, sidebar.
2. **The new analysis layer** (Integrity Audit page) — reads from the FastAPI backend, uses `lib/api.ts`, and renders integrity scores, fact-check verdicts, benchmarks, and the auditor.

These two systems share data (Supabase) but have **no cross-references, no shared state, and different visual paradigms.** The Portfolio Overview page computes its own `integrityScore` from claim counts (via `useClaims`), while the Integrity Audit page gets a completely different score from the backend's `build_report()`. These numbers will not agree.

**This is the single biggest product integrity risk.** A user who sees a score of 72 on the Portfolio page and 42 on the Integrity Audit page will lose all trust.

**Recommendation:** Either (a) retire the client-side scoring in Portfolio and make it consume the backend Integrity Report API, or (b) clearly label the two as different methodologies. Option (a) is strongly preferred.

### The Evidence Corpus Is the Product's Fuel Tank

The entire fact-check + verification story depends on having reference data to check against. With 3 illustrative records, the engine is architecturally complete but operationally inert. Prioritize corpus expansion over engine refinement — a perfect engine with no data produces no value.

### Naming Matters More Than Expected

"ESGenuine" is a strong brand name. But the internal terminology is inconsistent:
- "Integrity Score" vs "Integrity Report" vs "Integrity Audit" — are these the same thing?
- "Greenwashing Risk" (in Integrity Report) vs "Risk Level" (in Portfolio) — different computations, same word.
- "Evidence Analysis" (a page) vs "External Fact-Check" (a panel) vs "Claim Verdicts" (a card title) — same concept, three names.

Standardize terminology across the product. Create a glossary and enforce it.

### The 3D Globe Is a Liability

The Index page globe is visually stunning but functionally disconnected from the analysis layer. It implies geospatial verification ("click markers to inspect") but no geospatial verification exists. It's the most memorable element in the product and it's decorative. Either connect it to real data (plot company HQ locations from the claims data) or demote it to a subtle background element. As a centerpiece, it sets expectations the product cannot meet.

> **✅ Resolved 2026-06-25 — globe is now company-HQ-centric.** The globe plots **one marker per ingested company at its real headquarters** (curated coordinate registry in `frontend/src/lib/companyHeadquarters.ts`; unknown HQs are skipped, never fabricated). Markers are colored by company risk (low/moderate/high) and sized by claim volume. Clicking a company's HQ surfaces **all of that company's claims** in the right-hand `CompanyPanel` (name, HQ city/country, integrity score, risk, verified/review/gap breakdown, full claim list); clicking a claim drills into `ClaimIntelligence` with a "Back to company claims" affordance. The misleading "click markers to inspect" copy and the "Claim Status" legend were replaced with "click a company HQ to view its claims" and a "Company Risk" legend. This removes the false geospatial-verification implication and makes the centerpiece functional. (Files: `Globe.tsx` rewrite, new `companyHeadquarters.ts` + `CompanyPanel.tsx`, `Index.tsx` wiring, `ClaimIntelligence.tsx` back affordance.)

---

## Open Questions

1. **Who is the primary user?** An ESG analyst at a financial institution? A compliance officer at a reporting company? A regulator? The feature set tries to serve all three. Clarity here would sharpen every UX decision.
2. **Is the product a one-time report auditor or a continuous monitoring tool?** The "Live Dashboard" name implies monitoring, but the ingest pipeline is batch-based. Decide and commit.
3. **Should the product aim for regulatory compliance (EU Taxonomy, CSRD, SEC) or investment analysis (ESG ratings, portfolio screening)?** These are different markets with different expectations.
4. **What is the minimum viable evidence corpus size for the fact-check feature to be credible?** 10 companies × 5 metrics × 3 years = 150 records? This should be quantified and resourced.

---

## Notes

This is the inaugural review entry. Future reviews should narrow focus to 1–2 features and go deeper, rather than covering the full product each time. The patterns identified here — score calibration, corpus depth, naming consistency, the "two products" gap, and NLI correctness — should be treated as recurring themes to track across sessions.

The original review (above) was analysis-only. The correction pass below **did** touch code (one misleading comment) — noted inline.

---

# Correction & Verification Pass — 2026-06-25 (against actual code)

Each load-bearing claim above was checked against the source. Result: the review is **mostly accurate**; a handful of overstatements were corrected inline (search "*(Correction:*"). Summary:

## Verified accurate (kept as-is)
- **NLI input format is wrong** (§"NLI Contradiction Engine" #1). Confirmed: `nli_engine.py:23` builds `f"{text_a} </s></body> {text_b}"` and runs it through a single-string `text-classification` pipeline — not premise/hypothesis. Also independently flagged in [take_step_forward.md §3.3](take_step_forward.md). The "Textual" path is genuinely unreliable. **Highest-priority correctness fix.**
  > **✅ Resolved (commit `bbc1a54`).** `_textual_entailment` now passes `{"text": premise, "text_pair": hypothesis}` so the HF pipeline tokenizes a real NLI pair (premise `[SEP]` hypothesis), with robust label normalization and an empty-text guard. `evaluate_pair` short-circuits NLI when a numeric rule already fired, and numeric conflicts now report `confidence 1.0` instead of the model's meaningless score. Verified against current `nli_engine.py`.
- **Integrity score is flat, not "diminishing"** (Integrity Report #1). Confirmed: `integrity_report.py` looped `score -= _PENALTY[...]` while the comment claimed "diminishing." ✅ **Fixed in this pass** — the comment now states it's a flat per-flag penalty and points here for the count-weighting plan. (Behaviour unchanged on purpose; changing the formula would silently shift demoed scores.)
- **Evidence corpus = 3 real records, Scope-1 only** (Fact-Check #1). Confirmed (`evidence_corpus.json`, `_schema` row filtered out by `load_external_corpus`).
- **`llm_verdict()` defined but never called** (Fact-Check AI). Confirmed.
- **`credibility = SUPPORTED / checked`** and **cross-report requires `company_id` equality.** Confirmed.
- **"CAGR" is linear** `(last-first)/span` and a legitimate `0.0` first value suppresses it (falsy guard). Confirmed.
  > **✅ Resolved 2026-06-25 (this session).** The linear field is renamed `avg_change_per_year` (honest: absolute units/yr) and **remains** the basis for the gap-to-target `on_track` check — that comparison is against `required_per_year`, which is *also* a linear absolute rate, so substituting a compound fraction there would be a dimension error. A genuine compound **`cagr = (last/first)^(1/span) − 1`** is added for display, defined only when both endpoints are positive (else `None`: a CAGR across a zero baseline or a sign change is mathematically meaningless — which also resolves the "legitimate 0.0 suppressed" concern by reporting `None` honestly rather than a fabricated number). Smoke-tested (`benchmark.py:trajectory`); no frontend/backend consumer referenced the old `cagr_per_year` key.
- **Engine loads on import** at module scope. Confirmed.
- **In-memory `ingest_jobs`, no dedup/idempotency.** Confirmed.
- **"Two products" score divergence.** Confirmed: `useClaims.ts` computes Portfolio's `integrityScore` as mean groundability×100, entirely independent of the backend `build_report()` score. They will not agree. This remains the single biggest product-integrity risk.
  > **✅ Resolved (commit `bbc1a54`).** New `GET /reports/portfolio/integrity` computes per-company scores with the **same** `build_report()` the Integrity Audit page uses. `PortfolioOverview` overlays the backend score (tagging `scoreSource: 'backend'`) and falls back to the local groundability mean only when the backend is unreachable (`scoreSource: 'local'`); the misleading "weighted by materiality" tooltip was corrected to state the shared methodology. The `useClaims.ts` mean is now an explicit fallback, not the headline number — so the two pages agree whenever the backend is up.

## Corrected overstatements (changed inline)
- "Extensively tested" → there is **no pytest suite**; gates are spot-checked only. *(Update 2026-06-25: a first suite now exists — `backend/tests/test_unit_canonicalizer.py` — and `pytest` is pinned in `backend/requirements-dev.txt`; verified it collects and passes 7/7 under both pytest and the standalone runner. Coverage is still canonicalizer-only; the reasoning/benchmark modules remain spot-checked.)*
- DistilBERT "~500 MB RAM" → ~250–350 MB resident; cold start is dominated by importing torch/transformers.
- Benchmark "technical moat" → real strength but replicable, and limited by partial canonicalizer coverage.
- "even expensive ESG rating agencies don't automate this" → removed (unverifiable competitor claim).
- "Add `peer_count`" → per-metric peer count already exists as the `of` field; the gap is UI display + a top-level confidence.
- Scope line: marked **pre-push** (the branch was not yet pushed when this was written).

## New findings (not in the original review)
1. **The review predates the #17 re-score — its score numbers are now stale.** This session recalibrated the groundability/vagueness scorer (claim_type-aware) and re-scored all 1435 live rows (groundable ≥0.75: 879 → 368; vagueness ≥0.6: ~0 → 430). Any integrity-score example written above will have shifted. Re-run before quoting numbers.
2. **`observability_type` is computed but thrown away.** `GroundabilityClassifier.score` returns it, but it is **not persisted to the DB** and **not exposed** by the fact-check API. The frontend `verificationMethod()` therefore re-derives routing from a **duplicated** OPTICAL keyword list — two sources of truth that will drift. Fix: persist `observability_type` on ingest and have the FE consume it.

   > **✅ Resolved (commit `bbc1a54`).** Added the `observability_type` column (`schema.sql` + migration `2026-06-25_observability_type.sql`), written on ingest (`supabase_ingest.py`), selected through the fact-check API (`fact_check.py`/`api_reasoning.py`), and consumed by the frontend `verificationMethod(metric_key, hasValue, observability_type)` (`lib/api.ts:101`, used at `IntegrityAudit.tsx:157`). The OPTICAL keyword list is now an explicitly-documented **fallback for legacy rows only** (`api.ts:91-94`), and the existing 1435 rows were backfilled via `scripts/backfill_observability_type.py`. Single source of truth restored.
3. **`audit_summary` silently caps contradictions at 3000 pairs** (`_numeric_contradictions(cap=3000)`). For a large single report this truncates without telling the caller. Surface a `truncated: true` flag.

   > **✅ Resolved 2026-06-25 (this session).** `_numeric_contradictions` now returns `(contradictions, truncated)`; `truncated` is `True` when the pairwise scan hits `cap` and stops early. The `/audit/{doc_id}/summary` response always carries a `contradictions_truncated` boolean (so the frontend can caveat the executive summary instead of treating the contradiction set as exhaustive). The other call site — the portfolio scorecard loop — takes `[0]` (it doesn't need the flag). `py_compile`-checked; both call sites updated. (`api_reasoning.py`.)
4. **`search_claims` does a full scan** (ORDER BY `embedding <=> q` with no ANN/ivfflat index). Fine at ~1.4k rows; add an index before scale.

   > **⚠️ Corrected 2026-06-25 (this session) — the premise was wrong; no migration written.** Re-checked against the actual SQL before acting: `schema.sql:70-81` **already** creates **HNSW** indices (`USING hnsw (embedding vector_cosine_ops)`) on every partition — and HNSW is strictly better than the ivfflat I'd proposed. The `search_claims` RPC orders by `c.embedding <=> query_embedding`, and `<=>` (cosine distance) matches `vector_cosine_ops`, so the operator/index are aligned and per-partition ANN scans are the intended design ("HNSW indices per partition for massive scale"). Adding an ivfflat index would be redundant **and** inferior, so I deliberately did **not** write one. The genuine, narrower follow-ups that remain: (a) confirm with `EXPLAIN ANALYZE` on the live DB that the planner actually uses the per-partition HNSW for the parent-table `ORDER BY … LIMIT` (needs DB access); and (b) the `filter_doc IS NULL OR c.doc_id = filter_doc` predicate can't pre-filter an HNSW scan, so the doc-scoped path may approximate/under-return — splitting it into two query forms would be the real fix if that ever bites. Lesson: this is exactly why "verify before asserting" is in the process note — the original finding asserted "no ANN index" without checking the schema. **Deliverable added this session:** `backend/database/verify_search_claims_index.sql` — a no-op, ready-to-run script (index-existence check + `EXPLAIN (ANALYZE, BUFFERS)` for both the global and doc-scoped query forms, with "what to look for") so the live-DB confirmation is one paste rather than a research task.
5. **Canonicalizer coverage is the quiet ceiling on three features at once** (fact-check, benchmark, contradiction). Verbose/compound units ("tonnes CO2 per year", "gCO2e/MJ", "million hectares") pass through unconverted. Expanding `UnitCanonicalizer._CONV` + the substring parser lifts all three simultaneously — high leverage, low risk.

   > **✅ Partially resolved 2026-06-25.** Re-probed against the actual code first: several of the journal's examples were *already* handled — "tonnes CO2 per year" (cadence strip), "million hectares" (magnitude word), and "gCO2e/MJ" (correctly kept distinct as an intensity, not a gap). The **genuine** remaining gaps — found by probing realistic ESG units — were closed in `_CONV` + the substring fallback: **verbose joules** (gigajoule/terajoule/megajoule/joule → MWh; abbreviations GJ/TJ already worked), **barrels/bbl** (→ m3; directly relevant to the Shell/BP oil & gas reports), **verbose cubic metres**, **gallons**, and **m2/square metres** (→ hectares). These touch only `to_canonical` (read-time value comparison) — **not** `dimension_of`/`generate_metric_key` — so `metric_key`s and partitioning are unchanged and **no re-ingest is needed**. Locked with a new regression suite: `backend/tests/test_unit_canonicalizer.py` (runs under pytest *or* as a plain script; 7 groups incl. cross-unit equivalence, intensity-kept-distinct, cadence-stripped, and the #15 value-plausibility gates) — the first such suite, addressing the recurring "no pytest suite" note. Still open (lower value, deferred): MMT disambiguation, and intensity-unit *comparison* (currently they're correctly isolated, not compared).
6. **`evidence_corpus.json` mixes a `_note`/`_schema` pseudo-record into the data array.** Works (filtered on load) but is a smell; prefer a `{ "_meta": {...}, "records": [...] }` shape.

   > **✅ Resolved 2026-06-25 (this session).** The corpus is now `{ "_meta": { note, record_schema }, "records": [...] }` — metadata is cleanly separated from data, so no pseudo-record is smuggled in. `load_external_corpus` reads `records` from the dict shape, **still accepts the legacy bare-list** (filtering the inline `_schema` row) for forward/backward safety, and defensively drops non-dict / blank-`company_id` rows. Locked by `backend/tests/test_fact_check_corpus.py` (both shapes + malformed/missing file). All routing still goes through `load_external_corpus` (only reader), so no other call site changed.

## Process note
Future entries: keep the "verify against code before asserting" discipline — the original review's few misses were all in *quantification* (RAM, "extensively", competitor claims), not in the structural critiques, which held up well.

---

# Resolution Log — 2026-06-25 (follow-up session)

Re-verified each prior finding against the *current* code before acting (the journal's corrections pass predates commit `bbc1a54`, so several "highest-priority" items were already fixed but never marked). Status after this session — full notes inline at each finding above:

| # | Finding | Status | Where |
|---|---------|--------|-------|
| NLI #1 | Textual entailment ran a single concatenated string, not a premise/hypothesis pair | ✅ Resolved (`bbc1a54`) | `nli_engine.py` |
| Cross-cut | "Two products" — Portfolio score ≠ Integrity Audit score | ✅ Resolved (`bbc1a54`) | `/reports/portfolio/integrity`, `PortfolioOverview.tsx` |
| New #2 | `observability_type` computed but not persisted/exposed; FE duplicated the routing list | ✅ Resolved (`bbc1a54`) | schema + ingest + `api.ts` |
| New #3 | `audit_summary` silently capped contradictions at 3000 pairs | ✅ Resolved (this session) | `api_reasoning.py` |
| Bench #4 | "CAGR" was a linear average and the field name was misleading | ✅ Resolved (this session) | `benchmark.py:trajectory` |
| New #5 | Canonicalizer coverage gaps (joules/barrels/m²/gallons/cubic-metres) | ✅ Resolved (prior session) | `ontology.py` + first pytest suite |
| New #6 | `evidence_corpus.json` smuggled a `_schema` pseudo-record into the data array | ✅ Resolved (this session) | `evidence_corpus.json` + `fact_check.py` |
| NLI #2/#3 | NLI model loaded eagerly on import; NLI run even when numeric decided | ✅ Resolved (lazy-load this session; short-circuit `bbc1a54`) | `nli_engine.py` |
| NLI suite | Contradiction path had no regression tests (blocked by eager model load) | ✅ Resolved (this session) | `tests/test_nli_engine.py` |
| Fact-Check AI | `llm_verdict()` defined but never called | ✅ Resolved (grounding-guarded, opt-in, this session) | `fact_check.py` + `api_reasoning.py` |
| New #4 | "`search_claims` has no ANN index → full scan" | ⚠️ Premise wrong — HNSW per-partition indices already exist; verification script shipped | `schema.sql:70-81`, `verify_search_claims_index.sql` |
| Corr. | "No pytest suite" | ✅ Resolved (this session) | `tests/` (7 suites, 49 tests), `requirements-dev.txt` |
| NLI #4 | Directed contradiction pairs not deduplicated (endpoint double-counted) | ✅ Resolved (this session) | `contradiction_scan.py` + `api_reasoning.py` |
| Route tests | FastAPI route wiring untested (blocked by heavy transitive imports) | ✅ Resolved for `get_contradictions` (stub-and-remove harness) | `tests/test_api_routes.py` |

**Implemented (code changed) — across this follow-up's rounds:**
- `pytest>=8.0` pinned in new `backend/requirements-dev.txt`; **five regression suites** now collect + pass under pytest *and* standalone (**40 tests**): `test_unit_canonicalizer.py` (7), `test_benchmark.py` (8 — ranking, cross-unit comparability, modal-unit dropping, scorecard verdicts, CAGR fix), `test_fact_check_corpus.py` (4 — loader, both corpus shapes), `test_nli_engine.py` (13 — numeric rules + gates + evaluate_pair short-circuit + injected-model textual path), `test_fact_check_llm.py` (8 — grounding guards + opt-in fallback).
- `_numeric_contradictions` → `(contradictions, truncated)`; `/audit/{doc_id}/summary` always returns `contradictions_truncated`. Portfolio scorecard call site updated to `[0]`.
- `benchmark.trajectory`: linear field renamed `avg_change_per_year` (kept as the dimensionally-correct basis for `on_track`); added true compound `cagr` for display (positive-endpoints-only, else `None`).
- `evidence_corpus.json` migrated to `{ "_meta", "records" }`; `load_external_corpus` reads the new shape, still accepts the legacy bare-list, and drops malformed rows.
- **NLI model lazy-loaded** via an `nli_model` property (construction is ~0.02s, no `transformers` import until first textual NLI) — resolves the eager-load weakness and unblocked the contradiction-path suite.
- **`llm_verdict` hardened + wired** as a guarded, opt-in, numeric-authoritative fallback in `fact_check_document(..., llm=...)`; routes pass `_optional_llm()`; response carries `llm_assisted`.
- **Contradiction dedup (NLI #4)** — extracted the `get_contradictions` loop into pure `contradiction_scan.scan_contradictions(...)`, deduping unordered pairs so the endpoint no longer double-counts within a document. Six fast tests cover it.
- **Route-level integration tests** — `backend/tests/test_api_routes.py` drives the real `get_contradictions` route end-to-end (real `scan_contradictions` + real numeric engine; only Supabase + the embedding model faked). Solved the import blocker with a **stub-and-remove** harness: the heavy import-time libs (`sentence_transformers`, `supabase`, `dotenv`, `claim_extractor`) are stubbed in `sys.modules` *only during* `api_reasoning`'s import, then removed so other suites still get the real libraries. Covers dedup-through-the-route, the no-conflict path (fake NLI injected so no real model loads), and the 404. (Now **7 suites, 49 tests**.)
- **`search_claims` verification script** — `backend/database/verify_search_claims_index.sql` (see corrected New #4); the live `EXPLAIN ANALYZE` is now a one-paste step.

**Still open (deferred — needs live infra / content / a heavier tier):**
- **Run** `verify_search_claims_index.sql` on the live DB and act on the plan (only step that needs DB access; script is ready).
- **Evidence-corpus depth** (3 illustrative records) — content/sourcing work; deliberately **not** fabricating reference figures (that would undermine the product's integrity premise).
- **Remaining route coverage** — `test_api_routes.py` proves the harness; extending it to `get_fact_check` / `audit_summary` / the benchmark routes is mechanical follow-on. Also `_numeric_contradictions`'s grouping+cap wrapper is still only compile-checked (its `contradictions_truncated` flag), though its underlying engine is unit-tested.

## Process note (session 2)
Verifying-before-asserting paid off **three** more times this round: (1) three findings flagged "highest-priority / confirmed broken" were already fixed in `bbc1a54`; (2) the CAGR field is *correctly* linear for the target math, so I renamed + augmented rather than naively "fixing" it into a dimension bug; (3) **New #4 was simply wrong** — I was about to write an ivfflat migration when the schema already had superior HNSW indices. Checking the SQL first turned a redundant-and-inferior change into a one-line correction. The pattern holds: read the load-bearing code before writing the fix, especially when the fix is a migration or a "make it match the textbook" rewrite.

---

# Resolution Log — 2026-06-25 (session 3: 5 additive improvements)

Five low-risk, additive improvements (no behaviour change to existing scores/verdicts; all new fields/messages). Each is locked by a fast, dual-mode test. Inline ✅ notes at each finding above.

| Finding | Change | Where |
|---------|--------|-------|
| Integrity Report — score decomposition | `penalty_breakdown` (per-flag points, sorted) | `integrity_report.py` |
| Integrity Report — provenance | `computed_at` + `report_version` (extraction/model version still TODO) | `integrity_report.py` |
| Fact-Check — coverage metric | `checkable` + `coverage` = checked/checkable | `fact_check.py` |
| Fact-Check — actionable UNVERIFIED | reason names metric/year/company + remedy; flags incomparable-unit case | `fact_check.py` |
| Auditor — robust LLM JSON parse | `json_utils.loads_lenient` (fences/preamble) wired into 3 LLM callers | `json_utils.py` + `agent.py` + `fact_check.py` |

**Tests:** +9 (now **9 suites, 58 tests** — added `test_json_utils.py` ×5, `test_report_extras.py` ×4). All green under pytest + standalone.

**Still open (unchanged):** run `verify_search_claims_index.sql` on live DB; evidence-corpus depth (content, no-fabricate); extend route harness to remaining endpoints; thread `extraction_version`/`model_version` from ingest into `build_report`; count-weighted integrity penalties (deferred — would shift demoed scores).

---

# Resolution Log — 2026-06-25 (session 4: 5 more additive improvements)

All additive (no change to existing scores/verdicts), each test-locked.

| Finding | Change | Where |
|---------|--------|-------|
| Benchmark — peer-depth confidence | `cross_company.confidence`, scorecard `low_confidence`/`low_confidence_metrics` (n<3) | `benchmark.py` |
| Auditor — suggested questions | pure `suggest_questions(report)` + `GET /audit/{doc_id}/suggested-questions` | `agent.py` + `api_reasoning.py` |
| Auditor — citation grounding | `ask` returns `unsupported_citations` (hallucinated `[n]`) | `agent.py` |
| Auditor — scope signal | `ask` returns `top_similarity` + `low_relevance` (soft, not a hard refusal) | `agent.py` |
| Integrity Report — richer non-LLM fallback | `_key_findings` bullets; `synthesize_audit` emits `key_findings` + uses it as structured summary | `agent.py` |

**Tests:** +5 (now **11 suites, 63 tests** — `test_agent_helpers.py` ×4 via the stub-and-remove harness, +1 in `test_benchmark.py`). Green under pytest + standalone.

**Still partial / open:** citation *semantic-relevance* check (only existence done); UI display of `of`/gray-out (frontend); the deferred set above unchanged.

---

# Resolution Log — 2026-06-25 (session 5: 2 additive + 1 verified-N/A)

| Finding | Change | Where |
|---------|--------|-------|
| Verification method in Integrity Report | `statistics.verification_profile` {imagery/data_crosscheck/document_review}; backend `_verification_method` mirrors the frontend mapping | `integrity_report.py` |
| Weighted credibility (materiality) | additive `weighted_credibility` + per-verdict `materiality`; plain `credibility` unchanged | `fact_check.py` |
| Evidence freshness/staleness | ⚠️ **N/A** — `find_evidence` matches exact year, so no staleness gap exists; flag would be dead code → reverted | (n/a) |

**Tests:** +2 (now **11 suites, 65 tests** — both in `test_report_extras.py`). Green under pytest + standalone.

**Process note (session 5):** verify-before-asserting caught the staleness item *during implementation* — a smoke test showed the `stale` flag could only ever be False under exact-year matching. Reverted rather than ship dead code that implies a freshness check the system doesn't actually perform.

---

# Resolution Log — 2026-06-25 (session 6: close the four standing caveats)

The prior sessions' honest self-critique named four gaps the additive backend work had **not** closed: (1) all new fields sat in API responses **unconsumed by the frontend**; (2) **nothing was committed** — the whole tree was one `git reset` from gone; (3) it was **never run against live data** (synthetic tests only; the index SQL never executed); (4) the **big product risks** (evidence-corpus depth, count-weighting) were untouched. This session worked all four in order.

| Gap | What was done | Where |
|-----|---------------|-------|
| **2. Commit** | Committed the entire multi-session working tree on `ESG_V1` after a green run (66 tests) so nothing is at risk. | commit `7307c8a` |
| **1. Frontend wiring** | The Integrity Audit page now **consumes** the additive fields: Score Breakdown bars (`penalty_breakdown`), Verification Profile panel (`statistics.verification_profile`), coverage + weighted-credibility in the fact-check card, suggested-question chips (`/audit/{doc}/suggested-questions`), low-relevance + unsupported-citation caveats in chat, and an illustrative-corpus warning. | `IntegrityAudit.tsx`, `lib/api.ts` |
| **3. Live-data validation** | Ran the full reasoning pipeline against the **live Supabase corpus** (1435 claims, 3 docs) read-only, and **executed** `verify_search_claims_index.sql` on the live DB. Found + fixed a real schema bug (below). | validation scripts (scratch), `schema.sql`, migration |
| **4. Evidence corpus** | Honest path (no fabricated figures): added machine-readable **provenance/quality tiers** so the illustrative state is transparent and the credibility % is never silently presented as verified-backed. | `evidence_corpus.json`, `fact_check.py` |

## Gap 1 — frontend wiring (the fields are now visible to users)
- **`lib/api.ts`**: typed `penalty_breakdown`, `statistics.verification_profile`, `computed_at`/`report_version`, fact-check `coverage`/`checkable`/`weighted_credibility`/`llm_assisted`/`corpus_quality`, per-result `materiality`/`evidence_quality`, `AskAnswer.top_similarity`/`low_relevance`/`unsupported_citations`; added `getSuggestedQuestions`.
- **`IntegrityAudit.tsx`**: new **Score Breakdown** card (per-flag points-deducted bars + provenance line), **Verification Profile** card (imagery/data/document distribution), fact-check card now shows **coverage** and **weighted credibility** alongside credibility, **suggested-question chips** (click → asks), and chat answers now render the **low-relevance** and **unsupported-citation** caveats. Frontend `tsc --noEmit` clean.
- *Honest scope:* wired the **Integrity Audit** page (the page these fields were built for). Portfolio/other pages and the benchmark `of`/gray-out display remain unwired — follow-on, not done here.

## Gap 3 — what running against live data actually showed
1. **Every additive field populates correctly on real claims**, and the score invariant **`score == 100 − Σ(points_deducted)` held for all three docs** (tata_power_2024 28/F, shell_2022 13/F, shell_2023 6/F). Benchmark confidence fields correctly flagged the thin-peer corpus (`shell` scorecard: 8/8 metrics `low_confidence`; `cross_company` n=2 `confidence=low`).
2. **New empirical finding — the integrity score saturates to grade F across the whole live corpus.** All three reports are F because the Critical "Internally inconsistent figures" flag fires with huge counts (×50, ×956, ×634) yet, under the **flat per-flag** model, deducts a fixed 25 regardless. This is the first *empirical* evidence for the long-deferred **count-weighting** recommendation: with real data the score has **no discriminating power**. (Also worth a look: 956 internal-inconsistency pairs on shell_2022 may indicate the numeric-contradiction pass over-fires — flagged, not yet investigated.)

> **Follow-up (same session) — investigated + fixed the contradiction over-fire (existing_issues.md #18).** The 956 broke down as `{Temporal 569, Metric 350, Scope 32, Hard 5}`. The 569 `Temporal` were a **false-positive class**: the engine flagged *every cross-year value difference* of a metric as a "shift" contradiction, so a normal multi-year disclosure (LTIFR 0.4@2022 / 1.7@2021 / 1.4@2019) read as dozens of contradictions. Fixed by dropping the cross-year value-shift type entirely (same-year `Metric`, cross-scope `Scope`, and `Hard` direction conflicts are kept; tests updated, 69 green). Live result: shell_2022 **956 → 387**. **But the grade did not move** — all three stay F. So the contradiction over-fire was a *count-honesty* bug, **not** the cause of score saturation: the flat penalty makes the contradiction flag Critical from any single same-year mismatch, and the `VAGUE`/`TARGETS` flags alone already exceed the F threshold. The score won't gain discrimination until **count-weighting** lands and **#19** (metric_key conflation — fatalities vs employees sharing `ltifr.count`) is fixed upstream. Lesson: removing a loud false-positive *count* and *moving the headline metric* are different problems; verifying on live data after the fix is what separated them.

> **Follow-up (next session) — count-weighting SHIPPED; the headline metric now discriminates.** Replaced the flat per-flag-type penalty in `integrity_report.py` with `penalty = sev_weight × prevalence` (prevalence = `count/total`; structural flags fixed at 0.5). Calibrated on the live corpus — **OLD: all three F** (Shell'22 13, Shell'23 6, Tata'24 28; range 22, single grade). **NEW: Shell'22 34.5 (F), Shell'23 25.7 (F), Tata'24 84.2 (B)** — range 58, grades {B, F}. The score now separates a clean, metric-dense report (Tata, B) from greenwash-heavy ones (Shell, F), exactly the discrimination the saturation finding said was missing. Why it works: Tata's flags are mostly 3–14% prevalence (e.g. VAGUE 4%, MISSING_BASELINE 4%) which under flat scoring each cost a full −8; now they cost ~−0.6. Shell's flags are pervasive (CONTRADICTION 68%, ASPIRATIONAL 74%, NON_GROUNDABLE 40%) so they still dominate. Frontend Score-Breakdown caption + bar rescaled; new regression test `test_score_is_count_weighted_by_prevalence` locks "more pervasive ⇒ lower score". 71 tests green. **Caveat carried forward:** Critical×prevalence makes CONTRADICTION the single biggest lever, so **#19** (metric_key conflation inflating Metric contradictions) now has direct score impact — fixing it upstream will further sharpen the score. This is the *first* center-of-product problem landed (vs the prior additive/refining loop).
3. **New empirical finding — fact-check coverage is the bottleneck, exactly as predicted.** Coverage was 0.04 / 0.46 / 0.43 — i.e. for tata_power only **4%** of checkable claims had any reference evidence — a direct consequence of the 3-record corpus, not an engine defect.
4. **`verify_search_claims_index.sql` — run, and the premise was subtler than the journal's correction said.** The 4 HNSW indexes exist and match `<=>`, but the planner does **not** use them — and is **right** not to at this scale: a literal-vector query seq-scans 1435 rows in **8.9 ms** vs **194 ms** for a forced HNSW scan (per-partition graph-traversal overhead dominates on tiny tables). The indexes are correct *dormant insurance*, not an active path yet. (The alarming **488 ms** in the first EXPLAIN was an artifact of the script's scalar-subquery probe re-evaluating per row; the real `search_claims` RPC passes a **bound** `query_embedding` ≈ the 8.9 ms literal path — so production latency was never the 488 ms figure.)
5. **🐛 Real schema bug found + fixed: the `claims_default` partition had no HNSW index.** Only 4 of the 5 partitions were indexed; `claims_default` — the DEFAULT catch-all that holds `emissions.scope1` (the most material family) and is currently the **largest** partition (746 rows) — had none, so it would seq-scan under semantic search while its peers use ANN at scale. **Fixed** in `schema.sql`, shipped as migration `2026-06-25_claims_default_hnsw.sql`, and **applied to the live DB** (idempotent `CREATE INDEX IF NOT EXISTS`; verified 5 HNSW indexes now exist). Safe because it's additive + the planner won't even use it at current scale, so zero behavioural change to the live app today.

## Gap 4 — evidence corpus (the honest, no-fabrication path)
The product's integrity premise forbids inventing reference figures, so "depth" here means **making the corpus productionizable and its current state transparent**, not faking rows:
- **Machine-readable trust tiers** on every record (`quality: verified | self_reported | illustrative | unverified`) replacing the free-text "(illustrative sample)" string; documented in the corpus `_meta`. `load_external_corpus` normalizes the tier (missing → `unverified`).
- **`corpus_quality`** summary on every `fact_check_document` response (`by_quality` counts + `illustrative_only` boolean) and **`evidence_quality`** per verdict (best tier among compared sources; cross-report evidence is correctly tagged `self_reported` — it's the company's own real filing).
- **Frontend caveat**: when `illustrative_only` is true the Integrity Audit fact-check card now warns "treat credibility as a demo signal, not production ground truth" — so the credibility % can never be mistaken for verified-backed.
- *Still genuinely open:* real **external reference figures** (CDP/BRSR/filings) — content/sourcing work, deliberately **not fabricated**. The structure to add them safely (with `quality: "verified"`) now exists.

**Tests:** +3 (now **12 suites, 69 tests** — `test_fact_check_corpus.py` extended: quality normalization, `corpus_quality` illustrative-only, `evidence_quality` on a verdict). Green under pytest; frontend `tsc` clean.

## Process note (session 6)
Running against live data earned its keep twice: it **found a real bug** the synthetic tests never could (the missing `claims_default` index — synthetic suites don't exercise the partition router), and it **corrected an over-optimistic prior correction** (the journal said the HNSW path was "the intended design, just confirm"; confirming showed it's dormant-and-correct, not active, and that the scary 488 ms was a probe artifact). The verify-before-asserting discipline now extends to *runtime*: the EXPLAIN plan, not the schema text, is the source of truth about what the planner does.
