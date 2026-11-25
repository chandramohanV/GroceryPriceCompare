// Loads this week's and next week's offers; shared by the deals page (app.js) and the update page (upload.js).
window.offersData = (() => {
  "use strict";

  // Saved by the daily refresh and the AH upload (Cloudflare KV); the static files come from a local run.
  const OFFERS_SOURCES = {
    this: { api: "/api/offers", file: "offers.json" },
    next: { api: "/api/offers?week=next", file: "offers-next.json" },
  };
  const DATA_DIRS = ["data/", "../data/"];

  async function fetchJson(url) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      return r.ok ? await r.json() : null;
    } catch (_) {
      return null; /* missing here: the caller tries the next source */
    }
  }

  // The static file works both when deployed (data/ next to index.html) and locally (../data/)
  async function loadStaticData(file) {
    for (const dir of DATA_DIRS) {
      const data = await fetchJson(dir + file);
      if (data) return data;
    }
    return null;
  }

  // One week's offers: the saved ones (Cloudflare KV) or the static file, whichever is newer.
  // Locally there is no API.
  async function loadWeek(week) {
    const { api, file } = OFFERS_SOURCES[week];
    const candidates = (await Promise.all([fetchJson(api), loadStaticData(file)])).filter(Boolean);
    return candidates.length ? candidates.reduce((a, b) => (a.generated_at >= b.generated_at ? a : b)) : null;
  }

  // Both weeks; next week is null until a store publishes it. Throws when this week has no offers at all.
  async function loadWeeks() {
    const [thisWeek, nextWeek] = await Promise.all([loadWeek("this"), loadWeek("next")]);
    if (!thisWeek) throw new Error("Could not load offers.json");
    return { this: thisWeek, next: nextWeek };
  }

  return Object.freeze({ loadWeeks });
})();
