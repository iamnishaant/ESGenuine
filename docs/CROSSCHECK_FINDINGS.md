# Cross-check of the paper-readiness audit

**What this is:** the credentialed half of `HANDOFF_ROADMAP.md`, executed on the machine that
holds `.env`, the live Supabase project and the LLM keys — plus a re-verification of the
offline half that the roadmap said to confirm rather than assume.

**Date:** 2026-08-11 · **Branch:** `paper/icmlde-evaluation`

Two things came back clean, two did not. The two that did not are both *upstream of numbers
already written into the paper*, so they are listed first.

---

## Summary

| | Task | Result |
|---|---|---|
| 🔴 | **P0** password rotation | leak **confirmed live**; code fixed here, **rotation still outstanding — owner action** |
| 🟠 | **P1** frontier baseline | roadmap procedure was **unsafe on a populated `.env`**. Harness hardened, then run: **extractor choice dominates the table surface**, but the 2×2 **cannot** answer whether repair survives a model upgrade — reported as a null. |
| ✅ | **P2** corpus statistics | collected; roadmap's provisional figures confirmed exactly |
| ✅ | **P3** offline harnesses | **all 8 expected values reproduce exactly** |
| 🔴 | *(new)* fixture provenance | **the frozen "raw LLM" fixtures are not raw.** Retracts one published finding. |
| 🔴 | *(new)* 2×2 design | **the A and B rows came from different code paths.** Plus a verdict bug that printed a conclusion the numbers contradict. |
| 🟠 | *(new)* metered runs | generation never used the repo's own checkpoint, so any failure discarded every completed page |
| 🟠 | *(new)* cost figure | 0.58 ms/claim had **no harness**; measured 0.45 ms/claim, harness added |
| 🟡 | *(new)* figure pipeline | regenerating figures never updated the copies `main.tex` compiles |
| 🟡 | *(new)* CI coverage | CI did not run on `paper/**` — the gold-set tamper gate was unguarded |

---

## Finding 1 — the frozen fixtures are not raw LLM output 🔴

**This was not on the roadmap and it outranks everything on it.**

`PAPER_README.md` §3.2 describes the ablation as *"Six cumulative stages over frozen raw LLM
output"*, and `run_ablation.py` documents S0 as *"no deterministic layer at all … the honest
'what did the model alone produce' condition. THE BASELINE."*

Neither is true of the committed fixtures. Both carry the deterministic layer's own output:

```
tata_docling_full.jsonl   n=373     shell_2022_raw.jsonl   n=247
  type_fixed          157             type_fixed          152
  value_not_in_source  86             value_not_in_source  36
  scope_fixed          21             scope_fixed          13
  implausible_unit     11             implausible_unit      9
  value_not_in_table    9             aspect_fixed          8
                                      gender_fixed          1
```

`type_fixed`, `scope_fixed`, `aspect_fixed` and `gender_fixed` are emitted **only by
`apply_gate`** — the S4 stage. `normalized_aspect` also disagrees with a fresh
`normalize_aspect(aspect)` on 67/373 (Tata) and 44/247 (Shell) rows, always in the direction
of a *more specific* node (`social.health_safety.ltifr` where a replay yields
`social.health_safety`) — i.e. the gate's aspect repair had already fired before the freeze.

Independently, `claim_extractor.py:862-868` applies `fix_fy_column` (S2) and appends
`value_not_in_table` (S3) **at extraction time**, before anything is written to disk.

So the fixtures are the shipped extractor's output *after an older revision of the very
repair layer being measured*. The ablation resets three fields (`quality_flags`,
`framework_tags`, `normalized_aspect`) and replays the current stack over the rest.

### What this does and does not break

**Does not break — the headline result survives.** The stages are still scored on identical
claims, so the paired deltas remain internally valid, and they are *conservative*: the S0
baseline is already partly repaired, so **+24.6 / +7.0 understate the repair layer** rather
than flattering it. The central regime-dependence claim (gate carries the statutory filing,
taxonomy carries the narrative report; intervals non-overlapping) is unaffected.

**Does break — finding (ii).** `PAPER_README.md` §3.2 currently reads:

> **(ii) Only two of five components pay for themselves.** FY repair and value-in-table are
> indistinguishable from zero on both documents.

