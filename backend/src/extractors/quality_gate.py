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
# Strong commitment phrasing only — promotes text performance/narrative -> target.
_FUTURE_STRONG = re.compile(
    r"\b(we (have )?set a target|we pledged?|pledged|we aim to|we are committed to|"
    r"we will \w+|expected to be \w+ed)\b|\bby\s+20[2-9]\d,?\s+we will\b", re.I)

# Aspect backstops (gold v0.2 taxonomy-gap classes). Each maps an unmistakable
# sentence signal to the node the taxonomy now has for it.
_AIRPOLL = re.compile(r"\b(sox|nox|particulate matter|pm10|pm2\.5|air pollutant)", re.I)
_DISCHARGE = re.compile(r"\bdischarg", re.I)
# BRSR discharge-by-destination fragments carry no "discharge" word, just the row
# label: "To Surface water 1,24,89,82,509 ..."
_DISCHARGE_DEST = re.compile(r"^\s*to\s+(surface\s*water|sea\s*water|seawater|ground\s*water|third\s*part)", re.I)
_BIODIV = re.compile(r"\b(afforestation|reforestation|tree plant\w*|plantation)\b", re.I)
_WATER_REUSE = re.compile(r"\b(reused|recycled|zero.liquid discharge|zld)\b", re.I)
_NONRENEW = re.compile(r"\b(non-?renewable|fuel consumption)\b", re.I)
_TOTAL_ENERGY = re.compile(r"\btotal energy consum", re.I)
_RENEW_WORD = re.compile(r"\brenewable\b", re.I)
_HEATRATE = re.compile(r"\b(heat rate)\b|kcal\s*/\s*kwh", re.I)
_POSH = re.compile(r"\b(posh|sexual harassment)\b", re.I)
_HUMAN_RIGHTS = re.compile(r"\bhuman rights\b", re.I)
_UNION = re.compile(r"\b(union|collective bargaining|freedom of association)\b", re.I)
_CSR = re.compile(r"\b(csr|corporate social responsibility|beneficiaries)\b", re.I)
_VALUE_CHAIN = re.compile(r"\bvalue chain partners\b", re.I)
_ACCESS = re.compile(r"\b(wheelchair|assistive technolog|braille|differently.abled)\b", re.I)

# Round 2 backstops (gold v0.3 / Shell taxonomy-gap classes)
_SCOPE12 = re.compile(r"\bscope\s*1\s*and\s*(scope\s*)?2\b", re.I)
_OFFSET = re.compile(r"\b(carbon.?compensated|carbon credits?|carbon offsets?|emissions? offset)\b", re.I)
_CCS = re.compile(r"\b(carbon capture|ccus|ccs)\b|\bco2\b[^.]*\bcaptured\b|\bcaptured\b[^.]*\bco2\b", re.I)
_INTENSITY = re.compile(r"\b(net carbon intensity|carbon intensity|emissions? intensity)\b|gco2e\s*/\s*mj", re.I)
_METHANE = re.compile(r"\b(ogmp|methane)\b", re.I)
_LNG = re.compile(r"\b(lng|liquefied natural gas)\b", re.I)
_EVCHARGE = re.compile(r"\b(charge points|charging points|ev charging|charging stations)\b", re.I)
_INVEST_LC = re.compile(r"\binvest\w*\b[^.]*\b(low.carbon|non.energy)|\b(low.carbon|non.energy)[^.]*\binvest\w*\b", re.I)
_PAY_GOV = re.compile(r"\b(payments? to governments?|production entitlements)\b", re.I)
_LOBBY = re.compile(r"\b(lobbying|transparency register)\b", re.I)
_PENALTY = re.compile(r"\b(administrative penalty|penalty of|fined)\b", re.I)
_SIF = re.compile(r"\bserious injuries and fatalities\b", re.I)
_LTIFR = re.compile(r"\b(ltifr|lost time injury)\b", re.I)
_SAFETY_GENERIC = re.compile(r"\b(exposure hours|safety principles|process safety|"
                             r"assessments of assets|change impact assessments)\b", re.I)
