# Gold-Set Change Log

Every change to a gold **label** must be recorded here, with a section heading matching
`<filename> v<manifest version>`. `tests/test_gold_integrity.py` enforces this: the hash
manifest and this file are checked against each other, so a relabel cannot land without
a written reason.

**The rule:** ground truth must never drift toward the system it measures. A relabel is
legitimate when the *original annotation was wrong about the source text*. It is not
legitimate when it is merely bringing the label into line with a taxonomy the system just
gained. If a new ontology node makes an old label look outdated, that is a **mapping**
change — update the concept→node mapping, not the gold.

---

## gold_set.json v1
## gold_set_docling_tata.json v1
## gold_set_shell_v03.json v1

**2026-08-10 — baseline manifest.** Not a relabel. Records the hashes of the three gold
sets exactly as they stood when the tamper gate was introduced, so all subsequent changes
are visible.

Labels are recorded here in the state produced by the historical edits below, which
predate the gate and are documented for the record rather than reverted:

| commit | file | labels changed | what happened |
|---|---|---|---|
| `48555ea` 2026-07-11 | `gold_set_shell_v03.json` | 2 | Ontology round 2 added `emissions.methane` and `waste.recycled`; the same commit rewrote `emissions.methane_reporting → emissions.methane` and `waste.recycling → waste.recycled` in the gold, and reported the resulting 81.1 → 89.7 as "out-of-sample". |
| `95e1f20` 2026-07-19 | `gold_set_docling_tata.json` | 4 | Ontology round 3 added child nodes; the same commit rewrote `emissions.air_pollutants → .pm` (×2), `→ .sox`, and `social.diversity.gender → .female`. |

**Why these are not being reverted:** the sentences were verified at the time and the
revised labels are defensible readings of the source. The problem was never that any one
label is wrong — it is that the *measurement stopped being independent* of the system,
and that both sets are consequently development sets rather than held-out ones. Reverting
six labels would not restore independence; only a fresh, never-tuned-against set will.
See `docs/ANNOTATION_PROTOCOL.md`.

**Consequence for reporting:** the 96.1 (Tata) and 89.7 (Shell) figures are development
scores. They remain valid as CI regression floors and invalid as evidence of
generalization.
