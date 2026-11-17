"""finder.py: what the Volunteer finder and the Sports tracker share.

Both pages ask the same kind of question: "which real places of this kind are
within N miles of me, and are they open when I'm free?" search() answers it by
running a few map searches (services/places.py), merging the results and
adding opening-hours information for the day and time the student picked.
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from services import places
from services.web import FETCH_ERRORS

RADIUS_CHOICES = [1, 2, 3, 5, 10, 15, 20, 25]
DEFAULT_RADIUS = 10
MAX_PLACES = 30

SLOT_NAMES = {"any": "any time", "morning": "morning", "afternoon": "afternoon", "evening": "evening"}


def clean_radius(value, default=DEFAULT_RADIUS):
    """A travel distance in miles, kept between 1 and 25."""
    try:
        return max(1, min(25, int(float(value))))
    except (TypeError, ValueError):
        return default


def clean_when(day_text, slot):
    """The student's free time: (date or None, slot). An unreadable or past date means "any day"."""
    slot = slot if slot in SLOT_NAMES else "any"
    try:
        day = datetime.strptime(str(day_text or ""), "%Y-%m-%d").date()
    except ValueError:
        return None, slot
    if day < date.today() or day > date.today() + timedelta(days=366):
        return None, slot
    return day, slot


def when_label(day, slot):
    """"Saturday, Nov 21, morning" / "any day, afternoon" / "any time"."""
    if day is None and slot == "any":
        return "any time"
    on = f"{day:%A}, {day:%b} {day.day}" if day else "any day"
    return on if slot == "any" else f"{on}, {SLOT_NAMES[slot]}"


def search(phrases, home, radius, keep=None):
    """Places matching any of the phrases within radius miles of home, nearest first.

    keep(place) can drop places that don't fit. Returns (places, problem):
    problem is a sentence for the student when the map service couldn't be reached.
    """
    found, problem = {}, ""
    for phrase in phrases:
        try:
            results = places.nearby(phrase, home["lat"], home["lon"], radius)
        except FETCH_ERRORS as error:
            print(f"[SAM] Map search for {phrase!r} failed: {error}")
            problem = "SAM couldn’t reach the map service just now, so some places may be missing. Try again in a minute."
            continue
        # Each search gets a fair share, so "Any kind" isn't all libraries.
        share = max(8, MAX_PLACES // len(phrases))
        for place in results:
            place = {**place, "phrase": phrase}
            if share and place["id"] not in found and (keep is None or keep(place)):
                found[place["id"]] = place
                share -= 1
    return sorted(found.values(), key=lambda p: p["miles"])[:MAX_PLACES], problem


def add_hours(place, day, slot):
    """Add readable opening hours, and whether the place is open when the student is free."""
    status = places.open_status(place["hours"], day.weekday() if day else None, slot)
    when = when_label(day, slot)
    place["hours_text"] = places.pretty_hours(place["hours"])
    place["open_status"] = status
    if status is None and not place["hours_text"]:
        place["open_text"] = "Hours not listed"
    elif day is None and slot == "any":
        place["open_text"] = ""  # No time picked: just show the hours
    else:
        place["open_text"] = {"open": f"Open {when}", "closed": f"Closed {when}"}.get(status, "Check the hours")
    return place


def directions_url(place):
    return f"https://www.openstreetmap.org/?mlat={place['lat']:.5f}&mlon={place['lon']:.5f}#map=17/{place['lat']:.5f}/{place['lon']:.5f}"


def search_url(words):
    return "https://duckduckgo.com/?q=" + quote(" ".join(str(words).split()), safe="")


def mentions(name, pattern):
    return re.search(pattern, str(name), re.I) is not None
