# SAM
High/Middle School Students need access to more resources to enhance their High School Learning journey without explicitly providing answers for tasks and assignments. SAM provides learning resources, sports and volunteering opportunities.

## What SAM does

1. **Sign in**: create an account (first name, username, email, password), or use **Continue with Google** or **Continue with Apple**. "Keep me signed in" lasts 30 days.
2. **Survey**: new students answer it first. It asks their age, where they live, the gender they identify as (optional), whether they're into sports and which ones, and how they'd like to volunteer. Study resources are already built in, so they aren't in the survey.
3. **Home**: the dashboard. A map of the student's area with their travel distance and saved places, a form to change where they live, and a card for each of SAM's four assistants.
4. **The four assistants**, in the sidebar on every page:
   - **Volunteer finder** (`/volunteer`): real places near the student that take volunteers (animal shelters, food banks, libraries, nature reserves, hospitals, community centers), from OpenStreetMap. Choose where, how far (a 1 to 25 mile slider), what kind, and the day and time you're free. Each card shows the distance, opening hours and whether it's open then, a typical time commitment, and a link to sign up. Places also appear on a map.
   - **Sports tracker** (`/sports`): fields, courts, pools, tracks and clubs for the sports the student picks, filtered by distance and by girls, boys or co-ed, as a list beside a map. Mark places "Interested" to add them to My plan. Clinic and camp listings come from web search.
   - **Concept helper** (`/chat`): "Hello there, how may I assist you today?" Ask about schoolwork or everyday life. SAM reads sources first (the web, Wikipedia and a list of trusted study sites), then replies with rich text, expandable deep dives and numbered citations. It coaches students through homework and never hands them the answer (see below).
   - **Code translator** (`/code`): paste code, pick its language from a searchable list, and see what each line does in plain English, or switch to pseudocode. Students can also invent their own language by renaming Python's keywords.
5. **My plan** (`/plan`): the places a student saved, with a day and time for each, a map, and a calendar file to add them to Google Calendar, Apple Calendar or Outlook.
6. **For you**, **Popular near you** and **Resources**: picks from the survey, what students nearby open most, and links students share.

## How SAM avoids giving answers away

The team's rule is to help students learn "without explicitly providing answers for tasks and assignments". The AI model is told this, but SAM doesn't rely on that alone. Every chat message passes three checks in [`assistants/guardrails.py`](SAM_Frontend/assistants/guardrails.py), which are plain Python and behave the same every time:

1. **Before the model sees the message**, SAM decides what kind of message it is. "Give me the answer to #4", "Solve 2x + 6 = 14", a multiple-choice question, "write my essay" and "write a function that..." are all flagged. Short follow-ups like "so what is x?" stay flagged.
2. **A flagged message is rewritten.** The model never receives the bare request. It receives the student's words inside instructions to coach: name the idea, ask what they've tried, give one hint for the next step, and end with a question.
3. **After the model replies, SAM reads the reply.** If it states an answer, gives a value for the student's unknown, contains a finished paragraph or finished code, or doesn't ask a question, it's thrown away. The model gets one more try. If that fails too, the student sees SAM's own guiding questions, written in the code, with no model involved.

The student sees a short note when SAM coached instead of answering, so it doesn't feel like a dodge. Explaining concepts, checking a student's own answer, and everyday questions are always fine. Messages that suggest a student may be in danger get a fixed reply pointing to a trusted adult and to 988, without the model.

## Run it

