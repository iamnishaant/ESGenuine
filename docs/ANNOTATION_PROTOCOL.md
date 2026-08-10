# Annotation Protocol — source-anchored gold set

**Status:** specification, not yet executed · **Created:** 2026-08-10 (audit response)
**Tooling:** [`backend/scripts/enumerate_units.py`](../backend/scripts/enumerate_units.py)
**Supersedes the frame used by:** `backend/tests/eval/gold_set*.json`

This is the working document you hand a second annotator. It exists because the current
gold sets cannot support a research claim, for reasons that are properties of how they
were *sampled* rather than of how carefully they were *labelled*.

---

## 1. What went wrong, precisely

All three existing gold sets are sampled **from claims the extractor emitted**
(`_meta.source_extraction` points at an output JSONL). Three consequences:

| # | Defect | Why the frame causes it |
|---|---|---|
| 1 | **No recall is measurable** | A missed claim never enters the sample, so it can never be counted. `precision_composite` is precision-only *by construction*. |
| 2 | **Annotator anchoring** | The old rubric reads "for each sampled extracted claim we read its `source_sentence` and record the CORRECT label" — the label is formed while looking at the prediction. |
| 3 | **Ground truth drifts toward the system** | Labels name taxonomy nodes, so a new node makes an old label look stale and invites editing the gold to match. This happened: `48555ea` (2 Shell labels) and `95e1f20` (4 Tata labels), each in the same commit as the ontology change being measured. |

Defect 3 is why `89.7` was reported as "out-of-sample" when the ontology had been tuned
against that very set 35 minutes earlier. **No untouched test set currently exists in
this repository.**

---

## 2. The three design decisions that fix it

**(1) Enumerate units from the document, not claims from the output.**
A *unit* is a sentence or a table cell that could carry a claim. The frame is fixed
before the system runs, so a miss is visible and recall has a denominator.

**(2) Stratify, then reweight.**
Most sentences assert nothing; uniform sampling would spend the budget on negatives.
Units are split by claim density, sampled at different rates, and every unit carries its
inclusion probability so estimates reweight to the whole document (Horvitz–Thompson).
Unbiased document-level precision *and* recall, without exhaustive annotation.

**(3) Record a CONCEPT, never a taxonomy node.** ← *the one that prevents recurrence*

> Gold says: `concept = "particulate matter emissions"`, `pillar = emissions`
> A separate versioned file `tests/eval/concept_map.json` says:
> `"particulate matter emissions" → emissions.air_pollutants.pm`

When the ontology gains a node you edit **the mapping**, which is a system artifact and
reads as a system change in the diff. You never edit ground truth. Had this separation
existed, `48555ea` would have been a one-line mapping change instead of a gold rewrite,
and the contamination would not have occurred.

---

## 3. Which documents

Use reports **never used for tuning**. All three are already committed:

| Use | Report | Why |
|---|---|---|
| ✅ **Primary** | `bp-esg-datasheet-2023.pdf` | Datasheet format — a third disclosure regime, distinct from both BRSR and IR-narrative |
| ✅ **Primary** | `infosys-esg-report-2024-25.pdf` | Services sector; the corpus is otherwise energy/utilities-heavy |
| ✅ **Secondary** | `Microsoft-2024-Environmental-Sustainability-Report.pdf` | Tech sector, narrative-heavy |
| ❌ **Never** | Tata Power BRSR FY24 | Ontology + quality gate tuned on it |
| ❌ **Never** | Shell SR2022 | Ontology round 2 tuned on it (`48555ea`) |

Balance the budget across at least two disclosure regimes. The existing ablation shows
regime determines *which* repair matters (gate +20.5 on form-heavy BRSR vs ontology +10.6
on narrative IR), so a single-regime test set cannot support a general claim.

---

## 4. Building the worksheet

```bash
python backend/scripts/enumerate_units.py \
    --docling  <docling_cache.json> \
    --sentences <parsed>_sentences.json \
    --doc-id   bp_2023 \
    --n 400 \
    --out backend/tests/eval/worksheets/
```

