# Handoff return — answers to `HANDOFF_ROADMAP.md`

**From:** the machine holding `.env`, the live Supabase project and the LLM keys
**Date:** 2026-08-12 · **Branch:** `paper/icmlde-evaluation`
**Full detail:** [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md)

---

## Your checklist

| | Item | Status |
|---|---|---|
| ⚠️ | **P0** — rotated / code fixed / logs checked | **code fixed ✅ · rotation NOT DONE · logs NOT CHECKED** |
| ✅ | **P1** — `baselines_frontier.md` + fixtures + `.meta.json` + model id | done, **with a null result — read §"P1" below** |
| ✅ | **P2** — corpus numbers + page counts + format per report | done, your provisional figures were exact |
| ✅ | **P3** — the results files, expected values confirmed | **all 8 values reproduced to the decimal** |

Your three "please don't"s were all respected, verified mechanically:

```
gold_set*.json ............ UNTOUCHED (zero diff, and test_gold_integrity still passes)
corpus extraction ......... NOT re-run (shipped fixtures + docling caches untouched)
.env / password ........... never committed
```

---

## P0 — **the two parts only you can do are still open** 🔴

The code is fixed (`ba4f102`): all three files now read `os.environ["DATABASE_URL"]` with no
default. Verified working — `audit_pharos_db.py` connects and reports 1730 claims.

**But the credential is still live.** The literal in those files was byte-identical to the
one in the working `.env`, and it authenticated successfully during this audit. Rotation is
what makes it inert and it has not happened.

> **Your advice to delay the commit is now moot.** `HANDOFF_ROADMAP.md` is itself committed
> and pushed, and it names all three files with line numbers. Anyone with repo access
> already has the map. There is no longer any disclosure cost to weigh against fixing it —
> only rotation matters now.

Still outstanding: **rotate**, update `.env`, **check Supabase → Logs → Postgres**, and
change the password anywhere else that pattern was reused (it looks personal).

**Unrelated, minor, no action needed:** `.env` was committed once in `9338e89` (Jan 2026,
gpt-engineer scaffold, lives only on the stale `origin/main`). It contained only the three
`VITE_SUPABASE_*` frontend values — publishable keys, public by design — and that anon key
has since been superseded. Not a leak. Flagged only so it doesn't surprise you later.

---

## P1 — done, and the answer is a null 🟠

**Model id: `openai/gpt-oss-120b`** (NVIDIA NIM), against incumbent
**`meta/llama-3.3-70b-instruct`**. `max_tokens=8000`, `temperature=0.1`, single-provider
pool. Deliverable: [`results/baselines_frontier.md`](results/baselines_frontier.md).

### Your procedure would have produced a mislabelled fixture — do not re-run it as written

`LLMClient` builds a round-robin pool from **every** NVIDIA/Groq/HF key in `.env` and takes
that path *instead of* the OpenAI branch. On this machine your command would have:

- never called OpenAI at all (the OpenAI branch sits behind the pool check);
- blended `llama-3.1-8b-instant` + `Llama-3.1-8B-Instruct` + `llama-3.3-70b` into one file;
- written `"model": "gpt-4o"` into the meta over llama output.

Your own `reingest_corpus.py:33-38` already blanks Groq/HF for this reason. `run_baselines.py`
now requires `--provider` and refuses a heterogeneous pool. **Four extra fixtures exist
because of this**; see Finding 2.

### The 2×2 also compared two different code paths

The A row was the **shipped** fixture (full-document, text + tables); the B row is
table-only. Scored against a table-cell denominator that is not a model comparison — on
Shell it was **13 table claims against 191**. Fixed by generating a matched incumbent arm.
See Finding 3.

### Result — extractor choice dominates the tabular surface

Page-matched (only pages both arms produced claims for):

| Document | Extractor | Fact recall | Grounding |
|---|---|--:|--:|
| BRSR | llama-3.3-70b | 41.2% | 68.3% |
| BRSR | **gpt-oss-120b** | **97.2%** | **99.1%** |
| IR | llama-3.3-70b | 44.1% | 100% |
| IR | **gpt-oss-120b** | **89.8%** | 100% |

**31.7%** of the incumbent's emitted values on the BRSR do not occur on the page they cite,
against **0.9%** for gpt-oss-120b. That is the misattribution class the source-value check
exists to catch, ~30× rarer in the newer model.

### 🔴 The 2×2 does **not** answer "does repair survive a better model"

Structural, not a failed run. Recall and grounding read only a claim's value and page, so
they see the layer **only where it adds, removes or rewrites a claim** — and its one such
action, the furniture filter, removes **0** claims at **both** tiers, because form furniture
is a full-document artifact absent from table-only extraction. The gold composite, where
aspect/type/unit corrections *would* land, matches **2%** and **0%** of the two arms. No
lane is both sensitive to the layer and comparable across extractors.

