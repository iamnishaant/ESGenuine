"""
ESGenuine — per-claim regulatory framework tags (external eval #3).

The greenwash taxonomy already maps *flags* to regulations; this maps every CLAIM
to the disclosure-framework clause IDs it reports against (GRI / ESRS / TCFD pillar).
Deterministic — derived from the claim's normalized aspect node plus any explicit
GRI code printed in the source row (ESG data tables routinely carry them, e.g.
Shell's "305-1" column) — so it costs no LLM calls and never hallucinates a clause.

Why it matters: "metric_key emissions.scope1" is internal vocabulary; "GRI 305-1 /
ESRS E1-6" is what a compliance officer or regulator can act on. Tags make the
adversarial findings citable against standard anchors.
"""
import re
from typing import List, Optional

# aspect node -> framework clause IDs. Conservative, checkable mappings only:
# GRI Standards (2021), ESRS Set 1 (2023), TCFD pillar. Extend as nodes grow.
FRAMEWORK_MAP = {
    "emissions.scope1":                ["GRI 305-1", "ESRS E1-6", "TCFD Metrics & Targets"],
    "emissions.scope2":                ["GRI 305-2", "ESRS E1-6", "TCFD Metrics & Targets"],
    "emissions.scope3":                ["GRI 305-3", "ESRS E1-6", "TCFD Metrics & Targets"],
    "emissions.total":                 ["GRI 305", "ESRS E1-6", "TCFD Metrics & Targets"],
    "energy.total":                    ["GRI 302-1", "ESRS E1-5"],
    "energy.renewable":                ["GRI 302-1", "ESRS E1-5"],
    "water.consumption":               ["GRI 303-5", "ESRS E3-4"],
    "water.recycled":                  ["GRI 303-3", "ESRS E3-4"],
    "waste.total":                     ["GRI 306-3", "ESRS E5-5"],
    "waste.recycled":                  ["GRI 306-4", "ESRS E5-5"],
    "biodiversity.conservation":       ["GRI 304-3", "ESRS E4"],
    "social.diversity.gender":         ["GRI 405-1", "ESRS S1-9"],
    "social.health_safety.ltifr":      ["GRI 403-9", "ESRS S1-14"],
    "social.health_safety.fatalities": ["GRI 403-9", "ESRS S1-14"],
    "social.workforce.total":          ["GRI 2-7", "ESRS S1-6"],
    "social.training.hours":           ["GRI 404-1", "ESRS S1-13"],
    "governance.board.diversity":      ["GRI 405-1", "ESRS G1", "TCFD Governance"],
    "governance.ethics.incidents":     ["GRI 205-3", "ESRS G1-4"],
}

# Explicit GRI codes printed in the source text (data tables carry them verbatim).
# Constrained to the topic-standard families actually in scope (2xx/3xx/4xx + GRI 2).
_GRI_IN_TEXT = re.compile(r"\b(2-\d{1,2}|20[1-8]-\d{1,2}|30[1-8]-\d{1,2}|4[0-1]\d-\d{1,2})\b")


def framework_tags(normalized_aspect: Optional[str], source_sentence: Optional[str] = None) -> List[str]:
    """Framework clause IDs for a claim. Aspect mapping first; any explicit GRI code
    in the source row is added (prefixed 'GRI ') when not already implied."""
    tags = list(FRAMEWORK_MAP.get(normalized_aspect or "", []))
    for code in _GRI_IN_TEXT.findall(source_sentence or ""):
        tag = f"GRI {code}"
        if tag not in tags:
            tags.append(tag)
    return tags
