// code.js: the Code translator's editor and searchable language list.
//
//  - The plain <textarea> becomes a CodeMirror editor with line numbers and colours
//    for the chosen language.
//  - The language <select> becomes a box you can type in to search ("jav" finds
//    Java and JavaScript). The <select> stays in the form and is what gets sent.
//  - "Explain my code" (or Ctrl/Cmd+Enter) asks /code/explain for the explanation
//    and swaps it into the right-hand pane without reloading the page.
// Without JavaScript the form posts to /code and the page reloads with the result.
(() => {
  const form = document.querySelector("form[data-code-form]");
  if (!form) return;
  const select = form.querySelector("select[data-combobox]");
  const textarea = form.querySelector("textarea[data-editor]");
  const output = document.querySelector("[data-output]");
  const mirrorField = form.querySelector("[data-mirror-field]");
  const exampleButton = form.querySelector("[data-example]");
  const examples = JSON.parse(form.querySelector("[data-examples]").textContent || "{}");
  let editor = null;

  const modeOf = () => select.selectedOptions[0]?.dataset.mode || "python";
  const isCustom = () => select.value.startsWith("custom:");

  function languageChanged() {
    if (editor) editor.setOption("mode", modeOf());
    if (mirrorField) mirrorField.hidden = select.value !== "python";
    const key = isCustom() ? "" : select.value;
    if (exampleButton) {
      exampleButton.hidden = !examples[key];
      exampleButton.dataset.language = key;
    }
  }

  // ---------- Editor ----------
  function startEditor() {
    if (!window.CodeMirror) return; // The editor library didn't load: the plain box still works
    editor = CodeMirror.fromTextArea(textarea, {
      lineNumbers: true, mode: modeOf(), indentUnit: 4, tabSize: 4, indentWithTabs: false,
      extraKeys: {
        Tab: (cm) => cm.execCommand(cm.somethingSelected() ? "indentMore" : "insertSoftTab"),
        "Shift-Tab": "indentLess",
        "Ctrl-Enter": () => form.requestSubmit(),
        "Cmd-Enter": () => form.requestSubmit(),
        Esc: (cm) => cm.getInputField().blur(), // Lets keyboard users leave the editor
      },
      screenReaderLabel: "Your code",
    });
  }

  exampleButton?.addEventListener("click", () => {
    const code = examples[exampleButton.dataset.language] || "";
    if (editor) editor.setValue(code);
    else textarea.value = code;
  });

  // ---------- Searchable language list ----------
  function makeCombobox() {
    const options = [...select.options].map((option) => ({
      value: option.value, name: option.textContent.trim(), group: option.parentElement.label || "",
    }));
    const wrap = document.createElement("div");
    wrap.className = "combo";
    const input = document.createElement("input");
    input.type = "text";
    input.id = select.id;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", "language-options");
    input.autocomplete = "off";
    input.spellcheck = false;
    input.value = select.selectedOptions[0]?.textContent.trim() || "";
    const listbox = document.createElement("ul");
    listbox.id = "language-options";
    listbox.setAttribute("role", "listbox");
    listbox.hidden = true;
    select.id = "";
    select.hidden = true;
    select.tabIndex = -1;
    select.after(wrap);
    wrap.append(input, listbox, select);

    let shown = [];
    let active = -1;

    function render(filter) {
      const words = filter.trim().toLowerCase();
      shown = options.filter((o) => !words || o.name.toLowerCase().includes(words));
      listbox.innerHTML = "";
      shown.forEach((option, index) => {
        const li = document.createElement("li");
        li.id = `language-option-${index}`;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", String(index === active));
        li.innerHTML = `<span></span><span class="small"></span>`;
        li.firstChild.textContent = option.name;
        li.lastChild.textContent = option.group === "Your languages" ? "Yours" : "";
        li.addEventListener("mousedown", (event) => {
          event.preventDefault();
          choose(index);
        });
        listbox.append(li);
      });
      if (!shown.length) {
        const li = document.createElement("li");
        li.className = "combo-empty";
        li.textContent = "No language matches. Make your own below.";
        listbox.append(li);
      }
      input.setAttribute("aria-activedescendant", active >= 0 ? `language-option-${active}` : "");
    }

    function open(filter = "") {
      active = Math.max(0, shown.findIndex((o) => o.value === select.value));
      render(filter);
      listbox.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function close() {
      listbox.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.value = select.selectedOptions[0]?.textContent.trim() || "";
    }
    function choose(index) {
      const option = shown[index];
      if (!option) return;
      select.value = option.value;
      languageChanged();
      close();
    }

    input.addEventListener("focus", () => { input.select(); open(); });
    input.addEventListener("input", () => { active = 0; render(input.value); listbox.hidden = false; input.setAttribute("aria-expanded", "true"); });
    input.addEventListener("blur", close);
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (listbox.hidden) open(input.value);
        active = (active + (event.key === "ArrowDown" ? 1 : -1) + shown.length) % Math.max(shown.length, 1);
        render(input.value);
        listbox.querySelector(`#language-option-${active}`)?.scrollIntoView({ block: "nearest" });
      } else if (event.key === "Enter") {
        if (!listbox.hidden) {
          event.preventDefault();
          choose(active);
        }
      } else if (event.key === "Escape") {
        close();
      }
    });
  }

  // ---------- Explain without reloading ----------
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (editor) editor.save();
    if (!textarea.value.trim()) {
      output.innerHTML = '<p class="alert" role="alert">Paste or type some code first.</p>';
      (editor || textarea).focus();
      return;
    }
    const button = form.querySelector("button.primary");
    const label = button.querySelector(".label");
    const idle = label.textContent;
    label.textContent = button.dataset.busyText;
    button.classList.add("is-busy");
    output.setAttribute("aria-busy", "true");
    output.innerHTML = '<div class="result" role="status"><p class="typing"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>Reading your code line by line…</p>' +
      '<span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>';
    try {
      const reply = await fetch("/code/explain", { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "fetch" } });
      const data = await reply.json();
      output.innerHTML = data.ok ? data.html : `<p class="alert" role="alert"></p>`;
      if (!data.ok) output.querySelector(".alert").textContent = data.error;
    } catch (error) {
      output.innerHTML = '<p class="alert" role="alert">SAM couldn’t be reached. Check your connection and try again.</p>';
    } finally {
      label.textContent = idle;
      button.classList.remove("is-busy");
      output.removeAttribute("aria-busy");
      if (innerWidth < 1100) output.scrollIntoView({ block: "start" });
    }
  });

  select.addEventListener("change", languageChanged);
  makeCombobox();
  languageChanged();
  if (document.readyState === "complete") startEditor();
  else window.addEventListener("load", startEditor);
})();
