> # ⚠ UNIMPLEMENTED DESIGN NOTE — DO NOT CITE AS THE SYSTEM'S METHOD
>
> **Status: never built.** Nothing on this page exists in the codebase. Grepping
> `backend/src/` for `Integrity_Gap`, `w_C`, `w_E`, `CVE_score` or `uncertainty_penalty`
> returns zero hits. There is no per-claim integrity gap, no CVE term, and no
> uncertainty penalty anywhere in the running system.
>
> **What actually ships** is a different formula, at document level rather than per
> claim, in [`src/reasoning/integrity_report.py`](../../src/reasoning/integrity_report.py)
> (`_score_flags`, report version 2.3):
>
> ```
> score = 100 − Σ over flags ( severity_weight × prevalence )
>         severity_weight = {Critical: 50, High: 30, Medium: 16, Low: 6}
>         prevalence      = claims_triggering_flag / total_claims
>                           (structural flags use a fixed 0.5)
> ```
>
> Fact-check and satellite evidence fold in additively on top of that, not as the
> weighted `w_E` term described below.
>
> **Why this banner exists:** an audit on 2026-08-10 found this page was the only written
> specification of "the integrity score", making it the natural source for a paper's
> methods section — which would have described a system that does not exist. Kept rather
> than deleted because the design is a reasonable target, and the per-claim framing plus
> the uncertainty term are both things the shipped score lacks and arguably needs.
>
> **Before implementing any of it:** note that the weights below are as uncalibrated as
> the shipped ones. Neither set has ever been validated against an external criterion.
> See roadmap item 6.4.

---

# Integrity Gap Formula *(design target, not built)*

The Integrity Gap is the final output score per claim: **how much does the evidence support or contradict the claim?**

Scale: `[0, 1]` → mapped to `[0, 100]` in UI.

- `0`: Claim is well-supported (No Gap)
- `1`: Significant integrity concern (Massive Gap)

---

## Formula

```
Integrity_Gap = w_C * contradiction_severity
              + w_E * (1 - evidence_support)
              + w_V * (1 - CVE_score)
              + w_U * uncertainty_penalty
```

---

## Components

### 1. Contradiction Severity (`C`) — `[0, 1]`

_From RoBERTa-MNLI + aspect clustering (Week 4)._

| Type                                    | Severity |
| --------------------------------------- | -------- |
| Hard logical contradiction              | `1.0`    |
| Metric contradiction (numbers conflict) | `0.8`    |
| Temporal contradiction                  | `0.6`    |
| Scope contradiction                     | `0.4`    |
| No contradiction                        | `0.0`    |

### 2. Evidence Support (`E_support`) — `[0, 1]`

_Composite of all physical evidence signals (Week 7)._

```
E_support = max(NDVI_support, SAR_support, vision_support)
```

Per signal:

| Condition                           | Support Score |
| ----------------------------------- | ------------- |
| Strong support (z-score > 2)        | `1.0`         |
| Weak support (z-score > 1)          | `0.7`         |
| Neutral                             | `0.5`         |
| Weak contradiction (z-score < -1)   | `0.3`         |
| Strong contradiction (z-score < -2) | `0.0`         |

### 3. CVE Score (`V`) — `[0, 1]`

_From the Claim Verifiability Estimator (Week 6)._

### 4. Uncertainty Penalty (`U`) — `[0, 1]`

_Prevents overconfidence when evidence is sparse or noisy._

```
U = 1 - (data_quality * coverage_ratio * temporal_match)
```

Where:

- `data_quality`: cloud cover ratio inverted (0 = all clouds, 1 = clear)
- `coverage_ratio`: % of target area actually covered by imagery
- `temporal_match`: how closely available imagery dates match the claim's time window (1.0 = exact match, 0.0 = >3 years off)

---

## Weight Scenarios

### Scenario A: Satellite Evidence Valid (`evidence_quality == "valid"`)

| Weight | Value  | Why                                |
| ------ | ------ | ---------------------------------- |
| `w_C`  | `0.30` | Textual contradiction              |
| `w_E`  | `0.35` | Physical evidence (primary signal) |
| `w_V`  | `0.15` | Verifiability penalty              |
| `w_U`  | `0.20` | Uncertainty guard                  |

_Sum = 1.0_

### Scenario B: No Satellite Evidence (`evidence_quality == "inconclusive" or null`)

Falls back to text-heavy:

| Weight | Value                       |
| ------ | --------------------------- |
| `w_C`  | `0.50`                      |
| `w_E`  | `0.00` (no evidence to use) |
| `w_V`  | `0.25`                      |
| `w_U`  | `0.25`                      |

_Sum = 1.0_

---

## Explanation Assembly (Week 9)

The formula directly generates UI explanations:

| Condition         | Explanation                                                                                          |
| ----------------- | ---------------------------------------------------------------------------------------------------- |
| `C > 0.6`         | _"CONTRADICTION: Report states X elsewhere, conflicting with this claim (severity: high)"_           |
| `E_support < 0.4` | _"SATELLITE: Imagery shows no significant change consistent with claimed activity"_                  |
| `V < 0.4`         | _"CVE: Claim lacks verifiable specifics — relying on textual consistency only"_                      |
| `U > 0.5`         | _"UNCERTAINTY: Evidence quality is low (cloud cover / temporal mismatch) — score may be unreliable"_ |
