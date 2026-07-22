"""
ESGenuine — geocode result-filter regression suite
===================================================
Locks the geographic-class filter added after a live run geocoded "Lake
Xochimilco" (a Mexico City wetland) to a Chicago RESTAURANT named Xochimilco
(class=amenity) — Nominatim ranked the exact-name POI first, and the NDVI check
then sampled the wrong continent. `_acceptable` keeps only real ground features
(place/natural/water/boundary/landuse + park-like leisure) so a POI sharing a
place name can never win. Pure/offline — no network.

Runs two ways: pytest backend/tests/test_geocode_filter.py | python backend/tests/test_geocode_filter.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from verification.geocode import _acceptable, geocodable  # noqa: E402


def _hit(cls, typ):
    return {"class": cls, "type": typ}


def test_restaurant_poi_rejected():
    # the exact bug: amenity/restaurant must never be accepted as a place.
    assert not _acceptable(_hit("amenity", "restaurant"))
    assert not _acceptable(_hit("shop", "supermarket"))
    assert not _acceptable(_hit("office", "company"))
    assert not _acceptable(_hit("building", "yes"))


def test_geographic_features_accepted():
    assert _acceptable(_hit("waterway", "river"))       # Río Jarama
    assert _acceptable(_hit("natural", "water"))        # a lake
    assert _acceptable(_hit("place", "village"))
    assert _acceptable(_hit("boundary", "administrative"))
    assert _acceptable(_hit("landuse", "forest"))


def test_leisure_narrowed_to_ground_features():
    # a park/reserve is real vegetated ground; a gym/pitch is not.
    assert _acceptable(_hit("leisure", "park"))
    assert _acceptable(_hit("leisure", "nature_reserve"))
    assert not _acceptable(_hit("leisure", "fitness_centre"))
    assert not _acceptable(_hit("leisure", "pitch"))


def test_geocodable_junk_filter_still_holds():
    # unchanged pre-filter: company/vague scopes never reach the network.
    assert geocodable("Jarama riverbed, Madrid")
    assert not geocodable("globally")
    assert not geocodable("Shell")
    assert not geocodable("India")   # too coarse


_ALL_TESTS = [
    test_restaurant_poi_rejected,
    test_geographic_features_accepted,
    test_leisure_narrowed_to_ground_features,
    test_geocodable_junk_filter_still_holds,
]


if __name__ == "__main__":
    failures = 0
    for t in _ALL_TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(_ALL_TESTS) - failures}/{len(_ALL_TESTS)} passed")
    sys.exit(1 if failures else 0)
