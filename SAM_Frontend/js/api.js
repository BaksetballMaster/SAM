/* =====================================================================
   api.js: every function the backend will eventually replace ("BACKEND:").
   Right now they return sample data so the pages work.
   ===================================================================== */

// =====================================================================
// BACKEND: login and the confirmation email
// Use a login service (for example Supabase Auth, Firebase Auth or Auth0) rather
// than writing your own: it stores passwords safely and handles Google sign-in.
// Never store passwords in this file or in the browser.
// =====================================================================

async function signIn(email, password) {
  // BACKEND: POST /api/auth/signin  body: { email, password }
  await wait(400);
  return { ok: true, user: { name: email.split("@")[0], email } };
}

async function signUp(name, email, password) {
  // BACKEND: POST /api/auth/signup  body: { name, email, password }
  await wait(400);
  return { ok: true, user: { name, email } };
}

async function signInWithGoogle() {
  // BACKEND: redirect to the login service's Google page; it sends the student back
  await wait(400);
  return { ok: true, user: { name: "Student", email: "student@gmail.com" } };
}

async function sendLoginConfirmation(email) {
  // BACKEND: POST /api/auth/send-confirmation
  // The server creates a one-time code that expires after a few minutes and emails a
  // link with Yes / No buttons, using an email service such as Amazon SES, SendGrid or Resend.
  // The student isn't fully signed in until the Yes link is clicked.
  await wait(300);
  return { ok: true };
}

async function answerLoginConfirmation(email, itWasMe) {
  // BACKEND: the Yes / No links in the email go to /api/auth/confirm?code=...&answer=yes|no
  // "No" should end that sign-in and suggest changing the password.
  await wait(300);
  return { ok: true, confirmed: itWasMe };
}

async function signOut() {
  // BACKEND: POST /api/auth/signout
  return { ok: true };
}

// =====================================================================
// BACKEND: preferences, websites, popular, resources and chat
// Swap each sample body for a fetch() to your server, e.g.
//   const res = await fetch("/api/for-you"); return res.json();
// Never call the AI model or a search API from here: API keys must stay on the server.
// =====================================================================

async function savePreferences(prefs) {
  // BACKEND: POST /api/preferences  body: prefs
  fakeDB.set("prefs:" + state.user.email.toLowerCase(), prefs);
  return { ok: true };
}

async function loadPreferences(email) {
  // BACKEND: GET /api/preferences  → the student's saved answers, or null
  return fakeDB.get("prefs:" + email.toLowerCase());
}

// Sample websites, standing in for live web search results.
const SAMPLE_SITES = {
  "Soccer": [{ title: "US Youth Soccer", url: "https://www.usyouthsoccer.org", text: "Leagues, programs and player development for youth soccer across the US." }],
  "Basketball": [{ title: "USA Basketball", url: "https://www.usab.com", text: "Youth programs, coaching resources and national team news." }],
  "Track & Field": [{ title: "USA Track & Field", url: "https://www.usatf.org", text: "Youth track and cross country clubs, meets and events." }],
  "Swimming": [{ title: "USA Swimming", url: "https://www.usaswimming.org", text: "Find a local swim club and learn about competitive swimming." }],
  "Tennis": [{ title: "USTA", url: "https://www.usta.com", text: "Junior tennis programs, places to play and tournaments." }],
  "Cricket": [{ title: "USA Cricket", url: "https://www.usacricket.org", text: "The governing body of cricket in the US, with clubs, leagues and youth programs." }],
  "Volleyball": [{ title: "USA Volleyball", url: "https://www.usavolleyball.org", text: "Junior clubs, beach volleyball and events." }],
  "Tutoring younger kids": [{ title: "Schoolhouse.world", url: "https://schoolhouse.world", text: "Free peer tutoring where students help each other over video." }],
  "Environment & parks": [{ title: "National Park Service: Volunteer", url: "https://www.nps.gov/getinvolved/volunteer.htm", text: "Volunteer opportunities in national parks, including youth programs." }],
  "Animal shelters": [{ title: "ASPCA", url: "https://www.aspca.org", text: "Animal welfare information and ways to help shelter animals." }],
  "Food banks": [{ title: "Feeding America", url: "https://www.feedingamerica.org", text: "Find your local food bank and sign up for volunteer shifts." }],
  "Coding for nonprofits": [{ title: "Code for America", url: "https://codeforamerica.org", text: "Use technology to improve public services, with volunteer projects." }],
  "_volunteer_general": [
    { title: "VolunteerMatch", url: "https://www.volunteermatch.org", text: "Search volunteer opportunities near you, including ones for teens." },
    { title: "DoSomething.org", url: "https://dosomething.org", text: "Campaigns and volunteer ideas made for young people." }
  ]
};

