/* =====================================================================
   SAM prototype — plain HTML/CSS/JS, no libraries.
   core.js: constants, small helpers, storage and the shared state.
   Loaded first on every page.
   ===================================================================== */

const SPORTS = ["Soccer", "Basketball", "Track & Field", "Swimming", "Tennis", "Cricket", "Volleyball", "Martial arts", "Other"];
const VOLUNTEER = ["Tutoring younger kids", "Environment & parks", "Animal shelters", "Food banks", "Hospitals & senior care", "Coding for nonprofits", "Other"];
const EXAMPLES = ["Help me understand photosynthesis", "How do I start learning Python?", "Check my essay thesis", "Find soccer leagues near me", "Volunteering for students my age"];

const blankPrefs = () => ({ age: "", loc: "", gender: "", playsSports: null, sports: [], sportOther: "", vol: [], volOther: "" });

// ---------- Small helpers ----------
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const place = () => state.prefs.loc.trim() || "you";
const domainOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return url; } };
const go = (page) => (location.href = page);

// Website picture: a screenshot from WordPress's free mShots service.
// The first time a site is requested, mShots may show a "generating" image for a few seconds.
// BACKEND: the real app should take or fetch these pictures on the server and cache them.
const shotOf = (url) => `https://s0.wp.com/mshots/v1/${encodeURIComponent(url)}?w=600&h=400`;

// Carries the signed-in user and chat between pages for this browser tab.
// BACKEND: the real app uses the login service's session cookie instead.
const session = {
  get: (key) => { try { return JSON.parse(sessionStorage.getItem("sam-" + key)); } catch (e) { return null; } },
  set: (key, value) => { try { sessionStorage.setItem("sam-" + key, JSON.stringify(value)); } catch (e) {} },
  remove: (key) => { try { sessionStorage.removeItem("sam-" + key); } catch (e) {} }
};

const state = {
  user: session.get("user"),               // { name, email } once signed in and confirmed
  pendingUser: session.get("pendingUser"), // signed in, waiting for the confirmation email
  prefs: blankPrefs()
};

function setUser(user) {
  state.user = user;
  user ? session.set("user", user) : session.remove("user");
}

function setPendingUser(user) {
  state.pendingUser = user;
  user ? session.set("pendingUser", user) : session.remove("pendingUser");
}