That inference is not supported. S2 and S3 measure ≈0 because **those operations had already
been applied before the fixture was frozen** — a fresh `fix_fy_column` pass still moves only
3 values on Tata and 0 on Shell, which is the residual between an old and current revision,
not the value of the stage. The honest statement is that **their contribution is not
identifiable from these fixtures.** Claiming they are worthless is a claim the data cannot
support, and it is the kind of over-reach a reviewer can check by grepping the artifact.

### Recommended wording changes

1. Rename S0 in prose from *"raw LLM"* to **"no taxonomy layer"**, and state that the
   fixtures are shipped-extractor output with the taxonomy fields reset.
2. Replace finding (ii) with: *FY-column repair and the value-in-table check were applied
   before the fixtures were frozen, so the ablation cannot attribute a contribution to them;
   they are reported as not identifiable, not as ineffective.*
3. Keep §3.2's remaining findings (i) and (iii) unchanged — both hold.
4. Add to the limitations list: *the ablation's baseline is a reconstruction, and is
   therefore a lower bound on the repair layer's contribution.*

**Do not regenerate the fixtures to fix this.** The roadmap is right that re-extracting days
before a deadline is the larger risk. Disclosure costs a paragraph; regeneration costs the
results section.

---

## Finding 2 — P1's procedure would have produced a mislabelled fixture 🟠

The roadmap's P1 says: set `OPENAI_API_KEY` / `OPENAI_MODEL=gpt-4o`, run
`run_baselines.py --generate frontier`. On a machine with a populated `.env` that silently
does the wrong thing, in two compounding ways.

`LLMClient.__init__` (`claim_extractor.py:208-221`) builds a **round-robin pool** from every
`NVIDIA_*`, `GROQ_*` and `HF_*`/`HUGGING_FACE_*` key it can find, and `extract()` takes the
pool path whenever that pool is non-empty. Therefore:

1. **The OpenAI and Anthropic branches are unreachable when any pool key exists.** They are
   only consulted after `if self.endpoints:` falls through. Setting `OPENAI_API_KEY` on this
   machine would never have called OpenAI.
2. **The pool is heterogeneous**, so the fixture blends models. Running the roadmap's command
   verbatim here selects:

   ```
   providers: groq, hf, nvidia
   models   : llama-3.1-8b-instant, meta-llama/Llama-3.1-8B-Instruct, meta/llama-3.3-70b-instruct
   ```

   Two 8B models and a 70B, round-robined across pages of one document.

