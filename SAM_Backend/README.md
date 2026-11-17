# SAM Backend

SAM's data, sign-in and AI now run inside the Flask app in `SAM_Frontend`:

| Module | What it does |
|---|---|
| [`database.py`](../SAM_Frontend/database.py) | The database: an Excel workbook (`SAM_Frontend/data/sam_database.xlsx`), as the team plan says "for now" |
| [`sign_in_providers.py`](../SAM_Frontend/sign_in_providers.py) | Continue with Google / Apple (OpenID Connect) |
| [`sam_ai.py`](../SAM_Frontend/sam_ai.py) | The NVIDIA Nemotron model, plus web search (Tavily or Brave) |
| [`assistants/`](../SAM_Frontend/assistants) | The Volunteer finder, Sports tracker, Concept helper (with its guardrails) and Code translator |
| [`services/`](../SAM_Frontend/services) | Maps, places, Wikipedia, the cache, and safe rich text |
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

## The four assistants and My plan

| Endpoint | Body / query | `api.py` function | Notes |
|---|---|---|---|
| `POST /api/home` | `{ loc, radius }` | `set_home` | Finds the town or ZIP code on the map (`services/geo.py`: Nominatim, with Open-Meteo as a backup) and saves the point |
| `GET /api/volunteer` | `?lat&lon&radius&category&day&slot&open` | `find_volunteering` | Real places from OpenStreetMap (`assistants/volunteer.py`). Each: distance, address, hours, open-then status, typical time commitment, sign-up link |
| `GET /api/sports` | `?lat&lon&radius&sports&group&day&slot&open` | `find_sports` | Places to play for each sport (`assistants/sports.py`), plus clinic listings from web search |
| `GET /api/saved` | | `saved_items` | My plan, the soonest day first |
| `POST /api/saved/toggle` | `{ item, day, slot }` | `toggle_saved` | `item` is signed by the server when the page is drawn, so students can only save real results |
| `POST /api/saved/<item_id>` | `{ date, time }` | `plan_item` | |
| `DELETE /api/saved/<item_id>` | | `remove_saved` | |
| `GET /plan.ics` | | `plan_calendar` | My plan as an iCalendar file |
| `POST /api/chat` | `{ message, history }` | `ask_sam` | Now runs `assistants/concepts.py`: guardrail check, sources, the model, then a second guardrail check. Returns `{ text, main, deep_dives, sources, guard, mode, error }` |
| `POST /api/code/explain` | `{ code, language, mirror }` | `explain_code` | `assistants/code_translator.py`. Built-in explainer, or Nemotron when connected. Never runs the code |
| `POST /api/languages` | `{ name, words }` | `save_language` | A student's made-up language: their own words for up to 15 Python keywords. Up to 5 per student |
| `DELETE /api/languages/<name>` | | `delete_language` | |

## Rules

- API keys stay on the server (in `SAM_Frontend/.env`), never in the browser or in git.
- Student data lives in `SAM_Frontend/data/`, which is in `.gitignore`. Never commit it.
- Before launch: move from the Excel file to a real database (SQLite or Postgres), send real confirmation emails, and fetch and cache website preview pictures on the server (the pages use WordPress's mShots service for now).
