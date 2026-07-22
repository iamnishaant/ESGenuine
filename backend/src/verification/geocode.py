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

# Version suffix: bump whenever _candidates() OR the result filtering changes —
# cached results from an older ladder/filter must not mask what the new one yields.
# v3: added the geographic-class filter (reject POIs like the Xochimilco restaurant).
_CACHE_PATH = Path(__file__).resolve().parents[2] / ".geocode_cache_v3.json"
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
    m = re.match(r"^([A-Z][\w ]+?)'s (.+)$", t)
    if m:
        cands.append(f"{m.group(2)}, {m.group(1)}")   # "Madrid's Jarama riverbed" -> "Jarama riverbed, Madrid"
        cands.append(f"{_DESCRIPTOR.sub('', m.group(2)).strip()}, {m.group(1)}")
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


# Nominatim `class` values that denote a real GEOGRAPHIC feature (a place on the
# ground with vegetation/land to sample), vs a point-of-interest. Without this
# filter "Lake Xochimilco" (a Mexico City wetland) matched a Chicago restaurant
# named Xochimilco (class=amenity) ranked first for the exact-name query — and the
# NDVI was then measured around the wrong continent.
_GEO_CLASSES = {"place", "natural", "water", "waterway", "boundary", "landuse",
                "leisure", "geological", "landcover"}
# POI leisure sub-types that ARE ground features worth sampling (a park/reserve),
# vs a gym/pitch. `leisure` is in _GEO_CLASSES but narrowed here.
_GOOD_LEISURE = {"park", "nature_reserve", "garden", "recreation_ground", "common"}


def _acceptable(h: Dict[str, Any]) -> bool:
    cls, typ = h.get("class", ""), h.get("type", "")
    if cls == "leisure":
        return typ in _GOOD_LEISURE
    return cls in _GEO_CLASSES


def _query(q: str) -> Optional[Dict[str, Any]]:
    wait = 1.1 - (time.monotonic() - _LAST_CALL[0])
    if wait > 0:
        time.sleep(wait)
    # Ask for several candidates and keep the highest-importance GEOGRAPHIC one,
    # so a POI (restaurant/shop/office) sharing the place name never wins.
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": q, "format": "json", "limit": 10, "addressdetails": 0},
                     headers=_UA, timeout=20)
    _LAST_CALL[0] = time.monotonic()
    r.raise_for_status()
    hits = r.json()
    if not hits:
        return None
    geo = [h for h in hits if _acceptable(h)]
    if not geo:
        return None   # only POIs matched — honest miss, don't sample a business
    h = max(geo, key=lambda x: float(x.get("importance", 0) or 0))
    return {"lat": float(h["lat"]), "lon": float(h["lon"]),
            "display_name": h.get("display_name", ""),
            "class": h.get("class", ""),
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
