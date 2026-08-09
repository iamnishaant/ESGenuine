"""
ESGenuine — Peer Benchmarking & Target Trajectory
=================================================
Cross-company comparison and per-metric time trajectories, built on the canonical
unit layer (UnitCanonicalizer) so values from different reports are actually
comparable (ktCO2e vs tCO2e, ML vs m³, …).

Pure functions operate on lists of claim dicts; the API layer supplies them.

Polarity: for some metrics lower is better (emissions, LTIFR, water use), for others
higher is better (renewables, recycling, diversity). Used to phrase "better/worse".
"""

from typing import List, Dict, Any, Optional
import statistics

try:
    from extractors.ontology import UnitCanonicalizer
except ImportError:  # pragma: no cover
    from src.extractors.ontology import UnitCanonicalizer

_LOWER_BETTER = ("emissions", "waste.total", "water.consumption",
                 "social.health_safety.ltifr", "social.health_safety.fatalities",
                 "governance.ethics.incidents")
_HIGHER_BETTER = ("energy.renewable", "water.recycled", "waste.recycled",
                  "biodiversity", "social.diversity", "social.training",
                  "governance.board.diversity")


def polarity(metric_key: str) -> str:
    k = str(metric_key or "")
    for p in _LOWER_BETTER:
        if k.startswith(p):
            return "lower_better"
    for p in _HIGHER_BETTER:
        if k.startswith(p):
            return "higher_better"
    return "neutral"


# Absolute magnitude metrics where a reported ZERO is, in practice, an extraction
# artefact rather than a disclosure: no operating company emits exactly 0 tCO2e or
# consumes exactly 0 energy. Deliberately NOT applied to counts — "zero fatalities" and
# "zero incidents" are real, meaningful, and must keep benchmarking.
_NONZERO_SUFFIXES = (".co2e", ".intensity", ".energy", ".volume", ".mass")


def _is_artefact_zero(metric_key: str, value) -> bool:
    try:
        if float(value) != 0.0:
            return False
    except (TypeError, ValueError):
        return False
    return str(metric_key or "").endswith(_NONZERO_SUFFIXES)


def _canon_vals(claims: List[Dict[str, Any]], metric_key: str):
    """Canonical (value, unit) for plausible, metric-bearing claims of one metric_key."""
    out = []
    for c in claims:
        if c.get("metric_key") != metric_key or c.get("metric_value") is None:
            continue
        # A narrative mention is prose that happens to contain a number ("we aim to cut
        # Scope 1 emissions..."), not a reported figure. Ranking one against audited
        # disclosures compares an aspiration with a measurement.
        if str(c.get("claim_type") or "").lower() == "narrative":
            continue
        # Guard the specific failure found in live data 2026-08-09: an Infosys claim
        # extracted from a CLIENT case study ("A leading consumer goods company set
        # sustainability goals for net zero emissions") landed as
        # emissions.scope1.co2e = 0 tCO2e and cross_company ranked Infosys BEST in class
        # — publishing "Infosys has the lowest Scope 1 emissions" off a sentence about
        # somebody else. The quality gate had already flagged it `value_not_in_source`.
        #
        # We do NOT filter on that flag: `source_type` is not persisted to the DB, and
        # for TABLE claims the flag is expected (the source_sentence is only the row
        # label), so flag-filtering would also delete Shell's legitimate 50 Mt figure.
        # The zero-guard is narrower and safe.
        if _is_artefact_zero(metric_key, c.get("metric_value")):
            continue
        if not UnitCanonicalizer.is_value_plausible(metric_key, c.get("metric_value")):
            continue
        v, u = UnitCanonicalizer.to_canonical(c.get("metric_value"), c.get("metric_unit"))
        out.append((v, (u or "").strip()))
    return out


def _representative(claims, metric_key):
    """A single comparable number for a (company, year, metric): median of canonical
    values sharing the modal unit."""
    vals = _canon_vals(claims, metric_key)
    if not vals:
        return None, None
    # pick the most common canonical unit so we never average across units
    modal_unit = statistics.mode([u for _, u in vals]) if vals else ""
    same = [v for v, u in vals if u == modal_unit]
    if not same:
        return None, None
    return round(statistics.median(same), 4), (modal_unit or None)


