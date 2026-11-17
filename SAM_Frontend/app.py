"""app.py: SAM's website, written in Python with Flask.

Each page is a route here plus a template in templates/. Forms send the
student's choices to these routes, which draw the next page. Data comes from
api.py.

The order a new student goes through:
    1. Sign in or create an account (email or username and password, Google, or Apple)
    2. The survey (age, where they live, gender, sports, volunteering), saved to the database
    3. Home, the dashboard, which leads to SAM's four assistants:
         Volunteer finder   /volunteer   real places to volunteer near the student
         Sports tracker     /sports      places to play and train, on a map
         Concept helper     /chat        a study coach that never hands over answers
         Code translator    /code        what each line of code does, and pseudocode
       Places a student saves go to My plan (/plan), their schedule.

How data flows: a page's form (or the page's JavaScript, which calls the same
routes and asks for JSON) sends the student's choices here. The route calls a
function in api.py, which uses the assistants/ and services/ folders and the
database, and the route draws the result with a template from templates/.
Every page also works without JavaScript; the scripts in static/js only add
the map, the code editor, and replies that appear without reloading the page.

Run:  python app.py   then open http://localhost:5050
"""

import hashlib
import json
import os
import secrets
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer  # Installed with Flask
from markupsafe import Markup  # Installed with Flask

HERE = Path(__file__).resolve().parent


def load_env_file(path):
    """Read KEY=value lines from .env, so API keys don't have to be typed in each time."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env_file(HERE / ".env")

import api  # noqa: E402  (imported after .env is read, so it sees the settings)
import database  # noqa: E402
import sign_in_providers as providers  # noqa: E402
from assistants import finder  # noqa: E402
from services import richtext  # noqa: E402


def secret_key():
    """Signs the session cookie. Kept in data/ so restarting SAM doesn't sign everyone out."""
    if os.environ.get("SAM_SECRET_KEY"):
        return os.environ["SAM_SECRET_KEY"]
    key_file = database.DATA_DIR / ".secret_key"
    if not key_file.exists():
        database.DATA_DIR.mkdir(parents=True, exist_ok=True)
        key_file.write_text(secrets.token_hex(32))
        key_file.chmod(0o600)
    return key_file.read_text().strip()


PUBLIC_URL = os.environ.get("SAM_PUBLIC_URL", "").strip().rstrip("/")

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PUBLIC_URL.startswith("https://"),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
app.secret_key = secret_key()
signer = URLSafeTimedSerializer(app.secret_key, salt="sam-links")

# The sidebar: (group heading, [(page, label, icon)]). Icons are in templates/base.html.
NAV = [
    ("", [("home", "Home", "home")]),
    ("Assistants", [
        ("volunteer_page", "Volunteer finder", "heart"),
        ("sports_page", "Sports tracker", "trophy"),
        ("chat", "Concept helper", "book"),
        ("code", "Code translator", "code"),
    ]),
    ("You", [
        ("plan", "My plan", "calendar"),
        ("foryou", "For you", "sparkles"),
        ("popular", "Popular near you", "pin"),
        ("resources", "Resources", "link"),
        ("survey", "Preferences", "sliders"),
    ]),
]

# Chat messages for each student, kept in memory while SAM runs.
chats = {}
MAX_CHAT_MESSAGES = 100


# ---------- Helpers used by the templates ----------

@app.template_filter("domain")
def domain_of(url):
    host = urlparse(url).hostname or url
    return host[4:] if host.startswith("www.") else host


@app.template_filter("shot")
def shot_of(url):
    # Website picture from WordPress's free mShots service.
    # BACKEND: the real app should fetch these pictures on the server and cache them.
    return f"https://s0.wp.com/mshots/v1/{quote(url, safe='')}?w=600&h=400"


@app.template_filter("date")
def nice_date(when):
    return f"{when:%b} {when.day}, {when.year}"


@app.template_filter("go")
def go_link(site):
    """Open a website through SAM, so Popular near you can count what students open."""
    return url_for("go", t=signer.dumps({k: site.get(k) or "" for k in ("url", "title", "kind", "topic")}))


