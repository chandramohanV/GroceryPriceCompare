// The app bar's theme button: cycles Auto (follow the device) → Light → Dark.
(() => {
  "use strict";

  const user = window.userState;
  const ICON = { auto: "brightness_auto", light: "light_mode", dark: "dark_mode" };
  const LABEL = { auto: "Theme: automatic", light: "Theme: light", dark: "Theme: dark" };
  const button = document.getElementById("theme-btn");

  const current = () => (user.THEMES.includes(user.prefs.theme) ? user.prefs.theme : "auto");

  function show() {
    const theme = current();
    button.querySelector(".material-symbols-outlined").textContent = ICON[theme];
    button.title = `${LABEL[theme]} (click to change)`;
    button.setAttribute("aria-label", button.title);
  }

  button.addEventListener("click", () => {
    const themes = user.THEMES;
    user.setPrefs({ theme: themes[(themes.indexOf(current()) + 1) % themes.length] });
  });
  user.subscribe(show);
  show();
})();