Emits `<doc>_units.csv` (annotate this), `<doc>_units.jsonl` (machine-readable frame) and
`<doc>_units.manifest.json` (strata sizes, inclusion probabilities, seed).

### Strata

| Stratum | Definition | Sampling share |
|---|---|---|
| `A_numeral_and_esg` | table cell with an ESG term in its label, **or** sentence with both a numeral and an ESG term | 60% |
| `B_numeral_only` | table cell without an ESG term, **or** sentence with a numeral only | 25% |
| `C_other` | sentence with no numeral | 15% |

Table cells are always treated as numeric — they are in the frame *because* they parsed
as a number, so testing the row label for a digit would be meaningless.

The definitions are deliberately crude keyword/regex rules. A smarter classifier would
make the inclusion probabilities depend on a model, which would bias the estimator and
make the frame unauditable. **A reviewer must be able to verify the frame by reading it.**

### Budget

**≈400 units per document, ≥2 documents.** At ~45 s/unit that is about 5 hours per
annotator per document. Double-annotate a **≥150-unit overlap** for κ.

---

## 5. Field schema

The annotator sees `unit_id`, `kind`, `page`, `source_text` — **and nothing else**.

| Field | Values | Notes |
|---|---|---|
| `is_esg_claim` | `yes` / `no` | `no` for page furniture, form questions, headers, ToC, bare labels |
| `concept` | **free text** | What is actually asserted. Never a taxonomy node. `"particulate matter emissions"`, not `emissions.air_pollutants.pm` |
| `pillar` | `emissions` `energy` `water` `waste` `social` `governance` `other` | Coarse and stable; the only controlled vocabulary in the schema |
| `claim_type` | `performance` / `target` / `narrative` | Delivered / forward-looking / qualitative |
| `value` | number or blank | As asserted |
| `unit` | as written | `"kilolitres"`, `"tCO2e"`, `"%"` |
| `value_ambiguous` | `yes` / `no` | Row carries several values and none is pinnable from the unit alone |
| `annotator_note` | free text | Reasoning for anything non-obvious |

### Decision rules

1. **Judge the unit alone.** If the text does not assert it, it is not in the label. Do
   not resolve a figure by consulting elsewhere in the report — the system does not get
   that context either, so allowing it inflates gold in a way the system can never match.
2. **Form questions are not claims.** "Please specify, if any." → `is_esg_claim = no`.
3. **A bare row label with no value is not a claim.** "Particulate matter (PM)" alone →
   `no`. With a value → `yes`.
4. **Targets need commitment language.** "By 2030 we will…" → `target`. "We aim to
   explore…" → `narrative`.
5. **Where the taxonomy has no node, say the true concept anyway.** That is the whole
   point of free-text concepts: it lets `node_acc` penalise a force-fit while the concept
   map records the gap honestly.
6. **When genuinely unsure, mark it and move on.** Flagged units go to adjudication.
   Guessing is worse than disagreeing.

> **Do not open the system's output. Do not run the pipeline on these documents until
> annotation is frozen.** Anchoring is the defect being fixed; a single peek reintroduces
> it and silently invalidates every κ computed afterwards.

---

## 6. Two annotators, κ, adjudication

1. Both annotators label the ≥150-unit overlap **independently**, from the same
   worksheet, without discussion.
2. Report **Cohen's κ** for:
   - `is_esg_claim` (binary) — the load-bearing agreement number
   - `pillar` (categorical)
   - `claim_type` (categorical)
   `concept` is free text, so report normalised exact-match rate instead, not κ.
3. **Interpretation:** κ < 0.6 means the *rubric* is broken, not the annotators. Fix the
   rubric, re-annotate, and say so in the paper. κ ≥ 0.8 on `is_esg_claim` is the target.
4. **Adjudication:** a third party resolves disagreements, or the two annotators discuss
   and record the resolution. Log every adjudicated unit with the reason — the
   disagreement classes are themselves a reportable finding about which ESG claims are
   genuinely ambiguous.
