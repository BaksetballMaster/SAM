"""api.py: every call the SAM pages make for data.

app.py (the pages) only talks to this file. Each function is still marked with
the backend endpoint it stands for (see SAM_Backend/README.md), so it can move
behind a separate API later without changing the pages.

Where things live:
    database.py           accounts, survey answers, activity and shared links (an Excel workbook)
    sign_in_providers.py  Continue with Google / Apple
    sam_ai.py             the chat with SAM (NVIDIA Nemotron) and web search
"""

import re
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urlparse

from werkzeug.security import check_password_hash, generate_password_hash

import database as db
import sam_ai

SPORTS = ["Soccer", "Basketball", "Track & Field", "Swimming", "Tennis", "Cricket", "Volleyball", "Martial arts", "Other"]
VOLUNTEER = ["Tutoring younger kids", "Environment & parks", "Animal shelters", "Food banks", "Hospitals & senior care", "Coding for nonprofits", "Other"]
GENDERS = [("female", "Female"), ("male", "Male"), ("nonbinary", "Non-binary"), ("na", "Prefer not to say")]
AGES = [str(a) for a in range(10, 19)]
EXAMPLES = ["Help me understand photosynthesis", "How do I start learning Python?", "Check my essay thesis", "Find soccer leagues near me", "Volunteering for students my age"]

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")
CONFIRM_MINUTES = 10
POPULAR_DAYS = 30
# PBKDF2-SHA256 with OWASP's recommended 600,000 rounds. Works on every Python
# (scrypt, Werkzeug's default, is missing from the Python that comes with macOS).
HASH_METHOD = "pbkdf2:sha256:600000"
# Checked when nobody matches, so a wrong username takes as long as a wrong password.
_NO_USER_HASH = generate_password_hash("not-a-real-password", method=HASH_METHOD)


def blank_prefs():
    return {"age": "", "loc": "", "gender": "", "playsSports": None, "sports": [], "sportOther": "", "vol": [], "volOther": ""}


def ok(**data):
    return {"ok": True, **data}


def fail(message, field=None):
    """field names the form field the message is about, so the page can show it there."""
    return {"ok": False, "error": message, "field": field}


# ---------- Accounts ----------

def _public(user):
    """The part of a student's record the pages keep in the session cookie."""
    return {"id": user["user_id"], "name": user["name"] or user["username"], "username": user["username"],
            "email": user["email"], "provider": user["provider"]}


def _users():
    return db.rows("Users")


def get_user(user_id):
    return next((_public(u) for u in _users() if u["user_id"] == user_id), None)


def _free_username(base):
    """A username nobody has yet, made from a name or email."""
    base = re.sub(r"[^a-z0-9_.]", "", base.lower())[:16] or "student"
    base = base if len(base) >= 3 else base + "123"
    taken = {str(u["username"]).lower() for u in _users()}
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}{n}"
    return name


def sign_up(name, username, email, password):
    """BACKEND: POST /api/auth/signup  { name, username, email, password }"""
    name, username, email = name.strip()[:40], username.strip().lower(), email.strip().lower()
    if not name:
        return fail("Enter your first name.", "name")
    if not USERNAME_RE.match(username):
        return fail("Use 3 to 20 letters, numbers, dots or underscores.", "username")
    if not EMAIL_RE.match(email):
        return fail("Enter a valid email address, like you@example.com.", "email")
    if len(password) < 8:
        return fail("Use at least 8 characters.", "password")
    password_hash = generate_password_hash(password, method=HASH_METHOD)  # Slow on purpose, so done before locking
    with db.lock:  # Check and save together, so two students can't grab the same username at once
        users = _users()
        if any(str(u["username"]).lower() == username for u in users):
            return fail("That username is taken. Try adding a number.", "username")
        if any(u["provider"] == "Password" and str(u["email"]).lower() == email for u in users):
            return fail("An account already uses this email. Sign in instead.", "email")
        user_id = db.add_user({
            "username": username, "name": name, "email": email, "provider": "Password",
            "password_hash": password_hash, "last_sign_in": db.now(),
        })
    return ok(user=get_user(user_id))