3. **The recorded metadata would have been wrong, not merely absent.** `generate()` chose the
   `model` string by env precedence (`OPENAI_MODEL or … or NVIDIA_MODEL`), not from the
   endpoint actually called — so the meta would have read `"model": "gpt-4o"` over claims
   produced by llama. The docstring's promise that *"a 'frontier' fixture that is nothing of
   the sort cannot be produced"* did not hold: the guard tested `not probe.endpoints and
   provider == "fallback"`, which is the opposite of the real failure mode.

This hazard is already known elsewhere in the repo — `reingest_corpus.py:33-38` blanks the
Groq/HF keys for exactly this reason (*"8B = quality pollution"*). The baseline harness,
whose entire purpose is attributing a difference to the model, lacked the same discipline.

### Fix applied

`run_baselines.py` now has:

- `--provider {nvidia,groq,hf,openai,anthropic}` — blanks every other provider's pool vars
  (blank, not pop: imported modules re-run `load_dotenv()`, which would repopulate a missing
  key but leaves an empty one alone), applied *after* the import that triggers `load_dotenv`;
- a **heterogeneous-pool guard** that refuses to generate when the configured pool spans more
  than one model, printing the providers and models it found;
- `model` in the meta now read from the endpoint that will actually be called, plus new
  `pool_providers` / `pool_models` / `pool_size` / `isolated_provider` fields so the fixture
  is self-describing.

---

## Finding 3 — the 2×2 compared two different code paths 🔴

*Found while executing P1. It invalidates the harness's headline output, not just a
number, so it is reported before the smaller items.*

`run_baselines.run()` built the **A row** (`A0/A1 llama`) from the **shipped fixture** and
the **B row** from the **generated fixture**. Those come from different pipelines:

| fixture | claims | table | text | pages | gate flags |
|---|--:|--:|--:|--:|--:|
| `tata_docling_full.jsonl` (A) | 373 | 179 | 194 | 29 | 178 |
| `baseline_frontier_tata.jsonl` (B) | 451 | **451** | 0 | 27 | 0 |
| `shell_2022_raw.jsonl` (A) | 247 | **13** | 234 | 50 | 174 |
| `baseline_frontier_shell.jsonl` (B) | 191 | **191** | 0 | 4 | 0 |

The shipped fixtures are full-document runs (text **and** tables, with that run's own page
coverage). A generated fixture comes from `extract_from_table_markdown` over the cached
pages — table surface only. Both are then scored against a **table-cell** recall
denominator. On Shell that is **13 table claims against 191**: the resulting 9.2% vs 89.7%
gap measures which claims are in each file, not which model produced them.

Two further asymmetries compound it:

- The shipped fixtures carry 178 / 174 `apply_gate` flags (Finding 1); a generated fixture
  carries none. So `_no_repair` does not produce the same condition on the two rows — the A
  row's "no repair" is already gate-repaired, the B row's genuinely is not.
- The shipped run used `max_tokens=3000`; the frontier run needed 8000. Different budget.

The module docstring states that generation *"extracts from the COMMITTED page markdown …
so the input is byte-identical across systems and the only variable is the model."* That
holds for a generated fixture against itself. It does **not** hold for the comparison the
harness actually printed, which is the one a reader would quote.

### Fix applied

The A row now comes from `baseline_incumbent_<case>.jsonl` — the incumbent model driven
through the *identical* code path, pages and token budget as the frontier run, so the model
is the only variable. The shipped fixture is retained as a clearly-labelled `S` row for
context and is never differenced. When no matched arm exists, the harness prints an
`[UNMATCHED ARMS]` warning and withholds the interaction term instead of printing an
uninterpretable one.

### And a verdict bug in the same function

`_print_interaction` decided the headline with `interaction > -0.02 -> "repair SURVIVES the
model upgrade"`. That fires on a *positive* interaction regardless of how it arose. In the
run that actually occurred — repair costing llama **−5.5pp** of recall and doing **0.0pp**
for the frontier model — the interaction is **+5.5pp**, and the harness duly printed
"repair SURVIVES", a conclusion its own two numbers contradict. The verdict now reads the
sign of each tier's delta, and distinguishes *helps both* / *helps only one* / *costs* /
*inert*.

A second clarification was added to the same block: L1 and L2 read only `metric.value` and
`page_number`, so they see the repair layer **only where it adds, removes or rewrites a
claim**. Aspect, type and unit corrections are invisible to them by construction. A zero
delta there is not evidence the gate did nothing — only that it did nothing *these lanes
can see*. Without that note the natural misreading is that the gate is worthless.

---

## Finding 4 — metered generation threw away completed work on any failure 🟠

The repo contains `backend/src/extractors/checkpoint.py`, written for precisely this
situation:

> *Without checkpointing, a single crash — a network read-timeout, a bad-JSON reply … a
> re-run RESUMES — units already in the checkpoint are skipped, not re-paid for.*

`extract_from_table_markdown` takes a `checkpoint_path`, records every **completed** page,
and deliberately does **not** record a failed one, so a resume re-pays only for what broke.
`run_baselines.generate()` never passed it.

The consequence, observed twice on 2026-08-11: an incumbent run over 40 pages lost 14 pages
to a DNS failure late in the run, and every one of the 26 pages that had already succeeded
was discarded with them. The same run had to be started from zero afterwards. For the one
part of the eval stack that costs money and wall-clock time, an unrelated failure at the
end destroyed all of it.

Fixed: `generate()` now checkpoints to `fixtures/.ckpt_<tag>_<case>.jsonl` (gitignored —
the fixture is the artifact, this is only crash insurance).

### The write guard, corrected

An earlier version of the guard added in this session counted **pages that produced zero
claims**. That conflates two different things, and the numbers show how badly: on the
frontier Tata run 13 of 40 pages were empty but only **2** had failed — the other 11 hold
no extractable numeric table at all. A ceiling tight enough to catch the broken run would
have rejected the good one.