```sh
cd SAM_Frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5050. (Not 5000: on Macs, AirPlay Receiver already uses port 5000.)

Everything works straight away in demo mode. To switch on the real AI, web search and Google / Apple sign-in, copy `SAM_Frontend/.env.example` to `SAM_Frontend/.env` and fill in the keys. `.env` is in `.gitignore`, so keys never get committed.

| Setting | Turns on | Without it |
|---|---|---|
| `NVIDIA_API_KEY` | Concept helper replies, and Code translator explanations, from NVIDIA Nemotron (free key at [build.nvidia.com](https://build.nvidia.com)) | SAM's built-in coaching (from its sources) and its built-in code explainer |
| `TAVILY_API_KEY` or `BRAVE_API_KEY` | Web results in the chat, on For you, in the Volunteer finder, and clinic listings in the Sports tracker | Wikipedia and SAM's study list for the chat; "search the web" links elsewhere |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Real Continue with Google | A clearly labelled demo sign-in |
| `APPLE_CLIENT_ID`, `SAM_PUBLIC_URL` | Real Continue with Apple | A clearly labelled demo sign-in |

Maps, places and Wikipedia need no keys. Places and map tiles come from [OpenStreetMap](https://www.openstreetmap.org/copyright), whose volunteers add opening hours and websites, so some places don't have them. SAM asks for at most one place search a second, as OpenStreetMap's rules require, and remembers every answer in `SAM_Frontend/data/cache/`. So a search takes a few seconds the first time and is instant after that, even without internet.

## Test it

```sh
cd SAM_Frontend
python -m unittest discover -s tests -v
```

The tests run offline: the map, Wikipedia and the AI model are replaced by stand-ins.

## Where the data is saved

As the team plan says, it's an Excel sheet for now: `SAM_Frontend/data/sam_database.xlsx`, created the first time someone signs up.

| Sheet | One row per | Columns |
|---|---|---|
| Users | student | User ID, username, first name, email, password (hashed), how they sign in, Google / Apple ID, created, last sign-in, their survey answers, travel distance, and where they live on the map |
| Saved | place in a student's plan | saved, user ID, kind, place, address, link, map point, planned day and time |
| Languages | made-up programming language | saved, user ID, name, and its keywords |
| Activity | website opened or chat subject asked about | time, user ID, area, category, topic, title, link. Only the chat's subject (like "Math") is saved, never what the student wrote. |
| Resources | shared link | posted, link, posted by, age, user ID |

- Passwords are never saved, only a one-way hash (PBKDF2-SHA256, 600,000 rounds), so nobody who opens the file can read them.
- You can open the file in Excel to look. Don't edit it while SAM is running: SAM rewrites the file each time it saves.
- `data/` is in `.gitignore`. Student data must never be committed to this repo.
- Moving to a real database later only means rewriting the functions at the bottom of `database.py`.

## Set up Google and Apple sign-in

**Google** (free, works on localhost):
1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Go to **APIs & Services → OAuth consent screen**, choose External, and add your team as test users.
3. Go to **Credentials → Create credentials → OAuth client ID**, and pick **Web application**.
4. Under **Authorized redirect URIs**, add `http://localhost:5050/login/google/callback`.
5. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then restart SAM.

Open SAM at `localhost`, not `127.0.0.1`: Google only accepts the redirect address you registered.

**Apple** (needs a paid Apple Developer account and an https address):
1. In [Certificates, Identifiers & Profiles](https://developer.apple.com/account/resources/identifiers/list), create an App ID with **Sign in with Apple**, then a **Services ID** linked to it.
2. Apple won't send students back to `localhost`, so give SAM a public https address, for example with [ngrok](https://ngrok.com): `ngrok http 5050`.
3. In the Services ID's Sign in with Apple settings, add that domain and the return URL `https://<your-ngrok-address>/login/apple/callback`.
4. Set `APPLE_CLIENT_ID` to the Services ID and `SAM_PUBLIC_URL` to `https://<your-ngrok-address>` in `.env`, restart SAM, and open it at that address.

Each Google or Apple account becomes its own SAM account, matched by the ID Google or Apple gives it, never by email. That way nobody can take over an account by signing up with someone else's email first.

## The code

How a request travels: a page's form (or its script, which calls the same route and asks for JSON) goes to a route in `app.py`. The route calls `api.py`, which uses `assistants/`, `services/` and the database, and draws the result with a template. Every page works without JavaScript; the scripts only add the maps, the code editor, and replies that appear without reloading.

| File | What it does |
|---|---|
| `app.py` | One route per page: signing in, the survey, Home, the four assistants, My plan, For you, Popular, Resources |
| `api.py` | Every data call the pages make. Each function names the backend endpoint it stands for (see [`SAM_Backend/README.md`](SAM_Backend/README.md)). |
| `assistants/volunteer.py`, `sports.py`, `finder.py` | The Volunteer finder and Sports tracker: which places to search for, distances, opening hours |
| `assistants/concepts.py` | One Concept helper turn, from the student's message to SAM's reply |
| `assistants/guardrails.py` | The no-answers rules, the safety reply, and school subjects |
| `assistants/retrieval.py` | The sources SAM reads before replying (web, Wikipedia, SAM's study list) |
| `assistants/code_translator.py` | Line-by-line explanations, pseudocode, and made-up languages |
| `services/` | Outside services: finding a town on the map, nearby places, Wikipedia, a cache, and safe rich text |
| `database.py` | The Excel workbook: users, survey answers, saved places, made-up languages, activity, shared links |
| `sign_in_providers.py` | Continue with Google / Apple, including checking the ID token's signature |
| `sam_ai.py` | The NVIDIA Nemotron model and web search |
| `templates/` | The pages (Jinja templates). `base.html` holds the sidebar; `_finder.html`, `_messages.html` and `_code_result.html` are shared pieces. |
| `static/` | Styles, the icon, `sam.js` (loading states, show password) and `js/` (the map, the chat and the code editor) |
| `tests/` | The test suite |

The maps use [Leaflet](https://leafletjs.com) and the code editor uses [CodeMirror 5](https://codemirror.net/5/), both loaded from cdnjs with integrity checks. There's nothing to install for them.