async function searchWebsites(topic, kind, loc) {
  // BACKEND: GET /api/websites?topic=...&area=...
  // The server calls a web search API, keeps only safe, student-appropriate sites,
  // reads each page's title, description and preview picture, and caches the results.
  await wait(250);
  const known = (SAMPLE_SITES[topic] || []).map((s) => ({ ...s, kind, topic }));
  const where = loc.trim();
  const q = `${topic} ${kind === "sport" ? "youth programs" : "volunteering for teens"}${where ? " near " + where : ""}`;
  known.push({ kind, topic, isSearch: true, title: `Search the web: ${topic}${where ? " near " + where : ""}`, url: `https://duckduckgo.com/?q=${encodeURIComponent(q)}`, text: "See the latest results from the web for this interest." });
  return known;
}

async function getForYou(prefs) {
  // BACKEND: GET /api/for-you  → server reads saved prefs and runs the website searches
  const sportTopics = prefs.playsSports === "yes"
    ? prefs.sports.filter((s) => s !== "Other").concat(prefs.sports.includes("Other") && prefs.sportOther.trim() ? [prefs.sportOther.trim()] : [])
    : [];
  const volTopics = prefs.vol.filter((v) => v !== "Other").concat(prefs.vol.includes("Other") && prefs.volOther.trim() ? [prefs.volOther.trim()] : []);

  const sportSites = (await Promise.all(sportTopics.map((t) => searchWebsites(t, "sport", prefs.loc)))).flat();
  let volSites = (await Promise.all(volTopics.map((t) => searchWebsites(t, "vol", prefs.loc)))).flat();
  if (volTopics.length) volSites = SAMPLE_SITES._volunteer_general.map((s) => ({ ...s, kind: "vol", topic: "Volunteering" })).concat(volSites);
  return { sportSites, volSites };
}

const STUDY = [
  { kind: "study", topic: "Free", title: "Khan Academy", url: "https://www.khanacademy.org", text: "Lessons and practice for math, science, humanities and test prep." },
  { kind: "study", topic: "Interactive", title: "Brilliant", url: "https://brilliant.org", text: "Hands-on problem solving in math, logic, data and computer science." },
  { kind: "study", topic: "Coding", title: "Boot.dev", url: "https://www.boot.dev", text: "Learn back-end programming by writing real code in the browser." },
  { kind: "study", topic: "Mentor", title: "Lokesh Gaur (Mama)", url: "", text: "Ask about tech, careers and study habits from someone who builds software." }
];

