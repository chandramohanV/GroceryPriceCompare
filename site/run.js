// "Run now": asks the site's /api/run Function to start the GitHub Actions
// job that scrapes Lidl, Aldi and Dirk (see functions/api/run.js and .github/workflows/update.yml).
(() => {
  "use strict";

  const RUN_URL = "/api/run";
  const button = document.getElementById("run-now");
  const message = document.getElementById("run-message");
  const passwordField = document.getElementById("update-password");

  function say(text, isError = false) {
    message.textContent = text;
    message.classList.toggle("bad", isError);
  }

  async function errorText(resp) {
    if (resp.status === 401) return "Wrong update password.";
    if (resp.status === 404 || resp.status === 405) return "Running only works on the Cloudflare site.";
    try {
      return (await resp.json()).message;
    } catch (_) {
      return `Could not start the run (HTTP ${resp.status}).`; /* not a JSON reply */
    }
  }

  button.addEventListener("click", async () => {
    if (!passwordField.value) { say("Enter the update password first.", true); return; }
    button.disabled = true;
    say("Starting…");
    try {
      const resp = await fetch(RUN_URL, {
        method: "POST",
        headers: { Authorization: `Bearer ${passwordField.value}` },
      });
      if (resp.ok) say("Started. Reload this page in about three minutes to see the new Lidl, Aldi and Dirk prices.");
      else say(await errorText(resp), true);
    } catch (e) {
      say(`Could not start the run: ${e.message}`, true);
    } finally {
      button.disabled = false;
    }
  });
})();
