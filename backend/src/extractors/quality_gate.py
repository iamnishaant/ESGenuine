"""
ESGenuine — deterministic post-extraction quality gate (improve_rating C2).

The LLM's *values* are now reliable (Docling gives it real tables), but its *labels*
still miss deterministically-recoverable signals that sit in the source sentence
itself. This gate runs after extraction, needs no LLM, and does two things:

  CORRECTIONS (mutate the claim, recompute derived keys, log a flag):
    scope_fixed          "Scope 1/2/3" in the row text beats a generic emissions.* label
    gender_fixed         male/female/gender wage & headcount rows are workforce
                         diversity, never biodiversity/uncategorized
    waste_water_fixed    waste rows mislabeled water.* (the swap class in the gold set)
    type_fixed           a table row with a value is `performance` (or `target` when
                         the text has future markers) — not `narrative`

  SUSPICIONS (flag only — nothing is silently dropped):
    implausible_unit     unit dimension impossible for the aspect (LTIFR in headcount,
                         emissions in USD) — reuses ESGOntology.is_plausible_metric
    value_not_in_source  the metric value does not appear in the source sentence —
                         the page-footer/fabrication class that poisoned the baseline
                         (35% of emitted claims). Downstream can filter on it.

Every correction recomputes metric_family / metric_key / claim_signature so the
partition routing and cross-report blocking stay consistent with the new aspect.
"""
import re
from typing import List, Tuple

from .models import ExtractedClaim
from .ontology import SignatureGenerator

# ── sentence signals ──────────────────────────────────────────────
_SCOPE1 = re.compile(r"\bscope\s*[- ]?1\b", re.I)
_SCOPE2 = re.compile(r"\bscope\s*[- ]?2\b", re.I)
_SCOPE3 = re.compile(r"\bscope\s*[- ]?3\b", re.I)
_GENDER = re.compile(r"\b(male|female|women|men|gender)\b", re.I)
_WASTE = re.compile(r"\b(waste|e-waste)\b", re.I)
_WATER = re.compile(r"\b(water|effluent|wastewater)\b", re.I)
_FUTURE = re.compile(r"\b(target|aim|aspire|commit|pledge|goal|will|by\s+20[2-9]\d)\b", re.I)


def _sentence(claim: ExtractedClaim) -> str:
    return (claim.provenance.source_sentence or "") if claim.provenance else ""


def _refresh_keys(claim: ExtractedClaim) -> None:
    """Aspect changed -> derived routing/blocking keys must follow."""
    unit = claim.metric.unit if claim.metric else None
    claim.metric_family = SignatureGenerator.generate_metric_family(claim.normalized_aspect)
    claim.metric_key = SignatureGenerator.generate_metric_key(claim.normalized_aspect, unit)
    claim.claim_signature = SignatureGenerator.generate_signature(
        claim.metric_key, claim.time_bucket, claim.location_scope)


def _fix_aspect(claim: ExtractedClaim, sent: str) -> None:
    asp = claim.normalized_aspect or "uncategorized"

    # Scope from the row text — trumps a generic emissions label.
    if asp.startswith("emissions") or asp == "uncategorized":
        s1, s2, s3 = bool(_SCOPE1.search(sent)), bool(_SCOPE2.search(sent)), bool(_SCOPE3.search(sent))
        want = None
        if s1 and s2:
            want = "emissions.total"        # combined "Scope 1 and Scope 2" rows
        elif s1:
            want = "emissions.scope1"
        elif s2:
            want = "emissions.scope2"
        elif s3:
            want = "emissions.scope3"
        if want and want != asp:
            claim.normalized_aspect = want
            claim.quality_flags.append("scope_fixed")
            _refresh_keys(claim)
            return

    # Gender/workforce rows can never be biodiversity; rescue uncategorized ones too.
    if asp in ("uncategorized",) or asp.startswith("biodiversity"):
        if _GENDER.search(sent):
            claim.normalized_aspect = "social.diversity.gender"
            claim.quality_flags.append("gender_fixed")
            _refresh_keys(claim)
            return

    # Waste rows mislabeled as water (the swap class): waste words, no water words.
    if asp.startswith("water") and _WASTE.search(sent) and not _WATER.search(sent):
        claim.normalized_aspect = "waste.total"
        claim.quality_flags.append("waste_water_fixed")
        _refresh_keys(claim)


def _fix_type(claim: ExtractedClaim, sent: str) -> None:
    """A table row carrying a reported value is performance data, not narrative."""
    if claim.source_type != "table" or claim.metric is None or claim.metric.value is None:
        return
    want = "target" if _FUTURE.search(sent) else "performance"
    if claim.claim_type != want:
        claim.claim_type = want
        claim.quality_flags.append("type_fixed")


# ── fabricated-value detection ────────────────────────────────────
_NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _value_in_source(value: float, sent: str) -> bool:
    """Does the claimed value appear in the sentence? Handles thousands separators
    (both 1,234,567 and Indian 3,86,71,851 grouping) and float equivalence."""
    if not sent:
        return False
    for tok in _NUM_TOKEN.findall(sent):
        plain = tok.replace(",", "")
        try:
            f = float(plain)
        except ValueError:
            continue
        if f == value:
            return True
        # tolerate float repr noise on decimals (0.0000186 etc.)
        if f != 0 and abs(f - value) / abs(f) < 1e-9:
            return True
    return False


def _flag_suspicions(claim: ExtractedClaim, sent: str) -> None:
    m = claim.metric
    if m is not None and m.value is not None:
        # Table claims: source_sentence is just the ROW LABEL ("Board of Directors");
        # the value lives in the table markdown. extract_from_table_markdown verifies
        # those against the markdown at extraction time ("value_not_in_table").
        if claim.source_type != "table" and not _value_in_source(float(m.value), sent):
            claim.quality_flags.append("value_not_in_source")
        if claim.normalized_aspect and not SignatureGenerator.is_plausible_metric(
                claim.normalized_aspect, m.unit):
            claim.quality_flags.append("implausible_unit")


# ── entry points ──────────────────────────────────────────────────
def apply_gate(claim: ExtractedClaim) -> ExtractedClaim:
    """Run all corrections + suspicions on one claim (mutates and returns it)."""
    sent = _sentence(claim)
    _fix_aspect(claim, sent)
    _fix_type(claim, sent)
    _flag_suspicions(claim, sent)
    return claim


def gate_claims(claims: List[ExtractedClaim]) -> Tuple[List[ExtractedClaim], dict]:
    """Gate a batch; returns (claims, stats) where stats counts each flag."""
    stats: dict = {}
    for c in claims:
        before = len(c.quality_flags)
        apply_gate(c)
        for f in c.quality_flags[before:]:
            stats[f] = stats.get(f, 0) + 1
    return claims, stats
