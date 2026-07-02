# Extraction-Quality Evaluation Harness

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
| **`extraction_score`** | 0–100 composite = mean of the five load-bearing rates |

## Baseline — 2026-07-03 (v0.1 gold, 46 claims, pre-Docling)
```
candidate_precision  65.2%   (30/46 emitted claims are real)
aspect_node_acc      56.7%
aspect_pillar_acc    70.0%
value_acc            75.0%   (unambiguous only)
unit_base_acc        68.0%
type_acc             53.3%
EXTRACTION_SCORE     63.6/100
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
