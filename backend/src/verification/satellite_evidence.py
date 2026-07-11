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
    "version": "sat-ev-2.1",
    "buffer_m": 250,
    "min_abs_delta": 0.05,   # NDVI units — below this the signal is noise
    "min_z": 2.0,            # paired-pixel z (see _paired_stats)
    "method": "paired_pixel",  # v2.0 used whole-composite means vs spatial std —
                               # spatial heterogeneity (river+urban in one AOI)
                               # drowned real change; pairing removes it.
    "n_eff_divisor": 16,     # spatial autocorrelation discount: ~4px correlation
                             # length -> one independent sample per 4x4 block
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
    (clamped to today). The claim's own time_bucket wins over report_year —
    reports describe the PRIOR fiscal year, and a planting dated FY23 inside a
    2024 report would otherwise land in the 'before' window. Sentinel-2
    coverage starts mid-2015."""
    tb = str(claim.get("time_bucket") or "")
    year = tb if tb.isdigit() else claim.get("report_year")
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None
    if year < 2017:  # need a full 'before' year of S2 coverage
        return None
    if year > date.today().year:  # "by 2028" targets: outcome not observable yet
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

    before_arr = before.pop("_median_array", None)
    after_arr = after.pop("_median_array", None)
    result: Dict[str, Any] = {
        "claim_id": claim.get("claim_id"), "report_id": claim.get("report_id"),
        "location_text": loc, "geocoded": geo, "windows": win,
        "expectation": expectation, "before": before, "after": after, "params": PARAMS,
    }
    if before.get("ndvi_mean") is None or after.get("ndvi_mean") is None \
            or before_arr is None or after_arr is None:
        result["verdict"] = "inconclusive"
        result["reason"] = "insufficient_cloud_free_scenes"
    else:
        stats = _paired_stats(before_arr, after_arr)
        result.update(stats)
        delta, z = stats["ndvi_delta"], stats["z_score"]
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


def _paired_stats(before_arr, after_arr) -> Dict[str, Any]:
    """Per-pixel paired differencing: the same ground cell compared with itself
    across time, so spatial heterogeneity (river+urban+field inside one AOI)
    cancels out of the noise term. z = mean(delta) / (std(delta)/sqrt(n_eff)),
    with n_eff discounted for spatial autocorrelation (PARAMS.n_eff_divisor).
    S2 L2A geolocation accuracy (~1 px) is adequate for 250 m vegetation AOIs."""
    import numpy as np
    h = min(before_arr.shape[0], after_arr.shape[0])
    w = min(before_arr.shape[1], after_arr.shape[1])
    d = after_arr[:h, :w] - before_arr[:h, :w]
    valid = d[~np.isnan(d)]
    if valid.size < 32:
        return {"ndvi_delta": 0.0, "z_score": 0.0, "n_pixels": int(valid.size)}
    n_eff = max(1.0, valid.size / PARAMS["n_eff_divisor"])
    mean = float(np.mean(valid))
    sd = float(np.std(valid)) or 1e-6
    return {"ndvi_delta": round(mean, 4),
            "z_score": round(mean / (sd / n_eff ** 0.5), 2),
            "n_pixels": int(valid.size)}
