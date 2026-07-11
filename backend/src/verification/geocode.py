"""
Nominatim geocoding with a disk cache and an honest junk filter.

The corpus's location_text is mostly un-geocodable ("Company facility",
"Shell Global", "globally"); the filter rejects those up front so the pipeline
reports "no geocodable location" instead of geocoding noise. Nominatim usage
policy: 1 req/s, identifying User-Agent, results cached to disk so re-runs are
free and hammering is impossible.
"""
import json
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any

import requests

_CACHE_PATH = Path(__file__).resolve().parents[2] / ".geocode_cache.json"
_UA = {"User-Agent": "ESGenuine-satellite-evidence/1.0 (open-source ESG audit tool)"}
_LAST_CALL = [0.0]

# Not places: company names, vague scopes, corporate boilerplate.
_JUNK = re.compile(
    r"^(global|globally|worldwide|various|multiple|company|the entire planet|earth|"
    r"planet|n/?a|shell|tata|infosys|microsoft|group|"
    r"all (our )?(sites|facilities|locations))\b|"
    # generic concepts that geocode to SOMETHING but denote no specific place
    r"^(world heritage|marine environment|critical habitats?|offshore|onshore|"
    r"communities|protected areas?|high.risk (areas|countries))\b|"
    r"(facilities|operations)$",
    re.I)
# Coarser than a city: whole countries/regions give a meaningless NDVI point sample.
_TOO_COARSE = {"india", "china", "usa", "united states", "uk", "united kingdom",
               "netherlands", "australia", "brazil", "nigeria", "germany", "canada",
               "andhra pradesh", "tamil nadu", "gujarat", "kerala", "amazon",
               "amazon rainforest", "europe", "asia", "africa"}


def geocodable(location_text: Optional[str]) -> bool:
    if not location_text:
        return False
    t = location_text.strip()
    return len(t) > 3 and not _JUNK.match(t) and t.lower() not in _TOO_COARSE


def _load_cache() -> Dict[str, Any]:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


# Report prose glued onto place names ("Jarama riverbed", "Heber Park at
# Hebersham", "buffer zones neighboring BMF") defeats verbatim search — build a
# ladder of progressively simplified queries and take the first hit.
_DESCRIPTOR = re.compile(
    r"\b(riverbed|revitali[sz]ation|datacenter|data center|buffer zones?|"
    r"neighboring|surrounding|near|around|project|programme|program|campus|"
    r"facility|plant|site)\b", re.I)


def _candidates(text: str) -> list:
    t = re.sub(r"\s+", " ", text.strip())
    cands = [t]
    if " at " in t:
        cands.append(t.split(" at ", 1)[1])          # "Heber Park at Hebersham" -> "Hebersham"
    stripped = _DESCRIPTOR.sub("", t)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" ,-")
    if stripped and stripped.lower() != t.lower():
        cands.append(stripped)                        # "Jarama riverbed, Madrid" -> "Jarama, Madrid"
    parts = [p.strip() for p in t.split(",") if p.strip()]
    if len(parts) >= 2:
        cands.append(parts[-1])                       # last locality token
    seen, out = set(), []
    for c in cands:
        if len(c) > 3 and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def _query(q: str) -> Optional[Dict[str, Any]]:
    wait = 1.1 - (time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "json", "limit": 1},
                     headers=_UA, timeout=20)
    _LAST_CALL[0] = time.monotonic()
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    h = hits[0]
    return {"lat": float(h["lat"]), "lon": float(h["lon"]),
            "display_name": h.get("display_name", ""),
            "type": h.get("type", ""), "boundingbox": h.get("boundingbox")}


def geocode(location_text: str) -> Optional[Dict[str, Any]]:
    """Resolve a place name to {lat, lon, display_name, type, boundingbox},
    trying progressively simplified queries. Returns None when the text is
    junk/too coarse or nothing resolves; the result records which query hit."""
    if not geocodable(location_text):
        return None
    cache = _load_cache()
    key = location_text.strip().lower()
    if key in cache:
        return cache[key] or None

    result = None
    try:
        for q in _candidates(location_text):
            result = _query(q)
            if result:
                result["matched_query"] = q
                break
    except Exception:
        return None  # network failure -> un-geocodable this run (not cached)

    cache[key] = result
    _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
