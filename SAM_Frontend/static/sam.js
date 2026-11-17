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

})();
