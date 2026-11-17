// chat.js: the Concept helper, without page reloads.
//
// The student's message goes to /chat/send (the same route the plain form uses,
// asking for JSON). While SAM works, the page shows the message right away and a
// loading skeleton with a typing indicator. The reply arrives as ready-made HTML
// from templates/_messages.html, so it looks exactly like a reloaded page.
// Without JavaScript, the form posts to /chat and the page reloads instead.
(() => {
  const form = document.querySelector("form[data-chat]");
  if (!form) return;
  const box = form.querySelector("textarea");
  const list = document.querySelector("[data-messages]");
  const send = form.querySelector(".send");
  const problem = form.querySelector("[data-chat-error]");
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let busy = false;

  // The box grows with the message, up to a limit.
  const grow = () => {
    box.style.height = "auto";
    box.style.height = `${Math.min(box.scrollHeight, 220)}px`;
  };
  box.addEventListener("input", grow);

  // Enter sends; Shift+Enter makes a new line.
  box.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit(send);
    }
  });

  function pending(text) {
    const mine = document.createElement("div");
    mine.className = "msg user";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    mine.append(bubble);

    const thinking = document.createElement("div");
    thinking.className = "msg sam pending";
    thinking.setAttribute("role", "status");
    thinking.innerHTML =
      '<span class="avatar" aria-hidden="true"><svg class="i"><use href="#i-compass"/></svg></span>' +
      '<div class="bubble"><span class="typing"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>SAM is reading sources and thinking…</span>' +
      '<span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>';
    list.append(mine, thinking);
    thinking.scrollIntoView({ block: "end", behavior: calm ? "auto" : "smooth" });
    return [mine, thinking];
  }

  form.addEventListener("submit", async (event) => {
    if (event.submitter && event.submitter.name === "action") return; // "New chat" posts normally
    event.preventDefault();
    if (busy) return;
    const fromExample = event.submitter && event.submitter.name === "prompt";
    const text = (fromExample ? event.submitter.value : box.value).trim();
    if (!text) {
      box.focus();
      return;
    }
    busy = true;
    problem.textContent = "";
    send.setAttribute("aria-disabled", "true");
    document.querySelector(".hello")?.remove();
    const saved = box.value;
    box.value = "";
    grow();
    const placeholders = pending(text);

    try {
      const reply = await fetch("/chat/send", {
        method: "POST",
        body: new URLSearchParams({ message: text }),
        headers: { "X-Requested-With": "fetch" },
      });
      const data = await reply.json();
      if (!reply.ok || !data.ok) throw new Error(data.error || "SAM couldn’t answer just now.");
      placeholders.forEach((el) => el.remove());
      list.insertAdjacentHTML("beforeend", data.html);
      const answer = list.lastElementChild;
      answer.scrollIntoView({ block: "start", behavior: calm ? "auto" : "smooth" });
    } catch (error) {
      placeholders.forEach((el) => el.remove());
      box.value = fromExample ? saved : text;
      grow();
      problem.textContent = error.message && !error.message.startsWith("Failed") ? error.message : "SAM couldn’t be reached. Check your connection and send it again.";
    } finally {
      busy = false;
      send.removeAttribute("aria-disabled");
      box.focus({ preventScroll: true });
    }
  });

  // Citation pop-ups: open next to the number that was pressed (the page centres them without this).
  let opener = null;
  document.addEventListener("click", (event) => {
    const cite = event.target.closest("button.cite");
    if (cite) opener = cite;
  });
  document.addEventListener("toggle", (event) => {
    const pop = event.target;
    if (!(pop instanceof HTMLElement) || !pop.classList.contains("cite-pop") || event.newState !== "open" || !opener) return;
    const spot = opener.getBoundingClientRect();
    const width = Math.min(360, innerWidth - 32);
    pop.style.inset = "auto";
    pop.style.width = `${width}px`;
    pop.style.left = `${Math.max(16, Math.min(spot.left - 12, innerWidth - width - 16))}px`;
    const below = spot.bottom + 8;
    pop.style.top = `${below + pop.offsetHeight > innerHeight - 16 ? Math.max(16, spot.top - pop.offsetHeight - 8) : below}px`;
  }, true);

  // Arriving after a reply without JavaScript's help: show the newest message.
  if (location.hash === "#latest" && list.lastElementChild) {
    list.lastElementChild.scrollIntoView({ block: "start" });
  }
  grow();
})();
