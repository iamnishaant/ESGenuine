# Handoff roadmap — tasks needing credentials

> ## ✅ EXECUTED 2026-08-11 — results in [`CROSSCHECK_FINDINGS.md`](CROSSCHECK_FINDINGS.md)
>
> This document is kept as the record of what was asked. **Read the findings before
> re-running anything here.** Two corrections you need:
>
> - **P1's procedure is unsafe on a machine with a populated `.env`.** `LLMClient` builds a
>   round-robin pool from every NVIDIA/Groq/HF key and takes that path *instead of* the
>   OpenAI/Anthropic branch, so `OPENAI_API_KEY=...` never calls OpenAI, and the fixture
>   blends a 70B with two 8B models while the meta records whatever `OPENAI_MODEL` said.
>   `run_baselines.py` now requires `--provider` and refuses a heterogeneous pool. See
>   findings §2.
> - **P3's expected values all reproduced exactly** — nothing to flag. See findings §P3.
>
> A finding that was *not* on this roadmap outranks everything on it: the frozen
> "raw LLM" fixtures are not raw, which retracts §3.2 finding (ii). See findings §1.

**For:** the repo owner (holds `.env`, live Supabase, LLM API keys)
**From:** paper-readiness audit, 2026-08-10
**Deadline context:** ICMLDE 5.0 submission, 15 Aug 2026

Everything else in the paper pipeline runs **offline from committed fixtures** and is already
done. These four tasks are the only ones that need credentials or a live database.

**Total time: ~1 hour.** P0 is security and is independent of the paper. P1 is the only task
blocking the paper.

---

## P0 — Rotate the database password 🔴 *do this first, ~15 min*

### The problem

Three **tracked, committed** files hardcode the plaintext Postgres **superuser** password for
the live Supabase project:

```
backend/scripts/audit_pharos_db.py:5      conn_str = "postgresql://postgres:****@db.<ref>.supabase.co:5432/postgres"
backend/scripts/clean_suspicious_claims.py:3
backend/src/reasoning/run_nli_batch.py:14
```

Committed in `8587151` (2026-06-23, the initial commit) and never removed.

**Why this is severe:**

- It is the `postgres` **superuser**, not the `anon` role.
- **Superuser bypasses RLS.** The `2026-08-09_enable_rls.sql` migration, the demotion of
  `anon` to SELECT-only, the TRUNCATE fix — none of it constrains this credential.
- It is in **git history**, so removing the lines is not sufficient.

### Fix

1. **Rotate now.** Supabase Dashboard → Project Settings → Database → *Reset database
   password*. Do this before editing any code — the leaked value must stop working.

2. **Update `.env`** with the new `DATABASE_URL`.

3. **Remove the hardcoding.** In all three files replace the literal with:

   ```python
   import os
   CONN_STR = os.environ["DATABASE_URL"]   # KeyError beats a silent fallback to a leaked default
   ```

   Do not add a default value. A missing env var should crash loudly.

4. **Check for abuse.** Supabase Dashboard → Logs → Postgres. Look for connections from IPs
   you do not recognise, and for unexpected reads of `claims`.

5. **Decide on history.** Rotating makes the leaked value useless, which is the important
   part. Scrubbing history (`git filter-repo`) additionally removes the string but rewrites
   every commit hash and breaks existing clones. For a repo about to be published as a
   research artifact it is worth doing — but **only after** rotation, and coordinate it so
   collaborators re-clone.

6. **Sweep for others** before publishing:
   ```bash
   git grep -nE "postgresql://[^\"' ]*:[^\"'@ ]+@|sk-[A-Za-z0-9]{20,}|nvapi-|gsk_"
   ```

> ⚠️ Do not skip step 1 because the repo "might be private". The credential is in history,
> has been for seven weeks, and the repo is being prepared for public release.

---

## P1 — Frontier-model baseline 🔴 *the only task blocking the paper, ~30 min*

### Why it matters

Every comparison in the paper is currently the system against **itself** with components
removed. A reviewer's first question is: *does the deterministic repair layer still help
when the LLM underneath it is a frontier model, or is it patching a mid-tier model's
mistakes?* All committed fixtures were produced by `llama-3.3-70b`.

This fills the empty half of a 2×2:

|  | no repair | + repair |
|---|---|---|
| **llama-3.3-70b** | ✅ have | ✅ have |
| **frontier** | ❌ **need** | ❌ **need** |

Cost: roughly 25 + 5 API calls. Cents.

### Steps

```bash
git pull                      # the harnesses below are new — make sure you have them

python -m venv .venv
.venv\Scripts\activate                            # Windows
# source .venv/bin/activate                       # macOS/Linux
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
```

**Sanity check before spending anything** — expect `178 passed`:

```bash
cd backend && python -m pytest -m "not live" && cd ..
```

**Smoke test with 3 pages first** (verifies credentials and parsing before the full run):

```bash
set OPENAI_API_KEY=sk-...
set OPENAI_MODEL=gpt-4o
python backend/scripts/run_baselines.py --generate frontier --case tata --limit 3
```

Any of these providers works — pick whichever key you have:

| Provider | Env vars |
|---|---|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=<dated model id, not a -latest tag>` |
| NVIDIA NIM | `NVIDIA_API_KEY`, `NVIDIA_MODEL=<model>` |

> Use a **dated** model id, never a floating `-latest` tag. A floating tag makes the result
> unreproducible, and the paper claims reproducibility.

**If the smoke test printed claims, run both documents in full:**

```bash
python backend/scripts/run_baselines.py --generate frontier --case tata
python backend/scripts/run_baselines.py --generate frontier --case shell
python backend/scripts/run_baselines.py --markdown > baselines_frontier.md
```

### How to tell it worked

The harness refuses to run without credentials rather than silently falling back to the
rule-based extractor, so a "frontier" fixture that is nothing of the sort cannot be
produced. After a successful run:

- `backend/tests/eval/fixtures/baseline_frontier_tata.jsonl` exists and is non-empty
- `baseline_frontier_tata.meta.json` records the provider and the exact model id
- `run_baselines.py` output no longer says `[NOT RUN] frontier cells B0/B1 are missing`
  and instead prints a **2x2 INTERACTION** block

### Send back

- `baselines_frontier.md`
- both `baseline_frontier_*.jsonl` and `*.meta.json` files (commit them — they become
  frozen fixtures, so the result stays reproducible offline forever)
- the exact model id used

---

## P2 — Live corpus statistics 🟠 *~5 min*

The paper's §4.1 needs the real corpus description. A recent commit says *4 companies /
6 report cells / 1730 claims*; confirm it.

```python
# with .env loaded and the NEW rotated credentials
import os, collections, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("""
  SELECT company_name, report_year, count(*)
  FROM claims GROUP BY company_name, report_year ORDER BY company_name, report_year;
""")
rows = cur.fetchall()
for r in rows:
    print(r)
print("companies:", len({r[0] for r in rows}))
print("report cells:", len(rows))
print("total claims:", sum(r[2] for r in rows))
```

### Send back

That output verbatim, plus for each report: the **page count** of the source PDF and its
**disclosure format** (BRSR statutory / IR narrative / ESG datasheet). The paper's central
claim is that repair strategy depends on disclosure format, so the corpus must be
described in those terms.

---

## P3 — Capture the offline harness outputs 🟡 *~10 min, no credentials needed*

These already run and I have their numbers, but re-running on your machine confirms the
results reproduce outside my environment — which is worth one line in the paper.

```bash
python backend/scripts/run_ablation.py  --markdown > results_ablation.md
python backend/scripts/run_bootstrap.py --markdown -B 2000 > results_bootstrap.md
python backend/scripts/run_recall.py    > results_recall.txt
python backend/scripts/run_evaluation.py \
    --gold backend/tests/eval/gold_set_docling_tata.json \
    --extraction backend/tests/eval/fixtures/tata_docling_full.jsonl > results_eval_tata.txt
```

### Expected values — flag any mismatch, do not quietly overwrite

| Check | Expect |
|---|--:|
| Ablation Tata S5 | 96.1 |
| Ablation Shell S5 | 89.7 |
| Repair layer S1→S5 Tata | +24.6 |
| Repair layer S1→S5 Shell | +7.0 |
| Bootstrap CI, Tata composite | [93.5, 98.5] |
| Bootstrap CI, Shell composite | [85.3, 94.0] |
| Distinct-fact recall, Tata | 59.5% |
| Test suite | 178 passed |

A mismatch means something differs between our environments and we need to know **before**
the numbers go into a paper.

### Send back

All four output files.

---

## Return checklist

- [ ] **P0** — password rotated ✅ / hardcoded strings replaced ✅ / logs checked ✅
- [ ] **P1** — `baselines_frontier.md` + fixture files + `.meta.json` + model id
- [ ] **P2** — corpus query output + page counts + disclosure format per report
- [ ] **P3** — four results files, expected values confirmed or mismatches flagged

**Please do not:**

- edit anything in `backend/tests/eval/gold_set*.json` — a CI gate
  (`test_gold_integrity.py`) will fail the build if a label changes, and it is there
  deliberately: ground truth must not drift toward the system it measures
- commit `.env`, or any file containing the new password
- re-run the *extraction pipeline* over the corpus. The committed fixtures are what every
  number in the paper is computed from; regenerating them invalidates the whole results
  section four days before a deadline

---

## What happens after this comes back

| | |
|---|---|
| P1 → | §5.5 Baselines gets written around whatever the 2×2 actually shows |
| P2 → | §4.1 `[FILL]` resolved |
| P3 → | one sentence confirming independent reproduction |
| P0 → | unblocks publishing the repo as an artifact |

Remaining work that needs **neither** credentials nor the friend:

1. **Related work** — currently zero citations. Highest acceptance risk at a 3-reviewer
   venue. ~2 hours: ClimateBERT, Climate-FEVER, ClimaText, ESG-BERT, plus the ESG
   rating-divergence literature for motivation.
2. **Procedia CS template** — download from CMT and write directly into it.
3. **Sections 1–3, 7** — §4–6 are drafted in `docs/PAPER_DRAFT_SECTIONS.md`.
4. **Anonymise** — double-blind: no repo URL, no names, no institution in the PDF.
