// "Upload AH bonus page": turns ah.nl/bonus saved from the browser (Ctrl+S)
// into new offers and saves them for every visitor.
//
// The page is read here in the browser with the same code the Python scraper
// uses: ah_cards.js finds the cards, and the Python pipeline (run by Pyodide)
// classifies, normalises and compares them. The result goes to the Cloudflare
// Pages Function at /api/offers, which stores it in KV behind a password.
// Next week's page goes to /api/next-week instead and is held there until the
// daily refresh switches it in on Monday morning.
(() => {
  "use strict";

  const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  // Deployed: copied to py/scraper/ by tools/build_site.py. Locally: the repo's scraper/.
  const SCRAPER_DIRS = ["py/scraper/", "../scraper/"];
  // The modules scraper/upload.py needs; lidl.py and run.py do network and file I/O.
  const BROWSER_MODULES = [
    "__init__.py", "models.py", "match.py", "normalize.py", "translate.py",
    "pipeline.py", "ah.py", "held.py", "upload.py",
  ];
  const CARD_EXTRACTOR = "ah_cards.js";
  const SAVE_URL = "/api/offers";
  const HELD_URL = "/api/next-week";
  const PYODIDE_HOME = "/home/pyodide/scraper/";

  let shownOffers = null;
  let scraperDir = null;
  let pyodideReady = null;

  document.addEventListener("offers-shown", (e) => { shownOffers = e.detail; });

  const form = document.getElementById("upload-form");
  const message = document.getElementById("upload-message");
  const button = form.querySelector("button");
  const passwordField = document.getElementById("update-password");
  const heldStatus = document.getElementById("held-status");

  function say(text, isError = false) {
    message.textContent = text;
    message.classList.toggle("bad", isError);
  }

  // The scraper files are next to the page when deployed, one folder up locally.
  async function fetchScraperFile(name) {
    for (const dir of scraperDir ? [scraperDir] : SCRAPER_DIRS) {
      try {
        const r = await fetch(dir + name, { cache: "no-store" });
        if (r.ok) { scraperDir = dir; return r.text(); }
      } catch (_) { /* not in this folder, try the next */ }
    }
    throw new Error(`Could not load ${name}`);
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`Could not load ${src}`));
      document.head.append(script);
    });
  }

  async function startPyodide() {
    await loadScript(PYODIDE_URL + "pyodide.js");
    const pyodide = await window.loadPyodide({ indexURL: PYODIDE_URL });
    pyodide.FS.mkdirTree(PYODIDE_HOME);
    for (const name of BROWSER_MODULES) {
      pyodide.FS.writeFile(PYODIDE_HOME + name, await fetchScraperFile(name));
    }
    return pyodide;
  }

  // Loaded once, on the first upload: Pyodide is ~10 MB.
  function getPyodide() {
    pyodideReady = pyodideReady || startPyodide().catch((e) => { pyodideReady = null; throw e; });
    return pyodideReady;
  }

  async function readCards(file) {
    if (typeof window.extractAhCards !== "function") {
      // Run as a classic script so it defines extractAhCards on window.
      const source = await fetchScraperFile(CARD_EXTRACTOR);
      const url = URL.createObjectURL(new Blob([source], { type: "text/javascript" }));
      try { await loadScript(url); } finally { URL.revokeObjectURL(url); }
    }
    const page = new DOMParser().parseFromString(await file.text(), "text/html");
    return window.extractAhCards(page);
  }

  // Python errors carry a traceback; the last line is the readable part.
  function pythonMessage(error) {
    const lines = String(error.message || error).trim().split("\n");
    return lines[lines.length - 1].replace(/^\w+Error: /, "");
  }

  // Calls a function of scraper/upload.py with string arguments and parses its JSON result.
  async function runUpload(functionName, ...args) {
    const pyodide = await getPyodide();
    const upload = pyodide.pyimport("scraper.upload");
    try {
      return JSON.parse(upload[functionName](...args));
    } catch (e) {
      throw new Error(pythonMessage(e));
    } finally {
      upload.destroy();
    }
  }

  async function postJson(url, document, password) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${password}` },
      body: JSON.stringify(document),
    });
    if (r.ok) return;
    if (r.status === 401) throw new Error("Wrong upload password.");
    if (r.status === 404 || r.status === 405 || r.status === 501) {
      throw new Error("Saving only works on the Cloudflare site.");
    }
    throw new Error(`Saving failed (HTTP ${r.status}): ${await r.text()}`);
  }

  const dayName = (isoDate) => new Date(`${isoDate}T00:00`).toLocaleDateString("en-GB",
    { weekday: "long", day: "numeric", month: "long" });

  async function uploadThisWeek(cards, password) {
    const offers = await runUpload("import_ah_cards", JSON.stringify(cards), JSON.stringify(shownOffers || {}));
    const ah = offers.stores.ah;
    document.dispatchEvent(new CustomEvent("offers-uploaded", { detail: offers }));
    say(`Matched ${ah.matched} of ${ah.scraped} AH offers. Saving…`);
    try {
      await postJson(SAVE_URL, offers, password);
      say(`Saved: ${ah.matched} AH offers are now shown to everyone.`);
    } catch (e) {
      say(`${e.message} The new AH offers are shown here only, not saved.`, true);
    }
  }

  // Not shown yet: the offers wait on the site until their week starts.
  async function uploadNextWeek(cards, password) {
    const held = await runUpload("hold_next_week_ah_cards", JSON.stringify(cards));
    say(`Matched ${held.matched} of ${held.scraped} AH offers for next week. Saving…`);
    await postJson(HELD_URL, held, password);
    say(`Saved: ${held.matched} AH offers for next week, shown from ${dayName(held.valid_from)} at 06:00.`);
    showHeld(held);
  }

  async function upload(file, password, week) {
    say("Reading the page…");
    const cards = await readCards(file);
    say(`Found ${cards.length} cards. Loading the price checker (first time takes a few seconds)…`);
    if (week === "next") await uploadNextWeek(cards, password);
    else await uploadThisWeek(cards, password);
  }

  function showHeld(held) {
    heldStatus.hidden = !held;
    if (held) {
      heldStatus.textContent = `Next week's AH offers are ready: ${held.matched} offers, ` +
        `shown from ${dayName(held.valid_from)} at 06:00.`;
    }
  }

  // Locally there is no API, so nothing is held.
  async function loadHeld() {
    try {
      const r = await fetch(HELD_URL, { cache: "no-store" });
      showHeld(r.ok ? await r.json() : null);
    } catch (_) {
      showHeld(null);
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = form.elements.page.files[0];
    if (!file) { say("Choose the saved ah.nl/bonus page first.", true); return; }
    button.disabled = true;
    try {
      await upload(file, passwordField.value, form.elements.week.value);
    } catch (err) {
      say(err.message, true);
    } finally {
      button.disabled = false;
    }
  });

  loadHeld();
})();
