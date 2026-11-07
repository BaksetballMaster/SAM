// Popular near you: ranked lists of what students in the area open and save.

async function renderPopular() {
  $("#pop-title").textContent = `Popular near ${place()}`;
  const cols = await getPopular(state.prefs);
  $("#popular-cols").innerHTML = cols.map((col) => `
    <div class="list-card">
      <h2 style="font-size:19px">${esc(col.title)}</h2>
      <ol class="rank-list">
        ${col.items.map(([title, sub], i) => `<li><span class="rank">${i + 1}</span><div><strong>${esc(title)}</strong><span class="small muted">${esc(sub)}</span></div></li>`).join("")}
      </ol>
    </div>`).join("");
}

startPage("popular").then((ok) => ok && renderPopular());
