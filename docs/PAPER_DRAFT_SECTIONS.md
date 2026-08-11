# Paper draft — Evaluation, Results, Limitations

**Target:** ICMLDE 5.0 (Elsevier Procedia CS, Scopus). 3–10 pp, double-blind, 3 reviewers.
**Status:** draft scaffolding. Every number below was produced by re-running the harnesses
on 2026-08-10 and is reproducible offline. `[FILL]` marks something only you can supply.

> **Double-blind:** strip the repo URL, author names and institution before submitting.
> Refer to the system by name only; cite any prior work of yours in the third person.

---

## 4. Evaluation setup

### 4.1 Corpus

`[FILL: confirm from the live DB]` The corpus comprises **1,730 extracted claims** from
**6 sustainability reports** across **4 companies**, spanning three disclosure regimes:
Indian BRSR statutory filings, investor-relations-style narrative reports, and tabular ESG
datasheets. Reports range from 40 to 91 pages.

Evaluation uses two documents in depth: **Tata Power BRSR FY24** (form-heavy statutory
filing, 373 raw claims) and **Shell Sustainability Report 2022** (narrative IR-style, 247
raw claims). They were chosen because they sit at opposite ends of the disclosure-format
spectrum, which turns out to determine which component of our method matters (§5.2).

### 4.2 Annotated sets

Two hand-labelled sets of 50 claims each. Each record carries the correct
`is_esg_claim`, aspect, value, unit family and claim type, read from the claim's source
sentence; table values were additionally verified against the parsed table cell. Claims
whose source row carries several values with none pinnable are marked ambiguous and
excluded from strict value accuracy.

> **These are development sets, not held-out test sets.** The taxonomy and repair rules
> were tuned against both. We state this explicitly rather than reporting the scores as
> generalization performance, and §6 discusses the consequences. All 100 labels are
> single-annotator.

### 4.3 Metrics

We report six per-field rates and their unweighted mean, which we call
**`precision_composite`** to make its nature explicit:

| Metric | Definition |
|---|---|
| `candidate_precision` | of emitted claims, the share that are genuine ESG claims rather than page furniture, form questions or fabricated-value fragments |
| `aspect_node_acc` | exact match on the normalised taxonomy node |
| `aspect_pillar_acc` | match at pillar granularity (emissions / energy / water / …) |
| `value_acc` | \|x−gold\|/gold ≤ 0.05, unambiguous numeric claims only |
| `unit_base_acc` | unit canonicalises to the same dimensional family |
| `type_acc` | performance / target / narrative |

**All six are precision-family and the composite contains no recall term.** This is
structural: the annotated sets are sampled from claims the extractor emitted, so a claim
the system missed cannot appear in them. We therefore measure recall separately (§4.4)
and report the pair.

### 4.4 Recall without human annotation

Because the table parser emits each page as GitHub-flavoured Markdown with row labels and
column headers intact, the set of numeric facts on a page is **mechanically enumerable**
as `(row_label, column_header, value)` triples. This yields a recall denominator that is
independent of the system under test and costs no annotation.

We report **distinct-fact recall**: repeated `(row_label, value)` pairs across column
groups are collapsed to one fact, and governance-form cells (which carry numbers but
assert no ESG quantity) are excluded. The measure is conservative by construction — the
denominator still contains non-claim cells such as office counts — so true recall is at
least what we report.

This covers the table surface only. Narrative-claim recall requires human annotation and
remains open.

### 4.5 Reproducibility

Embedding and NLI weights are pinned to specific commit revisions
(`bge-base-en-v1.5` @ `a5beb1e3`, `distilbert-base-uncased-mnli` @ `cfa538a0`) and all RNGs
seeded (seed 42). The extraction LLM (`llama-3.3-70b-instruct`, temperature 0.1) is a
hosted endpoint and therefore **not** reproducible in the strict sense; we mitigate this by
committing the **raw LLM outputs and parsed page markdown as frozen fixtures**, so every
ablation, recall and baseline figure in this paper recomputes exactly, offline, in seconds,
at zero API cost.

---

## 5. Results

### 5.1 Extraction quality

95% confidence intervals from a nonparametric bootstrap over annotated claims
(2,000 resamples; the claim is the sampling unit).

**Tata Power BRSR FY24** (n = 50)

| Metric | Point | 95% CI | n |
|---|--:|:--:|--:|
| `candidate_precision` | 86.0% | [75.0, 95.5] | 43 |
| `aspect_node_acc` | 94.6% | [85.7, 100.0] | 37 |
| `aspect_pillar_acc` | no errors observed | — | 37 |
| `value_acc` | no errors observed | — | 12 |
| `unit_base_acc` | no errors observed | — | 30 |
| `type_acc` | no errors observed | — | 37 |
| **`precision_composite`** | **96.1** | **[93.5, 98.5]** | 50 |

