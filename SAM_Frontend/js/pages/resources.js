// Resources: links shared by the community, plus SAM's study resources.

async function renderResources() {
  const shared = await getSharedResources();
  $("#shared-empty").hidden = shared.length > 0;
  $("#shared-cards").innerHTML = shared.map((r) => {
    const domain = domainOf(r.url);
    const date = new Date(r.postedAt).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    return `
      <article class="card">
        <div class="thumb" data-domain="${esc(domain)}"><img src="${esc(shotOf(r.url))}" alt="Picture of ${esc(domain)}" loading="lazy" onerror="this.parentElement.classList.add('noimg');this.remove()"></div>
        <div class="content">
          <span class="tag">Shared</span>
          <h3>${esc(domain)}</h3>
          <p>Shared by ${esc(r.postedBy)}, age ${esc(r.age)}, on ${esc(date)}</p>
          <a class="visit" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">Visit ${esc(domain)}</a>
        </div>
      </article>`;
  }).join("");
  $("#res-study-cards").innerHTML = (await getStudyResources()).map(siteCard).join("");
}

startPage("resources").then((ok) => ok && renderResources());
