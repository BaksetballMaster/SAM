// sam.js: small extras on top of the Python-drawn pages. Every page still works without it.
(() => {
  // Buttons that take a moment show it, and a form can't be sent twice by double-clicking.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented) return;
    if (form.dataset.sending) {
      event.preventDefault();
      return;
    }
    form.dataset.sending = "1";
    form.setAttribute("aria-busy", "true");
    const button = event.submitter;
    const label = button && button.querySelector(".label");
    if (button && button.dataset.busyText && label) {
      button.dataset.idleText = label.textContent;
      label.textContent = button.dataset.busyText;
      button.classList.add("is-busy");
      button.setAttribute("aria-disabled", "true");
    }
  });

  // Coming back with the Back button shows the page as it was left: reset the busy state.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    document.querySelectorAll("form[data-sending]").forEach((form) => {
      delete form.dataset.sending;
      form.removeAttribute("aria-busy");
    });
    document.querySelectorAll(".is-busy").forEach((button) => {
      const label = button.querySelector(".label");
      if (label && button.dataset.idleText) label.textContent = button.dataset.idleText;
      button.classList.remove("is-busy");
      button.removeAttribute("aria-disabled");
    });
    document.querySelectorAll(".msg.pending, .msg.user.pending").forEach((m) => m.remove());
  });

  // When a form comes back with a problem, start at the problem: the survey's error
  // summary, or else the first answer that needs fixing.
  const problem = document.querySelector("#error-summary, [aria-invalid='true']");
  if (problem) problem.focus();

  // Show / hide password.
  document.querySelectorAll("[data-reveal]").forEach((button) => {
    const input = document.getElementById(button.dataset.reveal);
    if (!input) return;
    button.hidden = false;
    button.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.textContent = show ? "Hide" : "Show";
      button.setAttribute("aria-pressed", String(show));
      input.focus();
    });
  });

  // Chat: show the student's message and "SAM is thinking" while the reply is on its way.
  const chat = document.querySelector("form.chat-form");
  if (chat) {
    const box = chat.querySelector("#chatbox");
    const list = chat.querySelector(".messages");
    chat.addEventListener("submit", (event) => {
      const fromExample = event.submitter && event.submitter.name === "prompt";
      const text = (fromExample ? event.submitter.value : box.value).trim();
      if (!text) {
        event.preventDefault();
        box.focus();
        return;
      }
      if (chat.dataset.sending) return;
      document.querySelector(".hello")?.remove();

      const mine = document.createElement("div");
      mine.className = "msg user pending";
      const myBubble = document.createElement("div");
      myBubble.className = "bubble";
      myBubble.textContent = text;
      mine.append(myBubble);

      const thinking = document.createElement("div");
      thinking.className = "msg sam pending";
      thinking.setAttribute("role", "status");
      thinking.innerHTML = '<span class="avatar" aria-hidden="true"><svg class="i"><use href="#i-compass"/></svg></span>' +
        '<div class="bubble"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>SAM is searching the web and thinking…</div>';

      list.append(mine, thinking);
      thinking.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    });

    // After a reply arrives, show the newest messages instead of the top of the page.
    if (location.hash === "#latest" && list.lastElementChild) {
      list.lastElementChild.scrollIntoView({ block: "start" });
      box.focus({ preventScroll: true });
    }
  }
})();