_SUPPLIERS = re.compile(r"\bsuppliers\b", re.I)
_EMISSION_WORD = re.compile(r"\bemissions?\b", re.I)


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
        if (s1 and s2) or _SCOPE12.search(sent):
            want = "emissions.total"        # combined "Scope 1 and 2" rows/sentences
        elif s1:
            want = "emissions.scope1"
        elif s2:
            want = "emissions.scope2"
        elif s3:
            want = "emissions.scope3"
        if want:
            if want != asp:
                claim.normalized_aspect = want
                claim.quality_flags.append("scope_fixed")
                _refresh_keys(claim)
            # Scope-confirmed either way: later backstops (e.g. intensity) must not
            # override an explicit "Scope 1 and 2" label.
            return

    def _set(node: str) -> None:
        claim.normalized_aspect = node
        claim.quality_flags.append("aspect_fixed")
        _refresh_keys(claim)

    # Air pollutants (PM/SOx/NOx) are mass emissions, not GHG totals.
    if (asp.startswith("emissions") or asp == "uncategorized") and _AIRPOLL.search(sent):
        if asp != "emissions.air_pollutants":
            _set("emissions.air_pollutants")
        return

    # Round 2 (gold v0.3): offsets/CCS/intensity/methane are their own concepts,
    # not emissions.total. Offsets checked FIRST — "carbon-compensated LNG" is an
    # offset claim, not an energy-supply one.
    if asp.startswith(("emissions", "energy")) or asp == "uncategorized":
        if _OFFSET.search(sent):
            if asp != "emissions.offsets":
                _set("emissions.offsets")
            return
        if _CCS.search(sent):
            if asp != "emissions.ccs":
                _set("emissions.ccs")
            return
    if (asp.startswith("emissions") or asp == "uncategorized") and _INTENSITY.search(sent):
        if asp != "emissions.intensity":
            _set("emissions.intensity")
        return
    if asp == "uncategorized" and _METHANE.search(sent):
        _set("emissions.methane")
        return

    # LNG/gas supply force-fits to energy.renewable; EV charging is infrastructure,
    # not renewable generation. Low-carbon investment routinely lands on
    # social.community — the invest+low-carbon signal overrides any pillar.
    if asp.startswith("energy") or asp == "uncategorized":
        if _LNG.search(sent):
            if asp != "energy.supply":
                _set("energy.supply")
            return
        if _EVCHARGE.search(sent):
            if asp != "energy.ev_charging":
                _set("energy.ev_charging")
            return
    if _INVEST_LC.search(sent):
        if asp != "energy.investment":
            _set("energy.investment")
        return

    # Governance taxonomy-gap classes (Shell IR-style disclosures).
    if _PAY_GOV.search(sent):
        if asp != "governance.payments_to_governments":
            _set("governance.payments_to_governments")
        return
    if _LOBBY.search(sent):
        if asp != "governance.lobbying":
            _set("governance.lobbying")
        return
    if (asp == "uncategorized" or asp.startswith("governance")) and _PENALTY.search(sent):
        if asp != "governance.compliance":
            _set("governance.compliance")
        return

    # Supplier-count rows mislabel as scope3 ("24,000 suppliers worldwide" has no
    # emissions content). Requires the emissions word to be ABSENT.
    if (asp.startswith(("emissions", "social")) or asp == "uncategorized") \
            and _SUPPLIERS.search(sent) and not _EMISSION_WORD.search(sent):
        if asp not in ("social.supply_chain", "social.supply_chain.training"):
            _set("social.supply_chain")
        return

    # SIF-rate and generic safety-programme sentences force-fit to ltifr.
    # LTIFR checked FIRST — the parent health_safety node's keywords otherwise
    # steal explicit "Lost Time Injury Frequency Rate" rows via normalization.
    if asp.startswith(("social.health_safety", "social")) or asp == "uncategorized":
        if _LTIFR.search(sent):
            if asp != "social.health_safety.ltifr":
                _set("social.health_safety.ltifr")
            return
        if _SIF.search(sent):
            if asp != "social.health_safety.sif":
                _set("social.health_safety.sif")
            return
        if _SAFETY_GENERIC.search(sent):
            if asp != "social.health_safety":
                _set("social.health_safety")
            return

    # Heat-rate (Kcal/kWh) efficiency rows land on energy.renewable AND on
    # emissions.* (PAT-scheme tables mention CO2 goals) — override both.
    if (asp.startswith(("energy", "emissions")) or asp == "uncategorized") and _HEATRATE.search(sent):
        if asp != "energy.efficiency":
            _set("energy.efficiency")
        return

    # Fuel/non-renewable rows routinely force-fit to energy.renewable.
    if asp.startswith("energy") or asp == "uncategorized":
        if _NONRENEW.search(sent) or (_TOTAL_ENERGY.search(sent) and not _RENEW_WORD.search(sent)):
            if asp != "energy.total":
                _set("energy.total")
            return

    # Water discharge vs reuse: "treated and reused"/ZLD rows are recycling,
    # plain discharge rows are their own node (not consumption).
    if ((asp.startswith("water") or asp == "uncategorized")
            and (_DISCHARGE.search(sent) or _DISCHARGE_DEST.search(sent))):
        want = "water.recycled" if _WATER_REUSE.search(sent) else "water.discharge"
        if asp != want:
            _set(want)
        return

    # Afforestation/plantation narratives stay uncategorized without a keyword.
    if asp == "uncategorized" and _BIODIV.search(sent):
        _set("biodiversity.conservation")
        return

    # Social taxonomy-gap classes. POSH before the gender rescue below —
    # "complaints on POSH as % of female employees" must not become diversity.
    if asp.startswith("social") or asp == "uncategorized":
        if _POSH.search(sent):
            if asp != "social.posh_complaints":
                _set("social.posh_complaints")
            return
        if _ACCESS.search(sent):
            if asp != "social.accessibility":
                _set("social.accessibility")
            return
        if _HUMAN_RIGHTS.search(sent):
            if asp != "social.human_rights":
                _set("social.human_rights")
            return
        if _VALUE_CHAIN.search(sent):
            if asp != "social.supply_chain.training":
                _set("social.supply_chain.training")
            return
        if _UNION.search(sent):
            if asp != "social.labor_relations":
                _set("social.labor_relations")
            return
        if _CSR.search(sent):
            if asp != "social.community":
                _set("social.community")
            return

    # Gender/workforce rows can never be biodiversity; rescue uncategorized ones too.
    # A workforce stat split by male/female ("Female FY23" headcount) is a
    # gender-diversity disclosure, not a plain headcount.
    if asp in ("uncategorized",) or asp.startswith(("biodiversity", "social.workforce")):
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
    """A row carrying a reported value is performance data, not narrative; and a
    'target' with no future marker in its sentence is a description, not a promise."""
    has_value = claim.metric is not None and claim.metric.value is not None
    if claim.source_type == "table":
        if not has_value:
            return
        want = "target" if _FUTURE.search(sent) else "performance"
        if claim.claim_type != want:
            claim.claim_type = want
            claim.quality_flags.append("type_fixed")
        return
    # Text claims (gold v0.2 misses): ongoing practice mistyped 'target'
    # ("Since 1972 ... arranging afforestation", ZLD descriptions)...
    if claim.claim_type == "target" and not _FUTURE.search(sent):
        claim.claim_type = "narrative"
        claim.quality_flags.append("type_fixed")
        return
    # (gold v0.3): commitments mistyped 'performance'/'narrative'. Only STRONG,
    # unambiguous commitment phrasing promotes — bare "will"/"by 2030" appears in
    # too many mixed reporting sentences to be safe.
    if claim.claim_type in ("performance", "narrative") and _FUTURE_STRONG.search(sent):
        claim.claim_type = "target"
        claim.quality_flags.append("type_fixed")
        return
    # ...and reported numbers mistyped 'narrative' (row-label leaks like
    # "To Surface water 1,24,89,82,509", CSR spend sentences). Requires digits
    # in the sentence so pure prose stays narrative.
    if (claim.claim_type == "narrative" and has_value
            and not _FUTURE.search(sent) and _HAS_DIGIT.search(sent)):
        claim.claim_type = "performance"
        claim.quality_flags.append("type_fixed")
        return
    # ...and 'performance' whose value cannot have come from a digit-free
    # sentence is at best a narrative with an invented number.
    if (claim.claim_type == "performance" and has_value
            and not _HAS_DIGIT.search(sent)):
        claim.claim_type = "narrative"
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


