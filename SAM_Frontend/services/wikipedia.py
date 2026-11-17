"""wikipedia.py: short article introductions from Wikipedia.

The Concept helper uses these as sources: SAM reads the introduction of the
articles that best match the student's topic, shows them as citations, and
passes them to the AI model so its explanation is grounded in real text.
No key is needed. Only the topic is sent, never anything about the student.
"""

from . import cache
from .web import FETCH_ERRORS, get_json

API_URL = "https://en.wikipedia.org/w/api.php"


def introductions(topic, count=2):
    """[{"title", "url", "text", "source"}] for the best-matching articles. [] if none, or if Wikipedia can't be reached."""
    topic = " ".join(str(topic or "").split())[:120]
    if len(topic) < 3:
        return []
    try:
        data = cache.remember("wikipedia|" + topic.lower(), 7 * cache.DAY, lambda: get_json(API_URL, {
            "action": "query", "format": "json", "generator": "search", "gsrsearch": topic, "gsrlimit": count + 2,
            "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exsentences": 3, "exlimit": count + 2,
            "inprop": "url",
        }))
    except FETCH_ERRORS as problem:
        print(f"[SAM] Couldn't reach Wikipedia: {problem}")
        return []
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    found = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        text = " ".join(str(page.get("extract") or "").split())
        title = str(page.get("title") or "")
        url = str(page.get("fullurl") or "")
        if not text or not url.startswith("https://") or "(disambiguation)" in title or "may refer to" in text[:160]:
            continue
        found.append({"title": f"{title} (Wikipedia)", "url": url, "text": _clip(text, 420), "source": "Wikipedia"})
    return found[:count]


def _clip(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"