**Shell SR2022** (n = 50)

| Metric | Point | 95% CI | n |
|---|--:|:--:|--:|
| `candidate_precision` | 98.0% | [94.0, 100.0] | 50 |
| `aspect_node_acc` | 79.6% | [68.0, 90.0] | 49 |
| `aspect_pillar_acc` | 89.8% | [80.9, 98.0] | 49 |
| `value_acc` | 97.6% | [92.5, 100.0] | 42 |
| `unit_base_acc` | 77.3% | [64.4, 89.1] | 44 |
| `type_acc` | 95.9% | [89.8, 100.0] | 49 |
| **`precision_composite`** | **89.7** | **[85.3, 94.0]** | 50 |

> Four Tata rates had no errors in the annotated sample. We report these as "no errors
> observed in N" rather than 100%: a percentile bootstrap on all-correct data returns a
> degenerate [100, 100] interval, which is an artifact of the boundary, not evidence of
> zero uncertainty.

> The two composites' intervals **overlap** ([93.5, 98.5] and [85.3, 94.0]). We therefore
> do not claim a difference in extraction quality between the two documents.

### 5.2 Ablation: which part of the deterministic layer earns the gain

Six cumulative stages applied to the frozen extractor fixtures — which are **not** raw model
output; see [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) §1 before quoting per-stage
numbers. **S0** resets each claim's aspect to the model's own free text (no taxonomy layer),
along with the repair flags and framework tags; **S1** adds taxonomy normalisation;
**S2** repairs fiscal-year column misalignment; **S3** flags table values absent from the
source table; **S4** applies aspect/type repairs and suspicion flags; **S5** drops page
furniture. S5 is the shipped configuration.

| Stage | Tata | Shell |
|---|--:|--:|
| S0 raw LLM | 67.7 | 72.1 |
| S1 + ontology | 71.5 | 82.7 |
| S2 + FY repair | 73.2 | 82.7 |
| S3 + value-in-table | 73.2 | 82.7 |
| S4 + gate fixes | 93.7 | 89.7 |
| **S5 + furniture drop** | **96.1** | **89.7** |

**Paired bootstrap on the deltas.** Both stages of each comparison are scored on the same
resampled claims, so the interval reflects the paired design.

| Delta | Tata | Shell |
|---|:--:|:--:|
| S0 → S1 (ontology) | **+3.8** [+1.5, +6.5] | **+10.6** [+7.8, +13.5] |
| S1 → S2 (FY repair) | +1.7 [+0.0, +5.7] *n.s.* | +0.0 *n.s.* |
| S2 → S3 (value-in-table) | +0.0 *n.s.* | +0.0 *n.s.* |
| S3 → S4 (gate fixes) | **+20.5** [+16.3, +25.2] | **+7.0** [+4.0, +10.2] |
| S4 → S5 (furniture) | **+2.4** [+0.8, +4.3] | +0.0 *n.s.* |
| **S1 → S5 (repair layer)** | **+24.6** [+19.6, +30.4] | **+7.0** [+4.0, +10.2] |

Three findings.

**(i) The deterministic layer is worth +24.6 and +7.0 points over an LLM-plus-vocabulary
baseline**, at zero inference cost. We quote S1 → S5 rather than S0 → S5 because S0's node
accuracy is 0% by construction — free text cannot exact-match a controlled vocabulary — so
the S0 → S5 totals (+28.4, +17.6) flatter the method.

**(ii) Two components carry the layer; two more are not identifiable.** Taxonomy mapping and
the gate account for essentially all of the gain, so the method is better described as
*taxonomy normalisation plus rule-based repair* than as a five-stage pipeline. The near-zero
deltas for FY repair and the value-in-table check are **not** evidence that those stages do
nothing: the extractor applies both before the fixtures are written
(`claim_extractor.py:862-868`), so replaying them over an already-repaired fixture moves 3
values on Tata and 0 on Shell. They measure a residual between layer revisions, not the value
of the stage. Report as *not identifiable under this design*. See
[`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) §1.

**(iii) Which component dominates is determined by the disclosure regime.** On the
form-heavy BRSR filing the gate carries the result (+20.5, node accuracy 18.9% → 94.6%);
on the narrative IR report it is taxonomy mapping (+10.6), and the furniture filter
contributes nothing because that document contains no statutory form furniture. The
intervals for the two dominant levers do not overlap. **This is the paper's central
claim:** repair strategy must be matched to disclosure format, and a single pipeline tuned
on one regime will under-serve the other.

### 5.3 Cost

The deterministic layer runs in **0.45 ms per claim** — 168 ms for the 373-claim BRSR and
105 ms for the 247-claim IR report, single-threaded, no network, no API spend (best of 15,
`backend/scripts/run_cost.py`). Against an LLM re-extraction pass this is effectively free,
which is what makes (iii) actionable: a deployment can afford to carry repair rules for every
regime it might encounter. The figure is hardware-dependent — quote the order of magnitude,
not the digits. *(Was 0.58 ms; that value had no harness behind it. See
[`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) §3.)*

