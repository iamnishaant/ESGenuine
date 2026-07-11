"""
Sentinel-2 L2A NDVI composites via Planetary Computer (anonymous, free).

For an AOI point + date window: STAC-search sentinel-2-l2a, take the N
least-cloudy scenes, windowed-read B04 (red) + B08 (NIR) at 10 m around the
point, and return the median-composite NDVI with per-scene provenance and a
SHA-256 of every pixel array read — the raw material for a reproducible
evidence bundle. Scene selection uses eo:cloud_cover (per-pixel SCL masking is
a documented phase-2 refinement; the composite std already exposes noisy
windows and the verdict layer treats high spread as inconclusive).
"""
import hashlib
from typing import Dict, Any, List

import numpy as np
import rasterio
from rasterio.windows import Window
import planetary_computer
import pystac_client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
MAX_SCENES = 4
MAX_CLOUD = 30.0          # % scene cloud cover admitted to the composite


def _read_patch(href: str, lon: float, lat: float, buffer_m: int) -> np.ndarray:
    """Windowed read around (lon, lat); returns a float array (reflectance DN)."""
    with rasterio.open(href) as src:
        # Sentinel-2 COGs are in the tile's UTM CRS — project the point in.
        from rasterio.warp import transform as warp_transform
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        row, col = src.index(xs[0], ys[0])
        half = max(1, int(buffer_m / abs(src.transform.a)))
        win = Window(col - half, row - half, 2 * half, 2 * half)
        arr = src.read(1, window=win, boundless=True, fill_value=0).astype("float32")
    return arr


def ndvi_composite(lon: float, lat: float, date_from: str, date_to: str,
                   buffer_m: int = 250) -> Dict[str, Any]:
    """Median NDVI composite for the AOI over [date_from, date_to].

    Returns {ndvi_mean, ndvi_std, n_scenes, scenes:[{id, datetime, cloud_cover,
    b04_sha256, b08_sha256}], error?}. Never raises on 'no data' — reports it."""
    catalog = pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{date_from}/{date_to}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD}},
    )
    items = sorted(search.item_collection(),
                   key=lambda it: it.properties.get("eo:cloud_cover", 100.0))[:MAX_SCENES]
    if not items:
        return {"ndvi_mean": None, "ndvi_std": None, "n_scenes": 0, "scenes": [],
                "error": f"no scenes < {MAX_CLOUD}% cloud in {date_from}/{date_to}"}

    ndvis: List[np.ndarray] = []
    scenes: List[Dict[str, Any]] = []
    for it in items:
        try:
            red = _read_patch(it.assets["B04"].href, lon, lat, buffer_m)
            nir = _read_patch(it.assets["B08"].href, lon, lat, buffer_m)
        except Exception as e:  # one bad asset must not kill the composite
            scenes.append({"id": it.id, "error": str(e)[:120]})
            continue
        denom = nir + red
        ndvi = np.where(denom > 0, (nir - red) / np.where(denom == 0, 1, denom), np.nan)
        ndvis.append(ndvi)
        scenes.append({
            "id": it.id,
            "datetime": str(it.datetime),
            "cloud_cover": it.properties.get("eo:cloud_cover"),
            "b04_sha256": hashlib.sha256(red.tobytes()).hexdigest(),
            "b08_sha256": hashlib.sha256(nir.tobytes()).hexdigest(),
        })

    if not ndvis:
        return {"ndvi_mean": None, "ndvi_std": None, "n_scenes": 0, "scenes": scenes,
                "error": "all scene reads failed"}
    stack = np.stack(ndvis)
    median = np.nanmedian(stack, axis=0)
    return {
        "ndvi_mean": round(float(np.nanmean(median)), 4),
        "ndvi_std": round(float(np.nanstd(median)), 4),
        "n_scenes": len(ndvis),
        "scenes": scenes,
    }