@app.template_filter("markdown")
def markdown(text, sources=None, message_id="m"):
    """The AI's Markdown as safe HTML. [2] becomes a button that opens source 2 (see templates/_message.html)."""
    numbers = {s["n"] for s in sources or []}
    return richtext.render(text, lambda n: (f'<button type="button" class="cite" popovertarget="{message_id}-src{n}" '
                                            f'aria-label="Source {n}">{n}</button>') if n in numbers else None)


@app.template_filter("with_id")
def with_id(site):
    """A web page as something that can be saved: its id comes from its address, so it's the same every time."""
    return {**site, "id": site.get("id") or "web:" + hashlib.sha1(str(site.get("url", "")).encode()).hexdigest()[:12]}


@app.template_global()
def map_json(here, radius, places, saved=()):
    """The data static/js/map.js draws: home, the travel radius and the places, as JSON that's safe inside a page."""
    data = {
        "home": here or None,
        "radius": radius,
        "places": [{
            "id": p.get("id") or p.get("item_id"), "name": p.get("name") or p.get("title"), "lat": p.get("lat"), "lon": p.get("lon"),
            "miles": p.get("miles"), "topic": p.get("topic") or p.get("detail", ""), "saved": (p.get("id") or p.get("item_id")) in saved,
        } for p in places or [] if p.get("lat") is not None and p.get("lon") is not None],
    }
    text = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(text)


@app.template_filter("inline_md")
def inline_md(text):
    """One line of Markdown (like `code` in a sentence) as safe HTML."""
    return Markup(richtext.inline(text))


@app.template_filter("item")
def item_token(place):
    """A signed copy of a place, so the Save button can't be used to save made-up places."""
    return signer.dumps({
        "kind": place.get("kind", ""), "item_id": place.get("id") or place.get("item_id") or with_id(place)["id"],
        "title": place.get("name") or place.get("title", ""), "detail": place.get("topic", ""),
        "address": place.get("address", ""), "url": place.get("website") or place.get("url", ""),
        "lat": place.get("lat"), "lon": place.get("lon"),
    }, salt="sam-saved")


@app.template_filter("pretty_day")
def pretty_day(day):
    if not day:
        return "No day set"
    if day == date.today():
        return "Today"
    if day == date.today() + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%a}, {day:%b} {day.day}"


@app.template_filter("pretty_time")
def pretty_time(hh_mm):
    try:
        hour, minute = (int(x) for x in str(hh_mm).split(":"))
    except ValueError:
        return ""
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


@app.context_processor
def page_globals():
    user = session.get("user")
    return {"user": user, "nav": NAV, "survey_done": bool(user and api.load_preferences(user.get("id"))),
            "today": date.today().isoformat()}


def wants_json():
    """True when the page's JavaScript is asking (it sends this header), so the route answers with JSON."""
    return request.headers.get("X-Requested-With") == "fetch"


def back_to(default_endpoint):
    """Where to go after a form: the page the form was on, if it's a page inside SAM."""
    back = request.form.get("next", "")
    if back.startswith("/") and not back.startswith(("//", "/\\")):
        return back
    return url_for(default_endpoint)


def external_url(endpoint):
    """The full address of a SAM page, as Google and Apple must see it."""
    return PUBLIC_URL + url_for(endpoint) if PUBLIC_URL else url_for(endpoint, _external=True)


# ---------- Signed-in state ----------

def current_prefs():
    return api.load_preferences(session["user"]["id"]) or api.blank_prefs()


def chat_messages():
    return chats.setdefault(session["user"]["id"], [])


def signed_in_page(view):
    """Pages for signed-in students: everyone else goes to sign in."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = session.get("user") or {}
        if not user.get("id") or not api.get_user(user["id"]):  # Not signed in, or the account was removed
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def survey_first(view):
    """Pages built from the survey: students who haven't done it go there first."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if api.load_preferences(session["user"]["id"]) is None:
            return redirect(url_for("survey"))
        return view(*args, **kwargs)
    return wrapper


