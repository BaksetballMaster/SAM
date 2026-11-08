"""app.py: SAM's Python backend (Flask).

It serves the API the frontend calls (see README.md) and also serves the
SAM_Frontend pages, so the site and the API share one address.

Run:  python app.py   then open http://localhost:5000
"""

import os
import re
import secrets
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory, session

import db
import samples

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parent / "SAM_Frontend"

app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def _secret_key():
    """Signs the session cookie. Set SAM_SECRET_KEY in production."""
    if os.environ.get("SAM_SECRET_KEY"):
        return os.environ["SAM_SECRET_KEY"]
    key_file = HERE / ".secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


app.secret_key = _secret_key()

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONFIRM_MINUTES = 10
# One-time confirmation codes: code -> {"email", "expires"}. Kept in memory, so a restart clears them.
pending_codes = {}


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return error("Sign in first.", 401)
        return view(*args, **kwargs)
    return wrapper


def current_email():
    return session["user"]["email"].lower()


def clean_prefs(raw):
    """Keep only known fields with the right types, so stored prefs are always well-formed."""
    prefs = samples.blank_prefs()
    if not isinstance(raw, dict):
        return prefs
    for key in ("age", "loc", "gender", "sportOther", "volOther"):
        if isinstance(raw.get(key), (str, int)):
            prefs[key] = str(raw[key])[:200]
    if raw.get("playsSports") in ("yes", "no"):
        prefs["playsSports"] = raw["playsSports"]
    for key in ("sports", "vol"):
        if isinstance(raw.get(key), list):
            prefs[key] = [str(x)[:100] for x in raw[key] if isinstance(x, str)][:20]
    return prefs


def saved_prefs():
    return clean_prefs(db.get("prefs:" + current_email()))


# ---------- Frontend pages ----------

@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


# ---------- Login and the confirmation email ----------
# REAL APP: use a login service (Supabase Auth, Firebase Auth, Auth0) so passwords are
# stored safely and Google sign-in is handled. This sample accepts any valid email and password.

def start_pending(user):
    session.clear()
    session["pending_user"] = user
    return jsonify({"ok": True, "user": user})


@app.post("/api/auth/signin")
def sign_in():
    data = body()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    if not EMAIL_RE.match(email):
        return error("Enter a valid email address, like you@example.com.")
    if len(password) < 8:
        return error("Password must be at least 8 characters.")
    return start_pending({"name": email.split("@")[0], "email": email})


@app.post("/api/auth/signup")
def sign_up():
    data = body()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    if not name:
        return error("Enter your first name.")
    if not EMAIL_RE.match(email):
        return error("Enter a valid email address, like you@example.com.")
    if len(password) < 8:
        return error("Password must be at least 8 characters.")
    return start_pending({"name": name, "email": email})


@app.post("/api/auth/google")
def sign_in_with_google():
    # REAL APP: redirect to the login service's Google page; it sends the student back.
    return start_pending({"name": "Student", "email": "student@gmail.com"})


@app.post("/api/auth/send-confirmation")
def send_confirmation():
    user = session.get("pending_user")
    if not user:
        return error("Sign in again to get a new confirmation email.")
    now = time.time()
    for code in [c for c, v in pending_codes.items() if v["expires"] < now or v["email"] == user["email"]]:
        del pending_codes[code]
    code = secrets.token_urlsafe(24)
    pending_codes[code] = {"email": user["email"], "expires": now + CONFIRM_MINUTES * 60}
    # REAL APP: email links to /api/auth/confirm?code=...&answer=yes|no with Amazon SES,
    # SendGrid or Resend, and do NOT return the code here. The demo inbox on the
    # confirm page needs it because no real email is sent.
    return jsonify({"ok": True, "demoCode": code})


@app.get("/api/auth/confirm")
def confirm():
    code = request.args.get("code", "")
    answer = request.args.get("answer", "")
    entry = pending_codes.pop(code, None)
    if not entry or entry["expires"] < time.time():
        return error("That confirmation link has expired. Send it again.")
    user = session.get("pending_user")
    if not user or user["email"] != entry["email"]:
        return error("That confirmation link is for a different sign-in.")
    session.pop("pending_user")
    if answer == "yes":
        session["user"] = user
        return jsonify({"ok": True, "confirmed": True})
    # "No": end that sign-in. The frontend suggests changing the password.
    return jsonify({"ok": True, "confirmed": False})


@app.post("/api/auth/signout")
def sign_out():
    session.clear()
    return jsonify({"ok": True})


# ---------- Preferences, websites, popular, resources and chat ----------

@app.get("/api/preferences")
@login_required
def load_preferences():
    saved = db.get("prefs:" + current_email())
    return jsonify(clean_prefs(saved) if saved else None)


@app.post("/api/preferences")
@login_required
def save_preferences():
    db.put("prefs:" + current_email(), clean_prefs(request.get_json(silent=True)))
    return jsonify({"ok": True})


@app.get("/api/websites")
@login_required
def websites():
    topic = request.args.get("topic", "").strip()
    if not topic:
        return error("Give a topic to search for.")
    kind = "sport" if request.args.get("kind") == "sport" else "vol"
    return jsonify(samples.search_websites(topic, kind, request.args.get("area", "")))


@app.get("/api/for-you")
@login_required
def for_you():
    return jsonify(samples.get_for_you(saved_prefs()))


@app.get("/api/popular")
@login_required
def popular():
    prefs = saved_prefs()
    if request.args.get("area"):
        prefs["loc"] = request.args["area"]
    return jsonify(samples.get_popular(prefs))


@app.get("/api/study")
@login_required
def study():
    return jsonify(samples.STUDY)


@app.get("/api/resources")
@login_required
def shared_resources():
    return jsonify(db.get("resources") or [])


@app.post("/api/resources")
@login_required
def add_shared_resource():
    # REAL APP: check the link is safe and hold new posts for review before they appear.
    data = body()
    url = str(data.get("url", "")).strip()
    posted_by = str(data.get("postedBy", "")).strip()[:100]
    age = data.get("age")
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or "." not in (parsed.hostname or ""):
        return error("Enter a full website link, like https://www.example.com.")
    if not posted_by:
        return error("Enter who is posting this link.")
    if not isinstance(age, int) or isinstance(age, bool) or not 10 <= age <= 120:
        return error("Enter the age of the person posting, as a number from 10 up.")
    db.prepend("resources", {
        "url": url,
        "postedBy": posted_by,
        "age": age,
        "postedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    return jsonify({"ok": True})


@app.post("/api/chat")
@login_required
def chat():
    data = body()
    message = str(data.get("message", "")).strip()
    if not message:
        return error("Type a message first.")
    history = data.get("history") if isinstance(data.get("history"), list) else []
    return jsonify(samples.ask_sam(message[:4000], history[-50:], saved_prefs()))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
