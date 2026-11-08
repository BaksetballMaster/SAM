"""api.py: every call the SAM frontend makes for data.

There is no backend yet, so each function returns sample data. Each one is
marked with the backend endpoint it stands for (see SAM_Backend/README.md).
To connect a real backend, replace the body of each function with a request to
that endpoint and keep the same return value.

Sample data lives in memory, so it is cleared when the app restarts.
"""

import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

SPORTS = ["Soccer", "Basketball", "Track & Field", "Swimming", "Tennis", "Cricket", "Volleyball", "Martial arts", "Other"]
VOLUNTEER = ["Tutoring younger kids", "Environment & parks", "Animal shelters", "Food banks", "Hospitals & senior care", "Coding for nonprofits", "Other"]
EXAMPLES = ["Help me understand photosynthesis", "How do I start learning Python?", "Check my essay thesis", "Find soccer leagues near me", "Volunteering for students my age"]

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONFIRM_MINUTES = 10

# Sample stand-ins for the backend's database.
_prefs_by_email = {}
_shared_resources = []
_pending_codes = {}  # code -> {"email", "expires"}


def blank_prefs():
    return {"age": "", "loc": "", "gender": "", "playsSports": None, "sports": [], "sportOther": "", "vol": [], "volOther": ""}


def ok(**data):
    return {"ok": True, **data}


def fail(message):
    return {"ok": False, "error": message}


# ---------- Login and the confirmation email ----------
# Sample: accepts any valid email and a password of 8 or more characters.

def _check_login(email, password):
    if not EMAIL_RE.match(email):
        return "Enter a valid email address, like you@example.com."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    return None


def sign_in(email, password):
    """BACKEND: POST /api/auth/signin  { email, password }"""
    problem = _check_login(email, password)
    return fail(problem) if problem else ok(user={"name": email.split("@")[0], "email": email})


def sign_up(name, email, password):
    """BACKEND: POST /api/auth/signup  { name, email, password }"""
    if not name:
        return fail("Enter your first name.")
    problem = _check_login(email, password)
    return fail(problem) if problem else ok(user={"name": name, "email": email})


def sign_in_with_google():
    """BACKEND: POST /api/auth/google (in the real app, a redirect to the login service)."""
    return ok(user={"name": "Student", "email": "student@gmail.com"})


def send_login_confirmation(email):
    """BACKEND: POST /api/auth/send-confirmation

    The real backend emails a Yes / No link. Here the code is returned as
    `demoCode` so the demo inbox on the confirm page can answer it.
    """
    now = time.time()
    for code in [c for c, v in _pending_codes.items() if v["expires"] < now or v["email"] == email]:
        del _pending_codes[code]
    code = secrets.token_urlsafe(24)
    _pending_codes[code] = {"email": email, "expires": now + CONFIRM_MINUTES * 60}
    return ok(demoCode=code)


def answer_login_confirmation(code, email, it_was_me):
    """BACKEND: GET /api/auth/confirm?code=...&answer=yes|no"""
    entry = _pending_codes.pop(code or "", None)
    if not entry or entry["expires"] < time.time():
        return fail("That confirmation link has expired. Send it again.")
    if entry["email"] != email:
        return fail("That confirmation link is for a different sign-in.")
    return ok(confirmed=bool(it_was_me))


def sign_out():
    """BACKEND: POST /api/auth/signout"""
    return ok()


# ---------- Preferences ----------

def clean_prefs(raw):
    """Keep only known fields with the right types."""
    prefs = blank_prefs()
    if not isinstance(raw, dict):
        return prefs
    for key in ("age", "loc", "gender", "sportOther", "volOther"):
        if isinstance(raw.get(key), (str, int)):
            prefs[key] = str(raw[key])[:200]
    if raw.get("playsSports") in ("yes", "no"):
        prefs["playsSports"] = raw["playsSports"]
    for key, allowed in (("sports", SPORTS), ("vol", VOLUNTEER)):
        if isinstance(raw.get(key), list):
            prefs[key] = [x for x in allowed if x in raw[key]]
    return prefs


def save_preferences(email, prefs):
    """BACKEND: POST /api/preferences  prefs object"""
    _prefs_by_email[email.lower()] = clean_prefs(prefs)
    return ok()


def load_preferences(email):
    """BACKEND: GET /api/preferences  -> saved prefs, or None"""
    saved = _prefs_by_email.get(email.lower())
    return clean_prefs(saved) if saved else None


# ---------- Websites, For you, Popular and study resources ----------

