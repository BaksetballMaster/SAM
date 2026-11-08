# SAM Backend

There is no backend code yet. This file lists the API the frontend expects, so the backend can be built to match.

Until then, the Python frontend (`SAM_Frontend`) uses sample data. Every function in [`SAM_Frontend/api.py`](../SAM_Frontend/api.py) stands in for one endpoint below and is marked with it. To connect a real backend, replace each function's body with a request to its endpoint and keep the same return value.

All replies are JSON. Failures return an error status with `{ "ok": false, "error": "<message to show the student>" }`.

## Login and confirmation email

Use a login service (for example Supabase Auth, Firebase Auth or Auth0) instead of building your own, so passwords are stored safely and Google sign-in is handled.

| Endpoint | Body / query | `api.py` function | Notes |
|---|---|---|---|
| `POST /api/auth/signin` | `{ email, password }` | `sign_in` | Returns `{ ok, user: { name, email } }`. The student isn't signed in until they confirm by email. |
| `POST /api/auth/signup` | `{ name, email, password }` | `sign_up` | Same reply as sign-in |
| `POST /api/auth/google` | | `sign_in_with_google` | In the real app this is a redirect handled by the login service |
| `POST /api/auth/send-confirmation` | | `send_login_confirmation` | Emails a one-time Yes / No link that expires after 10 minutes (e.g. via Amazon SES, SendGrid or Resend). The sample returns the code as `demoCode` for the demo inbox; the real backend must not. |
| `GET /api/auth/confirm` | `?code=...&answer=yes\|no` | `answer_login_confirmation` | Returns `{ ok, confirmed }`. "No" ends that sign-in and the frontend suggests changing the password. |
| `POST /api/auth/signout` | | `sign_out` | |

## Student data

| Endpoint | Body / query | `api.py` function | Notes |
|---|---|---|---|
| `GET /api/preferences` | | `load_preferences` | The student's saved survey answers, or `null`. Shape: `{ age, loc, gender, playsSports: "yes"\|"no"\|null, sports: [], sportOther, vol: [], volOther }` |
| `POST /api/preferences` | prefs object | `save_preferences` | Keep only the fields above |
| `GET /api/websites` | `?topic=...&kind=sport\|vol&area=...` | `search_websites` | Calls a web search API, keeps only safe, student-appropriate sites, and caches each site's title, description and preview picture. Each site: `{ kind, topic, title, url, text, isSearch? }` |
| `GET /api/for-you` | | `get_for_you` | Reads saved prefs and runs the website searches. Returns `{ sportSites, volSites }` |
| `GET /api/popular` | `?area=...` | `get_popular` | Ranks what students in that area open and save. Returns columns of `{ title, items: [[title, subtitle], ...] }` |
| `GET /api/study` | | `get_study_resources` | SAM's study resources, same shape as websites |
| `GET /api/resources` | | `get_shared_resources` | Newest first. Each: `{ url, postedBy, age, postedAt }` |
| `POST /api/resources` | `{ url, postedBy, age }` | `add_shared_resource` | Check the link is safe and hold new posts for review before they appear |
| `POST /api/chat` | `{ message, history }` | `ask_sam` | Adds SAM's rules and the student's prefs, calls the AI model with tools (web search, resource lookup) and returns `{ text, sources }` |

## Rules

- API keys for the AI model and search API stay on the server, never in the frontend.
- Student data lives in the backend's database. The frontend's sample data is in memory only and is cleared when it restarts.
- Website preview pictures should be fetched and cached on the server. The frontend currently uses WordPress's mShots service.