def public_page(view):
    """Sign-in pages: signed-in students go straight Home."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if (session.get("user") or {}).get("id"):
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapper


def render_signed_in(template, active, **context):
    """Draw a signed-in page, with the add-resource dialog ready to open."""
    prefs = context.setdefault("prefs", current_prefs())
    add = session.pop("add_form", None) or {"url": "", "by": session["user"]["name"], "age": prefs["age"], "error": ""}
    return render_template(template, active=active, add=add, **context)


# ---------- Entry point ----------

@app.get("/")
def index():
    return redirect(url_for("home" if (session.get("user") or {}).get("id") else "login"))


# ---------- Signing in ----------

def finish_sign_in(user, remember=True):
    """Signed in. New students do the survey first; everyone else goes Home."""
    session.clear()
    session["user"] = user
    session.permanent = remember  # "Keep me signed in": the cookie lasts 30 days instead of until the browser closes
    return redirect(url_for("home" if api.load_preferences(user["id"]) else "survey"))


def sign_in_problem(message):
    session["sign_in_problem"] = message
    return redirect(url_for("login"))


def start_confirmation(user, remember):
    """Email and password sign-ins: send the confirmation email and wait for Yes."""
    session.clear()
    session["pending_user"] = user
    session["remember"] = remember
    res = api.send_login_confirmation(user["email"])
    # Demo only: the real code arrives by email. Kept so the demo inbox can answer it.
    session["confirm_code"] = res.get("demoCode")
    return redirect(url_for("confirm"))


@app.route("/login", methods=["GET", "POST"])
@public_page
def login():
    mode = "signup" if request.values.get("mode") == "signup" else "signin"
    form = {"name": "", "username": "", "email": "", "identifier": "", "consent": False, "remember": True}
    error, field = session.pop("sign_in_problem", ""), None
    if request.args.get("stopped"):
        error = "Sign-in stopped. If you didn’t try to sign in, change your password."

    if request.method == "POST":
        f = request.form
        form = {key: f.get(key, "").strip() for key in ("name", "username", "email", "identifier")}
        form.update(consent=bool(f.get("consent")), remember=bool(f.get("remember")))
        password = f.get("password", "")
        if mode == "signup":
            if not form["consent"]:
                res = api.fail("Tick this box to continue. If you’re under 13, ask a parent or guardian first.", "consent")
            else:
                res = api.sign_up(form["name"], form["username"], form["email"], password)
        else:
            res = api.sign_in(form["identifier"], password)
        if res["ok"]:
            return start_confirmation(res["user"], form["remember"])
        error, field = res["error"], res.get("field")

    return render_template("login.html", mode=mode, form=form, error=error, field=field)


@app.post("/login/<provider>")
@public_page
def login_provider(provider):
    """Continue with Google / Apple: send the student to Google or Apple to sign in."""
    if provider not in providers.PROVIDERS:
        abort(404)
    if not providers.is_configured(provider):
        return redirect(url_for("demo_sign_in", provider=provider))
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    res = redirect(providers.start_url(provider, external_url(f"{provider}_callback"), state, nonce))
    if provider == "google":
        session["oauth"] = {"state": state, "nonce": nonce}
    else:
        # Apple posts the student back from appleid.apple.com, and browsers don't send SAM's
        # normal cookie (SameSite=Lax) with that. So the check rides in its own short cookie.
        res.set_cookie("sam_apple", signer.dumps({"state": state, "nonce": nonce}), max_age=600,
                       secure=True, httponly=True, samesite="None", path=url_for("apple_callback"))
    return res


@app.get("/login/google/callback")
def google_callback():
    saved = session.pop("oauth", None)
    if request.args.get("error"):  # For example, the student pressed Cancel
        return redirect(url_for("login"))
    if not saved or not secrets.compare_digest(request.args.get("state", ""), saved["state"]):
        return sign_in_problem("That Google sign-in has expired. Try again.")
    try:
        who = providers.finish_google(request.args.get("code", ""), external_url("google_callback"), saved["nonce"])
    except providers.SignInError as e:
        return sign_in_problem(str(e))
    return finish_sign_in(api.sign_in_with_provider("google", who["sub"], who["email"], who["name"])["user"])


@app.post("/login/apple/callback")
def apple_callback():
    try:
        saved = signer.loads(request.cookies.get("sam_apple", ""), max_age=600)
    except BadSignature:
        saved = None
    if request.form.get("error"):  # For example, the student pressed Cancel
        res = redirect(url_for("login"))
    elif not saved or not secrets.compare_digest(request.form.get("state", ""), saved["state"]):
        res = sign_in_problem("That Apple sign-in has expired. Try again.")
    else:
        try:
            who = providers.finish_apple(request.form.get("id_token", ""), request.form.get("user"), saved["nonce"])
            res = finish_sign_in(api.sign_in_with_provider("apple", who["sub"], who["email"], who["name"])["user"])
        except providers.SignInError as e:
            res = sign_in_problem(str(e))
    res.delete_cookie("sam_apple", path=url_for("apple_callback"), secure=True, httponly=True, samesite="None")
    return res


@app.route("/login/<provider>/demo", methods=["GET", "POST"])
@public_page
def demo_sign_in(provider):
    """Stands in for Google or Apple until their keys are set up (see README)."""
    if provider not in providers.PROVIDERS:
        abort(404)
    if providers.is_configured(provider):
        return redirect(url_for("login"))
    form, error, field = {"name": "", "email": ""}, "", None
    if request.method == "POST":
        form = {"name": request.form.get("name", "").strip(), "email": request.form.get("email", "").strip().lower()}
        if not form["name"]:
            error, field = "Enter a first name.", "name"
        elif not api.EMAIL_RE.match(form["email"]):
            error, field = "Enter an email address, like you@example.com.", "email"
        else:
            res = api.sign_in_with_provider(provider, "demo:" + form["email"], form["email"], form["name"], demo=True)
            return finish_sign_in(res["user"])
    return render_template("demo_sign_in.html", provider=provider, label=providers.PROVIDERS[provider]["label"],
                           form=form, error=error, field=field)


@app.route("/confirm", methods=["GET", "POST"])
@public_page
def confirm():
    pending = session.get("pending_user")
    if not pending:
        return redirect(url_for("login"))
    message = ""

    if request.method == "POST":
        action = request.form.get("action")
        if action == "back":
            session.clear()
            return redirect(url_for("login"))
        if action == "resend":
            res = api.send_login_confirmation(pending["email"])
            session["confirm_code"] = res.get("demoCode")
            message = f"Sent again to {pending['email']}." if res["ok"] else res["error"]
        elif action in ("yes", "no"):
            res = api.answer_login_confirmation(session.pop("confirm_code", None), pending["email"], action == "yes")
            if not res["ok"]:
                message = res["error"]
            elif res["confirmed"]:
                return finish_sign_in(pending, session.get("remember", True))
            else:
                session.clear()
                return redirect(url_for("login", stopped=1))

    return render_template("confirm.html", email=pending["email"], message=message)


@app.post("/signout")
def signout():
    api.sign_out()
    chats.pop((session.get("user") or {}).get("id"), None)
    session.clear()
    return redirect(url_for("login"))


# ---------- The survey ----------

@app.route("/survey", methods=["GET", "POST"])
@signed_in_page
def survey():
    user_id = session["user"]["id"]
    first_time = api.load_preferences(user_id) is None
    errors = {}
    if request.method == "POST":
        raw = {**request.form.to_dict(), "sports": request.form.getlist("sports"), "vol": request.form.getlist("vol")}
        prefs, errors = api.check_prefs(raw)
        if not errors:
            res = api.save_preferences(user_id, prefs)
            if res["ok"]:
                return redirect(url_for("home"))
            errors[res.get("field") or "form"] = res["error"]
    else:
        prefs = current_prefs()
    return render_signed_in("survey.html", "survey", prefs=prefs, errors=errors, first_time=first_time,
                            sports=api.SPORTS, volunteer=api.VOLUNTEER, ages=api.AGES, genders=api.GENDERS,
                            radii=api.RADIUS_CHOICES)


# ---------- Pages built from the survey ----------

@app.get("/foryou")
@signed_in_page
@survey_first
def foryou():
    prefs = current_prefs()
    picks = api.get_for_you(prefs)
    return render_signed_in("foryou.html", "foryou", prefs=prefs, study=api.get_study_resources(),
                            sport_sites=picks["sportSites"], vol_sites=picks["volSites"])


@app.get("/popular")
@signed_in_page
@survey_first
def popular():
    prefs = current_prefs()
    cols = api.get_popular(prefs)
    return render_signed_in("popular.html", "popular", prefs=prefs, place=prefs["loc"].strip() or "you", cols=cols,
                            has_activity=any(i["real"] for c in cols for i in c["items"]))


@app.get("/go")
@signed_in_page
def go():
    """Count that a student opened a website, then send them there."""
    try:
        site = signer.loads(request.args.get("t", ""), max_age=60 * 60 * 24 * 30)
    except BadSignature:
        abort(404)
    if not str(site.get("url", "")).startswith(("https://", "http://")):
        abort(404)
    api.log_open(session["user"]["id"], current_prefs(), site)
    return redirect(site["url"])


# ---------- Home: the dashboard ----------

@app.route("/home", methods=["GET", "POST"])
@signed_in_page
@survey_first
def home():
    user_id = session["user"]["id"]
    problem = ""
    if request.method == "POST":
        res = api.set_home(user_id, request.form.get("loc", ""), request.form.get("radius"))
        if res["ok"]:
            return redirect(url_for("home"))
        problem = res["error"]
    prefs = current_prefs()
    plan = api.saved_items(user_id)
    upcoming = [i for i in plan if i["date"] and i["date"] >= date.today()]
    popular_now = [(col["title"], col["items"][0]) for col in api.get_popular(prefs) if col["items"]]
    return render_signed_in(
        "home.html", "home", prefs=prefs, here=api.home_of(user_id), problem=problem, radii=api.RADIUS_CHOICES,
        plan=plan, upcoming=upcoming[:3], popular_now=popular_now, categories=api.VOLUNTEER_CATEGORIES,
        default_category=api.volunteer.default_category(prefs), sport_choices=api.SPORT_CHOICES,
        my_sports=api.sports.default_sports(prefs), examples=api.EXAMPLES[:3], languages=api.code_languages(user_id)[:6],
    )


# ---------- Volunteer finder and Sports tracker ----------

def search_area(user_id, prefs):
    """Where to search, from the form or the student's profile: (home, loc text, radius, problem)."""
    loc = " ".join(request.args.get("loc", "").split()) or prefs["loc"]
    radius = finder.clean_radius(request.args.get("radius"), prefs.get("radius", finder.DEFAULT_RADIUS))
    if loc.lower() == prefs["loc"].strip().lower():
        here = api.home_of(user_id)
    else:
        here = api.locate(loc)
    if here == {}:
        return None, loc, radius, f"SAM couldn’t find “{loc}” on the map. Try a ZIP code, or a town and state like “Austin, TX”."
    if not here:
        return None, loc, radius, "SAM couldn’t reach the map service just now. Wait a minute, then search again."
    return here, loc, radius, ""