SAMPLE_SITES = {
    "Soccer": [{"title": "US Youth Soccer", "url": "https://www.usyouthsoccer.org", "text": "Leagues, programs and player development for youth soccer across the US."}],
    "Basketball": [{"title": "USA Basketball", "url": "https://www.usab.com", "text": "Youth programs, coaching resources and national team news."}],
    "Track & Field": [{"title": "USA Track & Field", "url": "https://www.usatf.org", "text": "Youth track and cross country clubs, meets and events."}],
    "Swimming": [{"title": "USA Swimming", "url": "https://www.usaswimming.org", "text": "Find a local swim club and learn about competitive swimming."}],
    "Tennis": [{"title": "USTA", "url": "https://www.usta.com", "text": "Junior tennis programs, places to play and tournaments."}],
    "Cricket": [{"title": "USA Cricket", "url": "https://www.usacricket.org", "text": "The governing body of cricket in the US, with clubs, leagues and youth programs."}],
    "Volleyball": [{"title": "USA Volleyball", "url": "https://www.usavolleyball.org", "text": "Junior clubs, beach volleyball and events."}],
    "Tutoring younger kids": [{"title": "Schoolhouse.world", "url": "https://schoolhouse.world", "text": "Free peer tutoring where students help each other over video."}],
    "Environment & parks": [{"title": "National Park Service: Volunteer", "url": "https://www.nps.gov/getinvolved/volunteer.htm", "text": "Volunteer opportunities in national parks, including youth programs."}],
    "Animal shelters": [{"title": "ASPCA", "url": "https://www.aspca.org", "text": "Animal welfare information and ways to help shelter animals."}],
    "Food banks": [{"title": "Feeding America", "url": "https://www.feedingamerica.org", "text": "Find your local food bank and sign up for volunteer shifts."}],
    "Coding for nonprofits": [{"title": "Code for America", "url": "https://codeforamerica.org", "text": "Use technology to improve public services, with volunteer projects."}],
    "_volunteer_general": [
        {"title": "VolunteerMatch", "url": "https://www.volunteermatch.org", "text": "Search volunteer opportunities near you, including ones for teens."},
        {"title": "DoSomething.org", "url": "https://dosomething.org", "text": "Campaigns and volunteer ideas made for young people."},
    ],
}

STUDY = [
    {"kind": "study", "topic": "Free", "title": "Khan Academy", "url": "https://www.khanacademy.org", "text": "Lessons and practice for math, science, humanities and test prep."},
    {"kind": "study", "topic": "Interactive", "title": "Brilliant", "url": "https://brilliant.org", "text": "Hands-on problem solving in math, logic, data and computer science."},
    {"kind": "study", "topic": "Coding", "title": "Boot.dev", "url": "https://www.boot.dev", "text": "Learn back-end programming by writing real code in the browser."},
    {"kind": "study", "topic": "Mentor", "title": "Lokesh Gaur (Mama)", "url": "", "text": "Ask about tech, careers and study habits from someone who builds software."},
]


def search_websites(topic, kind, loc):
    """BACKEND: GET /api/websites?topic=...&kind=sport|vol&area=..."""
    sites = [{**s, "kind": kind, "topic": topic} for s in SAMPLE_SITES.get(topic, [])]
    where = (loc or "").strip()
    near = f" near {where}" if where else ""
    q = f"{topic} {'youth programs' if kind == 'sport' else 'volunteering for teens'}{near}"
    sites.append({
        "kind": kind,
        "topic": topic,
        "isSearch": True,
        "title": f"Search the web: {topic}{near}",
        "url": "https://duckduckgo.com/?q=" + quote(q, safe="-_.!~*'()"),
        "text": "See the latest results from the web for this interest.",
    })
    return sites


def _topics(picked, other):
    topics = [x for x in picked if x != "Other"]
    if "Other" in picked and other.strip():
        topics.append(other.strip())
    return topics


def get_for_you(prefs):
    """BACKEND: GET /api/for-you  -> {"sportSites": [...], "volSites": [...]}"""
    sport_topics = _topics(prefs["sports"], prefs["sportOther"]) if prefs["playsSports"] == "yes" else []
    vol_topics = _topics(prefs["vol"], prefs["volOther"])
    sport_sites = [site for t in sport_topics for site in search_websites(t, "sport", prefs["loc"])]
    vol_sites = [site for t in vol_topics for site in search_websites(t, "vol", prefs["loc"])]
    if vol_topics:
        general = [{**s, "kind": "vol", "topic": "Volunteering"} for s in SAMPLE_SITES["_volunteer_general"]]
        vol_sites = general + vol_sites
    return {"sportSites": sport_sites, "volSites": vol_sites}


