# SAM Backend

Not built yet. This is the API the frontend expects. Each endpoint matches a placeholder function in [`SAM_Frontend/js/api.js`](../SAM_Frontend/js/api.js) that currently returns sample data.

## Login and confirmation email

Use a login service (for example Supabase Auth, Firebase Auth or Auth0) instead of building your own, so passwords are stored safely and Google sign-in is handled.

| Endpoint | Body / query | Frontend function | Notes |
|---|---|---|---|
| `POST /api/auth/signin` | `{ email, password }` | `signIn` | |
| `POST /api/auth/signup` | `{ name, email, password }` | `signUp` | |
| Google sign-in redirect | | `signInWithGoogle` | Handled by the login service |
| `POST /api/auth/send-confirmation` | | `sendLoginConfirmation` | Emails a one-time, short-lived Yes / No link (e.g. via Amazon SES, SendGrid or Resend). The student isn't fully signed in until they click Yes. |
| `GET /api/auth/confirm` | `?code=...&answer=yes\|no` | `answerLoginConfirmation` | "No" ends that sign-in and suggests changing the password |
| `POST /api/auth/signout` | | `signOut` | |

## Student data

| Endpoint | Body / query | Frontend function | Notes |
|---|---|---|---|
| `GET /api/preferences` | | `loadPreferences` | The student's saved survey answers, or `null` |
| `POST /api/preferences` | prefs object | `savePreferences` | |
| `GET /api/websites` | `?topic=...&area=...` | `searchWebsites` | Calls a web search API, keeps only safe, student-appropriate sites, and caches each site's title, description and preview picture |
| `GET /api/for-you` | | `getForYou` | Reads saved prefs and runs the website searches |
| `GET /api/popular` | `?area=...` | `getPopular` | Ranks what students in that area open and save |
| `GET /api/resources` | | `getSharedResources` | Newest first |
| `POST /api/resources` | `{ url, postedBy, age }` | `addSharedResource` | Check the link is safe and hold new posts for review before they appear |
| `POST /api/chat` | `{ message, history }` | `askSAM` | Adds SAM's rules and the student's prefs, calls the AI model with tools (web search, resource lookup) and streams the reply back |

## Rules

- API keys for the AI model and search API stay on the server, never in the frontend.
- Student data lives in the server's database, not in the browser.
- Website preview pictures should be fetched and cached on the server.
