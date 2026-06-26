"""
osm_service.py — live economic-activity signal from OpenStreetMap (Overpass).

For a ward centroid we count nearby economic features (markets, shops, banks)
and road segments within 5 km, and map the total to a 0–100 activity score:

    0 nodes   -> 10
    1–5       -> 30
    6–15      -> 50
    16–30     -> 70
    31+       -> 90

If Overpass is unreachable or errors, we return the neutral default (50) so the
BOI can still be computed. Results are cached in-memory for the process so the
same ward is not re-queried, and a 1-second delay is enforced between live
calls to respect the public Overpass endpoint.
"""

import time
from threading import Lock

import requests

# Public Overpass endpoints, tried in order for resilience (the main endpoint
# rate-limits under load).
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
RADIUS_M = 5000
DEFAULT_SCORE = 50
MIN_INTERVAL_S = 1.0  # politeness delay between live calls

# Process-wide cache + rate-limit state.
_cache: dict = {}
_lock = Lock()
_last_call = [0.0]


def _score_from_count(n: int) -> int:
    if n == 0:
        return 10
    if n <= 5:
        return 30
    if n <= 15:
        return 50
    if n <= 30:
        return 70
    return 90


def _cache_key(lat: float, lon: float) -> str:
    # ~100 m precision is plenty for a 5 km query and keeps the cache effective.
    return f"{lat:.3f},{lon:.3f}"


def get_osm_activity(lat: float, lon: float, timeout: int = 45) -> dict:
    """
    Return a dict: {score, total_nodes, breakdown{shops,markets,banks,roads},
    source, cached}. Never raises — falls back to the default score on failure.
    """
    if lat is None or lon is None:
        return _default("missing coordinates")

    key = _cache_key(lat, lon)
    with _lock:
        if key in _cache:
            cached = dict(_cache[key])
            cached["cached"] = True
            return cached

    # Overpass QL: economic POIs + major roads within RADIUS_M of the point.
    # We request full element bodies (with tags) so we can count accurately by
    # category, rather than a bare total.
    query = f"""
    [out:json][timeout:{timeout}];
    (
      node["shop"](around:{RADIUS_M},{lat},{lon});
      node["amenity"="market"](around:{RADIUS_M},{lat},{lon});
      node["amenity"="marketplace"](around:{RADIUS_M},{lat},{lon});
      node["amenity"="bank"](around:{RADIUS_M},{lat},{lon});
      way["highway"~"^(primary|secondary|tertiary)$"](around:{RADIUS_M},{lat},{lon});
    );
    out body;
    """

    # Enforce the politeness delay between live calls.
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()

    # A descriptive User-Agent is required — Overpass returns 406 to the default
    # python-requests UA.
    headers = {"User-Agent": "BankMapAI/1.0 (banking market intelligence; +https://bankmap.ai)"}
    elements, last_exc = None, None
    for url in OVERPASS_URLS:
        try:
            resp = requests.post(url, data={"data": query}, headers=headers, timeout=timeout + 10)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            break
        except Exception as exc:  # network error, timeout, rate-limit, bad JSON
            last_exc = exc
            continue
    if elements is None:
        return _default(f"overpass unavailable ({type(last_exc).__name__})")

    # Count each category from the returned elements.
    breakdown = {"shops": 0, "markets": 0, "banks": 0, "roads": 0}
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity")
        highway = tags.get("highway")
        if "shop" in tags:
            breakdown["shops"] += 1
        elif amenity in ("market", "marketplace"):
            breakdown["markets"] += 1
        elif amenity == "bank":
            breakdown["banks"] += 1
        elif highway in ("primary", "secondary", "tertiary"):
            breakdown["roads"] += 1

    total = sum(breakdown.values())
    result = {
        "score": _score_from_count(total),
        "total_nodes": total,
        "breakdown": breakdown,
        "source": "overpass-live",
        "cached": False,
    }
    with _lock:
        _cache[key] = dict(result)
    return result


def _default(reason: str) -> dict:
    return {
        "score": DEFAULT_SCORE,
        "total_nodes": None,
        "breakdown": {"shops": 0, "markets": 0, "banks": 0, "roads": 0},
        "source": f"default ({reason})",
        "cached": False,
    }
