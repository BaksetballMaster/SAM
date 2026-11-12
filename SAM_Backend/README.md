# SAM Backend

SAM's data, sign-in and AI now run inside the Flask app in `SAM_Frontend`:

| Module | What it does |
|---|---|
| [`database.py`](../SAM_Frontend/database.py) | The database: an Excel workbook (`SAM_Frontend/data/sam_database.xlsx`), as the team plan says "for now" |
| [`sign_in_providers.py`](../SAM_Frontend/sign_in_providers.py) | Continue with Google / Apple (OpenID Connect) |
| [`sam_ai.py`](../SAM_Frontend/sam_ai.py) | Chat with NVIDIA Nemotron, plus web search (Tavily or Brave) |
| [`api.py`](../SAM_Frontend/api.py) | The only file the pages call. Each function is marked with the endpoint below it stands for. |

This file lists those calls as an HTTP API, so the backend can move into its own server later: build the endpoint, replace the matching `api.py` function's body with a request to it, and keep the same return value.

All replies are JSON. Failures return an error status with `{ "ok": false, "error": "<message to show the student>", "field": "<form field, if any>" }`.

## Signing in

| Endpoint | Body / query | `api.py` function | Notes |
|---|---|---|---|
| `POST /api/auth/signup` | `{ name, username, email, password }` | `sign_up` | Username: 3 to 20 letters, numbers, dots or underscores. Password: 8+ characters, stored only as a PBKDF2 hash. Returns `{ ok, user: { id, name, username, email, provider } }`. |
| `POST /api/auth/signin` | `{ identifier, password }` | `sign_in` | `identifier` is an email or username. Same reply as sign-up. |
| `POST /login/google` → `GET /login/google/callback` | | `sign_in_with_provider` | Google OpenID Connect (authorization code). The ID token's signature, audience, issuer, expiry and nonce are checked. |
| `POST /login/apple` → `/login/apple/callback` | | `sign_in_with_provider` | Sign in with Apple (form_post). Same checks. Apple sends the student's name only on their first sign-in. |
| `POST /api/auth/send-confirmation` | | `send_login_confirmation` | Emails a one-time Yes / No link that expires after 10 minutes (e.g. via Amazon SES, SendGrid or Resend). Not built yet: the demo inbox on the confirm page stands in. The sample returns the code as `demoCode`; a real backend must not. |
| `GET /api/auth/confirm` | `?code=...&answer=yes\|no` | `answer_login_confirmation` | Returns `{ ok, confirmed }`. "No" ends that sign-in. |
| `POST /api/auth/signout` | | `sign_out` | |

Google and Apple accounts are matched by the ID Google or Apple gives them, never by email, so nobody can take over an account by signing up with someone else's email first.

## Student data

| Endpoint | Body / query | `api.py` function | Notes |
|---|---|---|---|
| `GET /api/preferences` | | `load_preferences` | The saved survey answers, or `null` if the survey isn't done. Shape: `{ age, loc, gender, playsSports: "yes"\|"no"\|null, sports: [], sportOther, vol: [], volOther }` |
| `POST /api/preferences` | prefs object | `check_prefs`, `save_preferences` | Age, where they live and the sports question are required. Errors come back per field. |
| `GET /api/websites` | `?topic=...&kind=sport\|vol&area=...` | `search_websites` | SAM's saved picks plus live web results near the student. Sports searches use the gender answer (girls / boys / co-ed clinics). Each site: `{ kind, topic, title, url, text, live?, isSearch? }` |
| `GET /api/for-you` | | `get_for_you` | Returns `{ sportSites, volSites }` |
| `POST /api/activity` | `{ url, title, kind, topic }` | `log_open`, `log_chat_subject` | Records that a student opened a site, or which subject (like "Math") they asked SAM about. Never the chat text. |
| `GET /api/popular` | `?area=...` | `get_popular` | Counts different students per item in the same area (same first 3 ZIP digits, or same town) over 30 days. Returns columns of `{ title, items: [{ title, sub, url, match, real }] }`. Short lists are topped up with suggestions (`real: false`). |
| `GET /api/study` | | `get_study_resources` | SAM's study resources, same shape as websites |
| `GET /api/resources` | | `get_shared_resources` | Newest first. Each: `{ url, postedBy, age, postedAt }` |
| `POST /api/resources` | `{ url, postedBy, age }` | `add_shared_resource` | Still to do: check the link is safe and hold new posts for review before they appear |
| `POST /api/chat` | `{ message, history }` | `ask_sam` | Searches the web, adds SAM's rules and the student's survey answers, and asks Nemotron. Returns `{ text, sources: [{ n, title, url }] }`. |

## Rules

- API keys stay on the server (in `SAM_Frontend/.env`), never in the browser or in git.
- Student data lives in `SAM_Frontend/data/`, which is in `.gitignore`. Never commit it.
- Before launch: move from the Excel file to a real database (SQLite or Postgres), send real confirmation emails, and fetch and cache website preview pictures on the server (the pages use WordPress's mShots service for now).