The extractor already tracks `failed_units`, the count of pages whose call exhausted its
retries. The guard now uses that, and the meta records `failed_pages`,
`pages_with_claims` and `pages_without_claims`, so anything scoring a fixture can see how
much of the document it actually reached rather than reading a lost page as "the model
found nothing here".

---

## Finding 5 — the cost number had no harness behind it 🟠

`PAPER_README.md` §3.3 and `main.tex` quote **0.58 ms/claim, 218 ms per report**. §6 claims
every reported number recomputes from committed fixtures. That was true of every number
except this one: nothing in the repo produced it. `grep -r "0\.58"` matches only prose.

Measured properly here with a new `backend/scripts/run_cost.py`:

| document | claims in → out | layer runtime | per claim |
|---|--:|--:|--:|
| BRSR statutory | 373 → 339 | 168 ms | **0.45 ms** |
| IR narrative | 247 → 247 | 105 ms | **0.43 ms** |

Best of 15 runs, single-threaded. Timed: ontology + key refresh + FY repair + value-in-source
+ gate + furniture filter. Not timed: the LLM call (the point), PDF parsing (upstream and
cached), and the harness's own deep copies.

The original figure is the same order of magnitude, so nothing in the argument changes — but
it is hardware-dependent and was unverifiable. Both documents now quote the measured value,
cite the harness, and make the load-bearing claim the order of magnitude
("sub-millisecond per claim") rather than the digits.

---

## Finding 6 — regenerating figures did not update the ones the paper compiles 🟡

`main.tex` does `\includegraphics{figures/…}` relative to `docs/paper/`, so the PDFs the
paper actually builds from live in **`docs/paper/figures/`**. `make_figures.py` wrote only to
**`docs/figures/`**. The second set was a manual copy.

So the guarantee in §4 — *"values are computed from the fixtures at render time, so a figure
can never drift from the results table"* — did not hold for the figures in the PDF. A rerun
would update `docs/figures/` while the paper kept compiling the old copies, silently.

`make_figures.py` now mirrors each PDF into `docs/paper/figures/` after writing it.

The committed figures were **left byte-identical on purpose.** Every value behind them
reproduced exactly (§P3), so there was no numerical reason to regenerate, and re-rendering on
a different matplotlib and font stack would have churned the binaries and risked the
colourblind/greyscale properties that were validated when they were made.

---

## Finding 7 — CI did not run on the paper branch 🟡

`.github/workflows/ci.yml` triggered on push to `[V2, main, ESG_V1]`. `paper/icmlde-evaluation`
was not among them, so pushes to it ran no CI — including `test_gold_integrity.py`, the
gold-set tamper gate added on this very branch. The one branch where ground truth must not
drift was the one branch not checking it. (`pull_request` is unfiltered, so PRs were covered;
direct pushes were not, and this branch is being pushed to directly.)

Fixed: the trigger list now includes `"paper/**"`.

---

## P0 — credential leak 🔴 confirmed, rotation still outstanding

Verified exactly as described. The plaintext Postgres **superuser** password was present in
three tracked files since the initial commit:

- `backend/scripts/audit_pharos_db.py:5`
- `backend/scripts/clean_suspicious_claims.py:3`
- `backend/src/reasoning/run_nli_batch.py:14`

**The credential was still live at the time of this audit** — the value in the three files is
byte-identical to the one in the working `.env`, and a connection using it succeeded. So the
leak is not historical; it is current.

Two aggravating details beyond the roadmap's account:

- The password follows an obvious personal pattern (a name, a year, digits). If it is reused
  anywhere else, rotating Supabase alone is not sufficient.
- Superuser bypasses RLS, so `2026-08-09_enable_rls.sql` constrains nothing against a holder
  of this credential — as the roadmap says.

### Done here

All three literals replaced with `os.environ["DATABASE_URL"]` — no default, so a missing var
raises `KeyError` rather than silently reaching for a stale constant. Verified working
(`audit_pharos_db.py` connects and reports 1730 claims). The tracked tree is now clean:

```
git grep -nE "postgresql://[^\"' ]*:[^\"'@ ]+@"   ->  only .env.example placeholders
```

