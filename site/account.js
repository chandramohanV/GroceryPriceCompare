// The app bar's account button and the sign-in / create-account dialog.
// Accounts are invite-only: creating one needs the invite code (INVITE_CODE secret on Cloudflare).
(() => {
  "use strict";

  const user = window.userState;
  const dialog = document.getElementById("account-dialog");
  const button = document.getElementById("account-btn");
  const label = document.getElementById("account-label");
  const message = document.getElementById("account-message");
  const views = {
    signin: document.getElementById("signin-form"),
    signup: document.getElementById("signup-form"),
    signedIn: document.getElementById("signed-in"),
  };

  function say(text, isError = false) {
    message.textContent = text;
    message.classList.toggle("bad", isError);
  }

  function showView(name) {
    for (const [key, view] of Object.entries(views)) view.hidden = key !== name;
    say("");
  }

  function show() {
    const name = user.username;
    label.textContent = name || "Sign in";
    button.title = name ? `Signed in as ${name}` : "Sign in to save your list on every device";
    document.getElementById("signed-in-name").textContent = name || "";
  }

  // The account API only exists on the Cloudflare site, not on a plain local server.
  function friendly(error) {
    return /HTTP 40[45]/.test(error.message)
      ? "Accounts only work on the Cloudflare site." : error.message;
  }

  async function submit(form, action) {
    const submitButton = form.querySelector("button[type=submit]");
    submitButton.disabled = true;
    say("One moment…");
    try {
      await action(new FormData(form));
      form.reset();
      dialog.close();
    } catch (e) {
      say(friendly(e), true);
    } finally {
      submitButton.disabled = false;
    }
  }

  views.signin.addEventListener("submit", (e) => {
    e.preventDefault();
    submit(views.signin, (f) => user.signIn(f.get("username"), f.get("password")));
  });
  views.signup.addEventListener("submit", (e) => {
    e.preventDefault();
    submit(views.signup, (f) => user.signUp(f.get("username"), f.get("password"), f.get("invite")));
  });
  document.getElementById("sign-out").addEventListener("click", async () => {
    await user.signOut();
    dialog.close();
  });
  document.getElementById("to-signup").addEventListener("click", () => showView("signup"));
  document.getElementById("to-signin").addEventListener("click", () => showView("signin"));
  dialog.querySelector(".dialog-close").addEventListener("click", () => dialog.close());

  button.addEventListener("click", () => {
    showView(user.username ? "signedIn" : "signin");
    dialog.showModal();
  });

  user.subscribe(show);
  show();
  user.restore();
})();