def sign_in(identifier, password):
    """BACKEND: POST /api/auth/signin  { identifier (email or username), password }"""
    who = identifier.strip().lower()
    if not who or not password:
        return fail("Enter your email or username and your password.", "identifier" if not who else "password")
    users = _users()
    user = next((u for u in users if u["provider"] == "Password" and who in (str(u["email"]).lower(), str(u["username"]).lower())), None)
    if not user:
        check_password_hash(_NO_USER_HASH, password)
        other = next((u for u in users if u["provider"] in ("Google", "Apple") and who == str(u["email"]).lower()), None)
        if other:
            return fail(f"This email signs in with {other['provider']}. Use Continue with {other['provider']} above.")
        return fail("That email or username and password don’t match. Try again.")
    if not check_password_hash(str(user["password_hash"]), password):
        return fail("That email or username and password don’t match. Try again.")
    db.update_row("Users", "user_id", user["user_id"], {"last_sign_in": db.now()})
    return ok(user=get_user(user["user_id"]))


def sign_in_with_provider(provider, subject, email, name, demo=False):
    """BACKEND: the end of Continue with Google / Apple.

    Each Google or Apple account is matched by the ID Google or Apple gives it,
    never by email, so nobody can take over an account by signing up with
    someone else's address first.
    """
    label = {"google": "Google", "apple": "Apple"}[provider] + (" (demo)" if demo else "")
    with db.lock:  # Look up and create together, so a double-click can't make two accounts
        existing = next((u for u in _users() if u["provider"] == label and str(u["provider_id"]) == subject), None)
        if existing:
            db.update_row("Users", "user_id", existing["user_id"], {"last_sign_in": db.now()})
            return ok(user=get_user(existing["user_id"]), new=False)
        email = email.strip().lower()
        name = name.strip()[:40] or (email.split("@")[0] if email else "Student")
        user_id = db.add_user({
            "username": _free_username(email.split("@")[0] if email else name), "name": name, "email": email,
            "provider": label, "provider_id": subject, "last_sign_in": db.now(),
        })
    return ok(user=get_user(user_id), new=True)


# ---------- The confirmation email (demo inbox) ----------
# The confirmation codes are kept in memory: they only last 10 minutes anyway.

_pending_codes = {}  # code -> {"email", "expires"}


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


# ---------- The survey (preferences) ----------

def _text(value, limit=80):
    return " ".join(str(value or "").split())[:limit]


def check_prefs(form):
    """Turn the survey form into a prefs dict. Returns (prefs, errors), errors keyed by field."""
    prefs = blank_prefs()
    errors = {}
    prefs["age"] = _text(form.get("age"), 3) if _text(form.get("age"), 3) in AGES else ""
    if not prefs["age"]:
        errors["age"] = "Choose your age."
    prefs["loc"] = _text(form.get("loc"))
    if len(prefs["loc"]) < 2:
        errors["loc"] = "Enter your town or ZIP code so SAM can find things near you."
    gender = form.get("gender", "")
    prefs["gender"] = gender if gender in dict(GENDERS) else ""
    plays = form.get("playsSports")
    prefs["playsSports"] = plays if plays in ("yes", "no") else None
    if not prefs["playsSports"]:
        errors["playsSports"] = "Choose Yes or Not right now."
    if prefs["playsSports"] == "yes":
        prefs["sports"] = [s for s in SPORTS if s in form.get("sports", [])]
        prefs["sportOther"] = _text(form.get("sportOther"), 60) if "Other" in prefs["sports"] else ""
        if not prefs["sports"]:
            errors["sports"] = "Pick at least one sport, or choose Not right now."
        elif "Other" in prefs["sports"] and not prefs["sportOther"]:
            errors["sportOther"] = "Type the other sport."
    prefs["vol"] = [v for v in VOLUNTEER if v in form.get("vol", [])]
    prefs["volOther"] = _text(form.get("volOther"), 60) if "Other" in prefs["vol"] else ""
    if "Other" in prefs["vol"] and not prefs["volOther"]:
        errors["volOther"] = "Type how else you'd like to volunteer."
    return prefs, errors


def save_preferences(user_id, prefs):
    """BACKEND: POST /api/preferences  prefs object"""
    found = db.update_row("Users", "user_id", user_id, {
        "age": int(prefs["age"]), "loc": prefs["loc"], "gender": dict(GENDERS).get(prefs["gender"], ""),
        "plays_sports": {"yes": "Yes", "no": "No"}.get(prefs["playsSports"], ""),
        "sports": ", ".join(prefs["sports"]), "sport_other": prefs["sportOther"],
        "vol": ", ".join(prefs["vol"]), "vol_other": prefs["volOther"], "survey_saved": db.now(),
    })
    return ok() if found else fail("SAM couldn’t find your account. Sign in again.")


