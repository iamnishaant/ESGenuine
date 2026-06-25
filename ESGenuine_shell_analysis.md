# ESGenuine — Evidence-Quality Analysis: Shell

_Company: **Shell** · reports analyzed: 2022, 2023_

> **Defensive framing:** findings describe whether individual claims are *verifiable as written* (do they carry a number, a timeframe, a location, a source?). Low scores indicate **lack of disclosed evidence**, not that a statement is false.

## 2022 — shell-sustainability-report-2022.pdf (91 pp, 40 section-windows over 2170 sentences)

- Claims analyzed: **539**
- Groundability: high(≥0.75) **349 (64.7%)** · medium **90 (16.7%)** · low(<0.5) **100 (18.6%)**
- **Lack-of-evidence indicators:** no metric **22.3%** · no timeframe **26.0%** · no location **22.3%**
- Avg vagueness: **0.234** · narrative/aspirational claims: **339 (62.9%)**

**Lowest-evidence examples (unverifiable as written):**
  - _g=0.10, vague=0.80_ — "employees or contractor staff subject to disciplinary action"
  - _g=0.10, vague=0.80_ — "people dismissed"
  - _g=0.10, vague=0.80_ — "We continually measure and improve our cyber-security capabilities to reduce the likelihood of successful breaches."
  - _g=0.10, vague=0.80_ — "Our employees and contract staff receive regular mandatory training to protect our IT systems from threats."
  - _g=0.10, vague=0.80_ — "We work with governments, non-governmental organisations (NGOs), coalitions, industry bodies, academic institutions, national oil and gas companies and other bu"
  - _g=0.10, vague=0.80_ — "The Chair, certain Board committees and Non-executive Directors traditionally visit a number of Shell operations and overseas offices."

## 2023 — shell-sustainability-report-2023.pdf (98 pp, 40 section-windows over 2932 sentences)

- Claims analyzed: **756**
- Groundability: high(≥0.75) **396 (52.4%)** · medium **178 (23.5%)** · low(<0.5) **182 (24.1%)**
- **Lack-of-evidence indicators:** no metric **33.1%** · no timeframe **36.6%** · no location **16.4%**
- Avg vagueness: **0.308** · narrative/aspirational claims: **475 (62.8%)**

**Lowest-evidence examples (unverifiable as written):**
  - _g=0.10, vague=0.80_ — "We continue to support the UN Global Compact's corporate governance principles on human rights, environmental protection, anti-corruption and better labour prac"
  - _g=0.10, vague=0.80_ — "We respect human rights in our business and work hard to ensure that our joint-venture partners and supply chains do the same."
  - _g=0.10, vague=0.80_ — "We recognise the importance of a just transition to a net-zero emissions energy system in which the costs and benefits are distributed fairly."
  - _g=0.10, vague=0.80_ — "We will continue to be transparent in our reporting and demonstrate that sustainability is embedded in our way of doing business."
  - _g=0.10, vague=0.80_ — "We strive to play our part in helping governments and societies achieve the UN's 17 Sustainable Development Goals (SDGs)."
  - _g=0.10, vague=0.80_ — "The goals were one of the considerations in the development of our Powering Progress strategy."

## Year-over-year drift (2022 → 2023)

- `biodiversity.conservation.count`: 1.0 director (2022) → 9.0 incidents (2023)
- `biodiversity.conservation.percent`: 50.0 % (2022) → 32.0 % (2023)
- `emissions.scope1.co2e`: 77.0 gCO2e/MJ (2022) → 76.0 gCO2e/MJ (2023)
- `emissions.scope1.mass`: 3000000.0 tonnes of carbon dioxide equivalent (2022) → 700000.0 tonnes (2023)
- `emissions.scope1.percent`: 30.0 % (2022) → 30.0 % (2023)
- `emissions.scope2.mass`: 750000.0 tonnes per year (2022) → 300.0 tonnes diesel (2023)
- `emissions.scope2.percent`: 51.0 % (2022) → 49.0 % (2023)
- `social.health_safety.ltifr.count`: 103.0 events (2022) → 15000.0 people (2023)
- `social.health_safety.ltifr.percent`: 15.0 % (2022) → 7.5 % (2023)
- `social.health_safety.ltifr.rate`: 6.9 injuries and fatalities per 100 million working hours (2022) → 2.0 per 100 million working hours (2023)
- `water.consumption.percent`: 15.0 % (2022) → 15.0 % (2023)
- `water.consumption.volume`: 18000000.0 cubic metres (2022) → 17000000.0 m³ (2023)
- `water.recycled.mass`: 1982.0 thousand tonnes (2022) → 631000.0 tonnes (2023)

---
_Provider: pool[nvidiax1, groqx2, hfx1]. Representative even-spaced sample per report (not cherry-picked). Contradiction engine intentionally not used (see existing_issues.md #1–#3)._