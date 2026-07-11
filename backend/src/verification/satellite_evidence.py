"""
Satellite Evidence v2 — orchestrator.

claim -> scale gate -> geocode -> before/after NDVI composites -> deterministic
verdict -> SHA-256-committed evidence bundle.

Design rules (locked):
  - The agent/LLM never judges: the verdict is a pure function of committed
    numbers, and every input that produced it is hashed into the bundle.
  - Honesty first: anything the 10 m optical signal cannot support returns
    `inconclusive` with a machine-readable reason, never a guessed verdict.

Aspect expectations (direction of NDVI change if the claim is true):
  biodiversity.conservation / reforestation  -> NDVI UP
  energy.renewable solar build-out           -> NDVI DOWN (vegetation -> panels)
  everything else                            -> no optical expectation -> inconclusive
"""
import hashlib
import json
import re
from datetime import date
from typing import Dict, Any, Optional

from .geocode import geocode, geocodable
from .sentinel_ndvi import ndvi_composite

PARAMS = {
    "version": "sat-ev-2.0",
    "buffer_m": 250,
    "min_abs_delta": 0.05,   # NDVI units — below this the signal is noise
    "min_z": 1.0,            # |delta| / pooled composite std
    "collection": "sentinel-2-l2a",
}

_SOLAR = re.compile(r"\b(solar|photovoltaic|pv plant)\b", re.I)
_REFOREST = re.compile(r"\b(reforest|afforest|tree[s]? plant|sapling|plantation|"
                       r"agroforestry|habitat restor|riverbed revitali)\b", re.I)


def _expectation(claim: Dict[str, Any]) -> Optional[str]:
    """'up' | 'down' | None (no optical expectation)."""
    sent = (claim.get("source_sentence") or "")
    asp = claim.get("normalized_aspect") or ""
    if asp.startswith("biodiversity") or _REFOREST.search(sent):
        return "up"
    if asp.startswith("energy.renewable") and _SOLAR.search(sent):
        return "down"
    return None


def _windows(claim: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Before = calendar year preceding the claim year; after = claim year
    (clamped to today). Sentinel-2 coverage starts mid-2015."""
    year = claim.get("report_year")
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    if year < 2017:  # need a full 'before' year of S2 coverage
        return None
    today = date.today().isoformat()
    after_end = min(f"{year}-12-31", today)
    return {"before_from": f"{year - 2}-01-01", "before_to": f"{year - 1}-12-31",
            "after_from": f"{year}-01-01", "after_to": after_end}


def _inconclusive(claim: Dict[str, Any], reason: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
    out = {"claim_id": claim.get("claim_id"), "verdict": "inconclusive",
           "reason": reason, "params": PARAMS}
    if extra:
        out.update(extra)
    out["bundle_sha256"] = _commit(out)
    return out


def _commit(result: Dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of everything that produced the verdict.
    Anyone re-running the pipeline with the same scenes must reproduce this hash."""
    canon = json.dumps({k: v for k, v in result.items() if k != "bundle_sha256"},
                       sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def verify_claim(claim: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full satellite check for one claim dict (DB row shape).
    Always returns a committed result; never raises on data gaps."""
    expectation = _expectation(claim)
    if expectation is None:
        return _inconclusive(claim, "no_optical_expectation_for_aspect")

    loc = claim.get("location_text")
    if not geocodable(loc):
        return _inconclusive(claim, "no_geocodable_location", {"location_text": loc})
    geo = geocode(loc)
    if not geo:
        return _inconclusive(claim, "geocode_failed", {"location_text": loc})
    # Scale gate: geocoded to an admin area the size of a state/country -> a
    # 250 m point sample says nothing about the claim.
    if geo.get("type") in ("administrative", "state", "country") and geo.get("boundingbox"):
        bb = [float(x) for x in geo["boundingbox"]]
        if abs(bb[1] - bb[0]) > 0.5 or abs(bb[3] - bb[2]) > 0.5:  # > ~55 km extent
            return _inconclusive(claim, "aoi_too_coarse",
                                 {"location_text": loc, "geocoded": geo["display_name"]})

    win = _windows(claim)
    if not win:
        return _inconclusive(claim, "no_valid_date_window",
                             {"report_year": claim.get("report_year")})

    before = ndvi_composite(geo["lon"], geo["lat"], win["before_from"], win["before_to"],
                            buffer_m=PARAMS["buffer_m"])
    after = ndvi_composite(geo["lon"], geo["lat"], win["after_from"], win["after_to"],
                           buffer_m=PARAMS["buffer_m"])

    result: Dict[str, Any] = {
        "claim_id": claim.get("claim_id"), "report_id": claim.get("report_id"),
        "location_text": loc, "geocoded": geo, "windows": win,
        "expectation": expectation, "before": before, "after": after, "params": PARAMS,
    }
    if before.get("ndvi_mean") is None or after.get("ndvi_mean") is None:
        result["verdict"] = "inconclusive"
        result["reason"] = "insufficient_cloud_free_scenes"
    else:
        delta = round(after["ndvi_mean"] - before["ndvi_mean"], 4)
        pooled = max(1e-6, ((before["ndvi_std"] or 0) ** 2 + (after["ndvi_std"] or 0) ** 2) ** 0.5)
        z = round(delta / pooled, 2)
        result["ndvi_delta"] = delta
        result["z_score"] = z
        moved = abs(delta) >= PARAMS["min_abs_delta"] and abs(z) >= PARAMS["min_z"]
        if not moved:
            result["verdict"] = "inconclusive"
            result["reason"] = "no_significant_change"
        elif (delta > 0) == (expectation == "up"):
            result["verdict"] = "supported"
            result["reason"] = f"ndvi_moved_{expectation}_as_claimed"
        else:
            result["verdict"] = "not_supported"
            result["reason"] = f"ndvi_moved_against_expectation_{expectation}"
    result["bundle_sha256"] = _commit(result)
    return result
