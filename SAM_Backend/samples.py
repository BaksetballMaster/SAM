"""samples.py: sample data and scripted logic, ported from SAM_Frontend/js/api.js.

Each function here stands in for a real service:
  search_websites -> a web search API that keeps only safe, student-appropriate sites
  get_popular     -> ranking what students in an area open and save
  ask_sam         -> the AI model, called with SAM's rules, the student's prefs and tools
"""

import re
from urllib.parse import quote

SPORTS = ["Soccer", "Basketball", "Track & Field", "Swimming", "Tennis", "Cricket", "Volleyball", "Martial arts", "Other"]
VOLUNTEER = ["Tutoring younger kids", "Environment & parks", "Animal shelters", "Food banks", "Hospitals & senior care", "Coding for nonprofits", "Other"]


def blank_prefs():
    return {"age": "", "loc": "", "gender": "", "playsSports": None, "sports": [], "sportOther": "", "vol": [], "volOther": ""}


# Sample websites, standing in for live web search results.
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
    # REAL APP: call a web search API, keep only safe, student-appropriate sites,
    # read each page's title, description and preview picture, and cache the results.
    known = [{**s, "kind": kind, "topic": topic} for s in SAMPLE_SITES.get(topic, [])]
    where = (loc or "").strip()
    near = f" near {where}" if where else ""
    q = f"{topic} {'youth programs' if kind == 'sport' else 'volunteering for teens'}{near}"
    known.append({
        "kind": kind,
        "topic": topic,
        "isSearch": True,
        "title": f"Search the web: {topic}{near}",
        "url": "https://duckduckgo.com/?q=" + quote(q, safe="-_.!~*'()"),
        "text": "See the latest results from the web for this interest.",
    })
    return known


def _topics(picked, other):
    topics = [x for x in picked if x != "Other"]
    if "Other" in picked and other.strip():
        topics.append(other.strip())
    return topics


def get_for_you(prefs):
    sport_topics = _topics(prefs["sports"], prefs["sportOther"]) if prefs["playsSports"] == "yes" else []
    vol_topics = _topics(prefs["vol"], prefs["volOther"])

    sport_sites = [site for t in sport_topics for site in search_websites(t, "sport", prefs["loc"])]
    vol_sites = [site for t in vol_topics for site in search_websites(t, "vol", prefs["loc"])]
    if vol_topics:
        general = [{**s, "kind": "vol", "topic": "Volunteering"} for s in SAMPLE_SITES["_volunteer_general"]]
        vol_sites = general + vol_sites
    return {"sportSites": sport_sites, "volSites": vol_sites}


def get_popular(prefs):
    # REAL APP: count what students in the student's area open and save.
    my_sports = [[f"{s} leagues", "Matches your sports picks"] for s in [s for s in prefs["sports"] if s != "Other"][:2]] if prefs["playsSports"] == "yes" else []
    my_vol = [[v, "Matches your volunteering picks"] for v in [v for v in prefs["vol"] if v != "Other"][:2]]
    return [
        {"title": "Education", "items": [["PSAT / SAT prep", "Practice tests and study plans"], ["Intro to coding", "Python and web basics"], ["AP Biology review", "Unit summaries and practice"], ["Math competition prep", "Problem sets and clubs"]]},
        {"title": "Extracurriculars", "items": (my_sports + [["Robotics club", "Build and compete as a team"], ["Debate and Model UN", "Public speaking and research"], ["Summer STEM camps", "Week-long programs"]])[:4]},
        {"title": "Volunteering", "items": (my_vol + [["Library teen volunteers", "Reading buddies and events"], ["Park cleanup days", "Weekend, outdoors"], ["Food bank shifts", "Sorting and packing"]])[:4]},
    ]


def ask_sam(message, history, prefs):
    # REAL APP: add SAM's rules + the student's prefs, call the AI model with tools
    # (web search, resource lookup) and stream the reply back. Keep the API key on the server.
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
