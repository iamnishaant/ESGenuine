# Claim Verifiability Estimator (CVE) Rules

The CVE determines if a claim is physically verifiable, gating whether the system triggers satellite imagery or relies on text-only evaluation.

## Base Formula

```
CVE = 0.25 * location_specificity
    + 0.25 * temporal_specificity
    + 0.25 * numeric_metric
    + 0.25 * observability_type
```

Score is `[0, 1]`.

---

## 1. Location Specificity (`0.0 to 1.0`)

| Specificity                   | Score | Example                       |
| ----------------------------- | ----- | ----------------------------- |
| `facility` / `site`           | `1.0` | "Pune manufacturing facility" |
| `city` / `municipality`       | `0.6` | "operations in Nagpur"        |
| `region` / `state`            | `0.3` | "Maharashtra operations"      |
| `country` / `global` / `null` | `0.0` | "our global footprint"        |

---

## 2. Temporal Specificity (`0.0 to 1.0`)

| Condition                          | Score | Example                 |
| ---------------------------------- | ----- | ----------------------- |
| Both `start_date` and `end_date`   | `1.0` | "between 2021 and 2023" |
| Only `end_date` or `baseline_year` | `0.5` | "by FY2023"             |
| Vague or `null`                    | `0.0` | "in recent years"       |

---

## 3. Numeric Metric (`0.0 to 1.0`)

| Condition            | Score | Example                            |
| -------------------- | ----- | ---------------------------------- |
| Value + Unit present | `1.0` | "10,000 hectares", "40% reduction" |
| Value only (no unit) | `0.4` | "reduced by 40"                    |
| Qualitative / null   | `0.0` | "significantly improved"           |

---

## 4. Observability Type (`0.0 to 1.0`)

This is the critical addition. Not all claims can be seen from space.

| Type                 | Score | Output Flag        | Examples                                                                                             |
| -------------------- | ----- | ------------------ | ---------------------------------------------------------------------------------------------------- |
| Optically observable | `1.0` | `optical_possible` | reforestation, deforestation, land use change, solar installation, facility footprint, water surface |
| SAR observable       | `0.7` | `sar_possible`     | structural change, flooding, subsidence (radar-only)                                                 |
| Not observable       | `0.0` | `not_observable`   | emissions, employee diversity, governance, training, policy commitments, supply chain                |

### Keyword Matching Rules

**`optical_possible`**: reforestation, deforestation, land use, vegetation, forest, plantation, solar, wind farm, water surface, green cover, facility expansion, mining

**`sar_possible`**: structural, construction, flooding, subsidence, infrastructure, building

**`not_observable`**: emissions, carbon, CO2, governance, training, diversity, inclusion, ethics, anti-corruption, human rights, employee, supply chain, policy, commitment, sustainability strategy

---

## Gateway Logic

| CVE Score                      | Action                                                       |
| ------------------------------ | ------------------------------------------------------------ |
| `≥ 0.6` AND `optical_possible` | → Route to Sentinel-2 optical pipeline (Week 7)              |
| `≥ 0.6` AND `sar_possible`     | → Route to SAR pipeline (if implemented)                     |
| `< 0.6` OR `not_observable`    | → Skip satellite, route to NLI text-only evaluation (Week 4) |

---

## Example Scoring

### Claim: "We planted 10,000 trees in Rajasthan between 2021 and 2023"

```
location_specificity = 0.3  (region)
temporal_specificity = 1.0  (both dates)
numeric_metric      = 1.0  (10,000 trees)
observability_type  = 1.0  (optical: reforestation)

CVE = 0.25*0.3 + 0.25*1.0 + 0.25*1.0 + 0.25*1.0 = 0.825
→ Route to satellite pipeline ✓
```

### Claim: "We are committed to sustainability"

```
location_specificity = 0.0
temporal_specificity = 0.0
numeric_metric      = 0.0
observability_type  = 0.0  (not_observable: policy)

CVE = 0.0
→ Text-only evaluation ✓
```