@app.get("/volunteer")
@signed_in_page
@survey_first
def volunteer_page():
    user_id = session["user"]["id"]
    prefs = current_prefs()
    here, loc, radius, problem = search_area(user_id, prefs)
    category_id = request.args.get("category") or api.volunteer.default_category(prefs)
    day, slot = finder.clean_when(request.args.get("day"), request.args.get("slot"))
    open_only = request.args.get("open") == "1"
    found = api.find_volunteering(here, radius, category_id, day, slot, open_only) if here else None
    return render_signed_in(
        "volunteer.html", "volunteer_page", prefs=prefs, here=here, loc=loc, radius=radius, problem=problem, found=found,
        category_id=category_id, categories=api.VOLUNTEER_CATEGORIES, day=day, slot=slot, open_only=open_only,
        when=finder.when_label(day, slot), saved=api.saved_ids(user_id), radii=api.RADIUS_CHOICES,
    )


@app.get("/sports")
@signed_in_page
@survey_first
def sports_page():
    user_id = session["user"]["id"]
    prefs = current_prefs()
    here, loc, radius, problem = search_area(user_id, prefs)
    searched = "loc" in request.args
    if searched:
        chosen = api.sports.clean_sports(request.args.getlist("sport"), request.args.get("other"))
        group = request.args.get("group") if request.args.get("group") in dict(api.SPORT_GROUPS) else "any"
    else:
        chosen = api.sports.clean_sports(api.sports.default_sports(prefs), prefs["sportOther"] if "Other" in prefs["sports"] else "")
        group = api.sports.default_group(prefs)
    day, slot = finder.clean_when(request.args.get("day"), request.args.get("slot"))
    open_only = request.args.get("open") == "1"
    if here and not chosen and searched:
        problem = "Pick at least one sport to search for."
    found = api.find_sports(here, radius, chosen, group, day, slot, open_only) if here and chosen else None
    return render_signed_in(
        "sports.html", "sports_page", prefs=prefs, here=here, loc=loc, radius=radius, problem=problem, found=found,
        chosen=chosen, other=[s for s in chosen if s not in api.SPORT_CHOICES], group=group, groups=api.SPORT_GROUPS,
        sport_choices=api.SPORT_CHOICES, day=day, slot=slot, open_only=open_only, when=finder.when_label(day, slot),
        saved=api.saved_ids(user_id), radii=api.RADIUS_CHOICES,
    )


