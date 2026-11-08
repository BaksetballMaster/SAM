"""app.py: SAM's frontend, written in Python with Flask.

Each page is a route here plus a template in templates/. The pages use no
JavaScript: buttons and forms send the student's choices to these routes,
which draw the next page. Data comes from api.py.

Run:  python app.py   then open http://localhost:5000
"""

import os
import random
import secrets
from functools import wraps
from urllib.parse import quote, urlparse

from flask import Flask, redirect, render_template, request, session, url_for

import api

app = Flask(__name__)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
# Signs the session cookie. Without SAM_SECRET_KEY, a new key is made on each start,
# which signs everyone out when the app restarts.
app.secret_key = os.environ.get("SAM_SECRET_KEY") or secrets.token_hex(32)

NAV = [
    ("survey", "Preferences"),
    ("foryou", "For you"),
    ("popular", "Popular near you"),
    ("chat", "Chat with SAM"),
    ("resources", "Resources"),
]

# Chat messages for each browser session, kept in memory (too big for the session cookie).
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


@app.context_processor
def page_globals():
    return {"user": session.get("user"), "nav": NAV}


# ---------- Signed-in state ----------

def current_prefs():
    saved = api.load_preferences(session["user"]["email"])
    return saved or api.blank_prefs()


def chat_messages():
    sid = session.setdefault("sid", secrets.token_urlsafe(16))
    return chats.setdefault(sid, [])


def signed_in_page(view):
    """Pages for signed-in students: everyone else goes to login."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def public_page(view):
    """Login and confirm: signed-in students go straight to For you."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("user"):
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
    return redirect(url_for("foryou" if session.get("user") else "login"))


# ---------- Login and the confirmation email ----------

def start_confirmation(user):
    """Step 2 of signing in: send the confirmation email and wait for Yes."""
    session.clear()
    session["pending_user"] = user
    res = api.send_login_confirmation(user["email"])
    # Demo only: the real code arrives by email. Kept so the demo inbox can answer it.
    session["confirm_code"] = res.get("demoCode")
    return redirect(url_for("confirm"))


@app.route("/login", methods=["GET", "POST"])
@public_page
def login():
    mode = "signup" if request.values.get("mode") == "signup" else "signin"
    form = {"name": "", "email": "", "consent": False}
    error = ""
    if request.args.get("stopped"):
        error = "Sign-in stopped. If you didn’t try to sign in, change your password."

    if request.method == "POST":
        form = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "consent": bool(request.form.get("consent")),
        }
        password = request.form.get("password", "")
        if mode == "signup":
            res = api.sign_up(form["name"], form["email"], password)
            if res["ok"] and not form["consent"]:
                res = api.fail("Tick the box to confirm. If you’re under 13, ask a parent or guardian first.")
        else:
            res = api.sign_in(form["email"], password)
        if res["ok"]:
            return start_confirmation(res["user"])
        error = res["error"] or "That email and password don’t match. Try again."

    return render_template("login.html", mode=mode, form=form, error=error)


@app.post("/login/google")
@public_page
def login_google():
    res = api.sign_in_with_google()
    return start_confirmation(res["user"]) if res["ok"] else redirect(url_for("login"))


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
                # Step 3: it was them, so finish signing in.
                session.clear()
                session["user"] = pending
                saved = api.load_preferences(pending["email"])
                # No saved preferences yet → survey first. Otherwise → For you.
                return redirect(url_for("foryou" if saved else "survey"))
            else:
                session.clear()
                return redirect(url_for("login", stopped=1))

    return render_template("confirm.html", email=pending["email"], message=message)


@app.post("/signout")
def signout():
    api.sign_out()
    chats.pop(session.get("sid"), None)
    session.clear()
    return redirect(url_for("login"))


# ---------- Signed-in pages ----------

@app.route("/survey", methods=["GET", "POST"])
@signed_in_page
def survey():
    if request.method == "POST":
        f = request.form
        api.save_preferences(session["user"]["email"], {
            "age": f.get("age", ""),
            "loc": f.get("loc", ""),
            "gender": f.get("gender", ""),
            "playsSports": f.get("playsSports"),
            "sports": f.getlist("sports"),
            "sportOther": f.get("sportOther", ""),
            "vol": f.getlist("vol"),
            "volOther": f.get("volOther", ""),
        })
        return redirect(url_for("foryou"))
    return render_signed_in("survey.html", "survey", sports=api.SPORTS, volunteer=api.VOLUNTEER,
                            ages=[str(a) for a in range(10, 19)])


@app.get("/foryou")
@signed_in_page
def foryou():
    prefs = current_prefs()
    picks = api.get_for_you(prefs)
    return render_signed_in("foryou.html", "foryou", prefs=prefs, study=api.get_study_resources(),
                            sport_sites=picks["sportSites"], vol_sites=picks["volSites"])


@app.get("/popular")
@signed_in_page
def popular():
    prefs = current_prefs()
    return render_signed_in("popular.html", "popular", prefs=prefs, place=prefs["loc"].strip() or "you",
                            cols=api.get_popular(prefs))


@app.route("/chat", methods=["GET", "POST"])
@signed_in_page
def chat():
    messages = chat_messages()
    if request.method == "POST":
        text = (request.form.get("prompt") or request.form.get("message") or "").strip()[:4000]
        if text:
            messages.append({"role": "user", "text": text})
            reply = api.ask_sam(text, messages[-50:], current_prefs())
            messages.append({"role": "sam", "text": reply["text"], "sources": reply["sources"]})
        # Redirect so refreshing the page doesn't send the message again.
        return redirect(url_for("chat") + "#latest")
    return render_signed_in("chat.html", "chat", messages=messages, examples=api.EXAMPLES[:4],
                            placeholder=f"Ask SAM… e.g. “{random.choice(api.EXAMPLES)}”")


@app.get("/resources")
@signed_in_page
def resources():
    return render_signed_in("resources.html", "resources", shared=api.get_shared_resources(),
                            study=api.get_study_resources())


@app.post("/resources/add")
@signed_in_page
def add_resource():
    f = request.form
    res = api.add_shared_resource(f.get("url"), f.get("by"), f.get("age"))
    if res["ok"]:
        return redirect(url_for("resources"))
    # Go back to the page the dialog was opened on, with the dialog still open.
    session["add_form"] = {"url": f.get("url", ""), "by": f.get("by", ""), "age": f.get("age", ""), "error": res["error"]}
    back = f.get("back", "")
    if not back.startswith("/") or back.startswith("//"):
        back = url_for("resources")
    return redirect(back)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
