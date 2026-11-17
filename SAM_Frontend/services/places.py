"""places.py: real places near a point, from OpenStreetMap.

nearby("animal shelter", lat, lon, 10) asks Nominatim (OpenStreetMap's search
service, see geo.py) for animal shelters inside a box around the point, keeps
the ones within 10 miles, and returns them nearest first. Each place has its
name, address, distance, and, when OpenStreetMap volunteers have added them,
its website and opening hours.

The second half of the file reads OpenStreetMap's opening-hours text, like
"Mo-Fr 09:00-17:00; Sa 10:00-14:00", so SAM can say whether a place is open at
the time a student is free.
"""

import re

from . import cache, geo

MAX_RESULTS = 40  # The most Nominatim returns for one search


def nearby(phrase, lat, lon, radius_miles):
    """Places matching a phrase within radius_miles of a point, nearest first.

    Raises one of web.FETCH_ERRORS if the map service can't be reached and SAM
    has never run this search before.
    """
    key = f"places|{phrase.lower()}|{lat:.3f}|{lon:.3f}|{radius_miles}"
    rows = cache.remember(key, 3 * cache.DAY, lambda: geo.nominatim({
        "q": phrase, "viewbox": geo.box_around(lat, lon, radius_miles), "bounded": 1,
        "limit": MAX_RESULTS, "addressdetails": 1, "extratags": 1, "dedupe": 1,
    }))
    found = (_place(row, lat, lon) for row in rows if isinstance(row, dict))
    return sorted((p for p in found if p and p["miles"] <= radius_miles), key=lambda p: p["miles"])


def _place(row, lat, lon):
    """Tidy one Nominatim result. Returns None for places without a name, or marked private."""
    tags = row.get("extratags") or {}
    address = row.get("address") or {}
    name = " ".join(str(row.get("name") or "").split())
    if not name or tags.get("access") in ("private", "no"):
        return None
    try:
        place_lat, place_lon = float(row["lat"]), float(row["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    street = " ".join(part for part in (address.get("house_number"), address.get("road")) if part)
    town = next((address[k] for k in ("city", "town", "village", "hamlet", "suburb") if address.get(k)), "")
    website = str(tags.get("website") or tags.get("contact:website") or tags.get("url") or "").strip()
    if website and not re.match(r"^https?://", website, re.I):
        website = "https://" + website
    if not re.match(r"^https?://[^\s/.]+\.[^\s]+$", website, re.I):
        website = ""
    return {
        "id": f"osm:{str(row.get('osm_type') or 'x')[0]}{row.get('osm_id')}",
        "name": name[:120],
        "category": row.get("category") or "",
        "type": row.get("type") or "",
        "lat": place_lat,
        "lon": place_lon,
        "miles": round(geo.miles_between(lat, lon, place_lat, place_lon), 1),
        "address": ", ".join(part for part in (street, town) if part),
        "town": town,
        "website": website[:300],
        "hours": str(tags.get("opening_hours") or "").strip()[:200],
        "sports": [s for s in re.split(r"\s*[;,]\s*", str(tags.get("sport") or "").lower()) if s],
        "facility": tags.get("social_facility") or "",
        "members_only": tags.get("access") in ("customers", "members", "permit"),
    }


# ---------- Opening hours ----------

DAY_CODES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY = "(?:Mo|Tu|We|Th|Fr|Sa|Su)"
_SPAN = r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}"
_RULE = re.compile(rf"^({_DAY}(?:\s*[-,]\s*{_DAY})*)?\s*:?\s*((?:{_SPAN})(?:\s*,\s*{_SPAN})*|off|closed)$", re.I)

# The parts of the day a student can pick, in minutes after midnight.
SLOTS = {
    "any": (8 * 60, 20 * 60),
    "morning": (8 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, 21 * 60),
}


def parse_hours(text):
    """Read OpenStreetMap opening hours into {weekday: [(open, close), ...]}, in minutes.

    Weekdays are 0 (Monday) to 6 (Sunday). Returns None for text this simple
    reader doesn't understand (for example "by appointment" or seasonal hours),
    so callers can say "hours not listed" instead of guessing.
    """
    text = str(text or "").strip()
    if not text:
        return None
    if text == "24/7":
        return {day: [(0, 24 * 60)] for day in range(7)}
    week = {}
    for rule in text.split(";"):
        rule = rule.strip()
        if not rule or rule.upper().startswith(("PH", "SH")):  # Public and school holidays: skipped
            continue
        match = _RULE.match(rule)
        if not match:
            return None
        if match.group(2).lower() in ("off", "closed"):
            spans = []
        else:
            spans = []
            for span in match.group(2).split(","):
                start, end = (int(h) * 60 + int(m) for h, m in re.findall(r"(\d{1,2}):(\d{2})", span))
                spans.append((start, end if end > start else end + 24 * 60))
        for day in (_days(match.group(1)) if match.group(1) else range(7)):
            week[day] = spans  # A later rule replaces an earlier one for the same day
    return week or None


def _days(text):
    """"Mo-Fr" -> [0, 1, 2, 3, 4];  "Sa,Su" -> [5, 6];  "Sa-Mo" -> [5, 6, 0]."""
    days = []
    for part in text.split(","):
        ends = [DAY_CODES.index(code.strip().capitalize()) for code in part.split("-")]
        day = ends[0]
        days.append(day)
        while day != ends[-1]:
            day = (day + 1) % 7
            days.append(day)
    return days


def open_status(text, weekday, slot="any"):
    """"open", "closed" or None (not known) for a part of the day.

    weekday is 0 (Monday) to 6 (Sunday), or None to ask about any day of the week.
    A place counts as open if it's open for at least half an hour of the slot.
    """
    week = parse_hours(text)
    if week is None:
        return None
    start, end = SLOTS.get(slot, SLOTS["any"])
    for day in (range(7) if weekday is None else [weekday]):
        for opens, closes in week.get(day, []):
            if min(closes, end) - max(opens, start) >= 30:
                return "open"
    return "closed"


def _clock(minutes):
    minutes %= 24 * 60
    if minutes == 0:
        return "midnight"
    if minutes == 12 * 60:
        return "noon"
    hour, minute = divmod(minutes, 60)
    return f"{hour % 12 or 12}{f':{minute:02d}' if minute else ''} {'am' if hour < 12 else 'pm'}"


def pretty_hours(text):
    """Opening hours a student can read: "Mon–Fri 9 am to 5 pm; Sat 10 am to 2 pm"."""
    week = parse_hours(text)
    if week is None:
        return str(text or "").strip().strip('"')[:60]
    if all(week.get(day) == [(0, 24 * 60)] for day in range(7)):
        return "Open 24 hours"
    parts, day = [], 0
    while day < 7:
        spans, last = week.get(day), day
        while last + 1 < 7 and week.get(last + 1) == spans:
            last += 1
        if spans:
            days = "Every day" if (day, last) == (0, 6) else DAY_NAMES[day] if last == day else f"{DAY_NAMES[day]}–{DAY_NAMES[last]}"
            parts.append(f"{days} " + ", ".join(f"{_clock(a)} to {_clock(b)}" for a, b in spans))
        day = last + 1
    return "; ".join(parts) or "Closed"