# ---------- My plan ----------

@app.get("/plan")
@signed_in_page
@survey_first
def plan():
    items = api.saved_items(session["user"]["id"])
    today = date.today()
    groups = [
        ("Coming up", [i for i in items if i["date"] and i["date"] >= today]),
        ("No day picked yet", [i for i in items if not i["date"]]),
        ("Past", [i for i in items if i["date"] and i["date"] < today]),
    ]
    return render_signed_in("plan.html", "plan", items=items, groups=[g for g in groups if g[1]],
                            here=api.home_of(session["user"]["id"]), message=session.pop("plan_message", ""))


@app.post("/plan/toggle")
@signed_in_page
def plan_toggle():
    """The Save / Interested button on a place. Answers with JSON for the page's script, or goes back to the page."""
    try:
        item = signer.loads(request.form.get("item", ""), salt="sam-saved", max_age=60 * 60 * 24 * 7)
    except BadSignature:
        abort(400)
    day, slot = finder.clean_when(request.form.get("day"), request.form.get("slot"))
    res = api.toggle_saved(session["user"]["id"], item, day, slot)
    if wants_json():
        return jsonify(ok=True, saved=res["saved"])
    return redirect(back_to("plan"))


@app.post("/plan/update")
@signed_in_page
def plan_update():
    user_id, item_id = session["user"]["id"], request.form.get("item_id", "")
    if request.form.get("action") == "remove":
        api.remove_saved(user_id, item_id)
        session["plan_message"] = "Removed from your plan."
    else:
        res = api.plan_item(user_id, item_id, request.form.get("date", ""), request.form.get("time", ""))
        session["plan_message"] = "Saved." if res["ok"] else res["error"]
    return redirect(url_for("plan"))


