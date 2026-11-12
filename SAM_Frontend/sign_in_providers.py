"""sign_in_providers.py: "Continue with Google" and "Continue with Apple".

Both use OpenID Connect. SAM sends the student to Google or Apple, they sign in
there, and Google or Apple sends them back to SAM with a signed ID token that
says who they are. SAM checks the token's signature, audience, issuer, expiry
and one-time nonce before trusting it.

Setup (step by step in the README):
    Google:  GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
    Apple:   APPLE_CLIENT_ID (a Services ID). Apple only sends students back to
             an https address, so also set SAM_PUBLIC_URL (for example an ngrok URL).

Until these are set, the buttons open a clearly labelled demo sign-in instead,
so the rest of SAM can still be tried.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import jwt

PROVIDERS = {
    "google": {
        "label": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "keys": "https://www.googleapis.com/oauth2/v3/certs",
        "issuers": ["https://accounts.google.com", "accounts.google.com"],
        "client_id": "GOOGLE_CLIENT_ID",
    },
    "apple": {
        "label": "Apple",
        "authorize": "https://appleid.apple.com/auth/authorize",
        "keys": "https://appleid.apple.com/auth/keys",
        "issuers": ["https://appleid.apple.com"],
        "client_id": "APPLE_CLIENT_ID",
    },
}

_key_clients = {}


class SignInError(Exception):
    """Something went wrong signing in. The message is safe to show the student."""


def _client_id(provider):
    return os.environ.get(PROVIDERS[provider]["client_id"], "").strip()


def is_configured(provider):
    if provider == "google":
        return bool(_client_id("google") and os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())
    return bool(_client_id(provider))


def start_url(provider, redirect_uri, state, nonce):
    """Where to send the student to sign in."""
    p = PROVIDERS[provider]
    params = {"client_id": _client_id(provider), "redirect_uri": redirect_uri, "state": state, "nonce": nonce}
    if provider == "google":
        params.update(response_type="code", scope="openid email profile", prompt="select_account")
    else:
        # Apple posts the answer back to SAM (form_post), which it requires when asking for name and email.
        params.update(response_type="code id_token", response_mode="form_post", scope="name email")
    return p["authorize"] + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def finish_google(code, redirect_uri, nonce):
    """Swap Google's one-time code for the student's ID token, then check it."""
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": _client_id("google"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(PROVIDERS["google"]["token"], data=body, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            tokens = json.load(res)
    except (urllib.error.URLError, ValueError) as e:
        raise SignInError("Google sign-in didn’t finish. Try again.") from e
    return _identity("google", tokens.get("id_token", ""), nonce)


def finish_apple(id_token, user_json, nonce):
    """Check the ID token Apple posted back. Apple sends the student's name only the first time."""
    who = _identity("apple", id_token, nonce)
    try:
        name = (json.loads(user_json or "{}").get("name") or {}).get("firstName") or ""
    except (ValueError, AttributeError):
        name = ""
    return {**who, "name": who["name"] or name}


def _identity(provider, token, nonce):
    p = PROVIDERS[provider]
    label = p["label"]
    if not token:
        raise SignInError(f"{label} didn’t send back a sign-in. Try again.")
    try:
        if p["keys"] not in _key_clients:
            _key_clients[p["keys"]] = jwt.PyJWKClient(p["keys"], cache_keys=True, lifespan=3600)
        key = _key_clients[p["keys"]].get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"], audience=_client_id(provider), issuer=p["issuers"],
            leeway=60, options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise SignInError(f"SAM couldn’t confirm your {label} sign-in. Try again.") from e
    if claims.get("nonce") != nonce:
        raise SignInError(f"That {label} sign-in has expired. Try again.")
    email = claims.get("email") or ""
    if email and str(claims.get("email_verified", "true")).lower() != "true":
        email = ""  # Never trust an email address Google or Apple hasn't verified.
    return {"sub": str(claims["sub"]), "email": email, "name": claims.get("given_name") or claims.get("name") or ""}