# ── page furniture (candidate-precision killer) ───────────────────
# Text "claims" whose source is a BRSR form question / bare row label, with a value
# the extractor necessarily invented. Table claims never hit this (their label-only
# source is expected).
_QUESTION_END = re.compile(r"\?\s*$")
_FORM_LABEL = re.compile(r"^\s*(please specify|not applicable|if yes)", re.I)
_DISCLOSE = re.compile(r"\bdisclose\b", re.I)
_COUNT_LABEL = re.compile(r"^\s*(no\.|number)\s+of\b", re.I)
_HAS_DIGIT = re.compile(r"\d")


def is_furniture(claim: ExtractedClaim) -> bool:
    if claim.source_type == "table":
        return False
    sent = _sentence(claim).strip()
    if not sent:
        return True
    if _QUESTION_END.search(sent) or _FORM_LABEL.search(sent) or _DISCLOSE.search(sent):
        return True
    if not _HAS_DIGIT.search(sent):
        if _COUNT_LABEL.match(sent):
            return True
        # a short digit-free label carrying a numeric metric: the number cannot
        # have come from this sentence ("Permanent Employees" + 22,372)
        if len(sent) < 80 and claim.metric is not None and claim.metric.value is not None:
            return True
    return False


# ── FY-column verification (wrong-column class, gold v0.2) ────────
_FY_TOKEN = re.compile(r"\bfy\s*'?\s*(?:20)?(\d{2})\b", re.I)


