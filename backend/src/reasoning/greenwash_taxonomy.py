"""
ESGenuine — Greenwashing Taxonomy Engine
========================================
Turns the flat claim store into a *structured, explainable* greenwashing assessment:
a set of typed flags, each with a severity, the evidence that triggered it (claim ids,
source sentences, pages), and a mapping to the disclosure framework it violates.

This is the analysis primitive consumed by the Integrity Report and the agentic auditor.
It is deliberately dependency-light: it operates on plain claim dicts (as returned by
Supabase / the API) so it can be unit-tested offline.

Flag types (grounded in real greenwashing research + EU Green Claims Directive guidance):
  VAGUE                 — non-specific environmental claim, no measurable metric
  UNSUBSTANTIATED_TARGET— a target/pledge with no metric, baseline, or deadline
  MISSING_BASELINE      — a performance/direction claim with no baseline to judge it
  NON_GROUNDABLE        — claim that cannot be verified against any observable evidence
  SELECTIVE_SCOPE       — headline metric reported only for a narrow scope (cherry-picking)
  DISCLOSURE_GAP        — a material disclosure (e.g. Scope 3) is absent entirely
  ASPIRATIONAL_HEAVY    — portfolio skews to promises/narrative over delivered performance
  CONTRADICTION         — internally inconsistent figures (from the contradiction engine)
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
import collections

# ── Regulatory / framework references (kept short; cited verbatim in output) ──────
REG = {
    "EU_GREEN_CLAIMS": "EU Green Claims Directive (2024) — environmental claims must be specific & substantiated",
    "ISO_14021":       "ISO 14021 — self-declared environmental claims must be verifiable",
    "ESRS_E1":         "ESRS E1 (Climate) — GHG targets require base year & Scope 1/2/3 coverage",
    "SEC_CLIMATE":     "SEC Climate Disclosure Rule — material targets need a stated basis",
    "GHG_PROTOCOL":    "GHG Protocol — baseline year and full scope boundary required",
    "BRSR":            "SEBI BRSR — principle-wise quantitative disclosure",
}

_SEV_RANK = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1, "None": 0}


@dataclass
class GreenwashFlag:
    type: str
    severity: str                       # Critical | High | Medium | Low
    title: str
    description: str
    regulations: List[str] = field(default_factory=list)
    recommendation: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)  # {claim_id, source_sentence, page_number}
    count: int = 0                      # how many claims triggered this flag

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _ev(claim: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "claim_id": claim.get("claim_id"),
        "source_sentence": (claim.get("source_sentence") or "")[:240],
        "page_number": claim.get("page_number"),
    }


class GreenwashTaxonomy:
    """Produces a list[GreenwashFlag] from a document's claims (+ optional contradictions)."""

    VAGUE_MIN = 0.6          # vagueness_score at/above this is a vague claim
    NON_GROUND_MAX = 0.4     # groundability_score below this is non-groundable
    MAX_EVIDENCE = 5         # cap evidence snippets per flag (keep payloads small)

    @classmethod
    def analyze(cls, claims: List[Dict[str, Any]],
                contradictions: Optional[List[Dict[str, Any]]] = None) -> List[GreenwashFlag]:
        flags: List[GreenwashFlag] = []
        if not claims:
            return flags

        total = len(claims)
        ct = collections.Counter((c.get("claim_type") or "narrative") for c in claims)

        # ── per-claim accumulators ──────────────────────────────────────────────
        vague, untargeted, missing_base, non_ground, selective = [], [], [], [], []
        for c in claims:
            vagueness = _num(c.get("vagueness_score"))
            ground = _num(c.get("groundability_score"))
            ctype = (c.get("claim_type") or "narrative").lower()
            has_metric = c.get("metric_value") is not None
            has_time = bool(c.get("time_bucket")) and str(c.get("time_bucket")).lower() not in ("unknown_time", "none", "null", "")
            direction = (c.get("metric_direction") or "").lower()
            scope = (c.get("location_scope") or "global").lower()

            if vagueness is not None and vagueness >= cls.VAGUE_MIN:
                vague.append(c)
            if ctype == "target" and (not has_metric or not has_time):
                untargeted.append(c)
            if ctype == "performance" and direction in ("increase", "decrease") and not has_time:
                missing_base.append(c)
            if ground is not None and ground < cls.NON_GROUND_MAX:
                non_ground.append(c)
            if has_metric and scope not in ("global", "", "group", "company"):
                selective.append(c)

        flags += cls._maybe(
            "VAGUE", vague, total,
            title="Vague, unsubstantiated environmental claims",
            desc_t="{n} claims ({pct}%) are vague with no measurable metric — a primary greenwashing signal.",
            sev_fn=lambda n, pct: "High" if pct >= 30 else "Medium",
            regs=["EU_GREEN_CLAIMS", "ISO_14021"],
            rec="Attach a quantified metric, time period, and scope to each environmental claim.",
        )
        flags += cls._maybe(
            "UNSUBSTANTIATED_TARGET", untargeted, total,
            title="Targets without baseline, metric, or deadline",
            desc_t="{n} target/pledge claims lack a measurable metric or a deadline — not verifiable.",
            sev_fn=lambda n, pct: "High" if n >= 3 else "Medium",
            regs=["ESRS_E1", "SEC_CLIMATE", "GHG_PROTOCOL"],
            rec="State a base year, a quantified target value, and a target date for every pledge.",
        )
        flags += cls._maybe(
            "MISSING_BASELINE", missing_base, total,
            title="Performance claims with no baseline period",
            desc_t="{n} 'increase/decrease' claims have no time period, so the change cannot be judged.",
            sev_fn=lambda n, pct: "Medium",
            regs=["GHG_PROTOCOL", "ESRS_E1"],
            rec="Report the baseline year and value alongside any change figure.",
        )
        flags += cls._maybe(
            "NON_GROUNDABLE", non_ground, total,
            title="Claims that cannot be verified against evidence",
            desc_t="{n} claims ({pct}%) score below the groundability threshold — no observable basis.",
            sev_fn=lambda n, pct: "High" if pct >= 40 else "Medium",
            regs=["EU_GREEN_CLAIMS", "BRSR"],
            rec="Provide auditable evidence (data, methodology, third-party assurance).",
        )
        flags += cls._maybe(
            "SELECTIVE_SCOPE", selective, total,
            title="Selective scope (potential cherry-picking)",
            desc_t="{n} quantified claims report only a narrow geography/scope rather than group-wide figures.",
            sev_fn=lambda n, pct: "Medium",
            regs=["EU_GREEN_CLAIMS", "GHG_PROTOCOL"],
            rec="Report group-wide totals; disclose sub-scope figures as supplementary, not headline.",
        )

        # ── aggregate flags ─────────────────────────────────────────────────────
        # Disclosure gap: no Scope 3 emissions disclosure at all.
        has_scope3 = any(str(c.get("normalized_aspect") or "").startswith("emissions.scope3")
                         or "scope 3" in (c.get("source_sentence") or "").lower() for c in claims)
        has_emissions = any(str(c.get("metric_family") or "").startswith("emissions") for c in claims)
        if has_emissions and not has_scope3:
            flags.append(GreenwashFlag(
                type="DISCLOSURE_GAP", severity="High",
                title="No Scope 3 emissions disclosure",
                description="The report discloses emissions but contains no Scope 3 (value-chain) figures, "
                            "which are typically the majority of an organisation's footprint.",
                regulations=[REG["ESRS_E1"], REG["GHG_PROTOCOL"]],
                recommendation="Disclose Scope 3 categories or explain the omission with a remediation timeline.",
                count=0,
            ))

        # Aspirational-heavy: promises/narrative dominate delivered performance.
        perf = ct.get("performance", 0)
        promo = ct.get("target", 0) + ct.get("narrative", 0)
        if total >= 10 and perf > 0 and promo / max(perf, 1) >= 2.0:
            pct = round(promo * 100 / total)
            flags.append(GreenwashFlag(
                type="ASPIRATIONAL_HEAVY", severity="Medium",
                title="Aspiration outweighs delivered performance",
                description=f"{pct}% of claims are targets/narrative vs. delivered performance "
                            f"({perf} performance claims) — a tone-vs-substance imbalance.",
                regulations=[REG["EU_GREEN_CLAIMS"]],
                recommendation="Balance forward-looking pledges with reported, audited performance data.",
                count=promo,
            ))

        # Contradictions (from the contradiction engine) become a flag.
        contradictions = contradictions or []
        if contradictions:
            sev = "Critical" if any((x.get("severity") in ("Critical", "High")) for x in contradictions) else "Medium"
            flags.append(GreenwashFlag(
                type="CONTRADICTION", severity=sev,
                title="Internally inconsistent figures",
                description=f"{len(contradictions)} contradiction(s) detected between claims in this report.",
                regulations=[REG["BRSR"], REG["ESRS_E1"]],
                recommendation="Reconcile conflicting figures; ensure one consistent value per metric/period/scope.",
                evidence=[{"reasoning": x.get("reasoning"), "severity": x.get("severity")} for x in contradictions[:cls.MAX_EVIDENCE]],
                count=len(contradictions),
            ))

        flags.sort(key=lambda f: _SEV_RANK.get(f.severity, 0), reverse=True)
        return flags

    # ── helpers ─────────────────────────────────────────────────────────────────
    @classmethod
    def _maybe(cls, ftype, hits, total, title, desc_t, sev_fn, regs, rec) -> List[GreenwashFlag]:
        if not hits:
            return []
        n = len(hits)
        pct = round(n * 100 / max(total, 1))
        return [GreenwashFlag(
            type=ftype,
            severity=sev_fn(n, pct),
            title=title,
            description=desc_t.format(n=n, pct=pct),
            regulations=[REG[r] for r in regs],
            recommendation=rec,
            evidence=[_ev(c) for c in hits[:cls.MAX_EVIDENCE]],
            count=n,
        )]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
