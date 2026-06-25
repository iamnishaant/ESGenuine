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

    # Per-claim flag types, in the order _per_claim_flags reports them.
    PER_CLAIM_FLAGS = ("VAGUE", "UNSUBSTANTIATED_TARGET", "MISSING_BASELINE",
                       "NON_GROUNDABLE", "SELECTIVE_SCOPE")

    # Human-readable, per-claim explanation for each per-claim flag (the review UI shows
    # this; analyze()'s flag.description is the aggregate "{n} claims ({pct}%)…" wording).
    _FLAG_META = {
        "VAGUE": ("Vague, unsubstantiated environmental claim",
                  "Vague language with no measurable metric — a primary greenwashing signal."),
        "UNSUBSTANTIATED_TARGET": ("Target without baseline, metric, or deadline",
                  "A target/pledge with no measurable metric or deadline — not verifiable as written."),
        "MISSING_BASELINE": ("Performance claim with no baseline period",
                  "An increase/decrease claim with no time period, so the change cannot be judged."),
        "NON_GROUNDABLE": ("Claim cannot be verified against evidence",
                  "Groundability score below threshold — no observable basis to verify it."),
        "SELECTIVE_SCOPE": ("Selective scope (potential cherry-picking)",
                  "A quantified claim reporting only a narrow geography/scope rather than group-wide."),
    }

    @classmethod
    def _per_claim_flags(cls, c: Dict[str, Any]) -> List[str]:
        """Which per-claim flag types this single claim triggers. Membership is per-claim
        (threshold tests only); severity/prevalence is computed by the caller over all claims.
        Shared by analyze() and attribute() so the two never drift."""
        out: List[str] = []
        vagueness = _num(c.get("vagueness_score"))
        ground = _num(c.get("groundability_score"))
        ctype = (c.get("claim_type") or "narrative").lower()
        has_metric = c.get("metric_value") is not None
        has_time = bool(c.get("time_bucket")) and str(c.get("time_bucket")).lower() not in ("unknown_time", "none", "null", "")
        direction = (c.get("metric_direction") or "").lower()
        scope = (c.get("location_scope") or "global").lower()
        if vagueness is not None and vagueness >= cls.VAGUE_MIN:
            out.append("VAGUE")
        if ctype == "target" and (not has_metric or not has_time):
            out.append("UNSUBSTANTIATED_TARGET")
        if ctype == "performance" and direction in ("increase", "decrease") and not has_time:
            out.append("MISSING_BASELINE")
        if ground is not None and ground < cls.NON_GROUND_MAX:
            out.append("NON_GROUNDABLE")
        if has_metric and scope not in ("global", "", "group", "company"):
            out.append("SELECTIVE_SCOPE")
        return out

    @staticmethod
    def _contra_id(contra: Dict[str, Any]) -> str:
        """Stable id for a contradiction (which has no claim_id) — short sha1 of its
        reasoning text. Used to address a single contradiction for review/dismissal."""
        import hashlib
        basis = str(contra.get("reasoning") or contra.get("reason") or "")
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def analyze(cls, claims: List[Dict[str, Any]],
                contradictions: Optional[List[Dict[str, Any]]] = None,
                dismissed: Optional[set] = None) -> List[GreenwashFlag]:
        """`dismissed` is a set of (subject_id, flag_type) reviewer dismissals. A dismissed
        item is removed from its flag's evidence before scoring, so the flag's count (hence
        prevalence and penalty) shrinks; a flag with everything dismissed disappears."""
        flags: List[GreenwashFlag] = []
        if not claims:
            return flags

        dismissed = dismissed or set()
        total = len(claims)
        ct = collections.Counter((c.get("claim_type") or "narrative") for c in claims)

        # ── per-claim accumulators (honoring dismissals) ────────────────────────
        buckets: Dict[str, list] = {ft: [] for ft in cls.PER_CLAIM_FLAGS}
        for c in claims:
            cid = str(c.get("claim_id"))
            for ft in cls._per_claim_flags(c):
                if (cid, ft) in dismissed:
                    continue
                buckets[ft].append(c)
        vague = buckets["VAGUE"]
        untargeted = buckets["UNSUBSTANTIATED_TARGET"]
        missing_base = buckets["MISSING_BASELINE"]
        non_ground = buckets["NON_GROUNDABLE"]
        selective = buckets["SELECTIVE_SCOPE"]

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
        if has_emissions and not has_scope3 and ("__report__", "DISCLOSURE_GAP") not in dismissed:
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
        if (total >= 10 and perf > 0 and promo / max(perf, 1) >= 2.0
                and ("__report__", "ASPIRATIONAL_HEAVY") not in dismissed):
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

        # Contradictions (from the contradiction engine) become a flag. Drop any the
        # reviewer dismissed (by stable hash) before counting, so the count reflects only
        # the contradictions a human hasn't waved off.
        contradictions = [x for x in (contradictions or [])
                          if (cls._contra_id(x), "CONTRADICTION") not in dismissed]
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

    @classmethod
    def attribute(cls, claims: List[Dict[str, Any]],
                  contradictions: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """The reviewable inventory: one addressable entry per flagged item — every
        per-claim flag hit, every contradiction, and each fired report-level flag — with
        the model's stated reason. Drives the human-review queue. Mirrors analyze()'s
        firing conditions but yields items keyed by subject_id instead of aggregated flags."""
        items: List[Dict[str, Any]] = []
        if not claims:
            return items
        total = len(claims)

        # per-claim flags
        for c in claims:
            cid = str(c.get("claim_id"))
            for ft in cls._per_claim_flags(c):
                title, reason = cls._FLAG_META[ft]
                items.append({
                    "subject_id": cid, "flag_type": ft, "kind": "claim",
                    "title": title, "reason": reason,
                    "source_sentence": (c.get("source_sentence") or "")[:240],
                    "page_number": c.get("page_number"),
                })

        # contradictions — each addressable by its stable hash
        for x in (contradictions or []):
            txt = x.get("reasoning") or x.get("reason") or ""
            items.append({
                "subject_id": cls._contra_id(x), "flag_type": "CONTRADICTION", "kind": "contradiction",
                "title": "Internally inconsistent figures", "reason": txt,
                "source_sentence": txt[:240], "page_number": None,
            })

        # report-level flags — one item each, addressed by the '__report__' sentinel
        has_scope3 = any(str(c.get("normalized_aspect") or "").startswith("emissions.scope3")
                         or "scope 3" in (c.get("source_sentence") or "").lower() for c in claims)
        has_emissions = any(str(c.get("metric_family") or "").startswith("emissions") for c in claims)
        if has_emissions and not has_scope3:
            items.append({
                "subject_id": "__report__", "flag_type": "DISCLOSURE_GAP", "kind": "report",
                "title": "No Scope 3 emissions disclosure",
                "reason": "Emissions are disclosed but there is no Scope 3 (value-chain) figure.",
                "source_sentence": None, "page_number": None,
            })
        ct = collections.Counter((c.get("claim_type") or "narrative") for c in claims)
        perf = ct.get("performance", 0)
        promo = ct.get("target", 0) + ct.get("narrative", 0)
        if total >= 10 and perf > 0 and promo / max(perf, 1) >= 2.0:
            items.append({
                "subject_id": "__report__", "flag_type": "ASPIRATIONAL_HEAVY", "kind": "report",
                "title": "Aspiration outweighs delivered performance",
                "reason": f"{round(promo * 100 / total)}% of claims are targets/narrative vs. {perf} performance claims.",
                "source_sentence": None, "page_number": None,
            })
        return items

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
