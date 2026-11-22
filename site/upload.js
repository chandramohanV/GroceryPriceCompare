// "Upload AH bonus page": turns ah.nl/bonus saved from the browser (Ctrl+S)
// into new offers and saves them for every visitor.
//
// The page is read here in the browser with the same code the Python scraper
// uses: ah_cards.js finds the cards, and the Python pipeline (run by Pyodide)
// classifies, normalises and compares them. The result goes to the Cloudflare
// Pages Function at /api/offers, which stores it in KV behind a password.
// Next week's page goes into next week's offers (/api/offers?week=next); the
// daily refresh moves them into this week's on Monday morning.
(() => {
  "use strict";

  const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  // Deployed: copied to py/scraper/ by tools/build_site.py. Locally: the repo's scraper/.
  const SCRAPER_DIRS = ["py/scraper/", "../scraper/"];
  // The modules scraper/upload.py needs; lidl.py and run.py do network and file I/O.
  const BROWSER_MODULES = [
    "__init__.py", "models.py", "match.py", "normalize.py", "translate.py",
    "pipeline.py", "ah.py", "upload.py",
  ];
  const CARD_EXTRACTOR = "ah_cards.js";
  // Per week: the scraper/upload.py function that merges the page in, where it is saved, the message.
  const UPLOAD_WEEKS = {
    this: {
      importer: "import_ah_cards", saveUrl: "/api/offers",
      savedText: (n) => `Saved: ${n} AH offers are now shown to everyone.`,
    },
    next: {
      importer: "import_next_week_ah_cards", saveUrl: "/api/offers?week=next",
      savedText: (n) => `Saved: ${n} AH offers for next week. They move into this week on Monday at 06:00.`,
    },
  };
  const PYODIDE_HOME = "/home/pyodide/scraper/";

  let shownWeeks = { this: null, next: null };
  let scraperDir = null;
  let pyodideReady = null;

  document.addEventListener("offers-shown", (e) => {
    shownWeeks = e.detail;
    showNextWeekAh(shownWeeks.next);
  });

  const form = document.getElementById("upload-form");
  const message = document.getElementById("upload-message");
  const button = form.querySelector("button");
  const passwordField = document.getElementById("update-password");
  const nextWeekAhStatus = document.getElementById("ah-next-status");

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

  async function upload(file, password, week) {
    const { importer, saveUrl, savedText } = UPLOAD_WEEKS[week];
    say("Reading the page…");
    const cards = await readCards(file);
    say(`Found ${cards.length} cards. Loading the price checker (first time takes a few seconds)…`);
    const offers = await runUpload(importer, JSON.stringify(cards), JSON.stringify(shownWeeks[week] || {}));
    const ah = offers.stores.ah;
    document.dispatchEvent(new CustomEvent("offers-uploaded", { detail: { week, offers } }));
    say(`Matched ${ah.matched} of ${ah.scraped} AH offers. Saving…`);
    try {
      await postJson(saveUrl, offers, password);
      say(savedText(ah.matched));
    } catch (e) {
      say(`${e.message} The new AH offers are shown here only, not saved.`, true);
    }
  }

  // So it's clear next week's AH page is in, and when it goes live.
  function showNextWeekAh(nextWeek) {
    const starts = ((nextWeek && nextWeek.offers) || [])
      .filter((o) => o.store === "ah" && o.valid_from).map((o) => o.valid_from).sort();
    nextWeekAhStatus.hidden = starts.length === 0;
    if (starts.length) {
      nextWeekAhStatus.textContent = `Next week's AH offers are in: ${starts.length} offers, ` +
        `live from ${dayName(starts[0])} at 06:00.`;
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
})();