def load_preferences(user_id):
    """BACKEND: GET /api/preferences  -> saved prefs, or None if the survey isn't done yet"""
    u = next((u for u in _users() if u["user_id"] == user_id), None)
    if not u or not u["survey_saved"]:
        return None
    split = lambda s: [x.strip() for x in str(s).split(",") if x.strip()]
    gender_code = {label: code for code, label in GENDERS}.get(str(u["gender"]), "")
    return {
        "age": str(u["age"]), "loc": str(u["loc"]), "gender": gender_code,
        "playsSports": {"Yes": "yes", "No": "no"}.get(str(u["plays_sports"])),
        "sports": [s for s in SPORTS if s in split(u["sports"])], "sportOther": str(u["sport_other"]),
        "vol": [v for v in VOLUNTEER if v in split(u["vol"])], "volOther": str(u["vol_other"]),
    }


# ---------- Websites, For you and study resources ----------

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


def _near(prefs):
    return f" near {prefs['loc'].strip()}" if prefs["loc"].strip() else ""


def _query(topic, kind, prefs):
    """What SAM searches the web for. Sports use the gender answer for girls / boys / co-ed clinics."""
    if kind == "sport":
        who = {"female": "girls ", "male": "boys "}.get(prefs["gender"], "")
        return f"{who}{topic} youth clinics and leagues{_near(prefs)}"
    return f"{topic} volunteer opportunities for teens{_near(prefs)}"


def _search_link(topic, kind, prefs):
    return {"kind": kind, "topic": topic, "isSearch": True, "title": f"Search the web: {topic}{_near(prefs)}",
            "url": "https://duckduckgo.com/?q=" + quote(_query(topic, kind, prefs), safe="-_.!~*'()"),
            "text": "See the latest results from the web for this interest."}


def search_websites(topics, kind, prefs):
    """BACKEND: GET /api/websites?topic=...&kind=sport|vol&area=...

    SAM's saved picks for each topic, plus live web results near the student
    when web search is set up (otherwise a link to search the web).
    """
    queries = [_query(t, kind, prefs) for t in topics]
    live = sam_ai.web_search_many(queries, 3) if sam_ai.search_configured() else [[] for _ in topics]
    sites, seen = [], set()
    for topic, found in zip(topics, live):
        picks = SAMPLE_SITES.get(topic, []) + [{**r, "live": True} for r in found]
        for s in picks:
            if s["url"] not in seen:
                seen.add(s["url"])
                sites.append({**s, "kind": kind, "topic": topic})
        if not found:
            sites.append(_search_link(topic, kind, prefs))
    return sites


def _topics(picked, other):
    topics = [x for x in picked if x != "Other"]
    if "Other" in picked and other.strip():
        topics.append(other.strip())
    return topics[:5]


def get_for_you(prefs):
    """BACKEND: GET /api/for-you  -> {"sportSites": [...], "volSites": [...]}"""
    sport_topics = _topics(prefs["sports"], prefs["sportOther"]) if prefs["playsSports"] == "yes" else []
    vol_topics = _topics(prefs["vol"], prefs["volOther"])
    sport_sites = search_websites(sport_topics, "sport", prefs)
    vol_sites = search_websites(vol_topics, "vol", prefs)
    if vol_topics:
        general = [{**s, "kind": "vol", "topic": "Volunteering"} for s in SAMPLE_SITES["_volunteer_general"]]
        vol_sites = general + [s for s in vol_sites if s["url"] not in {g["url"] for g in general}]
    return {"sportSites": sport_sites, "volSites": vol_sites}


def get_study_resources():
    """BACKEND: GET /api/study"""
    return STUDY


# ---------- Activity and Popular near you ----------

SUBJECTS = [
    ("Math", r"\b(math\w*|algebra|equations?|geometry|calculus|fractions?|trig\w*|statistics?)\b"),
    ("Science", r"photosynth|biology|cell|science|chem|physics|atom|ecosystem"),
    ("Coding", r"code|coding|program|python|javascript|java\b|html|css|app\b"),
    ("Writing and essays", r"\b(essays?|thesis|paragraphs?|writing|grammar|poems?)\b"),
    ("Test prep", r"\bsat\b|\bpsat\b|\bact\b|\bap\b|exam|test prep|finals"),
    ("History and civics", r"history|civics|government|election|war\b"),
    ("Languages", r"spanish|french|hindi|mandarin|chinese|german|language"),
]


