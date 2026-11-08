/* =====================================================================
   api.js: every call to SAM's Python backend (SAM_Backend/app.py).
   The backend serves these pages too, so paths like "/api/..." reach it.
   Never call the AI model or a search API from here: API keys stay on the server.
   ===================================================================== */

// Sends a request to the backend and returns the JSON reply.
// Throws an Error with the server's message if the request fails.
async function callApi(method, path, body) {
  const options = { method, credentials: "same-origin" };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  if (res.status === 401 && state.user) {
    // The server's session ended (for example after sign-out elsewhere): sign in again.
    setUser(null);
    location.replace("login.html");
    return new Promise(() => {});
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.error) || "Something went wrong. Try again.");
  return data;
}

// For actions whose page shows the error: returns { ok: false, error } instead of throwing.
async function tryApi(method, path, body) {
  try { return await callApi(method, path, body); }
  catch (e) { return { ok: false, error: e.message }; }
}

// ---------- Login and the confirmation email ----------

function signIn(email, password) {
  return tryApi("POST", "/api/auth/signin", { email, password });
}

function signUp(name, email, password) {
  return tryApi("POST", "/api/auth/signup", { name, email, password });
}

function signInWithGoogle() {
  return tryApi("POST", "/api/auth/google", {});
}

async function sendLoginConfirmation(email) {
  const res = await tryApi("POST", "/api/auth/send-confirmation", {});
  // Demo only: the real code arrives by email. Kept so the demo inbox can answer it.
  if (res.ok) session.set("confirmCode", res.demoCode);
  return res;
}

async function answerLoginConfirmation(email, itWasMe) {
  const code = encodeURIComponent(session.get("confirmCode") || "");
  const res = await tryApi("GET", `/api/auth/confirm?code=${code}&answer=${itWasMe ? "yes" : "no"}`);
  if (res.ok) session.remove("confirmCode");
  return res;
}

function signOut() {
  return tryApi("POST", "/api/auth/signout", {});
}

// ---------- Preferences, websites, popular, resources and chat ----------

function savePreferences(prefs) {
  return tryApi("POST", "/api/preferences", prefs);
}

function loadPreferences(email) {
  // The server knows who is signed in, so `email` isn't sent.
  return callApi("GET", "/api/preferences");
}

function searchWebsites(topic, kind, loc) {
  const q = new URLSearchParams({ topic, kind, area: loc });
  return callApi("GET", "/api/websites?" + q);
}

function getForYou(prefs) {
  // The server reads the saved prefs itself.
  return callApi("GET", "/api/for-you");
}

function getPopular(prefs) {
  return callApi("GET", "/api/popular?" + new URLSearchParams({ area: prefs.loc.trim() }));
}

function getStudyResources() {
  return callApi("GET", "/api/study");
}

function getSharedResources() {
  return callApi("GET", "/api/resources");
}

function addSharedResource(resource) {
  return tryApi("POST", "/api/resources", resource);
}

function askSAM(message, history, prefs) {
  return callApi("POST", "/api/chat", { message, history });
}
