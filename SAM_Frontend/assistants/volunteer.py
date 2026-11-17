"""volunteer.py: the Volunteer finder.

The student gives a location, how far they'll travel, the kind of volunteering
they want, and when they're free. find() returns real places of that kind near
them, nearest first, from OpenStreetMap (see services/places.py), each with:

    distance, address, opening hours and whether it's open when they're free,
    a typical time commitment for that kind of place, and
    a link to sign up: the place's own website, or a search for how to volunteer there.

National and online programs that anyone can join are added at the end, and so
are web results when a search key is set (TAVILY_API_KEY or BRAVE_API_KEY).

Time commitments and age rules are typical for each KIND of place, not facts
about a particular place, and the page says so.
"""

import sam_ai

from . import finder

# (id, name, map searches, typical time commitment, age note)
CATEGORIES = [
    ("animals", "Animal shelters", ["animal shelter"],
     "Usually 2–3 hour shifts, about once a week",
     "Age rules vary. Many shelters ask volunteers under 16 to come with an adult."),
    ("food", "Food banks", ["food bank", "food pantry", "soup kitchen"],
     "Usually 2–3 hour sorting or packing shifts",
     "Many food banks welcome teens. Younger students often need an adult with them."),
    ("tutoring", "Libraries and tutoring", ["library"],
     "Usually 1–2 hours a week",
     "Many libraries run teen volunteer and reading-buddy programs."),
    ("environment", "Environment and parks", ["nature reserve", "community garden"],
     "Usually half-day workdays of 3–4 hours",
     "Outdoor workdays often welcome all ages, with a form signed by a parent."),
    ("care", "Hospitals and senior care", ["hospital", "nursing home", "assisted living"],
     "Usually 3–4 hour shifts, often weekly",
     "Hospitals often require volunteers to be 14 to 16 or older."),
    ("community", "Community centers", ["community centre"],
     "Usually an event, or a few hours a week",
     "Community centers often need help with events, camps and classes."),
]
ANY = ("any", "Any kind", ["animal shelter", "food bank", "library", "nature reserve"],
       "Depends on the place", "Age rules vary, so ask the place.")

# Survey answers -> category ids
FROM_SURVEY = {
    "Tutoring younger kids": "tutoring", "Environment & parks": "environment", "Animal shelters": "animals",
    "Food banks": "food", "Hospitals & senior care": "care", "Coding for nonprofits": "community",
}

ONLINE = [
    {"title": "VolunteerMatch", "url": "https://www.volunteermatch.org",
     "text": "Search thousands of volunteer openings, including ones for teens and ones you can do online."},
    {"title": "DoSomething.org", "url": "https://dosomething.org",
     "text": "Campaigns and volunteer ideas made for young people, many done from home."},
    {"title": "Schoolhouse.world", "url": "https://schoolhouse.world",
     "text": "Volunteer as a free peer tutor over video once you've mastered a subject."},
]


def category(category_id):
    return next((c for c in CATEGORIES if c[0] == category_id), ANY)


def default_category(prefs):
    """The first kind of volunteering the student picked in the survey, else "any"."""
    for picked in prefs.get("vol", []):
        if picked in FROM_SURVEY:
            return FROM_SURVEY[picked]
    return "any"


def find(home, radius, category_id, day, slot, open_only=False):
    """Volunteering near home. home is {"lat", "lon", "label"} from services/geo.py."""
    cat_id, name, phrases, commitment, ages = category(category_id)
    by_phrase = {phrase: entry for entry in CATEGORIES for phrase in entry[2]}

    places, problem = finder.search(phrases, home, radius)
    for place in places:
        finder.add_hours(place, day, slot)
        kind = by_phrase.get(place["phrase"], (cat_id, name, phrases, commitment, ages))
        place.update(
            kind="vol", topic=kind[1], commitment=kind[3], ages=kind[4],
            directions=finder.directions_url(place),
            signup=place["website"] or finder.search_url(f"{place['name']} {place['town']} volunteer"),
            signup_label="Visit website to sign up" if place["website"] else "Find how to volunteer here",
        )
    if open_only:
        places = [p for p in places if p["open_status"] != "closed"]

    words = "" if cat_id == "any" else name.lower()
    web = []
    if sam_ai.search_configured():
        web = [{**r, "kind": "vol", "topic": "From the web"}
               for r in sam_ai.web_search(f"teen volunteer opportunities {words} near {home['label']}", 5)]
    return {
        "places": places,
        "web": web,
        "online": [{**o, "kind": "vol", "topic": "Online and national"} for o in ONLINE],
        "category": {"id": cat_id, "name": name, "commitment": commitment, "ages": ages},
        "problem": problem,
        "search_link": finder.search_url(f"teen volunteer opportunities {words} near {home['label']}"),
    }
