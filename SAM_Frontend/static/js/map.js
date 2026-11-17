// map.js: the maps on Home, the Volunteer finder, the Sports tracker and My plan,
// the travel-distance slider, and the Save / Interested buttons.
//
// Each map box (.map[data-map]) is followed by a <script class="map-data"> holding
// {"home": {"lat", "lon", "label"}, "radius": miles, "places": [{"id", "name", "lat", "lon", "miles", "topic", "saved"}]},
// written by map_json() in app.py. Maps use Leaflet with OpenStreetMap tiles.
// Without JavaScript, every place is still in the list next to the map.
(() => {
  const METERS_PER_MILE = 1609.34;
  const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#0F766E";
  const maps = [];

  const escape = (text) => String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // A polite live region, so screen readers hear "Saved to your plan".
  const status = document.createElement("p");
  status.className = "sr-only";
  status.setAttribute("aria-live", "polite");
  document.body.append(status);
  const announce = (text) => { status.textContent = ""; setTimeout(() => { status.textContent = text; }, 50); };

  // The square around a circle. (Leaflet's own circle.getBounds() only works once the map has a view.)
  const areaOf = (circle) => circle.getLatLng().toBounds(circle.getRadius() * 2);

  function draw(box) {
    let data;
    try {
      data = JSON.parse(box.nextElementSibling.textContent);
    } catch (error) {
      return;
    }
    const map = L.map(box, { scrollWheelZoom: false, zoomControl: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    box.classList.add("ready");

    const points = [];
    let circle = null;
    if (data.home) {
      const home = [data.home.lat, data.home.lon];
      L.marker(home, {
        icon: L.divIcon({ className: "", html: '<div class="home-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
        title: "Where you live", alt: "Where you live", keyboard: false,
      }).addTo(map).bindPopup(`<strong>${escape(data.home.label)}</strong>Where you live`);
      if (data.radius) {
        circle = L.circle(home, { radius: data.radius * METERS_PER_MILE, color: accent, weight: 2, fillOpacity: 0.06 }).addTo(map);
      }
      points.push(home);
    }

    const markers = {};
    const numbered = box.hasAttribute("data-numbered");
    data.places.forEach((place, index) => {
      const html = `<div class="pin${place.saved ? " saved" : ""}" data-pin="${escape(place.id)}"><span>${numbered ? index + 1 : ""}</span></div>`;
      const marker = L.marker([place.lat, place.lon], {
        icon: L.divIcon({ className: "", html, iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -28] }),
        title: place.name, alt: place.name,
      }).addTo(map);
      const away = place.miles != null ? `${place.miles} mi away. ` : "";
      marker.bindPopup(`<strong>${escape(place.name)}</strong>${escape(away + (place.topic || ""))}`);
      marker.on("click", () => focusCard(place.id));
      markers[place.id] = marker;
      points.push([place.lat, place.lon]);
    });

    if (circle) {
      map.fitBounds(areaOf(circle), { padding: [12, 12] });
    } else if (points.length > 1) {
      map.fitBounds(points, { padding: [36, 36], maxZoom: 15 });
    } else if (points.length === 1) {
      map.setView(points[0], 13);
    } else {
      map.setView([39.8, -98.6], 4); // The whole US, until there is something to show
    }
    maps.push({ box, map, circle, markers });
  }

  function focusCard(id) {
    document.querySelectorAll(".place.is-focused").forEach((card) => card.classList.remove("is-focused"));
    document.querySelectorAll(".pin.active").forEach((pin) => pin.classList.remove("active"));
    const card = document.querySelector(`[data-place="${CSS.escape(id)}"]`);
    if (card) {
      card.classList.add("is-focused");
      card.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
    document.querySelectorAll(`[data-pin="${CSS.escape(id)}"]`).forEach((pin) => pin.classList.add("active"));
  }

  function focusPin(id) {
    for (const { box, map, markers } of maps) {
      const marker = markers[id];
      if (!marker) continue;
      if (box.getBoundingClientRect().bottom < 0 || box.getBoundingClientRect().top > innerHeight) {
        box.scrollIntoView({ block: "center" });
      }
      map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15));
      marker.openPopup();
      focusCard(id);
    }
  }

  function start() {
    if (!window.L) return; // The map library didn't load: the lists still work
    document.querySelectorAll("[data-map]").forEach(draw);
    document.querySelectorAll("[data-focus]").forEach((button) => {
      if (!maps.some(({ markers }) => markers[button.dataset.focus])) return;
      button.hidden = false;
      button.addEventListener("click", () => focusPin(button.dataset.focus));
    });
  }

  // Travel distance: show the number, and grow or shrink the circle as the slider moves.
  document.querySelectorAll("[data-radius]").forEach((slider) => {
    const out = slider.form?.querySelector("[data-radius-out]");
    slider.addEventListener("input", () => {
      const miles = Number(slider.value);
      if (out) out.textContent = `${miles} mile${miles === 1 ? "" : "s"}`;
      const first = maps.find((m) => m.circle);
      if (first) {
        first.circle.setRadius(miles * METERS_PER_MILE);
        first.map.fitBounds(areaOf(first.circle), { padding: [12, 12] });
      }
    });
  });

  // Save / Interested: toggle without reloading the page. The form still works without JavaScript.
  document.querySelectorAll("form[data-save]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button");
      if (button.getAttribute("aria-disabled") === "true") return;
      button.setAttribute("aria-disabled", "true");
      try {
        const reply = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "fetch" } });
        if (!reply.ok) throw new Error(String(reply.status));
        const { saved } = await reply.json();
        // Every button for this place (a place can show up twice) shows the new state.
        const item = form.querySelector('[name="item"]').value;
        document.querySelectorAll("form[data-save]").forEach((other) => {
          if (other.querySelector('[name="item"]').value !== item) return;
          const otherButton = other.querySelector("button");
          otherButton.setAttribute("aria-pressed", String(saved));
          otherButton.querySelector(".label").textContent = saved ? otherButton.dataset.done : otherButton.dataset.word;
        });
        const card = form.closest("[data-place]");
        if (card) document.querySelectorAll(`[data-pin="${CSS.escape(card.dataset.place)}"]`).forEach((pin) => pin.classList.toggle("saved", saved));
        announce(saved ? "Saved to your plan." : "Removed from your plan.");
      } catch (error) {
        form.submit(); // Fall back to the plain form
      } finally {
        button.removeAttribute("aria-disabled");
      }
    });
  });

  if (document.readyState === "complete") start();
  else window.addEventListener("load", start);
})();
