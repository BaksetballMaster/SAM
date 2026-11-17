"""geo.py: turn "Town or ZIP code" into a point on the map, and measure distances.

Where the answers come from (no keys needed):
    1. Nominatim, OpenStreetMap's search service
    2. Open-Meteo's geocoder, as a backup if Nominatim can't be reached

Only the town or ZIP code is sent. Nothing else about the student leaves SAM.

Nominatim's rules for free use are: at most one request a second, name your
app, and don't ask the same thing twice. nominatim() below waits its turn, and
every answer is kept by cache.py.
"""

import math
import re
import threading
import time

from . import cache
from .web import FETCH_ERRORS, get_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OPEN_METEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
SECONDS_BETWEEN_REQUESTS = 1.1
EARTH_RADIUS_MILES = 3958.8

_turn = threading.Lock()
_last_request = 0.0


def nominatim(params):
    """One Nominatim search. Waits its turn so SAM never sends more than one request a second."""
    global _last_request
    with _turn:
        wait = SECONDS_BETWEEN_REQUESTS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            return get_json(NOMINATIM_URL, {**params, "format": "jsonv2"})
        finally:
            _last_request = time.monotonic()


def geocode(text):
    """{"lat", "lon", "label"} for a town or ZIP code, like "94040" or "Austin, TX".

    Returns {} if the place doesn't exist, and None if SAM couldn't check
    (no geocoder could be reached, and SAM has never looked this place up before).
    """
    text = " ".join(str(text or "").split())[:80]
    if len(text) < 2:
        return {}
    key = "geocode|" + text.lower()
    found, age = cache.get(key)
    # A place that was found is remembered for a month; "not found" is only trusted for a day.
    if found is None or age > (30 * cache.DAY if found else cache.DAY):
        try:
            found = _look_up(text)
            cache.put(key, found)
        except FETCH_ERRORS as problem:
            print(f"[SAM] Couldn't look up {text!r} on the map: {problem}")
    return found


def _look_up(text):
    """Ask Nominatim, then Open-Meteo. Returns {} when the place doesn't exist."""
    zip_code = re.fullmatch(r"(\d{5})(-\d{4})?", text)
    query = {"postalcode": zip_code.group(1), "country": "US"} if zip_code else {"q": text}
    nominatim_down = False
    try:
        rows = nominatim({**query, "limit": 1, "addressdetails": 1})
        if rows:
            row = rows[0]
            return {"lat": float(row["lat"]), "lon": float(row["lon"]),
                    "label": _label(row.get("address") or {}, row.get("display_name") or text)}
    except FETCH_ERRORS as problem:
        print(f"[SAM] Nominatim didn't answer ({problem}). Trying the backup geocoder.")
        nominatim_down = True

    try:
        data = get_json(OPEN_METEO_URL, {"name": zip_code.group(1) if zip_code else text,
                                         "count": 5, "language": "en", "format": "json"})
    except FETCH_ERRORS:
        if nominatim_down:
            raise  # Both are unreachable: let geocode() fall back to an older answer.
        return {}
    results = data.get("results") or []
    if zip_code:
        results = [r for r in results if r.get("country_code") == "US"]
    if not results:
        return {}
    best = results[0]
    return {"lat": float(best["latitude"]), "lon": float(best["longitude"]),
            "label": ", ".join(part for part in (best.get("name"), best.get("admin1")) if part)}


def _label(address, full_name):
    """A short name for a place, like "Mountain View, CA"."""
    town = next((address[k] for k in ("city", "town", "village", "hamlet", "municipality", "suburb", "county")
                 if address.get(k)), "")
    if address.get("country_code") == "us":
        region = (address.get("ISO3166-2-lvl4") or "").split("-")[-1] or address.get("state", "")
    else:
        region = address.get("state") or address.get("country") or ""
    label = ", ".join(part for part in (town, region) if part)
    return label or ", ".join(part.strip() for part in full_name.split(",")[:2])


def miles_between(lat1, lon1, lat2, lon2):
    """Straight-line distance between two points, in miles (the haversine formula)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def box_around(lat, lon, radius_miles):
    """The square that holds a circle of radius_miles, as Nominatim's "left,top,right,bottom"."""
    up = radius_miles / 69.0  # One degree of latitude is about 69 miles
    across = radius_miles / (69.0 * max(math.cos(math.radians(lat)), 0.01))
    return f"{lon - across:.5f},{lat + up:.5f},{lon + across:.5f},{lat - up:.5f}"