def _metric_year(c) -> Optional[int]:
    """The year the METRIC DESCRIBES — not the year its report was published.

    `time_bucket` is the disclosure year ("Scope 1 emissions FY23" -> 2023);
    `report_year` is only the publication year of the containing document. They differ
    constantly, because an ESG report almost always discloses a multi-year series: Shell
    SR2022 carries Scope 1 for 2018-2022, all with report_year=2022.

    Grouping on report_year therefore merged unrelated years and took their MEDIAN,
    which produced numbers belonging to no year at all:
      * Tata FY23 28,312,137 + FY24 38,671,851 -> benchmarked as 33,491,994 (2024)
      * Shell's five-point 71->51 Mt series    -> one point at 2022, value 63
    The second case silently defeated the trajectory/YoY chart entirely.

    Falls back to report_year when the bucket is a placeholder ('unknown_time' etc.,
    ~38% of the corpus) so those claims still benchmark rather than vanishing.
    """
    tb = c.get("time_bucket")
    if tb is not None:
        s = str(tb).strip()
        if len(s) == 4 and s.isdigit():
            return int(s)
    ry = c.get("report_year")
    try:
        return int(ry) if ry is not None else None
    except (TypeError, ValueError):
        return None


def _company_year_groups(claims):
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for c in claims:
        key = (c.get("company_id") or c.get("company_name"), _metric_year(c))
        groups.setdefault(key, []).append(c)
    return groups


def cross_company(claims: List[Dict[str, Any]], metric_key: str,
                  year: Optional[int] = None) -> Dict[str, Any]:
    """Distribution of one metric across companies (latest year per company unless
    `year` is given). Returns ranked entries + summary stats."""
    groups = _company_year_groups(claims)
    # latest year per company (<= year if specified)
    latest: Dict[Any, tuple] = {}
    for (company, yr), cl in groups.items():
        if company is None or yr is None:
            continue
        if year is not None and yr > year:
            continue
        rep, unit = _representative(cl, metric_key)
        if rep is None:
            continue
        if company not in latest or yr > latest[company][0]:
            latest[company] = (yr, rep, unit)

    entries = [{"company": c, "year": y, "value": v, "unit": u} for c, (y, v, u) in latest.items()]
    if not entries:
        return {"metric_key": metric_key, "polarity": polarity(metric_key), "entries": [], "n": 0}

    # Never compare across canonical units (intensity vs absolute, etc.). Keep only the
    # entries sharing the most common canonical unit.
    unit_counts: Dict[Any, int] = {}
    for e in entries:
        unit_counts[e["unit"]] = unit_counts.get(e["unit"], 0) + 1
    modal_unit = max(unit_counts, key=unit_counts.get)
    dropped = [e for e in entries if e["unit"] != modal_unit]
    entries = [e for e in entries if e["unit"] == modal_unit]
    if not entries:
        return {"metric_key": metric_key, "polarity": polarity(metric_key), "entries": [], "n": 0}

    pol = polarity(metric_key)
    # rank best→worst per polarity
    reverse = (pol == "higher_better")
    entries.sort(key=lambda e: e["value"], reverse=reverse)
    vals = [e["value"] for e in entries]
    med = statistics.median(vals)
    for i, e in enumerate(entries):
        worse = sum(1 for v in vals if (v < e["value"] if pol == "higher_better" else v > e["value"]))
        e["rank"] = i + 1
        e["percentile"] = round(worse * 100 / max(len(vals) - 1, 1)) if len(vals) > 1 else 100
        e["vs_median"] = round(e["value"] - med, 4)

    return {
        "metric_key": metric_key, "polarity": pol, "n": len(entries),
        "median": round(med, 4), "best": entries[0], "worst": entries[-1],
        "unit": entries[0]["unit"], "entries": entries,
        "incomparable_dropped": len(dropped),
        # <3 peers → percentile/rank are statistically thin; UI should caveat.
        "confidence": "low" if len(entries) < 3 else "ok",
    }


