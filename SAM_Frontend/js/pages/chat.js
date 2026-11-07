// Chat with SAM. Messages are kept for this tab so they survive moving between pages.

let messages = session.get("chat") || [];

function renderMessages(typing = false) {
  $("#hello").hidden = messages.length > 0;
  $("#messages").innerHTML = messages.map((m) => `
    <div class="msg ${m.role}">
      <div class="bubble">${esc(m.text)}${m.sources && m.sources.length ? `<div class="sources"><span>Searched:</span>${m.sources.map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>` : ""}</div>
    </div>`).join("") + (typing ? `<div class="msg sam"><div class="bubble typing">SAM is searching…</div></div>` : "");
}

async function send(text) {
  text = text.trim();
  if (!text) return;
  messages.push({ role: "user", text });
  session.set("chat", messages);
  $("#chatbox").value = "";
  renderMessages(true);
  const reply = await askSAM(text, messages, state.prefs);
  messages.push({ role: "sam", text: reply.text, sources: reply.sources });
  session.set("chat", messages);
  renderMessages();
}

$("#send-btn").addEventListener("click", () => send($("#chatbox").value));
$("#chatbox").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); send($("#chatbox").value); } });
document.addEventListener("click", (e) => {
  const p = e.target.closest("[data-prompt]");
  if (p) send(p.dataset.prompt);
});

// Rotating example prompts in the search bar
let exampleIdx = 0;
const setPlaceholder = () => ($("#chatbox").placeholder = `Ask SAM… e.g. “${EXAMPLES[exampleIdx++ % EXAMPLES.length]}”`);
setPlaceholder();
setInterval(setPlaceholder, 3500);

$("#prompt-chips").innerHTML = EXAMPLES.slice(0, 4).map((x) => `<button type="button" class="btn pill" data-prompt="${esc(x)}">${esc(x)}</button>`).join("");

startPage("chat").then((ok) => {
  if (!ok) return;
  renderMessages();
  $("#chatbox").focus();
});
