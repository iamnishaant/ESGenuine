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

1. **Introduce count-weighted penalties.** Instead of a flat penalty per flag, `penalty = base * min(log2(count + 1), cap)`. This makes magnitude matter without letting a single flag type dominate.
2. **Score decomposition in the response.** Return `penalty_breakdown: [{flag_type, severity, count, points_deducted}]`. The frontend can render a stacked bar showing where points were lost.
3. **Sector-normalized scoring.** Use the benchmark data to show "your score relative to the median of companies in this sector/peer-group." Even a simple percentile rank transforms the score from abstract to actionable.
4. **Add `computed_at`, `extraction_version`, `model_version` fields** to the report payload. This is trivial to add and critical for auditability.
5. **Score sensitivity analysis.** Run the scorer across all 3 current reports and document the distribution. If all three cluster in the same narrow band, the formula needs recalibration.

### UX Improvements

- **"What would improve my score?" affordance.** The recommendations exist but aren't framed as "do X and your score would rise by ~Y points." This is the single highest-value UX improvement for the Integrity Report.
- **Expandable evidence.** When a flag shows `count: 47` but only 5 snippets, add an "Expand" affordance that queries the full list (an endpoint already exists to support this via claim filtering).

### AI Enhancements (if applicable)

- **LLM-generated executive summary is already wired** via `synthesize_audit()`. However, the non-LLM fallback just returns the template string from `build_report`. The fallback should be richer — a structured bullet list of the top 3 findings, not a single sentence.

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

- **Evidence freshness / staleness.** The corpus has no `last_updated` field. A reference figure from 2019 used to check a 2024 claim is technically a match but practically stale.
- **Evidence sourcing automation.** The corpus is manually maintained. There's no pipeline to pull CDP, GRI, or public filings into it. This is the bottleneck that will determine whether the feature is real or decorative.

### Improvement Opportunities

1. **Weighted credibility.** `credibility = Σ(weight_i × supported_i) / Σ(weight_i)` where weight is proportional to materiality (emissions > governance > social sentiment). Even a simple 3-tier weighting (critical/important/informational) would be a meaningful improvement.
2. **Enriched UNVERIFIED explanations.** When a claim has no evidence, explain what *would* be needed: "No external reference for `water.consumption.volume` at year 2024 for tata_power. Add a CDP Water Security response or official annual report figure."
3. **Coverage metric alongside credibility.** Report `checked / total_checkable` as a separate metric. A report with 80% credibility but only 5% coverage is not the same as one with 80% credibility and 60% coverage.
4. **Automate corpus ingestion.** A script that fetches CDP responses, BRSR filings, or official sustainability data sheets and writes them into the corpus schema would transform this from a demo to a product.

### AI Enhancements (if applicable)