### 5.4 Recall, and what the repair layer costs

Against 482 mechanically enumerated table facts in the BRSR filing:

| | |
|---|--:|
| Raw cell recall | 54.4% (262/482) |
| **Distinct-fact recall** | **59.5%** |
| Recall on pages the pipeline processed | 57.8% |
| Pages that produced no claims | 2 (29 cells) |

**Precision-oriented repair is a trade, not a free win.** The furniture filter removes 34
claims and raises the composite by 28.4 points, but **costs 5.5 percentage points of
table-fact recall** — some of what it discards are genuine table facts. A precision-only
evaluation cannot see this; we report it because a deployment tuned purely for precision
will silently drop real disclosures.

We report recall for the BRSR filing only. The Shell fixture is text-dominant (13 table
claims of 247) and its cached page coverage is partial, so a table-recall figure computed
from it would describe that configuration rather than the table pipeline.

### 5.5 Baselines

`[FILL — run before writing this section]`

```bash
OPENAI_MODEL=... OPENAI_API_KEY=... \
  python backend/scripts/run_baselines.py --generate frontier --case tata
python backend/scripts/run_baselines.py --case tata --markdown
```

A 2×2 over {mid-tier LLM, frontier LLM} × {no repair, repair}. The interaction term
answers whether the repair layer's contribution survives a stronger extractor.

Already measured, model-independent:

- **A no-LLM floor**: rule-based extraction with taxonomy keyword matching names only
  **43.1%** of table rows; the remaining 57% resolve to `uncategorized`, which is the share
  of the table surface that genuinely requires a model.
- **Grounding precision** (share of emitted numeric values that actually occur in the
  source page — mechanical, comparable across systems): **87.4%** without repair,
  **89.2%** with.

> If the frontier gain is large and the repair delta shrinks, reframe the contribution
> around cost: report tokens, latency and dollars per report alongside quality.

---

## 6. Limitations

We state these explicitly; several bound what the numbers above can support.

**Development sets, not held-out.** The taxonomy and repair rules were tuned against both
annotated sets. In one case the tuning commit that raised the Shell score from 81.1 to 89.7
also introduced taxonomy nodes named after concepts that set had revealed, and revised two
of its labels to match the new node names; a later commit revised four labels in the other
set. Six of 100 labels have been adjusted toward the system. **No untouched test set
exists**, so no number here is evidence of generalization. The paired ablation deltas are
unaffected — the stages are scored on identical claims — which is why we present those as
the primary result and the absolute scores as context.

**Single annotator.** All 100 labels were produced by one annotator with no second pass and
no agreement statistic. The ground truth is one reading of the source text.

**Precision-only composite.** `precision_composite` has no recall term and cannot have one
against sets sampled from extractor output. Measured table recall is 59.5% against the
composite's 96.1; the two describe the same pipeline. Narrative-claim recall is unmeasured.

**Parser-conditional recall.** Recall is relative to the units the document parser
surfaced. Facts in unparsed figures or scanned tables are outside the frame and are not
counted as misses.

**Two documents.** The regime-divergence finding rests on one document per regime. It
supports a claim about these two disclosure formats, not about ESG reporting generally.

**Extraction is not reproducible end to end.** The extraction LLM is a hosted endpoint at
non-zero temperature. Frozen fixtures make every result in this paper recomputable, but a
fresh end-to-end run will not reproduce the corpus exactly.

**Out of scope.** The system also produces cross-report contradiction flags, a
greenwashing-signal taxonomy, a document-level integrity score and satellite-imagery
verification. **None of these is evaluated here.** The integrity score's severity weights
are hand-set and have never been calibrated against an external criterion, and the
satellite component has been exercised on two locations. We describe them as system
components and make no accuracy claim for any of them.

---

## Reviewer questions to pre-empt

| Likely question | Where you answer it |
|---|---|
| "Is this just prompt engineering?" | §5.2 — the layer is deterministic, post-hoc, zero-cost, and ablated stage by stage |
| "Would a better LLM make this unnecessary?" | §5.5 — the 2×2. **Must be run.** |
| "96.1 on 50 claims — is that meaningful?" | §5.1 — CIs on every rate; you decline the 96.1-vs-89.7 comparison |
| "Where is recall?" | §5.4 — measured, reported, and its cost quantified |
| "Where is related work?" | **§2 — currently absent. Highest-priority gap.** |
| "Why should I believe the gold labels?" | §6 — stated plainly, including the label revisions |
