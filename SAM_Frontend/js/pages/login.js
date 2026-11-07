// Login page: sign in or create an account, then go to the confirmation email.

let authMode = "signin"; // "signin" or "signup"

function setAuthMode(mode) {
  authMode = mode;
  const signup = mode === "signup";
  $("#login-title").textContent = signup ? "Create your SAM account" : "Welcome to SAM";
  $("#login-sub").textContent = signup ? "It takes a minute. Then SAM asks a few questions to personalise your page." : "Sign in to see your resources, sports and volunteering picks.";
  $("#login-submit").textContent = signup ? "Create account" : "Sign in";
  $("#switch-text").textContent = signup ? "Already have an account?" : "New to SAM?";
  $("#switch-mode").textContent = signup ? "Sign in" : "Create an account";
  $("#name-field").hidden = !signup;
  $("#consent-row").hidden = !signup;
  $("#password").autocomplete = signup ? "new-password" : "current-password";
  $("#login-error").textContent = "";
}

// Step 2 of signing in: send the confirmation email and wait for Yes.
async function startConfirmation(user) {
  setPendingUser(user);
  await sendLoginConfirmation(user.email);
  go("confirm.html");
}

async function submitLogin() {
  const err = $("#login-error");
  const name = $("#name").value.trim();
  const email = $("#email").value.trim();
  const password = $("#password").value;
  const signup = authMode === "signup";
  if (signup && !name) return (err.textContent = "Enter your first name.");
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return (err.textContent = "Enter a valid email address, like you@example.com.");
  if (password.length < 8) return (err.textContent = "Password must be at least 8 characters.");
  if (signup && !$("#consent").checked) return (err.textContent = "Tick the box to confirm. If you’re under 13, ask a parent or guardian first.");
  err.textContent = "";
  $("#login-submit").disabled = true;
  $("#login-submit").textContent = signup ? "Creating account…" : "Signing in…";
  const res = signup ? await signUp(name, email, password) : await signIn(email, password);
  $("#login-submit").disabled = false;
  setAuthMode(authMode);
  if (!res.ok) return (err.textContent = res.error || "That email and password don’t match. Try again.");
  startConfirmation(res.user);
}

$("#switch-mode").addEventListener("click", () => setAuthMode(authMode === "signin" ? "signup" : "signin"));
$("#login-submit").addEventListener("click", submitLogin);
["#name", "#email", "#password"].forEach((id) =>
  $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submitLogin(); } })
);
$("#google-btn").addEventListener("click", async () => {
  const res = await signInWithGoogle();
  if (res.ok) startConfirmation(res.user);
});

if (startPublicPage()) {
  setAuthMode("signin");
  // Sent here after "No, it wasn't me" on the confirmation email.
  if (new URLSearchParams(location.search).has("stopped"))
    $("#login-error").textContent = "Sign-in stopped. If you didn’t try to sign in, change your password.";
}
