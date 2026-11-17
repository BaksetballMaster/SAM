"""sports.py: the Sports tracker.

The student picks the sports they're interested in, how far they'll travel,
whether they want girls, boys or co-ed programs, and when they're free.
find() returns real places to play and train for those sports near them, from
OpenStreetMap (fields, courts, pools, tracks, dojos, sports centers), with
distance and opening hours, so the page can show them as a list and on a map.

OpenStreetMap records places, not clinic dates. Dated clinic listings come from
web search when a search key is set (TAVILY_API_KEY or BRAVE_API_KEY), and the
page links to a search for them otherwise. The girls / boys / co-ed choice
shapes those searches and hides places whose names say they're only for the
other group; most places don't record it at all, and the page says so.
"""

import re

import sam_ai

from . import finder

SPORTS = ["Soccer", "Basketball", "Track & Field", "Swimming", "Tennis", "Cricket", "Volleyball", "Martial arts"]

# What to search the map for, and the OpenStreetMap "sport" values that count as this sport.
SEARCHES = {
    "Soccer": (["soccer"], r"soccer|football"),
    "Basketball": (["basketball", "sports centre"], r"basketball"),
    "Track & Field": (["running track"], r"athletics|running"),
    "Swimming": (["swim"], r"swimming"),
    "Tennis": (["tennis"], r"tennis"),
    "Cricket": (["cricket"], r"cricket"),
    "Volleyball": (["volleyball"], r"volleyball"),
    "Martial arts": (["martial arts"], r"martial|karate|taekwondo|judo|aikido|jiu|kung|kickbox|boxing|fencing|wushu|dojo"),
}

GROUPS = [("any", "Any"), ("girls", "Girls"), ("boys", "Boys"), ("coed", "Co-ed")]
_ONLY_GIRLS = r"\b(girls?|women'?s|ladies)\b"
_ONLY_BOYS = r"\b(boys?|men'?s)\b"

# Kinds of map results that are places to play (not, say, a phone shop called "Cricket Wireless").
_SPORTY = {"leisure", "club", "sport"}
_SPORTY_TYPES = {"dojo", "recreation_ground", "community_centre", "school", "college", "university"}
_NOT_PUBLIC = re.compile(r"\b(apartments?|condos?|residences?|hotel|hoa|homeowners)\b", re.I)

_PLACE_KIND = {
    "pitch": "Field or court", "sports_centre": "Sports center", "swimming_pool": "Pool", "track": "Track", "stadium": "Stadium",
    "dojo": "Martial arts school", "recreation_ground": "Recreation ground", "fitness_centre": "Gym", "park": "Park",
    "sports_hall": "Sports hall", "ice_rink": "Rink",
}


def default_sports(prefs):
    if prefs.get("playsSports") != "yes":
        return []
    picked = [s for s in prefs.get("sports", []) if s in SPORTS]
    if "Other" in prefs.get("sports", []) and prefs.get("sportOther"):
        picked.append(prefs["sportOther"])
    return picked


def default_group(prefs):
    return {"female": "girls", "male": "boys"}.get(prefs.get("gender"), "any")


def clean_sports(chosen, other=""):
    """The sports to search for: known ones, plus one typed-in sport."""
    sports = [s for s in SPORTS if s in chosen]
    other = " ".join(str(other or "").split())[:40]
    if other and other.lower() not in (s.lower() for s in sports):
        sports.append(other)
    return sports[:5]


def find(home, radius, sports, group, day, slot, open_only=False):
    """Places to play near home for the chosen sports, plus clinic listings."""
    places = []
    problem = ""
    seen = set()
    for sport in sports:
        phrases, sport_tags = SEARCHES.get(sport, ([sport.lower()], re.escape(sport.lower())))
        found, trouble = finder.search(phrases, home, radius, keep=lambda p, tags=sport_tags: _fits(p, tags))
        problem = problem or trouble
        share = max(6, finder.MAX_PLACES // len(sports))  # Each sport gets a fair share of the list
        for place in found:
            if share == 0:
                break
            if place["id"] in seen or not _fits_group(place["name"], group):
                continue
            seen.add(place["id"])
            share -= 1
            finder.add_hours(place, day, slot)
            place.update(
                kind="sport", topic=sport, place_kind=_PLACE_KIND.get(place["type"], place["type"].replace("_", " ").capitalize()),
                directions=finder.directions_url(place),
                signup=place["website"] or finder.search_url(f"{place['name']} {place['town']} youth {sport} clinic"),
                signup_label="Visit website" if place["website"] else "Find clinics here",
            )
            places.append(place)
    places.sort(key=lambda p: p["miles"])
    if open_only:
        places = [p for p in places if p["open_status"] != "closed"]

    who = {"girls": "girls ", "boys": "boys ", "coed": "co-ed "}.get(group, "")
    clinics, links = [], []
    for sport in sports:
        query = f"{who}youth {sport} clinic near {home['label']}"
        links.append({"sport": sport, "url": finder.search_url(query), "query": query})
        if sam_ai.search_configured():
            clinics += [{**r, "kind": "sport", "topic": sport} for r in sam_ai.web_search(query, 3)]
    return {"places": places[:finder.MAX_PLACES], "clinics": clinics, "clinic_links": links, "problem": problem}


def _fits(place, sport_tags):
    """Keep places to play: not shops or streets, not private pools, and general sports centers only if they list this sport."""
    if place["category"] not in _SPORTY and place["type"] not in _SPORTY_TYPES:
        return False
    if _NOT_PUBLIC.search(place["name"]):
        return False
    if place["phrase"] == "sports centre":
        return any(re.search(sport_tags, s) for s in place["sports"])
    return True


def _fits_group(name, group):
    """Hide places whose names say they're only for the other group. Most names say nothing, and stay."""
    says_girls, says_boys = finder.mentions(name, _ONLY_GIRLS), finder.mentions(name, _ONLY_BOYS)
    if says_girls and says_boys:
        return True  # "Boys & Girls Club" is for everyone
    if group == "girls":
        return not says_boys
    if group == "boys":
        return not says_girls
    if group == "coed":
        return not (says_girls or says_boys)
    return True
