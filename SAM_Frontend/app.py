"""app.py: SAM's website, written in Python with Flask.

Each page is a route here plus a template in templates/. Forms send the
student's choices to these routes, which draw the next page. Data comes from
api.py.

The order a new student goes through:
    1. Sign in or create an account (email or username and password, Google, or Apple)
    2. The survey (age, where they live, gender, sports, volunteering), saved to the database
    3. For you, then Popular near you and Chat with SAM

Run:  python app.py   then open http://localhost:5050
"""

import os
import random
import secrets
from datetime import timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import quote, urlparse

from flask import Flask, abort, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer  # Installed with Flask

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

NAV = [
    ("foryou", "For you"),
    ("popular", "Popular near you"),
    ("chat", "Chat with SAM"),
    ("resources", "Resources"),
    ("survey", "Preferences"),
]

# Chat messages for each student, kept in memory while SAM runs.
chats = {}


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


@app.context_processor
def page_globals():
    user = session.get("user")
    return {"user": user, "nav": NAV, "survey_done": bool(user and api.load_preferences(user.get("id")))}


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
    """Sign-in pages: signed-in students go straight to For you."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if (session.get("user") or {}).get("id"):
            return redirect(url_for("foryou"))
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
    return redirect(url_for("foryou" if (session.get("user") or {}).get("id") else "login"))


# ---------- Signing in ----------

def finish_sign_in(user, remember=True):
    """Signed in. New students do the survey first; everyone else goes to For you."""
    session.clear()
    session["user"] = user
    session.permanent = remember  # "Keep me signed in": the cookie lasts 30 days instead of until the browser closes
    return redirect(url_for("foryou" if api.load_preferences(user["id"]) else "survey"))


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
                return redirect(url_for("foryou"))
            errors["form"] = res["error"]
    else:
        prefs = current_prefs()
    return render_signed_in("survey.html", "survey", prefs=prefs, errors=errors, first_time=first_time,
                            sports=api.SPORTS, volunteer=api.VOLUNTEER, ages=api.AGES, genders=api.GENDERS)


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


@app.route("/chat", methods=["GET", "POST"])
@signed_in_page
@survey_first
def chat():
    messages = chat_messages()
    if request.method == "POST":
        if request.form.get("action") == "new":
            messages.clear()
            return redirect(url_for("chat"))
        text = (request.form.get("prompt") or request.form.get("message") or "").strip()[:4000]
        if text:
            prefs = current_prefs()
            reply = api.ask_sam(text, messages[-50:], prefs)
            api.log_chat_subject(session["user"]["id"], prefs, text)
            messages.append({"role": "user", "text": text})
            messages.append({"role": "sam", **reply})
            del messages[:-100]
        # Redirect so refreshing the page doesn't send the message again.
        return redirect(url_for("chat") + "#latest")
    return render_signed_in("chat.html", "chat", messages=messages, examples=api.EXAMPLES[:4], live=api.chat_is_live(),
                            placeholder=f"Ask SAM… e.g. “{random.choice(api.EXAMPLES)}”")


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