- The `llm_verdict()` function exists but is **never called** in the fact-check pipeline. Wiring it for narrative claims (where numeric comparison doesn't apply) would increase coverage significantly. However, this needs careful prompting to avoid hallucinated verdicts.

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
- **No visual trajectory chart.** The data is returned as a JSON array; the UI renders it as a flat list. A sparkline or line chart would transform understanding.

### Missing Considerations

- **Sector-specific benchmarks.** Energy companies should be benchmarked against energy peers, not all companies. Add a sector/industry field to claims metadata and filter accordingly.
- **Benchmark confidence threshold.** With < 3 companies, benchmarks should be withheld or clearly labeled "insufficient peer data."

### Improvement Opportunities

1. **Human-readable metric labels.** Maintain a mapping `metric_key → {label, unit_label, description}`. `emissions.scope1.co2e` → "Scope 1 Emissions (CO₂e)". This is a small effort with outsized UX impact.
2. **Fix the CAGR calculation** to be actual CAGR, not linear average. This affects gap-to-target accuracy.
3. **Surface peer count + add a confidence signal.** *(Correction: per-metric peer count already exists in the API as the `of` field — `cross_company` sets it to `n`. The real gaps are (a) the **UI doesn't display** the denominator, and (b) there's no top-level `confidence`/`peer_count` summarising data depth.)* Let the UI gray out or caveat metrics with `of` < 3.
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

1. **Suggested questions based on the selected report.** Analyze the report's flags and surface 3–5 relevant questions: "This report has 6 VAGUE flags — ask: 'Which environmental claims lack measurable metrics?'"
2. **Structured output parsing with fallback.** Use a regex extractor to pull JSON from the LLM response even when it's wrapped in markdown fences or preamble. This is a common pattern that would eliminate ~80% of parse failures.
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

- **Adversarial/off-topic questions.** "What is the weather today?" — the LLM will try to answer using ESG claims as context. Need a scope guard or graceful "I can only answer questions about ESG claims" response.
- **Empty retrieval.** If `search_claims` returns nothing (no relevant claims), the answer is "No relevant claims found" — correct, but the user might be asking a valid question with slightly different terminology.

### Trust & Reliability Improvements

- **Post-generation citation verification.** After the LLM generates an answer citing [1], [3], [5], verify that those citations exist and are semantically relevant. Flag hallucinated citations.

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
2. **Surface the verification method in the Integrity Report**, not just the Fact-Check detail. "12 of your claims are imagery-verifiable, 45 are data-checkable, 120 require document review" is a useful disclosure profile.

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
- **Integrity score is flat, not "diminishing"** (Integrity Report #1). Confirmed: `integrity_report.py` looped `score -= _PENALTY[...]` while the comment claimed "diminishing." ✅ **Fixed in this pass** — the comment now states it's a flat per-flag penalty and points here for the count-weighting plan. (Behaviour unchanged on purpose; changing the formula would silently shift demoed scores.)
- **Evidence corpus = 3 real records, Scope-1 only** (Fact-Check #1). Confirmed (`evidence_corpus.json`, `_schema` row filtered out by `load_external_corpus`).
- **`llm_verdict()` defined but never called** (Fact-Check AI). Confirmed.
- **`credibility = SUPPORTED / checked`** and **cross-report requires `company_id` equality.** Confirmed.
- **"CAGR" is linear** `(last-first)/span` and a legitimate `0.0` first value suppresses it (falsy guard). Confirmed.
- **Engine loads on import** at module scope. Confirmed.
- **In-memory `ingest_jobs`, no dedup/idempotency.** Confirmed.
- **"Two products" score divergence.** Confirmed: `useClaims.ts` computes Portfolio's `integrityScore` as mean groundability×100, entirely independent of the backend `build_report()` score. They will not agree. This remains the single biggest product-integrity risk.

## Corrected overstatements (changed inline)
- "Extensively tested" → there is **no pytest suite**; gates are spot-checked only.
- DistilBERT "~500 MB RAM" → ~250–350 MB resident; cold start is dominated by importing torch/transformers.
- Benchmark "technical moat" → real strength but replicable, and limited by partial canonicalizer coverage.
- "even expensive ESG rating agencies don't automate this" → removed (unverifiable competitor claim).
- "Add `peer_count`" → per-metric peer count already exists as the `of` field; the gap is UI display + a top-level confidence.
- Scope line: marked **pre-push** (the branch was not yet pushed when this was written).

## New findings (not in the original review)
1. **The review predates the #17 re-score — its score numbers are now stale.** This session recalibrated the groundability/vagueness scorer (claim_type-aware) and re-scored all 1435 live rows (groundable ≥0.75: 879 → 368; vagueness ≥0.6: ~0 → 430). Any integrity-score example written above will have shifted. Re-run before quoting numbers.
2. **`observability_type` is computed but thrown away.** `GroundabilityClassifier.score` returns it, but it is **not persisted to the DB** and **not exposed** by the fact-check API. The frontend `verificationMethod()` therefore re-derives routing from a **duplicated** OPTICAL keyword list — two sources of truth that will drift. Fix: persist `observability_type` on ingest and have the FE consume it.
3. **`audit_summary` silently caps contradictions at 3000 pairs** (`_numeric_contradictions(cap=3000)`). For a large single report this truncates without telling the caller. Surface a `truncated: true` flag.
4. **`search_claims` does a full scan** (ORDER BY `embedding <=> q` with no ANN/ivfflat index). Fine at ~1.4k rows; add an index before scale.
5. **Canonicalizer coverage is the quiet ceiling on three features at once** (fact-check, benchmark, contradiction). Verbose/compound units ("tonnes CO2 per year", "gCO2e/MJ", "million hectares") pass through unconverted. Expanding `UnitCanonicalizer._CONV` + the substring parser lifts all three simultaneously — high leverage, low risk.
6. **`evidence_corpus.json` mixes a `_note`/`_schema` pseudo-record into the data array.** Works (filtered on load) but is a smell; prefer a `{ "_meta": {...}, "records": [...] }` shape.

## Process note
Future entries: keep the "verify against code before asserting" discipline — the original review's few misses were all in *quantification* (RAM, "extensively", competitor claims), not in the structural critiques, which held up well.
