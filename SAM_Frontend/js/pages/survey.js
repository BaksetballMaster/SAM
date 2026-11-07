// Preferences survey: age, place, gender, sports and volunteering picks.

function chips(container, list, key) {
  container.innerHTML = list.map((x) => `<button type="button" class="btn chip" aria-pressed="${state.prefs[key].includes(x)}" data-key="${key}" data-val="${esc(x)}">${esc(x)}</button>`).join("");
}

// Make the survey match state.prefs (used after loading saved answers).
function fillSurvey() {
  const p = state.prefs;
  $("#age").value = p.age; $("#loc").value = p.loc; $("#gender").value = p.gender;
  $("#sport-other").value = p.sportOther; $("#vol-other").value = p.volOther;
  document.querySelectorAll("[data-sports]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sports === p.playsSports)));
  $("#sport-pick").hidden = p.playsSports !== "yes";
  $("#sport-other-field").hidden = !p.sports.includes("Other");
  $("#vol-other-field").hidden = !p.vol.includes("Other");
  chips($("#sport-chips"), SPORTS, "sports");
  chips($("#vol-chips"), VOLUNTEER, "vol");
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-key]");
  if (chip) {
    const key = chip.dataset.key;
    const list = state.prefs[key];
    const v = chip.dataset.val;
    const i = list.indexOf(v);
    i >= 0 ? list.splice(i, 1) : list.push(v);
    chip.setAttribute("aria-pressed", String(i < 0));
    if (v === "Other") {
      const field = key === "sports" ? "#sport-other-field" : "#vol-other-field";
      $(field).hidden = i >= 0;
      if (i < 0) $(field + " input").focus();
    }
    return;
  }

  const yn = e.target.closest("[data-sports]");
  if (yn) {
    state.prefs.playsSports = yn.dataset.sports;
    document.querySelectorAll("[data-sports]").forEach((b) => b.setAttribute("aria-pressed", String(b === yn)));
    $("#sport-pick").hidden = yn.dataset.sports !== "yes";
  }
});

[["age", "age"], ["loc", "loc"], ["gender", "gender"], ["sport-other", "sportOther"], ["vol-other", "volOther"]]
  .forEach(([id, key]) => $("#" + id).addEventListener("input", (e) => (state.prefs[key] = e.target.value)));

$("#survey-submit").addEventListener("click", async () => {
  await savePreferences(state.prefs);
  go("foryou.html");
});

startPage("survey").then((ok) => ok && fillSurvey());