5. Report κ **before** adjudication and use the **adjudicated** labels for scoring.

---

## 7. Freeze before you score

The discipline that makes the number credible:

```bash
# 1. commit the adjudicated worksheet
git add backend/tests/eval/worksheets/bp_2023_units.csv
git commit -m "gold(bp2023): adjudicated annotations, frozen pre-scoring"

# 2. register it in the tamper gate
python backend/tests/test_gold_integrity.py --update
#    ...and write the GOLD_CHANGELOG.md entry it asks for

# 3. tag, so the frozen state is addressable
git tag gold-bp2023-v1

# 4. only now run the system against it
```

Record the SHA-256 and the tag in the paper. Score once; log every scoring event with its
date and commit. `test_gold_integrity.py` will fail CI if a label changes afterwards
without a deliberate manifest bump and a written rationale — that gate exists specifically
so the `48555ea` failure mode cannot repeat silently.

---

## 8. Estimators

Let `S` = sampled units, `w_u = 1/p_u` the IPW weight from the manifest.

**Recall** — of what the document asserts, how much the system found:

```
recall = Σ w_u · [gold_claim(u) ∧ system_found(u)]  /  Σ w_u · [gold_claim(u)]
```

**Precision** — of what the system emitted, how much is real:

```
precision = Σ w_u · [system_claim(u) ∧ gold_claim(u)]  /  Σ w_u · [system_claim(u)]
```

**F1** = harmonic mean. Field accuracies (concept-via-map, value, unit, type) are computed
on the intersection, weighted the same way.

**Off-frame claims.** A system claim that maps to no unit in the frame — an invented
sentence, a value attributed to an unparsed region — cannot be scored by the formulas
above. **Count and report these separately.** They are the hallucination class and
quietly dropping them flatters the system.

**Confidence intervals.** Stratified bootstrap: resample units *within each stratum* with
replacement, recompute, take the 2.5th/97.5th percentiles. 2,000 resamples is plenty and
runs in seconds. Report an interval on every rate. With ~400 units the intervals will be
wide enough to matter — that is information, not a problem to hide.

**Paired comparisons.** For ablation stages and baselines, the same units are scored under
each condition, so use **McNemar** for per-field binary outcomes and a **paired bootstrap**
for composites. Unpaired tests would throw away real statistical power.

---

## 9. What this still does not measure

State these as limitations rather than letting a reviewer find them:

- **Recall is relative to the parser's units.** A fact the PDF parser never surfaced —
  unparsed figure, scanned table, OCR failure — is outside the frame and is not counted as
  a miss. This is *parser-conditional* recall, not "of everything in the PDF".
- **Stratum C is thinly sampled** (~9% inclusion), so its contribution carries the widest
  interval. If C turns out to hold more claims than expected, raise its allocation and
  re-sample rather than reporting a shaky reweighted estimate.
- **Two documents is a small test set**, even at 400 units each. It supports a claim about
  these disclosure regimes, not about ESG reporting in general.
- **This protocol says nothing about the integrity score.** Extraction quality and
  greenwashing-verdict validity are separate questions; see roadmap 6.4.

---

## 10. Checklist

- [ ] Pick 2 documents from §3 (never Tata FY24 or Shell 2022)
- [ ] Parse; produce Docling cache + sentences JSON
- [ ] `enumerate_units.py --describe` — sanity-check the frame before spending annotation time
- [ ] Generate worksheets, n=400 each
- [ ] Annotator 1: full set. Annotator 2: ≥150-unit overlap, independent
- [ ] Compute κ on `is_esg_claim` / `pillar` / `claim_type`; if κ < 0.6, fix the rubric and redo
- [ ] Adjudicate; log every resolution
- [ ] Build `concept_map.json` (concept → current taxonomy node) — **a system artifact, versioned separately**
- [ ] Freeze: commit, `--update` the manifest, changelog entry, git tag
- [ ] **Only now** run the system. Score once.
- [ ] Report precision, recall, F1, off-frame count, κ, and bootstrap CIs on all of them