async function getPopular(prefs) {
  // BACKEND: GET /api/popular?area=...  → server counts what students in that area open and save
  const mySports = prefs.playsSports === "yes" ? prefs.sports.filter((s) => s !== "Other").slice(0, 2).map((s) => [`${s} leagues`, "Matches your sports picks"]) : [];
  const myVol = prefs.vol.filter((v) => v !== "Other").slice(0, 2).map((v) => [v, "Matches your volunteering picks"]);
  return [
    { title: "Education", items: [["PSAT / SAT prep", "Practice tests and study plans"], ["Intro to coding", "Python and web basics"], ["AP Biology review", "Unit summaries and practice"], ["Math competition prep", "Problem sets and clubs"]] },
    { title: "Extracurriculars", items: mySports.concat([["Robotics club", "Build and compete as a team"], ["Debate and Model UN", "Public speaking and research"], ["Summer STEM camps", "Week-long programs"]]).slice(0, 4) },
    { title: "Volunteering", items: myVol.concat([["Library teen volunteers", "Reading buddies and events"], ["Park cleanup days", "Weekend, outdoors"], ["Food bank shifts", "Sorting and packing"]]).slice(0, 4) }
  ];
}

async function getSharedResources() {
  // BACKEND: GET /api/resources  → newest first
  return fakeDB.get("resources") || [];
}

async function addSharedResource(resource) {
  // BACKEND: POST /api/resources  body: { url, postedBy, age }
  // The server should check the link is safe and hold new posts for review before they appear.
  const list = fakeDB.get("resources") || [];
  list.unshift({ ...resource, postedAt: new Date().toISOString() });
  fakeDB.set("resources", list);
  return { ok: true };
}

async function askSAM(message, history, prefs) {
  // BACKEND: POST /api/chat  body: { message, history }
  // The server adds SAM's rules + the student's prefs, calls the AI model with tools
  // (web search, resource lookup) and streams the reply back.
  await wait(600);
  const t = message.toLowerCase();
  const where = prefs.loc.trim() || "your area";
  if (/answer|do my|write my|just give|solve it for/.test(t))
    return { text: "I can’t hand you the answer, but I can get you unstuck.\nWhat is the question asking for, and what have you tried so far? Share your first step and I’ll tell you whether you’re on track.", sources: [] };
  if (/essay|thesis|paragraph/.test(t))
    return { text: "Let’s pressure-test your thesis.\n1. Can you say your main claim in one sentence?\n2. Could a reasonable person disagree with it? If not, it may be a fact, not an argument.\n3. Which two pieces of evidence support it best?\nSend me your sentence and I’ll ask you a follow-up.", sources: ["Purdue OWL", "Khan Academy"] };
  if (/photosynth|biology|cell|science|chem|physics/.test(t))
    return { text: "Good topic. Before I explain, what do you already know about what plants need to grow?\nStart there, and we’ll connect it to where the energy actually comes from. A short video plus a simulation usually makes this click.", sources: ["Khan Academy", "PhET Simulations"] };
  if (/math|algebra|equation|geometry|calculus|graph/.test(t))
    return { text: "Let’s break it down. What do you know, and what are you trying to find?\nWrite the first step you’d try. To check yourself visually, graph both sides and see where they meet.", sources: ["Desmos", "Brilliant"] };
  if (/code|coding|program|python|javascript/.test(t))
    return { text: "Nice. Are you starting from zero or do you already know some basics?\nIf zero: pick one language and build something tiny this week. If you know basics: try a project course that makes you write real code.", sources: ["Boot.dev", "Khan Academy"] };
  if (/sport|team|tryout|league|soccer|basketball|cricket|tennis|swim/.test(t)) {
    const picked = prefs.sports.filter((s) => s !== "Other");
    const which = picked.length ? picked.join(", ") : "sports";
    return { text: `I looked for ${which} near ${where}.\nIn the real app I’d list current club teams, rec leagues and tryout dates here with links. Want options that fit after school or on weekends?`, sources: ["Local rec department", "School athletics page"] };
  }
  if (/volunteer|service|hours|nonprofit/.test(t))
    return { text: `I looked for volunteering near ${where} that matches what you picked.\nIn the real app I’d show openings with age requirements and how to sign up. How many hours a month can you give?`, sources: ["VolunteerMatch", "DoSomething.org"] };
  return { text: "Let’s work through it together. What subject is this, and which part feels confusing?\nTell me what you already understand and I’ll ask you a question to take the next step.", sources: [] };
}