def _cell_num(cell: str):
    plain = cell.strip().replace(",", "")
    if not plain or plain in ("-", "–"):
        return None
    try:
        return float(plain)
    except ValueError:
        return None


def fix_fy_column(claim: ExtractedClaim, markdown: str) -> None:
    """Row label names one FY but the value came from another FY's column →
    replace it with the labeled FY's cell (flag: fy_column_fixed).

    Walks the page markdown keeping the most recent header's column→FY map, so
    multi-table pages work. Only acts when the label names exactly one FY, the
    value is found under a different FY's column, and the labeled FY's cell in
    the same row parses to a number.
    """
    if claim.metric is None or claim.metric.value is None or not markdown:
        return
    fys = {m.group(1) for m in _FY_TOKEN.finditer(_sentence(claim))}
    if len(fys) != 1:
        return
    target = next(iter(fys))
    try:
        value = float(claim.metric.value)
    except (TypeError, ValueError):
        return

    colmap: dict = {}
    for line in markdown.splitlines():
        if "|" not in line:
            continue
        cells = line.split("|")
        fy_cells = {i: ms[0] for i, c in enumerate(cells)
                    for ms in [_FY_TOKEN.findall(c)] if len(ms) == 1}
        if len(fy_cells) >= 2:
            colmap = fy_cells
            continue
        if not colmap:
            continue
        target_cols = [i for i, fy in colmap.items() if fy == target]
        if not target_cols:
            continue
        nums = {i: _cell_num(c) for i, c in enumerate(cells)}
        # value already sits under the labeled FY somewhere on the page → correct
        if any(i < len(cells) and nums.get(i) == value for i in target_cols):
            return
        for i, fy in colmap.items():
            if fy == target or nums.get(i) != value:
                continue
            fixed = next((nums.get(t) for t in target_cols if nums.get(t) is not None), None)
            if fixed is None:
                return
            same = claim.metric.normalized_value == claim.metric.value
            claim.metric.value = fixed
            if same:
                claim.metric.normalized_value = fixed
            claim.quality_flags.append("fy_column_fixed")
            return


# ── entry points ──────────────────────────────────────────────────
def apply_gate(claim: ExtractedClaim) -> ExtractedClaim:
    """Run all corrections + suspicions on one claim (mutates and returns it)."""
    sent = _sentence(claim)
    _fix_aspect(claim, sent)
    _fix_type(claim, sent)
    _flag_suspicions(claim, sent)
    # Regulatory framework tags LAST — the aspect label is final by here.
    from .frameworks import framework_tags
    claim.framework_tags = framework_tags(claim.normalized_aspect, sent)
    return claim


def gate_claims(claims: List[ExtractedClaim]) -> Tuple[List[ExtractedClaim], dict]:
    """Gate a batch; returns (kept_claims, stats) where stats counts each flag.
    Furniture candidates (form questions / bare labels with invented numbers) are
    DROPPED — they are not claims at all, and they poison candidate precision."""
    stats: dict = {}
    kept: List[ExtractedClaim] = []
    for c in claims:
        if is_furniture(c):
            stats["furniture_dropped"] = stats.get("furniture_dropped", 0) + 1
            continue
        before = len(c.quality_flags)
        apply_gate(c)
        for f in c.quality_flags[before:]:
            stats[f] = stats.get(f, 0) + 1
        kept.append(c)
    return kept, stats