### Still outstanding — owner action, cannot be scripted

1. **Rotate** in Supabase → Settings → Database → Reset database password.
2. Update `DATABASE_URL` in `.env`.
3. Review Supabase → Logs → Postgres for unrecognised connections.
4. Change the password anywhere else the same pattern was used.

The value remains in git history regardless; rotation is what makes it inert.

---

## P1 — matched-extractor baseline ✅ run, with an explicit null

Completed 2026-08-12 after the harness fixes in Findings 2–4. Four fixtures, all frozen and
committed, all from a single-provider NVIDIA pool at `max_tokens=8000`, `temperature=0.1`,
generated from the committed Docling markdown:

| arm | model | claims | pages | failed |
|---|---|--:|--:|--:|
| incumbent BRSR | `meta/llama-3.3-70b-instruct` | 319 | 40 | 4 |
| frontier BRSR | `openai/gpt-oss-120b` | 451 | 40 | 2 |
| incumbent IR | `meta/llama-3.3-70b-instruct` | 102 | 5 | 0 |
| frontier IR | `openai/gpt-oss-120b` | 191 | 5 | 0 |

`nvidia/nemotron-3-ultra-550b-a55b` was tried first and rejected: it failed 15–20% of pages
on malformed JSON, which would have depressed its recall for formatting reasons rather than
extraction quality. `gpt-oss-120b` is a larger open-weight model, **not** a closed frontier
system, and the paper says so.

### Result 1 — extractor choice dominates the tabular surface

Page-matched (only pages both arms produced claims for, so a transport failure cannot read
as a model finding nothing):

| Document | Extractor | Fact recall | Grounding |
|---|---|--:|--:|
| BRSR | llama-3.3-70b | 41.2% | 68.3% |
| BRSR | **gpt-oss-120b** | **97.2%** | **99.1%** |
| IR | llama-3.3-70b | 44.1% | 100% |
| IR | **gpt-oss-120b** | **89.8%** | 100% |

The grounding line is the sharper one: **31.7%** of the incumbent's emitted values on the
statutory filing do not occur on the page they cite, against **0.9%** for the newer model —
roughly thirty times rarer. That is exactly the misattribution class the layer's
source-value check was built for.

### Result 2 — the 2×2 does not answer the question it was built for 🔴

**Reported as a null, not inferred around.** Fact recall and grounding read only a claim's
value and page, so they observe the deterministic layer solely where it *adds, removes or
rewrites* a claim. Its one such action on this path — the furniture filter — removes **0**
claims at **both** tiers, because statutory form furniture is an artifact of full-document
extraction and does not arise in table-only extraction. The gold composite, where the
layer's aspect/type/unit corrections *would* register, matched **2%** and **0%** of the two
arms: it was sampled from the shipped extractor's own output and cannot score another
model. No lane is both sensitive to the layer and comparable across extractors.

So "does the repair delta survive a better model" remains **unanswered**, and both the paper
and this document say so.

### Result 3 — but not because the gain is absorbed by scale

The one measurement that *is* comparable across models points the other way. The gate's
taxonomy intervention rate **rises** with the stronger extractor:

| | BRSR | IR |
|---|--:|--:|
| gate alters taxonomy, llama-3.3-70b | 15.4% | 0% |
| gate alters taxonomy, gpt-oss-120b | **37.7%** | **20.9%** |

An intervention is not evidence of an improvement, so this settles nothing — but it is
inconsistent with the layer simply being absorbed by a better model, and that convenient
story should not be told.

**Caveat carried into the paper:** both arms are single runs at temperature 0.1. There is no
variance estimate, so only the large gaps are rested on.

Harnesses: `run_baselines.py`, `run_page_matched.py`, `run_gate_workload.py`; outputs under
`docs/results/`.

---

## P2 — corpus statistics ✅

The roadmap's provisional figure (*4 companies / 6 report cells / 1730 claims*) is **exactly
right**. `reports.claim_count` agrees with the per-report `claims` counts row for row.