@app.get("/plan.ics")
@signed_in_page
def plan_calendar():
    return Response(api.plan_calendar(session["user"]["id"]), mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=sam-plan.ics"})


# ---------- Concept helper (chat) ----------

def run_chat(text):
    """Ask SAM one question and keep both messages. Returns (the student's message, SAM's reply)."""
    messages = chat_messages()
    prefs = current_prefs()
    reply = api.ask_sam(text, messages[-50:], prefs)
    api.log_chat_subject(session["user"]["id"], prefs, text)
    mine = {"id": "m" + secrets.token_hex(4), "role": "user", "text": text}
    theirs = {"id": "m" + secrets.token_hex(4), **reply}
    messages += [mine, theirs]
    del messages[:-MAX_CHAT_MESSAGES]
    return mine, theirs


@app.route("/chat", methods=["GET", "POST"])
@signed_in_page
@survey_first
def chat():
    """The chat page. Without JavaScript, the form posts here and the page reloads with the reply."""
    if request.method == "POST":
        if request.form.get("action") == "new":
            chat_messages().clear()
            return redirect(url_for("chat"))
        text = (request.form.get("prompt") or request.form.get("message") or "").strip()[:4000]
        if text:
            run_chat(text)
        # Redirect so refreshing the page doesn't send the message again.
        return redirect(url_for("chat") + "#latest")
    return render_signed_in("chat.html", "chat", messages=chat_messages(), examples=api.EXAMPLES, live=api.chat_is_live(),
                            placeholder="Ask about a topic, a problem you're stuck on, or something in your life…")


@app.post("/chat/send")
@signed_in_page
@survey_first
def chat_send():
    """The same as posting to /chat, for the page's script: answers with the two new messages as HTML."""
    text = (request.form.get("message") or "").strip()[:4000]
    if not text:
        return jsonify(ok=False, error="Type a question first."), 400
    mine, theirs = run_chat(text)
    return jsonify(ok=True, html=render_template("_messages.html", messages=[mine, theirs]))


# ---------- Code translator ----------

def code_page(result=None, code="", language_id="python", mirror="", problem="", make_open=False, draft=None):
    user_id = session["user"]["id"]
    return render_signed_in(
        "code.html", "code", result=result, code=code or api.code_translator.EXAMPLES.get(language_id, ""),
        language_id=language_id, mirror=mirror, languages=api.code_languages(user_id),
        custom=api.custom_languages(user_id), keywords=api.code_translator.KEYWORDS, problem=problem,
        make_open=make_open, draft=draft or {}, examples=api.code_translator.EXAMPLES,
    )


@app.route("/code", methods=["GET", "POST"])
@signed_in_page
@survey_first
def code():
    """The Code translator. Without JavaScript, the form posts here and the page shows the explanation."""
    if request.method == "POST":
        language_id, mirror, text = request.form.get("language", "python"), request.form.get("mirror", ""), request.form.get("code", "")
        result = api.explain_code(session["user"]["id"], text, language_id, mirror)
        return code_page(result if result["ok"] else None, text, language_id, mirror, "" if result["ok"] else result["error"])
    return code_page(language_id=request.args.get("language", "python"), make_open=request.args.get("make") == "1")


@app.post("/code/explain")
@signed_in_page
@survey_first
def code_explain():
    """The same as posting to /code, for the page's script: answers with the explanation as HTML."""
    result = api.explain_code(session["user"]["id"], request.form.get("code", ""), request.form.get("language", "python"),
                              request.form.get("mirror", ""))
    if not result["ok"]:
        return jsonify(ok=False, error=result["error"]), 400
    return jsonify(ok=True, html=render_template("_code_result.html", result=result))


@app.post("/code/languages")
@signed_in_page
@survey_first
def code_language_save():
    words = {key: request.form.get("word_" + key, "") for key, _ in api.code_translator.KEYWORDS}
    if request.form.get("action") == "delete":
        api.delete_language(session["user"]["id"], request.form.get("name", ""))
        return redirect(url_for("code"))
    res = api.save_language(session["user"]["id"], request.form.get("name", ""), words)
    if not res["ok"]:
        return code_page(problem=res["error"], make_open=True, draft={"name": request.form.get("name", ""), "words": words})
    return redirect(url_for("code", language="custom:" + res["language"]["name"]))


@app.get("/resources")
@signed_in_page
@survey_first
def resources():
    return render_signed_in("resources.html", "resources", shared=api.get_shared_resources(),
                            study=api.get_study_resources())


@app.post("/resources/add")
@signed_in_page
def add_resource():
    f = request.form
    res = api.add_shared_resource(f.get("url"), f.get("by"), f.get("age"), session["user"]["id"])
    if res["ok"]:
        return redirect(url_for("resources"))
    # Go back to the page the dialog was opened on, with the dialog still open.
    session["add_form"] = {"url": f.get("url", ""), "by": f.get("by", ""), "age": f.get("age", ""), "error": res["error"]}
    back = f.get("back", "")
    if not back.startswith("/") or back.startswith(("//", "/\\")):
        back = url_for("resources")
    return redirect(back)


if __name__ == "__main__":
    # 5050, not Flask's usual 5000: on Macs, AirPlay Receiver already uses port 5000.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5050)))
