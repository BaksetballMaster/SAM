"""retrieval.py: the sources SAM reads before it replies.

This is the "retrieval" half of retrieval-augmented generation (RAG). Before
the model writes anything, SAM gathers a few short passages about the student's
topic. The model is told to build its reply on them and cite them as [1], [2],
and the student sees the same sources next to the reply.

Three places are searched, and the best five passages are kept:
    1. The web, through sam_ai.web_search (only if a search key is set)
    2. Wikipedia article introductions (free, no key)
    3. LIBRARY below: study sites SAM trusts, matched by subject (works offline)

For a flagged message ("solve 2x + 6 = 14") SAM never searches for the problem
itself, which would only find the answer. It searches for the idea behind it.
"""

import re

import sam_ai
from services import wikipedia

MAX_SOURCES = 5

# Study sites SAM recommends. "subjects" uses the names in guardrails.SUBJECTS, plus "Life".
LIBRARY = [
    {"title": "Khan Academy: Math", "url": "https://www.khanacademy.org/math", "subjects": ["Math"],
     "text": "Free lessons and practice from arithmetic to calculus, with a hint for every step."},
    {"title": "Desmos graphing calculator", "url": "https://www.desmos.com/calculator", "subjects": ["Math"],
     "text": "Graph an equation to see what it looks like and to check your own work."},
    {"title": "Brilliant", "url": "https://brilliant.org", "subjects": ["Math", "Science", "Coding"],
     "text": "Hands-on problem solving in math, logic, data and computer science."},
    {"title": "Khan Academy: Science", "url": "https://www.khanacademy.org/science", "subjects": ["Science"],
     "text": "Biology, chemistry and physics lessons with practice questions."},
    {"title": "PhET simulations", "url": "https://phet.colorado.edu", "subjects": ["Science", "Math"],
     "text": "Free interactive science and math simulations from the University of Colorado Boulder."},
    {"title": "Purdue OWL", "url": "https://owl.purdue.edu", "subjects": ["Writing and essays"],
     "text": "Guides to planning, writing, citing and revising essays and research papers."},
    {"title": "Khan Academy: Humanities", "url": "https://www.khanacademy.org/humanities", "subjects": ["Writing and essays", "History and civics"],
     "text": "Grammar, history, civics and art history lessons."},
    {"title": "Boot.dev", "url": "https://www.boot.dev", "subjects": ["Coding"],
     "text": "Learn back-end programming by writing real code in the browser."},
    {"title": "freeCodeCamp", "url": "https://www.freecodecamp.org/learn", "subjects": ["Coding"],
     "text": "Free step-by-step coding lessons, from web pages to Python."},
    {"title": "Khan Academy: Computing", "url": "https://www.khanacademy.org/computing", "subjects": ["Coding"],
     "text": "Computer programming and computer science lessons for beginners."},
    {"title": "Khan Academy: Test prep", "url": "https://www.khanacademy.org/test-prep", "subjects": ["Test prep"],
     "text": "Free official practice for the SAT and other tests."},
    {"title": "Crash Course", "url": "https://thecrashcourse.com", "subjects": ["History and civics", "Science"],
     "text": "Short video courses on history, science, literature and more."},
    {"title": "DocsTeach", "url": "https://www.docsteach.org", "subjects": ["History and civics"],
     "text": "Primary sources and activities from the US National Archives."},
    {"title": "Duolingo", "url": "https://www.duolingo.com", "subjects": ["Languages"],
     "text": "Practise a language a few minutes at a time."},
    {"title": "OpenStax", "url": "https://openstax.org/subjects", "subjects": ["Math", "Science", "History and civics"],
     "text": "Free textbooks for high school and college subjects, reviewed by teachers."},
    {"title": "BigFuture", "url": "https://bigfuture.collegeboard.org", "subjects": ["Life"],
     "text": "Plan for college and careers: explore majors, scholarships and next steps."},
    {"title": "Khan Academy: College, careers and more", "url": "https://www.khanacademy.org/college-careers-more", "subjects": ["Life"],
     "text": "Lessons on personal finance, careers, college admissions and study skills."},
    {"title": "Next Gen Personal Finance", "url": "https://www.ngpf.org", "subjects": ["Life"],
     "text": "Free lessons and games about budgeting, saving, banking and credit."},
]

_LOCAL_WORDS = re.compile(r"\b(near|nearby|local|around|area|town|city|teams?|leagues?|clubs?|clinics?|camps?|tryouts?"
                          r"|volunteer\w*|program\w*|class(es)?|tutor\w*|events?|library|libraries)\b", re.I)
_OPENERS = re.compile(r"^(please\s+)?(can|could|will|would)\s+you\s+|^(please\s+)?(help me (to )?(understand|with|learn)|explain( to me)?"
                      r"|tell me about|what (is|are|was|were|does|do)|how (does|do|did|is|are)|why (is|are|was|were|does|do|did)"
                      r"|i (don'?t|do not) (understand|get)|i need help (with|understanding)|teach me( about)?|define)\s+", re.I)
_FILLER = set("""a about all an and answer answers any are as assignment at be by can check could did do does essay explain find for from
get give help homework how i in is it just know learn make me my need number of on one or page paragraph please problem question report
should show solve some start tell that the these this to understand want was what when where which who why will with word words would
write you your""".split())


def retrieve(message, verdict, prefs):
    """Up to five sources for this message: [{"title", "url", "text", "source"}]."""
    found = []
    if sam_ai.search_configured():
        for result in sam_ai.web_search(web_query(message, verdict, prefs), 3):
            found.append({**result, "source": "Web"})
    if verdict.kind not in ("near_me", "life"):
        found += wikipedia.introductions(topic_of(message, verdict), 2)
    found += from_library(message, "Life" if verdict.kind == "life" else verdict.subject)

    sources, seen = [], set()
    for source in found:
        if source["url"] not in seen:
            seen.add(source["url"])
            sources.append(source)
    return sources[:MAX_SOURCES]


def topic_of(message, verdict):
    """What to look up. For a flagged message, the idea behind the task, never the task itself."""
    if verdict.coach:
        if verdict.hint == "equation":
            return "Linear equation"
        if verdict.hint == "percent":
            return "Percentage"
        if verdict.hint == "arithmetic":
            return ""
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z']{2,}", message) if w.lower() not in _FILLER]
        return " ".join(words[:6])
    topic = _OPENERS.sub("", " ".join(message.split())).strip(" ?.!")
    return " ".join(topic.split()[:10])


def web_query(message, verdict, prefs):
    """What SAM searches the web for: the topic, plus the student's area for local questions."""
    query = topic_of(message, verdict) if verdict.coach else message
    where = str(prefs.get("loc") or "").strip()
    return f"{query} near {where}" if where and _LOCAL_WORDS.search(message) else query


def from_library(message, subject, count=2):
    """The study sites that best fit a message: same subject first, then shared words."""
    words = {w for w in re.findall(r"[a-z]{4,}", message.lower()) if w not in _FILLER}
    scored = []
    for entry in LIBRARY:
        score = 3 * (subject in entry["subjects"]) + len(words & set(re.findall(r"[a-z]{4,}", (entry["title"] + " " + entry["text"]).lower())))
        if score >= 2:
            scored.append((score, entry))
    scored.sort(key=lambda pair: -pair[0])
    return [{"title": e["title"], "url": e["url"], "text": e["text"], "source": "SAM's library"} for _, e in scored[:count]]
