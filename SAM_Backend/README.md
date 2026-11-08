# SAM Backend

A Python (Flask) backend. It serves the API below and the `SAM_Frontend` pages, so both share one address. Each endpoint matches a function in [`SAM_Frontend/js/api.js`](../SAM_Frontend/js/api.js).

The replies are still sample data: sign-in accepts any valid email and a password of 8 or more characters, website results come from a fixed list, and chat replies are scripted. Swap the parts marked `REAL APP:` in `app.py` and `samples.py` for real services.

## Run it

```sh
cd SAM_Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

| File | What it does |
|---|---|
| `app.py` | The endpoints, sign-in sessions and input checks |
| `samples.py` | Sample websites, study resources, popular lists and scripted chat replies |
| `db.py` | A small JSON-file database (`sam_data.json`). Replace it with a real database before launch. |

Set `SAM_SECRET_KEY` in production. Without it, a key is generated into `.secret_key`.

## Login and confirmation email

Use a login service (for example Supabase Auth, Firebase Auth or Auth0) instead of building your own, so passwords are stored safely and Google sign-in is handled.

| Endpoint | Body / query | Frontend function | Notes |
|---|---|---|---|
| `POST /api/auth/signin` | `{ email, password }` | `signIn` | |
| `POST /api/auth/signup` | `{ name, email, password }` | `signUp` | |
| `POST /api/auth/google` | | `signInWithGoogle` | Sample stand-in. In the real app this is a redirect handled by the login service. |
| `POST /api/auth/send-confirmation` | | `sendLoginConfirmation` | Emails a one-time, short-lived Yes / No link (e.g. via Amazon SES, SendGrid or Resend). The student isn't fully signed in until they click Yes. No email is sent yet: the code is returned as `demoCode` for the demo inbox, which must stop once real email is added. |
| `GET /api/auth/confirm` | `?code=...&answer=yes\|no` | `answerLoginConfirmation` | "No" ends that sign-in and suggests changing the password |
| `POST /api/auth/signout` | | `signOut` | |

## Student data

| Endpoint | Body / query | Frontend function | Notes |
|---|---|---|---|
| `GET /api/preferences` | | `loadPreferences` | The student's saved survey answers, or `null` |
| `POST /api/preferences` | prefs object | `savePreferences` | |
| `GET /api/websites` | `?topic=...&kind=sport\|vol&area=...` | `searchWebsites` | Calls a web search API, keeps only safe, student-appropriate sites, and caches each site's title, description and preview picture |
| `GET /api/for-you` | | `getForYou` | Reads saved prefs and runs the website searches |
| `GET /api/popular` | `?area=...` | `getPopular` | Ranks what students in that area open and save |
| `GET /api/study` | | `getStudyResources` | SAM's study resources |
| `GET /api/resources` | | `getSharedResources` | Newest first |
| `POST /api/resources` | `{ url, postedBy, age }` | `addSharedResource` | Check the link is safe and hold new posts for review before they appear |
| `POST /api/chat` | `{ message, history }` | `askSAM` | Adds SAM's rules and the student's prefs, calls the AI model with tools (web search, resource lookup) and streams the reply back |

## Rules

- API keys for the AI model and search API stay on the server, never in the frontend.
- Student data lives in the server's database, not in the browser.
- Website preview pictures should be fetched and cached on the server.