def area_of(loc):
    """Students "near" each other: the same first 3 ZIP digits, or the same town name."""
    loc = " ".join(str(loc or "").lower().replace(",", " ").split())
    zip_code = re.match(r"^(\d{5})(-\d{4})?$", loc)
    return zip_code.group(1)[:3] + "xx" if zip_code else loc


def log_open(user_id, prefs, site):
    """BACKEND: POST /api/activity  A student opened a website from SAM."""
    category = site.get("kind") if site.get("kind") in ("sport", "vol", "study", "shared") else "study"
    db.add_row("Activity", {"time": db.now(), "user_id": user_id, "area": area_of(prefs["loc"]), "category": category,
                            "topic": site.get("topic", ""), "title": site.get("title", ""), "url": site.get("url", "")})


def log_chat_subject(user_id, prefs, message):
    """Only the subject is saved (for example "Math"), never what the student wrote."""
    subject = next((name for name, pattern in SUBJECTS if re.search(pattern, message, re.I)), None)
    if subject:
        db.add_row("Activity", {"time": db.now(), "user_id": user_id, "area": area_of(prefs["loc"]), "category": "chat",
                                "topic": subject, "title": f"{subject} help", "url": ""})


def get_popular(prefs):
    """BACKEND: GET /api/popular?area=...

    Ranks what students in the same area opened (and asked SAM about) in the last
    30 days, by how many different students did. Items matching the student's own
    picks come first. Short lists are topped up with suggestions, marked as such.
    """
    area = area_of(prefs["loc"])
    since = datetime.now() - timedelta(days=POPULAR_DAYS)
    counts = {}
    for a in db.rows("Activity"):
        if a["area"] != area or not isinstance(a["time"], datetime) or a["time"] < since:
            continue
        column = {"study": "Education", "chat": "Education", "shared": "Education",
                  "sport": "Extracurriculars", "vol": "Volunteering"}.get(a["category"])
        if column:
            item = counts.setdefault((column, a["title"]), {"title": a["title"], "topic": a["topic"], "url": a["url"],
                                                             "chat": a["category"] == "chat", "students": set()})
            item["students"].add(a["user_id"])

    mine = set(prefs["sports"] + prefs["vol"] + [prefs["sportOther"], prefs["volOther"]]) - {"", "Other"}
    my_sports = [s for s in prefs["sports"] if s != "Other"] if prefs["playsSports"] == "yes" else []
    my_vol = [v for v in prefs["vol"] if v != "Other"]
    suggestions = {
        "Education": [["PSAT / SAT prep", "Practice tests and study plans"], ["Intro to coding", "Python and web basics"], ["AP Biology review", "Unit summaries and practice"], ["Math competition prep", "Problem sets and clubs"]],
        "Extracurriculars": [[f"{s} leagues", "Matches your sports picks"] for s in my_sports[:2]] + [["Robotics club", "Build and compete as a team"], ["Debate and Model UN", "Public speaking and research"], ["Summer STEM camps", "Week-long programs"]],
        "Volunteering": [[v, "Matches your volunteering picks"] for v in my_vol[:2]] + [["Library teen volunteers", "Reading buddies and events"], ["Park cleanup days", "Weekend, outdoors"], ["Food bank shifts", "Sorting and packing"]],
    }

    cols = []
    for column in ("Education", "Extracurriculars", "Volunteering"):
        ranked = sorted((v for (c, _), v in counts.items() if c == column),
                        key=lambda v: (v["topic"] not in mine, -len(v["students"]), v["title"]))
        items = []
        for v in ranked[:5]:
            n = len(v["students"])
            verb = "asked SAM about this" if v["chat"] else "opened this"
            items.append({"title": v["title"], "sub": f"{n} student{'s' if n != 1 else ''} near you {verb}",
                          "url": v["url"], "match": v["topic"] in mine, "real": True})
        for title, sub in suggestions[column]:
            if len(items) >= 4:
                break
            if title not in {i["title"] for i in items}:
                items.append({"title": title, "sub": sub, "url": "", "match": False, "real": False})
        cols.append({"title": column, "items": items})
    return cols


