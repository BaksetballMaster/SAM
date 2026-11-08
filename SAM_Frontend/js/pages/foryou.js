// For you: sports, volunteering and study websites picked from the student's preferences.

async function renderForYou() {
  $("#fy-sub").textContent = state.prefs.loc.trim()
    ? `Picked from your preferences and what’s around ${state.prefs.loc.trim()}. Start a chat anytime.`
    : "Picked from your preferences. Start a chat anytime.";
  $("#study-cards").innerHTML = (await getStudyResources()).map(siteCard).join("");
  $("#fy-loading").hidden = false;
  const { sportSites, volSites } = await getForYou(state.prefs);
  $("#fy-loading").hidden = true;
  $("#sports-section").hidden = sportSites.length === 0;
  $("#vol-section").hidden = volSites.length === 0;
  $("#extras-empty").hidden = sportSites.length + volSites.length > 0;
  $("#sport-cards").innerHTML = sportSites.map(siteCard).join("");
  $("#vol-cards").innerHTML = volSites.map(siteCard).join("");
}

startPage("foryou").then((ok) => ok && renderForYou());