**§3.5 reports this as a null.** Please don't let it become "repair survives" in the prose.

### 🔴 And do **not** write "the gain is absorbed by scale" either

The one cross-model-comparable measurement points the other way — the gate's taxonomy
intervention rate **rises** with the stronger model:

| | BRSR | IR |
|---|--:|--:|
| gate alters taxonomy, llama-3.3-70b | 15.4% | 0% |
| gate alters taxonomy, gpt-oss-120b | **37.7%** | **20.9%** |

Intervention ≠ improvement, so it settles nothing — but it rules out the tidy story.

Both arms are **single runs at temperature 0.1**; no variance estimate exists.

---

## P2 — corpus ✅ your provisional numbers were exact

**4 companies · 6 reports · 461 PDF pages · 1730 claims.** `reports.claim_count` agrees
row-for-row.

| Company | Year | Claims | Pages | Format |
|---|--:|--:|--:|---|
| Infosys | 2023 | 249 | 65 | ESG report (narrative + datasheet annex) |
| Infosys | 2025 | 242 | 77 | ESG report (narrative + datasheet annex) |
| Microsoft | 2024 | 278 | 88 | IR narrative + data appendix |
| Shell | 2022 | 247 | 91 | IR narrative |
| Shell | 2023 | 379 | 98 | IR narrative |
| Tata Power | 2024 | 335 | 42 | **BRSR statutory** |

**Two things to be careful about in §4.1:**

1. **The draft claimed the corpus spans "tabular ESG datasheets". It does not.** The two bp
   datasheets in `backend/ESG_Reports/` are **not ingested** — no claims, no `reports` row.
   That clause is removed.
2. **The two documents you evaluate are the corpus's easiest.** Uncategorized share is
   23.0% and 24.7% for them, against **52.2%** and **53.3%** for the two Infosys reports.
   Absolute scores are an upper region of the corpus range, and §4.1 and the limitations now
   say so. A reviewer would have found this.

---

## P3 — ✅ all 8 expected values reproduced exactly

Second machine, different OS, fresh dependency install. **Nothing to flag.**

| Check | Expected | Observed |
|---|--:|--:|
| Ablation Tata / Shell S5 | 96.1 / 89.7 | **96.1 / 89.7** ✅ |
| S1→S5 Tata / Shell | +24.6 / +7.0 | **+24.6 / +7.0** ✅ |
| Bootstrap CI Tata / Shell | [93.5, 98.5] / [85.3, 94.0] | **identical** ✅ |
| Distinct-fact recall Tata | 59.5% | **59.5%** ✅ |
| Test suite | 178 passed | **178 passed** ✅ |

Every paired delta and per-metric CI also matched to the decimal, as did the 43.1% no-LLM
floor, grounding 87.4→89.2, and the −5.5pp recall trade. Files in [`results/`](results/).

---

## 🔴 Things to be cautious of before you write

1. **§3.2 finding (ii) is retracted.** The frozen fixtures are **not** raw LLM output — they
   carry `type_fixed` (157 rows), `scope_fixed`, `aspect_fixed` from an older `apply_gate`,
   and `claim_extractor.py:862-868` applies FY repair and the value-in-table check *before*
   writing. So S2/S3 read ≈0 because **they already ran**, not because they contribute
   nothing. Say "not identifiable", never "ineffective" — this is greppable in the artifact.
   *(Findings (i) and (iii) are unaffected; the deltas are conservative.)*
2. **The cost figure changed: 0.58 → 0.45 ms/claim.** The old number had **no harness** — it
   was prose only, the one figure §6 could not regenerate. `run_cost.py` now measures it.
   It is hardware-dependent; quote the order of magnitude, not the digits.
3. **Regenerating figures used to not update the ones the paper compiles.** `main.tex` reads
   `docs/paper/figures/`; `make_figures.py` wrote only `docs/figures/`. Now mirrored. The
   committed binaries were left byte-identical on purpose — every value behind them
   reproduced, so re-rendering on a different matplotlib/font stack would only risk the
   colourblind properties you validated.
4. **CI never ran on this branch** until `e907777`. The gold-set tamper gate lives here and
   was unguarded on push. It runs now — expect it to actually gate you.
5. **Never quote a gold composite with a thin match rate.** The matched llama arm scores
   "100.0" off a **2% match** — one claim. `--markdown` now renders those as
   `n/a (match 2%)` so the warning travels with the number into whatever you paste.
6. **Both gold sets remain development sets**, and no held-out set exists. Unchanged from
   your assessment — restating because it bounds every absolute number in §3.

---

## Still the biggest risk, and it needs neither keys nor me

**Related work — zero citations.** At a three-reviewer venue that reads as not knowing the
field, regardless of how good the evaluation is. It is ~2 hours and it moves acceptance odds
more than anything else remaining.
