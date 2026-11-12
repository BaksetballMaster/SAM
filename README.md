# SAM
High/Middle School Students need access to more resources to enhance their High School Learning journey without explicitly providing answers for tasks and assignments. SAM provides learning resources, sports and volunteering opportunities.

## What SAM does

1. **Sign in**: create an account (first name, username, email, password), or use **Continue with Google** or **Continue with Apple**. "Keep me signed in" lasts 30 days.
2. **Survey**: new students answer it first. It asks their age, where they live, the gender they identify as (optional), whether they're into sports and which ones, and how they'd like to volunteer. Study resources are already built in, so they aren't in the survey.
3. **For you**: sports, volunteering and study picks built from the survey, with live web results near the student when web search is set up.
4. **Popular near you**: what students in the same area opened and asked SAM about in the last 30 days, with matches to the student's interests first.
5. **Chat with SAM**: "Hello there, how may I assist you today?" SAM searches the web and answers with NVIDIA Nemotron. It guides students through homework and never hands them the answer.

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
| `NVIDIA_API_KEY` | Chat answers from NVIDIA Nemotron (free key at [build.nvidia.com](https://build.nvidia.com)) | Scripted demo replies |
| `TAVILY_API_KEY` or `BRAVE_API_KEY` | Web search for the chat and live results on For you | SAM's saved picks plus "Search the web" links |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Real Continue with Google | A clearly labelled demo sign-in |
| `APPLE_CLIENT_ID`, `SAM_PUBLIC_URL` | Real Continue with Apple | A clearly labelled demo sign-in |

## Where the data is saved

As the team plan says, it's an Excel sheet for now: `SAM_Frontend/data/sam_database.xlsx`, created the first time someone signs up.

| Sheet | One row per | Columns |
|---|---|---|
| Users | student | User ID, username, first name, email, password (hashed), how they sign in, Google / Apple ID, created, last sign-in, and their survey answers |
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

| File | What it does |
|---|---|
| `app.py` | One route per page: signing in, the survey, For you, Popular, chat, resources |
| `api.py` | Every data call the pages make. Each function names the backend endpoint it stands for (see [`SAM_Backend/README.md`](SAM_Backend/README.md)). |
| `database.py` | The Excel workbook: reading, writing and setting up the sheets |
| `sign_in_providers.py` | Continue with Google / Apple, including checking the ID token's signature |
| `sam_ai.py` | Chat with NVIDIA Nemotron, SAM's rules for the AI, and web search |
| `templates/` | The pages (Jinja templates). `base.html` holds the header and the add-resource dialog. |
| `static/` | Styles, the icon, and `sam.js` (optional extras: loading states, show password, "SAM is thinking") |