def get_popular(prefs):
    """BACKEND: GET /api/popular?area=..."""
    my_sports = [[f"{s} leagues", "Matches your sports picks"] for s in [s for s in prefs["sports"] if s != "Other"][:2]] if prefs["playsSports"] == "yes" else []
    my_vol = [[v, "Matches your volunteering picks"] for v in [v for v in prefs["vol"] if v != "Other"][:2]]
    return [
        {"title": "Education", "items": [["PSAT / SAT prep", "Practice tests and study plans"], ["Intro to coding", "Python and web basics"], ["AP Biology review", "Unit summaries and practice"], ["Math competition prep", "Problem sets and clubs"]]},
        {"title": "Extracurriculars", "items": (my_sports + [["Robotics club", "Build and compete as a team"], ["Debate and Model UN", "Public speaking and research"], ["Summer STEM camps", "Week-long programs"]])[:4]},
        {"title": "Volunteering", "items": (my_vol + [["Library teen volunteers", "Reading buddies and events"], ["Park cleanup days", "Weekend, outdoors"], ["Food bank shifts", "Sorting and packing"]])[:4]},
    ]


def get_study_resources():
    """BACKEND: GET /api/study"""
    return STUDY


# ---------- Shared resources ----------

def get_shared_resources():
    """BACKEND: GET /api/resources  (newest first)"""
    return list(_shared_resources)


def add_shared_resource(url, posted_by, age):
    """BACKEND: POST /api/resources  { url, postedBy, age }"""
    url = (url or "").strip()
    posted_by = (posted_by or "").strip()[:100]
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or "." not in (parsed.hostname or ""):
        return fail("Enter a full website link, like https://www.example.com.")
    if not posted_by:
        return fail("Enter who is posting this link.")
    try:
        age = int(str(age).strip())
    except ValueError:
        age = 0
    if not 10 <= age <= 120:
        return fail("Enter the age of the person posting, as a number from 10 up.")
    _shared_resources.insert(0, {"url": url, "postedBy": posted_by, "age": age, "postedAt": datetime.now(timezone.utc)})
    return ok()


# ---------- Chat ----------

def ask_sam(message, history, prefs):
    """BACKEND: POST /api/chat  { message, history }  -> {"text", "sources"}

    Sample: scripted replies. The real backend calls the AI model.
    """
    t = message.lower()
    where = prefs["loc"].strip() or "your area"
    if re.search(r"answer|do my|write my|just give|solve it for", t):
        return {"text": "I can’t hand you the answer, but I can get you unstuck.\nWhat is the question asking for, and what have you tried so far? Share your first step and I’ll tell you whether you’re on track.", "sources": []}
    if re.search(r"essay|thesis|paragraph", t):
        return {"text": "Let’s pressure-test your thesis.\n1. Can you say your main claim in one sentence?\n2. Could a reasonable person disagree with it? If not, it may be a fact, not an argument.\n3. Which two pieces of evidence support it best?\nSend me your sentence and I’ll ask you a follow-up.", "sources": ["Purdue OWL", "Khan Academy"]}
    if re.search(r"photosynth|biology|cell|science|chem|physics", t):
        return {"text": "Good topic. Before I explain, what do you already know about what plants need to grow?\nStart there, and we’ll connect it to where the energy actually comes from. A short video plus a simulation usually makes this click.", "sources": ["Khan Academy", "PhET Simulations"]}
    if re.search(r"math|algebra|equation|geometry|calculus|graph", t):
        return {"text": "Let’s break it down. What do you know, and what are you trying to find?\nWrite the first step you’d try. To check yourself visually, graph both sides and see where they meet.", "sources": ["Desmos", "Brilliant"]}
    if re.search(r"code|coding|program|python|javascript", t):
        return {"text": "Nice. Are you starting from zero or do you already know some basics?\nIf zero: pick one language and build something tiny this week. If you know basics: try a project course that makes you write real code.", "sources": ["Boot.dev", "Khan Academy"]}
    if re.search(r"sport|team|tryout|league|soccer|basketball|cricket|tennis|swim", t):
        picked = [s for s in prefs["sports"] if s != "Other"]
        which = ", ".join(picked) if picked else "sports"
        return {"text": f"I looked for {which} near {where}.\nIn the real app I’d list current club teams, rec leagues and tryout dates here with links. Want options that fit after school or on weekends?", "sources": ["Local rec department", "School athletics page"]}
    if re.search(r"volunteer|service|hours|nonprofit", t):
        return {"text": f"I looked for volunteering near {where} that matches what you picked.\nIn the real app I’d show openings with age requirements and how to sign up. How many hours a month can you give?", "sources": ["VolunteerMatch", "DoSomething.org"]}
    return {"text": "Let’s work through it together. What subject is this, and which part feels confusing?\nTell me what you already understand and I’ll ask you a question to take the next step.", "sources": []}
