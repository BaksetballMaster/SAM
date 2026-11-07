/* =====================================================================
   layout.js: pieces shared by every page — header, add-resource dialog,
   website cards and page startup.
   ===================================================================== */

const NAV = [
  ["survey", "Preferences"],
  ["foryou", "For you"],
  ["popular", "Popular near you"],
  ["chat", "Chat with SAM"],
  ["resources", "Resources"]
];

const PLUS_SVG = `<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;

// Draws the header. Nav and sign-out only show once signed in.
function renderHeader(active) {
  const signedIn = state.user
    ? `
    <nav aria-label="Main">
      ${NAV.map(([page, label]) => `<a class="btn tab" href="${page}.html"${page === active ? ' aria-current="page"' : ""}>${label}</a>`).join("")}
      <button class="btn icon-btn" id="add-resource-btn" aria-label="Add a resource" title="Add a resource">${PLUS_SVG}</button>
    </nav>
    <div class="user-area">
      <span class="small muted">${esc(state.user.email)}</span>
      <button class="btn" id="signout">Sign out</button>
    </div>`
    : "";
  $("header").innerHTML = `
  <div class="bar">
    <div class="brand">
      <div class="logo" aria-hidden="true">S</div>
      <div>
        <strong>SAM</strong>
        <span class="muted small">Your learning, sports and volunteering guide</span>
      </div>
    </div>${signedIn}
  </div>`;
  if (state.user) {
    $("#add-resource-btn").addEventListener("click", openAdd);
    $("#signout").addEventListener("click", async () => {
      await signOut();
      setUser(null);
      session.remove("chat");
      go("login.html");
    });
  }
}

// One website card with a picture of the site.
function siteCard(s) {
  const tagClass = s.kind === "sport" ? "tag sport" : s.kind === "vol" ? "tag vol" : "tag";
  const domain = s.url ? domainOf(s.url) : "Mentor";
  let picture;
  if (s.isSearch) {
    picture = `<div class="thumb search" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><line x1="20" y1="20" x2="16.5" y2="16.5"/></svg></div>`;
  } else if (s.url) {
    picture = `<div class="thumb" data-domain="${esc(domain)}"><img src="${esc(shotOf(s.url))}" alt="Picture of the ${esc(s.title)} website" loading="lazy" onerror="this.parentElement.classList.add('noimg');this.remove()"></div>`;
  } else {
    picture = `<div class="thumb noimg" data-domain="${esc(s.title)}"></div>`;
  }
  const link = s.url
    ? `<a class="visit" href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${s.isSearch ? "Search the web" : "Visit " + esc(domain)}</a>`
    : `<span class="small muted">Mentor session</span>`;
  return `
    <article class="card">
      ${picture}
      <div class="content">
        <span class="${tagClass}">${esc(s.topic)}</span>
        <h3>${esc(s.title)}</h3>
        <p>${esc(s.text)}</p>
        ${link}
      </div>
    </article>`;
}

// ---------- Add-resource dialog ----------
function mountAddDialog() {
  document.body.insertAdjacentHTML("beforeend", `
<div class="overlay" id="add-overlay" hidden>
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="add-title">
    <div class="stack" style="gap:4px">
      <h2 id="add-title">Add a resource</h2>
      <p class="muted small">Share a website that helped you. It will show on the Resources page.</p>
    </div>
    <div class="field">
      <label for="res-link">Link</label>
      <input id="res-link" type="url" placeholder="https://www.example.com" autocomplete="off">
    </div>
    <div class="field">
      <label for="res-by">Posted by</label>
      <input id="res-by" type="text" placeholder="Your name">
    </div>
    <div class="field">
      <label for="res-age">Age of the person posting</label>
      <input id="res-age" type="number" min="10" max="120" inputmode="numeric" placeholder="For example, 14">
    </div>
    <p class="error" id="add-error" role="alert"></p>
    <div class="dialog-actions">
      <button type="button" class="btn" id="add-cancel">Cancel</button>
      <button type="button" class="btn primary" id="add-save">Add resource</button>
    </div>
  </div>
</div>`);
  $("#add-cancel").addEventListener("click", closeAdd);
  $("#add-save").addEventListener("click", saveAdd);
  $("#add-overlay").addEventListener("click", (e) => { if (e.target.id === "add-overlay") closeAdd(); });
  $("#add-overlay").addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAdd();
    if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); saveAdd(); }
  });
  document.addEventListener("click", (e) => { if (e.target.closest("[data-open-add]")) openAdd(); });
}

let lastFocus = null;
function openAdd() {
  lastFocus = document.activeElement;
  ["#res-link", "#res-by", "#res-age"].forEach((id) => ($(id).value = ""));
  if (state.user) $("#res-by").value = state.user.name;
  if (state.prefs.age) $("#res-age").value = state.prefs.age;
  $("#add-error").textContent = "";
  $("#add-overlay").hidden = false;
  $("#res-link").focus();
}
function closeAdd() {
  $("#add-overlay").hidden = true;
  if (lastFocus) lastFocus.focus();
}
async function saveAdd() {
  const err = $("#add-error");
  let url = $("#res-link").value.trim();
  const by = $("#res-by").value.trim();
  const age = Number($("#res-age").value);
  if (url && !/^https?:\/\//i.test(url)) url = "https://" + url;
  let valid = false;
  try { const u = new URL(url); valid = (u.protocol === "https:" || u.protocol === "http:") && u.hostname.includes("."); } catch (e) {}
  if (!valid) return (err.textContent = "Enter a full website link, like https://www.example.com.");
  if (!by) return (err.textContent = "Enter who is posting this link.");
  if (!Number.isInteger(age) || age < 10 || age > 120) return (err.textContent = "Enter the age of the person posting, as a number from 10 up.");
  $("#add-save").disabled = true;
  await addSharedResource({ url, postedBy: by, age });
  go("resources.html");
}

// ---------- Page startup ----------
// Signed-in pages: send logged-out visitors to login, load prefs, draw the header and dialog.
// Returns false when the page is redirecting away.
async function startPage(active) {
  document.querySelectorAll("form").forEach((f) => f.addEventListener("submit", (e) => e.preventDefault()));
  if (!state.user) { location.replace("login.html"); return false; }
  const saved = await loadPreferences(state.user.email);
  state.prefs = saved ? { ...blankPrefs(), ...saved } : blankPrefs();
  renderHeader(active);
  mountAddDialog();
  return true;
}

// Logged-out pages (login, confirm): signed-in visitors go straight to For you.
function startPublicPage() {
  document.querySelectorAll("form").forEach((f) => f.addEventListener("submit", (e) => e.preventDefault()));
  if (state.user) { location.replace("foryou.html"); return false; }
  renderHeader(null);
  return true;
}