# ---------- Shared resources ----------

def get_shared_resources():
    """BACKEND: GET /api/resources  (newest first)"""
    shared = [{"url": r["url"], "postedBy": r["posted_by"], "age": r["age"], "postedAt": r["posted"]}
              for r in db.rows("Resources") if isinstance(r["posted"], datetime)]
    return sorted(shared, key=lambda r: r["postedAt"], reverse=True)


def add_shared_resource(url, posted_by, age, user_id=""):
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
    db.add_row("Resources", {"posted": db.now(), "url": url, "posted_by": posted_by, "age": age, "user_id": user_id})
    return ok()


# ---------- Chat ----------

SOURCE_LINKS = {
    "Purdue OWL": "https://owl.purdue.edu", "Khan Academy": "https://www.khanacademy.org", "PhET Simulations": "https://phet.colorado.edu",
    "Desmos": "https://www.desmos.com", "Brilliant": "https://brilliant.org", "Boot.dev": "https://www.boot.dev",
    "VolunteerMatch": "https://www.volunteermatch.org", "DoSomething.org": "https://dosomething.org",
}


def chat_is_live():
    return sam_ai.chat_configured()


def ask_sam(message, history, prefs):
    """BACKEND: POST /api/chat  { message, history }  -> {"text", "sources": [{"n", "title", "url"}]}

    Uses NVIDIA Nemotron with web search when NVIDIA_API_KEY is set,
    otherwise SAM's scripted demo replies.
    """
    if sam_ai.chat_configured():
        return sam_ai.ask(message, history, prefs)
    reply = _scripted_reply(message, prefs)
    reply["sources"] = [{"n": None, "title": s, "url": SOURCE_LINKS.get(s, "")} for s in reply["sources"]]
    return reply


def _scripted_reply(message, prefs):
    t = message.lower()
    where = prefs["loc"].strip() or "your area"
    if re.search(r"answer|do my|write my|just give|solve it for", t):
        return {"text": "I can’t hand you the answer, but I can get you unstuck.\nWhat is the question asking for, and what have you tried so far? Share your first step and I’ll tell you whether you’re on track.", "sources": []}
    if re.search(r"\b(essays?|thesis|paragraphs?)\b", t):
        return {"text": "Let’s pressure-test your thesis.\n1. Can you say your main claim in one sentence?\n2. Could a reasonable person disagree with it? If not, it may be a fact, not an argument.\n3. Which two pieces of evidence support it best?\nSend me your sentence and I’ll ask you a follow-up.", "sources": ["Purdue OWL", "Khan Academy"]}
    if re.search(r"photosynth|biology|cell|science|chem|physics", t):
        return {"text": "Good topic. Before I explain, what do you already know about what plants need to grow?\nStart there, and we’ll connect it to where the energy actually comes from. A short video plus a simulation usually makes this click.", "sources": ["Khan Academy", "PhET Simulations"]}
    if re.search(r"\b(math|algebra|equations?|geometry|calculus|graphs?)\b", t):
        return {"text": "Let’s break it down. What do you know, and what are you trying to find?\nWrite the first step you’d try. To check yourself visually, graph both sides and see where they meet.", "sources": ["Desmos", "Brilliant"]}
    if re.search(r"code|coding|program|python|javascript", t):
        return {"text": "Nice. Are you starting from zero or do you already know some basics?\nIf zero: pick one language and build something tiny this week. If you know basics: try a project course that makes you write real code.", "sources": ["Boot.dev", "Khan Academy"]}
    if re.search(r"sport|team|tryout|league|soccer|basketball|cricket|tennis|swim", t):
        picked = [s for s in prefs["sports"] if s != "Other"]
        which = ", ".join(picked) if picked else "sports"
        return {"text": f"I looked for {which} near {where}.\nWith web search turned on, I’d list current club teams, rec leagues and tryout dates here with links. Want options that fit after school or on weekends?", "sources": []}
    if re.search(r"volunteer|service|hours|nonprofit", t):
        return {"text": f"I looked for volunteering near {where} that matches what you picked.\nWith web search turned on, I’d show openings with age requirements and how to sign up. How many hours a month can you give?", "sources": ["VolunteerMatch", "DoSomething.org"]}
    return {"text": "Let’s work through it together. What subject is this, and which part feels confusing?\nTell me what you already understand and I’ll ask you a question to take the next step.", "sources": []}