| Company | Year | Claims | Source PDF | Pages | Claim page span | Disclosure format |
|---|--:|--:|---|--:|--:|---|
| Infosys | 2023 | 249 | `infosys-esg-report-2022-23.pdf` | 65 | 2–64 | ESG report (narrative + datasheet annex) |
| Infosys | 2025 | 242 | `infosys-esg-report-2024-25.pdf` | 77 | 3–76 | ESG report (narrative + datasheet annex) |
| Microsoft | 2024 | 278 | `Microsoft-2024-Environmental-Sustainability-Report.pdf` | 88 | 2–87 | IR narrative + data appendix |
| Shell | 2022 | 247 | `shell-sustainability-report-2022.pdf` | 91 | 4–91 | IR narrative |
| Shell | 2023 | 379 | `shell-sustainability-report-2023.pdf` | 98 | 4–96 | IR narrative |
| Tata Power | 2024 | 335 | `business-responsibility-and-sustainability-report-2023-24.pdf` | 42 | 1–42 | **BRSR statutory** |

**Totals: 4 companies · 6 reports · 461 PDF pages · 1730 claims.**

Every report's claim page span is bounded by its PDF page count, which independently confirms
the file↔row mapping (the DB stores no `file_path`).

Two corpus facts worth stating in §4.1, both of which support the paper's framing:

- **Exactly one report in the corpus is a statutory filing.** The BRSR/narrative contrast that
  carries the paper's central claim is *n=1 per regime*. §5's "two documents" limitation
  already says this; §4.1 should not accidentally imply a broader corpus.
- `backend/ESG_Reports/` also holds two **bp ESG datasheets** (15 and 16 pp) which are **not
  ingested** — no claims, no `reports` row. The third disclosure format named in the roadmap
  is therefore absent from the corpus; do not describe it as covered.

Supporting distributions:

| | |
|---|---|
| claim types | performance 1263 · narrative 370 · target 97 |
| carrying a numeric value | 1394 / 1730 (80.6%) |
| pillars | uncategorized 598 · social 427 · emissions 238 · energy 174 · water 149 · waste 88 · biodiversity 46 · governance 10 |
| `uncategorized` share | Tata 23.0% · Shell'22 24.7% · MSFT 23.7% · Shell'23 35.6% · Infosys'23 52.2% · Infosys'25 53.3% |

That last row is a live finding: **the taxonomy covers the two evaluated documents far better
than it covers the two Infosys reports** (23–25% vs 52–53% uncategorized). Both evaluated
documents sit at the favourable end of the corpus. That belongs in the limitations section —
it is precisely the generalization question a reviewer will raise, and stating it first is
cheaper than being caught by it.

---

## P3 — offline harnesses ✅ all reproduce exactly

Re-run from a clean venv on Windows / Python 3.11.8. **Every expected value matched; nothing
to flag.**

| Check | Expected | Observed |
|---|--:|--:|
| Ablation Tata S5 | 96.1 | **96.1** ✅ |
| Ablation Shell S5 | 89.7 | **89.7** ✅ |
| Repair layer S1→S5 Tata | +24.6 | **+24.6** ✅ |
| Repair layer S1→S5 Shell | +7.0 | **+7.0** ✅ |
| Bootstrap CI, Tata composite | [93.5, 98.5] | **[93.5, 98.5]** ✅ |
| Bootstrap CI, Shell composite | [85.3, 94.0] | **[85.3, 94.0]** ✅ |
| Distinct-fact recall, Tata | 59.5% | **59.5%** ✅ |
| Test suite | 178 passed | **178 passed, 1 deselected** ✅ |

Every paired ablation delta and per-metric CI in §3.1/§3.2 also reproduced to the decimal.
Outputs committed under `docs/results/`.

The reproduction claim in §6 is therefore stronger than stated: it holds on a second machine,
a different OS, and a fresh dependency install. One correction to §6's wording — it says
*"this whole audit ran with no `.env` present"*; that is true of the original audit, but the
harnesses do read a `.env` if one exists (`claim_extractor.py:25` calls `load_dotenv()` at
import). They do not *use* it offline, but the claim is best phrased as "requires no
credentials" rather than "ran with none present".

Minor drift, cosmetic: `run_ablation.py --markdown` still prints the column header
`EXTRACTION_SCORE` although `46364fd` renamed the metric to `precision_composite`
(`run_bootstrap.py` prints the new name). Worth aligning before the artifact is published.
