// Confirmation page: the student answers the "was this you?" email.

// Step 3: the student clicked Yes, so finish signing in.
async function finishLogin(user) {
  setUser(user);
  setPendingUser(null);
  const saved = await loadPreferences(user.email);
  // No saved preferences yet → survey first. Otherwise → For you.
  go(saved ? "foryou.html" : "survey.html");
}

$("#confirm-yes").addEventListener("click", async () => {
  const user = state.pendingUser;
  const res = await answerLoginConfirmation(user.email, true);
  if (res.ok && res.confirmed) finishLogin(user);
});
$("#confirm-no").addEventListener("click", async () => {
  await answerLoginConfirmation(state.pendingUser.email, false);
  setPendingUser(null);
  go("login.html?stopped=1");
});
$("#confirm-resend").addEventListener("click", async () => {
  await sendLoginConfirmation(state.pendingUser.email);
  $("#resend-msg").textContent = `Sent again to ${state.pendingUser.email}.`;
});
$("#confirm-back").addEventListener("click", () => {
  setPendingUser(null);
  go("login.html");
});

if (startPublicPage()) {
  if (!state.pendingUser) location.replace("login.html");
  else $("#confirm-email").textContent = state.pendingUser.email;
}