def company_scorecard(all_claims: List[Dict[str, Any]], company_id: str,
                      min_peers: int = 2) -> Dict[str, Any]:
    """For each metric_key the company shares with ≥`min_peers` companies, where it ranks."""
    company_claims = [c for c in all_claims
                      if (c.get("company_id") == company_id or c.get("company_name") == company_id)]
    if not company_claims:
        return {"company": company_id, "metrics": []}

    my_keys = {c.get("metric_key") for c in company_claims
               if c.get("metric_key") and c.get("metric_key") != "uncategorized"
               and not str(c.get("metric_key")).endswith(".unspecified")
               and c.get("metric_value") is not None}

    metrics = []
    for mk in my_keys:
        dist = cross_company(all_claims, mk)
        if dist["n"] < min_peers:
            continue
        mine = next((e for e in dist["entries"]
                     if e["company"] in (company_id, company_claims[0].get("company_name"))), None)
        if not mine:
            continue
        verdict = ("leading" if mine["percentile"] >= 66 else
                   "lagging" if mine["percentile"] <= 33 else "mid-pack")
        metrics.append({
            "metric_key": mk, "polarity": dist["polarity"], "unit": dist["unit"],
            "value": mine["value"], "rank": mine["rank"], "of": dist["n"],
            "percentile": mine["percentile"], "peer_median": dist["median"], "verdict": verdict,
            "low_confidence": dist["n"] < 3,   # thin peer set → caveat this row
        })
    metrics.sort(key=lambda m: m["percentile"])  # worst first (actionable)
    return {"company": company_id, "metrics_compared": len(metrics), "metrics": metrics,
            "low_confidence_metrics": sum(1 for m in metrics if m["low_confidence"])}


def trajectory(all_claims: List[Dict[str, Any]], company_id: str, metric_key: str,
               target_value: Optional[float] = None, target_year: Optional[int] = None) -> Dict[str, Any]:
    """Per-year canonical value series for one company+metric, with YoY + trend, and
    optional gap-to-target."""
    company_claims = [c for c in all_claims
                      if (c.get("company_id") == company_id or c.get("company_name") == company_id)]
    groups = _company_year_groups(company_claims)
    series = []
    for (company, yr), cl in groups.items():
        if yr is None:
            continue
        rep, unit = _representative(cl, metric_key)
        if rep is not None:
            series.append({"year": yr, "value": rep, "unit": unit})
    series.sort(key=lambda p: p["year"])

    out = {"company": company_id, "metric_key": metric_key,
           "polarity": polarity(metric_key), "series": series, "points": len(series)}
    if len(series) >= 2:
        first, last = series[0], series[-1]
        span = last["year"] - first["year"]
        out["change"] = round(last["value"] - first["value"], 4)
        out["change_pct"] = round((last["value"] - first["value"]) * 100 / abs(first["value"]), 1) if first["value"] else None
        # Linear average change per year (absolute units/yr). This — NOT a compound rate —
        # is the basis for the gap-to-target check below, because required_per_year is also
        # a linear absolute rate; comparing a compound fraction against it would be a
        # dimension error. (Was misleadingly named `cagr_per_year`; see self_improvement.md.)
        out["avg_change_per_year"] = round((last["value"] - first["value"]) / span, 4) if span else None
        # True compound annual growth rate (fraction/yr), for display only. Defined only when
        # both endpoints are positive: a CAGR across a zero baseline or a sign change is
        # mathematically meaningless, so report None rather than a misleading number.
        out["cagr"] = (round((last["value"] / first["value"]) ** (1 / span) - 1, 4)
                       if span and first["value"] > 0 and last["value"] > 0 else None)
        out["trend"] = ("up" if last["value"] > first["value"] else
                        "down" if last["value"] < first["value"] else "flat")
        if target_value is not None and target_year is not None and out.get("avg_change_per_year") is not None:
            needed = target_value - last["value"]
            years_left = target_year - last["year"]
            req_rate = needed / years_left if years_left else None
            pol = polarity(metric_key)
            on_track = None
            if req_rate is not None:
                # moving the right direction fast enough? (linear rate vs linear required rate)
                if pol == "lower_better":
                    on_track = out["avg_change_per_year"] <= req_rate
                elif pol == "higher_better":
                    on_track = out["avg_change_per_year"] >= req_rate
            out["target"] = {"value": target_value, "year": target_year,
                             "gap": round(needed, 4), "required_per_year": round(req_rate, 4) if req_rate is not None else None,
                             "on_track": on_track}
    return out
