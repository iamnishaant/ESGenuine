# Extraction-Quality Evaluation Harness

> ## ⚠ READ FIRST — what these numbers are, and are not
>
> Added by the 2026-08-10 audit. Three limits are structural, not bugs, and every one of
> them changes how the headline figures may be quoted.
>
> **1. Both gold sets are DEVELOPMENT sets. Neither is held out.**
> `gold_set_shell_v03.json` is described elsewhere in this repo as "out-of-sample". It is
> not. It was created in `dd63093` (scoring 81.1) and the ontology was then tuned against
> the errors it revealed in `48555ea` **the same day** — a commit whose own message reads
> *"ontology round 2 (Shell gap classes) — out-of-sample 81.1 -> 89.7"*, which added 14
> taxonomy nodes named after concepts that set surfaced, **and edited two of its gold
> labels** to match the new node names. `95e1f20` did the same to four Tata labels.
> Six of 100 labels have been revised toward the system.
>
> → **89.7 and 96.1 are both development-set numbers.** There is currently no untouched
> test set in this repository. Do not report either as out-of-sample, held-out, or
> generalization performance.
>
> **2. `precision_composite` has no recall term, and cannot have one.**
> Every gold set is sampled *from claims the extractor already emitted*
> (`_meta.source_extraction` points at an output JSONL), so a claim the system **missed
> is invisible here by construction**. Measured recall is much lower — Tata 59.5%
> distinct-fact vs this harness's 96.1. Quote the pair, never the composite alone:
> `backend/scripts/run_recall.py`.
>
> **3. All 146 labels are single-annotator, self-labelled**, by the author of the system
> being measured, reading the extractor's own output. No second annotator, no Cohen's κ.
>
> **The fix for all three** is a gold set anchored to source text units rather than to
> extractor output — specified in [`docs/ANNOTATION_PROTOCOL.md`](../../docs/ANNOTATION_PROTOCOL.md).
> Until that lands, these sets remain useful as **regression gates** (their job in CI) and
> unsuitable as **evidence of generalization** (their job in a paper).

Gives ESGenuine's extraction pipeline a **number**. Before this, quality was
assessed by inspection only — so there was no way to prove a parser change
(the planned Docling table-parse swap, the quality gate, a 70B re-extraction)
actually helped. This is the measuring stick.

## Files
- `gold_set.json` — hand-labeled ground truth. Each record is one claim the
  extractor emitted, with the **correct** label read from its `source_sentence`.
  When the sentence is page furniture / a table-header fragment / a form
  question / bare numbers with a fabricated value, `is_esg_claim=false` (the
  extractor should never have emitted it).
- `../../scripts/run_evaluation.py` — the scorer.
- `../test_evaluation.py` — regression suite (pytest **and** standalone).

## Run
```bash
python backend/scripts/run_evaluation.py --report          # full per-claim detail
python backend/scripts/run_evaluation.py --json out.json   # machine-readable
```

## Metrics
| metric | what it measures |
|---|---|
| `candidate_precision` | of emitted claims, how many are real (not furniture/hallucination) |
| `aspect_node_acc` | exact normalized-aspect-node match, on real claims |
| `aspect_pillar_acc` | pillar match (emissions/social/water/…), looser bar |
| `value_acc` | \|x−gold\|/gold ≤ 5%, on real **non-ambiguous** numeric claims |
| `unit_base_acc` | unit canonicalizes to the same family |
| `type_acc` | performance / target / narrative match |
| **`precision_composite`** | 0–100 composite = mean of the five load-bearing rates. **No recall term** — see the banner. Emitted as `extraction_score` too, a deprecated alias kept so the CI gate and ablation harness keep working. |
| *(not computed here)* | recall, F1 — structurally impossible against a set sampled from output. Use `run_recall.py`. |

## Baseline — 2026-07-03 (v0.1 gold, 46 claims, pre-Docling)
```
candidate_precision  65.2%   (30/46 emitted claims are real)
aspect_node_acc      56.7%
aspect_pillar_acc    70.0%
value_acc            75.0%   (unambiguous only)
unit_base_acc        68.0%
type_acc             53.3%
PRECISION_COMPOSITE  63.6/100
```
**Read:** ~35% of emitted claims are not real claims (page footers with
fabricated values, table-header fragments, form questions) — the single biggest
lever, since a false claim poisons every downstream module (NLI, integrity
score, fact-check). The classic diversity→biodiversity mislabel (#19) and
Scope-1/Scope-3 confusion are both live in the sample.

## Matching & portability
Gold matches extraction by `claim_id`, falling back to normalized
`source_sentence`. Re-extraction changes claim_ids, so after the Docling swap:
re-run against the new claims JSONL. Sentences whose text is stable still match
by the fallback; genuinely new/changed sentences need re-labeling. The harness,
the labeling rubric (`gold_set.json._meta`), and the metrics are all reusable —
only the labels are extraction-specific.

## Expanding the gold set
Add records to `gold_set.json.claims` following `_meta.fields`. Target ≥100 for
a stable number. Prioritize the revealing classes: `uncategorized` (~30% of the
corpus), diversity vs biodiversity, scope confusion, waste vs water, and
page-furniture false positives.
