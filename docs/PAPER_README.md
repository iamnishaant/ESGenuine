# ESGenuine — paper kit

**Target:** ICMLDE 5.0 · Elsevier Procedia CS (Scopus/WoS/DBLP) · 3–10 pp · double-blind, 3 reviewers · **deadline 15 Aug 2026**
**Branch:** `paper/icmlde-evaluation`

Everything needed for the submission, in one place. Start here.

```bash
git fetch origin && git checkout paper/icmlde-evaluation
```

| I want to… | Go to |
|---|---|
| know what to run (needs API key / DB) | [§1 Roadmap](#1-roadmap--tasks-needing-credentials) |
| paste the results section | [§3 Results](#3-results--paste-ready) |
| paste the ablation section | [§3.2](#32-ablation-which-component-earns-the-gain) |
| use the figures | [§4 Figures](#4-figures) |
| know what NOT to claim | [§5 Claim discipline](#5-claim-discipline) |
| reproduce every number | [§6 Reproducing](#6-reproducing-every-number) |

---

## 0. Status

| | |
|---|---|
| ✅ Done | ablation, per-metric evaluation, bootstrap CIs, table recall, cost/latency, no-LLM floor, grounding precision, 3 figures, reproducibility (pinned weights, seeds, frozen fixtures) |
| ✅ Done 08-11 | **frontier baseline** (§3.5), **corpus counts** (§4.1), offline harnesses re-verified on a second machine, cost harness added, credential leak patched in code |
| 🔴 Owner action | **rotate the Supabase DB password** — still live. See [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) §P0 |
| ❌ Not started | **related work (zero citations — biggest rejection risk)**, Procedia template, §1–3, §7 |

The evaluation is no longer the weak point. **Related work and the template are.**

> **Read [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) before writing §3.** The
> 2026-08-11 cross-check confirmed every offline number exactly, but retracted §3.2
> finding (ii) and revised the §3.3 cost figure. Both are corrected below.

---

## 1. Roadmap — tasks needing credentials

Full version with troubleshooting: [`HANDOFF_ROADMAP.md`](HANDOFF_ROADMAP.md). Summary:

### P0 — rotate the database password 🔴 *15 min, do first*

Three **committed** files hardcode the plaintext Postgres **superuser** password for the
live project — `backend/scripts/audit_pharos_db.py:5`,
`backend/scripts/clean_suspicious_claims.py:3`,
`backend/src/reasoning/run_nli_batch.py:14` — present since the initial commit.

Superuser **bypasses RLS**, so the entire `2026-08-09_enable_rls.sql` migration is void
against anyone holding it. It is in git history, so deleting the lines is not enough.

1. Supabase → Settings → Database → **Reset database password**
2. Update `DATABASE_URL` in `.env`
3. Replace the three literals with `os.environ["DATABASE_URL"]` — **no default**
4. Check Supabase → Logs → Postgres for unrecognised connections

> Do not commit the code fix until *after* rotating. A commit titled "removed hardcoded
> password" advertises the leak and points at the history where it still lives.

### P1 — frontier baseline 🔴 *30 min — blocks the paper*

Every comparison is currently the system against **itself**. All fixtures came from
`llama-3.3-70b`. Reviewers will ask whether the repair layer survives a better extractor.

```bash
cd backend && python -m pytest -m "not live" && cd ..      # expect 178 passed

set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o
python backend/scripts/run_baselines.py --generate frontier --case tata --limit 3  # smoke
python backend/scripts/run_baselines.py --generate frontier --case tata
python backend/scripts/run_baselines.py --generate frontier --case shell
python backend/scripts/run_baselines.py --markdown > baselines_frontier.md
```

Use a **dated** model id, never `-latest`. Anthropic/NVIDIA keys work too.
**Worked if** the output stops saying `[NOT RUN] frontier cells B0/B1 are missing` and
prints a `2x2 INTERACTION` block. **Commit** the generated `baseline_frontier_*.jsonl`
and `.meta.json` — they become frozen fixtures.

### P2 — corpus statistics 🟠 *5 min* · P3 — re-run offline harnesses 🟡 *10 min*

See [`HANDOFF_ROADMAP.md`](HANDOFF_ROADMAP.md) §P2/§P3. P3 lists expected values —
**flag mismatches, don't overwrite.**

### Do not

- edit `backend/tests/eval/gold_set*.json` — a CI gate fails the build, deliberately
- commit `.env` or the new password
- **re-run the extraction pipeline over the corpus.** Every number comes from the
  committed fixtures; regenerating them days before the deadline invalidates §3 entirely

---

## 2. The paper in one paragraph

> A deterministic post-correction layer recovers most of what an LLM extractor gets wrong
> on ESG disclosures, at **0.58 ms/claim and zero inference cost** — and *which* repair
> matters is determined by the **disclosure regime**. On a form-heavy statutory filing the
> rule-based quality gate carries the result (+20.5 points); on a narrative
> investor-relations report it is taxonomy normalisation (+10.6). Both intervals exclude
> zero and do not overlap each other.

That last sentence is the contribution. It is also **immune to the gold-set contamination**
(§5), because the ablation stages are scored on identical claims.

---

## 3. Results — paste-ready

> Rewrite in your own prose before submitting. Procedia runs similarity checks, and text
> lifted verbatim from a repo doc is a needless risk.

### 3.1 Extraction quality

Nonparametric bootstrap over annotated claims, 2,000 resamples, claim as sampling unit.

| Metric | BRSR statutory | 95% CI | n | IR narrative | 95% CI | n |
|---|--:|:--:|--:|--:|:--:|--:|
| candidate precision | 86.0% | [75.0, 95.5] | 43 | 98.0% | [94.0, 100.0] | 50 |
| aspect node | 94.6% | [85.7, 100.0] | 37 | 79.6% | [68.0, 90.0] | 49 |
| aspect pillar | †no errors | — | 37 | 89.8% | [80.9, 98.0] | 49 |
| value (±5%) | †no errors | — | 12 | 97.6% | [92.5, 100.0] | 42 |
| unit family | †no errors | — | 30 | 77.3% | [64.4, 89.1] | 44 |
| claim type | †no errors | — | 37 | 95.9% | [89.8, 100.0] | 49 |
| **precision composite** | **96.1** | **[93.5, 98.5]** | 50 | **89.7** | **[85.3, 94.0]** | 50 |

† No errors in the annotated sample. Reported this way rather than as 100%: a percentile
bootstrap on all-correct data returns a degenerate [100, 100] interval, which is a
boundary artifact, not certainty. A one-sided rule-of-three bound gives ≈92% at n=37.

**The two composites' intervals overlap**, so no difference between the documents is
claimed.

### 3.2 Ablation: which component earns the gain

Six cumulative stages over the frozen extractor fixtures. **S0** resets each aspect to the
model's free text (no taxonomy layer); S5 is the shipped configuration.

> ⚠️ **The fixtures are not raw model output** — see
> [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md) §1. They carry `type_fixed`,
> `scope_fixed`, `aspect_fixed` and `value_not_in_table` flags written by an earlier
> revision of the gate. S0 is a *reconstruction* (three fields reset, current stack
> replayed). The aggregate deltas survive and are conservative; the S2/S3 per-stage
> deltas do not mean what they appear to.

| Stage | BRSR | IR |
|---|--:|--:|
| S0 raw LLM | 67.7 | 72.1 |
| S1 + ontology | 71.5 | 82.7 |
| S2 + FY repair | 73.2 | 82.7 |
| S3 + value-in-table | 73.2 | 82.7 |
| S4 + gate fixes | 93.7 | 89.7 |
| **S5 + furniture drop** | **96.1** | **89.7** |

Paired bootstrap (both stages scored on the same resample):

| Δ | BRSR | IR |
|---|:--:|:--:|
| S0→S1 ontology | **+3.8** [+1.5, +6.5] | **+10.6** [+7.8, +13.5] |
| S1→S2 FY repair | +1.7 [+0.0, +5.7] *n.s.* | +0.0 *n.s.* |
| S2→S3 value-in-table | +0.0 *n.s.* | +0.0 *n.s.* |
| S3→S4 gate fixes | **+20.5** [+16.3, +25.2] | **+7.0** [+4.0, +10.2] |
| S4→S5 furniture drop | **+2.4** [+0.8, +4.3] | +0.0 *n.s.* |
| **S1→S5 repair layer** | **+24.6** [+19.6, +30.4] | **+7.0** [+4.0, +10.2] |

**Three findings.**

**(i) The layer is worth +24.6 / +7.0 over an LLM-plus-vocabulary baseline**, at zero
inference cost. Quote S1→S5, not S0→S5: S0's node accuracy is 0% *by construction* (free
text cannot exact-match a controlled vocabulary), so the S0→S5 totals (+28.4, +17.6)
flatter the method.

**(ii) Two components carry the layer; two more are *not identifiable*.** ~~FY repair and
value-in-table are indistinguishable from zero, so they don't pay for themselves.~~
**Retracted 2026-08-11.** Both stages are applied by the extractor *before the fixtures are
written* (`claim_extractor.py:862-868`), so replaying them over an already-repaired fixture
moves 3 values on Tata and 0 on Shell. Their ≈0 deltas measure the residual between the old
and current revision, not the value of the stage. Say **not identifiable under this design**,
never "ineffective" — a reviewer can check this by grepping the artifact. Taxonomy mapping
and the gate do carry the layer, so *taxonomy normalisation plus rule-based repair* is still
the right description of the method.

**(iii) The dominant component is set by the disclosure regime.** Gate fixes carry the
statutory filing (+20.5, node accuracy 18.9%→94.6%); taxonomy mapping carries the
narrative report (+10.6), where the furniture filter contributes nothing because there is
no statutory form furniture. **The intervals do not overlap.** This is the central claim:
a single pipeline tuned on one regime will under-serve the other.

### 3.3 Cost

**0.45 ms per claim** — 168 ms for the 373-claim BRSR, 105 ms for the 247-claim IR report.
Single-threaded, no network, no API spend; best of 15 runs. Against an LLM re-extraction
pass this is free, which is what makes (iii) actionable: a deployment can afford repair
rules for every regime it may meet.

> Revised 2026-08-11. The previous **0.58 ms / 218 ms** had **no harness behind it** — it
> was prose only, the one number in the paper that §6 could not regenerate. `run_cost.py`
> now measures it. The figure is hardware-dependent, so quote the order of magnitude
> ("sub-millisecond per claim") and cite the harness, not the digits.

### 3.4 Recall, and what precision costs

Against 482 mechanically enumerated table facts (statutory filing):

| | |
|---|--:|
| Raw cell recall | 54.4% (262/482) |
| **Distinct-fact recall** | **59.5%** |
| Recall on pages the pipeline processed | 57.8% |
| Pages producing no claims | 2 (29 cells) |

**Precision-oriented repair is a trade.** Across S0→S5 the composite rises 67.7→96.1 while
table-fact recall **falls 59.5%→54.0%**. The furniture filter removes 34 claims, some of
them genuine facts. A precision-only evaluation cannot see this; a deployment tuned purely
for precision silently drops real disclosures.

Recall is reported for the statutory filing only. The IR fixture is text-dominant (13
table claims of 247) with partial page coverage, so its table recall would describe the
fixture, not the pipeline.

### 3.5 Baselines

**Model-independent, already measured:**

- **No-LLM floor** — rule-based extraction with taxonomy keyword matching names only
  **43.1%** of table rows; the remaining 57% resolve to `uncategorized`. That is the share
  of the table surface genuinely requiring a model.
- **Grounding precision** (share of emitted numeric values that occur in the source page —
  mechanical, comparable across systems): **87.4%** → **89.2%** with repair.

**`[FILL after P1]`** the 2×2. If the frontier gain is large and the repair delta shrinks,
reframe around cost: report tokens, latency and dollars per report.

---

## 4. Figures

Regenerate: `python backend/scripts/make_figures.py` → `docs/figures/*.pdf` (camera-ready)
+ `*.png` (preview). **Values are computed from the fixtures at render time**, so a figure
can never drift from the results table.

Colourblind-safe (validated: worst adjacent pair ΔE 24.7 protan / 33.6 normal) and
greyscale-safe — series 2 carries a hatch and different markers, so a mono printout loses
nothing.

**Figure 1 — `fig1_ablation_by_regime`** *(full width)* — the thesis in one image.

> **Caption:** Contribution of each deterministic repair stage, by disclosure regime.
> (a) cumulative precision composite; (b) marginal contribution per stage with 95%
> confidence intervals from a paired bootstrap (2,000 resamples; both stages scored on the
> same resampled claims). The dominant stage differs by regime — the rule-based gate on the
> statutory filing, taxonomy mapping on the narrative report — and the two intervals do not
> overlap. Stages marked *n.s.* have intervals containing zero.

**Figure 2 — `fig2_precision_recall_tradeoff`** *(single column)* — the honesty figure.

> **Caption:** Precision composite and table-fact recall across the same repair stages
> (statutory filing). Stacked panels share an x-axis rather than twinning y, since the two
> measures are not commensurable. Precision rises 28.4 points while recall falls 5.5 pp;
> dotted lines mark the two stages that cost recall. A precision-only evaluation cannot
> observe this trade.

**Figure 3 — `fig3_per_metric_by_regime`** *(full width)* — where the regimes differ.

> **Caption:** Per-field accuracy for the shipped configuration, with 95% bootstrap
> confidence intervals. The narrative report is harder for aspect-node assignment and unit
> canonicalisation; the statutory filing is harder for candidate precision (form furniture).
> † marks rates with no observed errors, where the percentile bootstrap returns a
> degenerate interval; the one-sided rule-of-three bound is ≈92% at n=37.

**Not generated: the pipeline diagram.** Draw it in TikZ or draw.io — matplotlib flow
diagrams look amateurish and a weak figure hurts more than a missing one.

---

## 5. Claim discipline

### Do not claim

| ❌ | Why |
|---|---|
| "out-of-sample 89.7" | The ontology was tuned against that set **the same day** it was built (`48555ea`, 35 min later). Your own git log contradicts it. |
| a 96.1-vs-89.7 generalization gap | The intervals overlap. |
| 100% on anything | Ceiling artifact — say "no errors observed in N". |
| accuracy or F1 | The composite is precision-family with no recall term. |
| greenwashing-detection accuracy | Never evaluated. |
| anything about the integrity score | Severity weights are hand-set and uncalibrated. |

### Limitations section — do not skip this

Stating these is what makes reviewers trust the rest. Full prose in
[`PAPER_DRAFT_SECTIONS.md`](PAPER_DRAFT_SECTIONS.md) §6:

1. **Development sets, not held-out.** Both were tuned against; 6 of 100 labels were
   revised toward the system. **No untouched test set exists.** The paired ablation deltas
   are unaffected — identical claims at both stages — which is why they are the primary
   result and the absolute scores are context.
2. **Single annotator**, no agreement statistic.
3. **Precision-only composite**; narrative-claim recall unmeasured.
4. **Parser-conditional recall** — facts in unparsed figures are outside the frame.
5. **Two documents.** Supports a claim about these regimes, not ESG reporting generally.
6. **Extraction is not reproducible end to end** — hosted LLM at non-zero temperature.
   Frozen fixtures make every *reported* number recomputable.
7. **Out of scope, unevaluated:** contradiction detection, greenwashing taxonomy,
   integrity score, satellite verification (n=2). Describe as components; claim nothing.

### Reviewer questions, pre-empted

| Question | Answer lives in |
|---|---|
| "Just prompt engineering?" | §3.2 — deterministic, post-hoc, zero-cost, stage-wise ablated |
| "Would a better LLM make this moot?" | §3.5 — **the 2×2. Must be run.** |
| "96.1 on 50 claims — meaningful?" | §3.1 — CIs throughout; the cross-document comparison is declined |
| "Where is recall?" | §3.4 — measured, and its cost quantified |
| "Where is related work?" | **absent — highest-priority gap** |
| "Why believe the gold labels?" | §5 — stated plainly, including the revisions |

---

## 6. Reproducing every number

All offline, no credentials, seconds:

```bash
python backend/scripts/run_ablation.py  --markdown     # §3.2
python backend/scripts/run_bootstrap.py --markdown     # §3.1 CIs
python backend/scripts/run_recall.py                   # §3.4
python backend/scripts/run_baselines.py --markdown     # §3.5
python backend/scripts/run_cost.py      --markdown     # §3.3
python backend/scripts/make_figures.py                 # §4
cd backend && python -m pytest -m "not live"           # 178 passed
```

Local weights are pinned by commit SHA (`bge-base-en-v1.5` @ `a5beb1e3`,
`distilbert-base-uncased-mnli` @ `cfa538a0`) and all RNGs seeded (42). Raw LLM outputs and
parsed page markdown are committed as frozen fixtures, so results recompute exactly,
offline, at zero API cost — **this whole audit ran with no `.env` present.** Say so in the
paper; it is stronger than most artifacts at this venue.

---

## 7. Before you submit

- [ ] Procedia CS template from CMT — **write into it from the start**
- [ ] Related work (~2 h): ClimateBERT, Climate-FEVER, ClimaText, ESG-BERT; Berg/Kölbel/Rigobon *Aggregate Confusion* for motivation
- [ ] §1–3, §7 written; §4–6 adapted from [`PAPER_DRAFT_SECTIONS.md`](PAPER_DRAFT_SECTIONS.md)
- [ ] §3.5 completed from the P1 output
- [ ] §4.1 corpus line completed from P2
- [ ] Figures embedded as **PDF**
- [ ] **Anonymised** — no repo URL, names, institution, or `CITATION.cff` identifiers
- [ ] Everything rewritten in your own prose (similarity check)
- [ ] 3–10 pages; check the special-session list for a better-fitting track than the main one
