(() => {
  "use strict";

  const STORE_NAMES = window.STORE_NAMES;
  // Category codes come from scraper/match.py (CATEGORIES).
  const CATEGORY_ICON = {
    fruit: "🍎", groente: "🥦", vlees: "🥩", vis: "🐟", zuivel: "🧀", granen: "🥣", koffie: "☕",
    diepvries: "🧊",
  };
  // Saved by the daily refresh and the AH upload (Cloudflare KV); the static files come from a local run.
  const OFFERS_SOURCES = {
    this: { api: "/api/offers", file: "offers.json" },
    next: { api: "/api/offers?week=next", file: "offers-next.json" },
  };
  const DATA_DIRS = ["data/", "../data/"];
  const WEEK_TITLE = { this: "This week's best grocery deals", next: "Next week's best grocery deals" };
  const EMPTY_TEXT = {
    this: "No offers match your filter.",
    next: "No offers for next week match yet. Stores publish next week's offers during the week; check back later.",
  };
  // Shown for next week before any store has published it.
  const NO_OFFERS = Object.freeze({ generated_at: "", stores: {}, offers: [], comparisons: [], verdicts_by_store_set: {} });
  const UNIT_LABEL = { kg: "per kg", l: "per litre", stuk: "per piece" };
  const DEFAULT_MEMBER_LABEL = "with card";
  // Loyalty card names are brand names, the same in English and Dutch.
  const MEMBER_CARD_NAME = { lidl: "Lidl Plus" };
  const DEFAULT_MEMBER_CARD_NAME = "Card price";
  // Used when a saved payload predates per-store verdicts: show offers without picking a winner.
  const NO_VERDICT = { unit: null, compared: false, best: null, saving_pct: null };
  const eur = (n) => n == null ? "–" : "€" + n.toFixed(2).replace(".", ",");
  const user = window.userState;
  const state = { cat: "all", q: "", sort: "compare", week: "this", weeks: { this: null, next: null }, data: null };
  const lang = () => (user.prefs.lang === "nl" ? "nl" : "en");

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

  async function loadData() {
    const [thisWeek, nextWeek] = await Promise.all([loadWeek("this"), loadWeek("next")]);
    if (!thisWeek) throw new Error("Could not load offers.json");
    return { this: thisWeek, next: nextWeek };
  }

  const isWebUrl = (url) => typeof url === "string" && url.startsWith("https://");
  const storeOf = (offerKey) => offerKey.slice(0, offerKey.indexOf(":"));

  // Offer text in the chosen language, falling back to the store's Dutch original.
  function offerText(o, field) {
    const original = field === "note" ? o.extras && o.extras.note : o[field];
    return (lang() === "en" && o.en && o.en[field]) || original;
  }

  const productName = (c) => (lang() === "en" && c.product_en) || c.product;
  const shownPrice = (o) => (o.price != null ? o.price : o.member_price);

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function icon(name) {
    const span = el("span", "material-symbols-outlined", name);
    span.setAttribute("aria-hidden", "true");
    return span;
  }

  // ---------- stores to compare ----------
  const availableStores = (d) => Object.keys(STORE_NAMES).filter((s) => d.offers.some((o) => o.store === s));

  // The stores the person picked, among those with offers; all of them when nothing is picked.
  function chosenStores(d) {
    const available = availableStores(d);
    const picked = user.prefs.stores;
    const chosen = Array.isArray(picked) ? available.filter((s) => picked.includes(s)) : [];
    return chosen.length ? chosen : available;
  }

  function toggleStore(store) {
    const chosen = chosenStores(state.data);
    const next = chosen.includes(store) ? chosen.filter((s) => s !== store) : [...chosen, store];
    if (next.length) user.setPrefs({ stores: next }); // at least one store stays chosen
  }

  const selectAllStores = () => user.setPrefs({ stores: availableStores(state.data) });

  // "Albert Heijn" -> "AH", "Lidl" -> "Li": the letters on a store's avatar.
  function storeInitials(name) {
    const words = name.split(/\s+/);
    return words.length > 1 ? words.map((w) => w[0]).join("").toUpperCase() : name.slice(0, 2);
  }

  // Decorative: the store's name is always written next to it.
  function storeAvatar(store) {
    const avatar = el("span", "store-avatar", storeInitials(STORE_NAMES[store] || store));
    avatar.setAttribute("aria-hidden", "true");
    return avatar;
  }

  const shortDay = (isoDate) => new Date(`${isoDate}T00:00`).toLocaleDateString("en-GB",
    { weekday: "short", day: "numeric", month: "short" });

  // Next week starts on a different day per store (Dirk and Jumbo on Wednesday), so say when.
  function startText(offers) {
    const starts = offers.map((o) => o.valid_from).filter(Boolean).sort();
    return state.week === "next" && starts.length ? ` · from ${shortDay(starts[0])}` : "";
  }

  function offerCountText(d, store) {
    const offers = d.offers.filter((o) => o.store === store);
    const status = d.stores[store];
    const carriedOver = status && !status.ok;
    const count = `${offers.length} offer${offers.length === 1 ? "" : "s"}`;
    return count + (carriedOver ? " · from last import" : startText(offers));
  }

  const missingOffersText = () => (state.week === "next" ? "Not published yet" : "Not available this run");

  // Stores that failed this run and have no offers still get a (disabled) tile, so the gap is visible.
  function storeTile(d, store, isOn) {
    const isAvailable = availableStores(d).includes(store);
    const tile = el("button", `store-tile ${store}${isOn ? " on" : ""}`);
    tile.type = "button";
    tile.disabled = !isAvailable;
    tile.classList.toggle("not-yet", !isAvailable && state.week === "next");
    tile.setAttribute("aria-pressed", isOn);
    const check = icon("check_circle");
    check.classList.add("store-check");
    tile.append(storeAvatar(store), check, el("span", "store-tile-name", STORE_NAMES[store]),
      el("span", "store-tile-count", isAvailable ? offerCountText(d, store) : missingOffersText()));
    if (!isAvailable) tile.title = (d.stores[store] && d.stores[store].error) || "";
    tile.addEventListener("click", () => toggleStore(store));
    return tile;
  }

  function renderStoreTiles(d) {
    const box = document.getElementById("stores");
    const chosen = chosenStores(d);
    const shown = Object.keys(STORE_NAMES).filter((s) => d.stores[s] || availableStores(d).includes(s));
    box.textContent = "";
    for (const store of shown) box.append(storeTile(d, store, chosen.includes(store)));
    document.getElementById("stores-all").disabled = chosen.length === availableStores(d).length;
  }

  // A comparison narrowed to the chosen stores, with the verdict worked out for exactly those
  // stores by the scraper (scraper/pipeline.py verdicts_by_store_set).
  function forChosenStores(c, chosen, verdicts, isAllStores) {
    const offerIds = c.offer_ids.filter((k) => chosen.has(storeOf(k)));
    if (!offerIds.length) return null;
    const verdict = (verdicts && verdicts[c.product]) || (isAllStores ? c : NO_VERDICT);
    return {
      ...c,
      offer_ids: offerIds,
      stores: c.stores.filter((s) => chosen.has(s)),
      unit: verdict.unit, compared: verdict.compared, best: verdict.best, saving_pct: verdict.saving_pct,
    };
  }

  // ---------- status ----------
  // Per-store offer counts are on the store tiles; this clears "Loading…" and dates the data.
  function renderStatus(d) {
    document.getElementById("status").textContent = "";
    if (!d.generated_at) return; // next week, before any store published it
    const when = new Date(d.generated_at);
    document.getElementById("updated").textContent =
      "Last updated " + when.toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short" }) + ".";
  }

  function discountPct(o) {
    const now = Math.min(...[o.price, o.member_price].filter((x) => x != null));
    if (!o.old_price || !isFinite(now)) return 0;
    return Math.round((1 - now / o.old_price) * 100);
  }

  // ---------- offer rows ----------
  function listButton(o) {
    const isListed = user.hasItem(o.key);
    const name = offerText(o, "name");
    const button = el("button", "icon-btn add" + (isListed ? " on" : ""));
    button.type = "button";
    button.setAttribute("aria-pressed", isListed);
    button.title = isListed ? "On your grocery list (click to remove)" : "Add to grocery list";
    button.setAttribute("aria-label", `${button.title}: ${name}`);
    button.append(icon(isListed ? "playlist_add_check" : "add_shopping_cart"));
    button.addEventListener("click", () => {
      if (user.hasItem(o.key)) { user.removeItem(o.key); return; }
      user.addItem({
        id: o.key, text: name, store: o.store, price: shownPrice(o),
        detail: offerText(o, "quantity_text") || undefined,
      });
    });
    return button;
  }

  function row(o, isBest) {
    const li = el("li", `row ${o.store}` + (isBest ? " best" : ""));
    const offerName = offerText(o, "name");

    const img = el("img", "thumb");
    img.loading = "lazy";
    img.alt = offerName;
    img.referrerPolicy = "no-referrer";
    const placeholder = () => {
      const ph = el("div", "thumb ph", CATEGORY_ICON[o.category] || "🛒");
      ph.setAttribute("aria-hidden", "true");
      img.replaceWith(ph);
    };
    img.addEventListener("error", placeholder);
    li.append(img);
    if (isWebUrl(o.image)) img.src = o.image; else placeholder();

    const meta = el("div", "meta");
    const storeLabel = el("div", "store " + o.store);
    storeLabel.append(storeAvatar(o.store), STORE_NAMES[o.store] || o.store);
    meta.append(storeLabel);
    const hasLink = isWebUrl(o.url);
    const name = el(hasLink ? "a" : "span", "name", offerName);
    if (hasLink) { name.href = o.url; name.target = "_blank"; name.rel = "noopener"; }
    name.title = o.name;
    meta.append(name);
    const details = [offerText(o, "quantity_text"), offerText(o, "note")].filter(Boolean).join(" · ");
    if (details) meta.append(el("div", "small", details));
    const badges = el("div", "badges");
    if (isBest) badges.append(el("span", "badge best", "Best deal"));
    if (o.member_price != null) {
      badges.append(el("span", "badge member", MEMBER_CARD_NAME[o.store] || DEFAULT_MEMBER_CARD_NAME));
    }
    if (o.deal_text) badges.append(el("span", "badge", offerText(o, "deal_text")));
    if (badges.childElementCount) meta.append(badges);
    li.append(meta);

    const price = el("div", "price");
    const line = el("div");
    const shown = shownPrice(o);
    const memberLabel = offerText(o, "member_label");
    if (o.old_price && o.old_price > shown) line.append(el("span", "old", eur(o.old_price)));
    line.append(el("span", "now", eur(shown)));
    price.append(line);
    if (o.price != null && o.member_price != null && o.member_price < o.price) {
      price.append(el("span", "member", `${eur(o.member_price)} ${memberLabel || DEFAULT_MEMBER_LABEL}`));
    } else if (o.price == null && memberLabel) {
      price.append(el("span", "member", memberLabel));
    }
    if (o.unit_price != null) {
      price.append(el("span", "unit", `${eur(o.unit_price)} ${UNIT_LABEL[o.qty_unit] || ""}`));
    }
    li.append(price);
    li.append(listButton(o));
    return li;
  }

  // Search matches Dutch and English names, whichever language is shown.
  function searchableTexts(c, byKey) {
    const offers = c.offer_ids.map((k) => byKey[k]).filter(Boolean);
    return [c.product, c.product_en, ...offers.flatMap((o) => [o.name, o.en && o.en.name])]
      .filter(Boolean)
      .map((s) => s.toLowerCase());
  }

  function comparisonTag(c) {
    if (c.stores.length === 1) return `Only at ${STORE_NAMES[c.stores[0]]}`;
    if (!c.compared) return "Can't compare: price missing";
    return c.saving_pct ? `${STORE_NAMES[c.best.store]} ${c.saving_pct}% cheaper` : "Same price";
  }

  function visibleComparisons(d, byKey) {
    const chosen = chosenStores(d);
    const verdicts = (d.verdicts_by_store_set || {})[[...chosen].sort().join(",")];
    const isAllStores = chosen.length === availableStores(d).length;
    const chosenSet = new Set(chosen);
    const q = state.q.trim().toLowerCase();
    return d.comparisons
      .map((c) => forChosenStores(c, chosenSet, verdicts, isAllStores))
      .filter((c) => c && (state.cat === "all" || c.category === state.cat))
      .filter((c) => !q || searchableTexts(c, byKey).some((s) => s.includes(q)));
  }

  function sortRows(rows, byKey) {
    const maxDisc = (c) => Math.max(0, ...c.offer_ids.map((k) => discountPct(byKey[k])));
    if (state.sort === "compare") rows.sort((a, b) => b.stores.length - a.stores.length);
    if (state.sort === "name") rows.sort((a, b) => productName(a).localeCompare(productName(b), lang()));
    if (state.sort === "saving") rows.sort((a, b) => maxDisc(b) - maxDisc(a));
    return rows;
  }

  function render() {
    const d = state.data;
    const byKey = Object.fromEntries(d.offers.map((o) => [o.key, o]));
    const list = document.getElementById("list");
    const tpl = document.getElementById("card-tpl");
    const rows = sortRows(visibleComparisons(d, byKey), byKey);

    renderStoreTiles(d);
    list.textContent = "";
    for (const c of rows) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector("h2").textContent = productName(c);
      node.querySelector(".tag").textContent = comparisonTag(c);
      const ul = node.querySelector(".rows");
      for (const k of c.offer_ids) {
        const o = byKey[k];
        if (!o) continue;
        ul.append(row(o, c.compared && `${c.best.store}:${c.best.id}` === k));
      }
      list.append(node);
    }
    const empty = document.getElementById("empty");
    empty.textContent = EMPTY_TEXT[state.week];
    empty.hidden = rows.length > 0;
  }

  function markSelected(group, chosen) {
    group.querySelectorAll("button").forEach((b) => {
      b.classList.toggle("on", b === chosen);
      b.setAttribute("aria-selected", b === chosen);
    });
  }

  function bindSegment(id, onPick) {
    const group = document.getElementById(id);
    group.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      markSelected(group, b);
      onPick(b);
      render();
    }));
  }

  function showLanguage() {
    const langGroup = document.getElementById("lang");
    markSelected(langGroup, langGroup.querySelector(`[data-lang="${lang()}"]`));
  }

  function showWeek(week) {
    state.week = week;
    state.data = state.weeks[week] || NO_OFFERS;
    document.getElementById("hero-title").textContent = WEEK_TITLE[week];
    renderStatus(state.data);
  }

  function bind() {
    bindSegment("week", (b) => showWeek(b.dataset.week));
    bindSegment("cat", (b) => { state.cat = b.dataset.cat; });
    bindSegment("lang", (b) => { user.setPrefs({ lang: b.dataset.lang }); });
    showLanguage();
    document.getElementById("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
    document.getElementById("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
    document.getElementById("stores-all").addEventListener("click", selectAllStores);
    // Signing in, picking stores or changing the list all change what the cards show.
    user.subscribe(() => { showLanguage(); render(); });
  }

  // Shared with upload.js: it reads both weeks' offers and sends back an updated week.
  function showData(weeks) {
    state.weeks = weeks;
    showWeek(state.week);
    render();
    document.dispatchEvent(new CustomEvent("offers-shown", { detail: weeks }));
  }

  document.addEventListener("offers-uploaded", (e) => showData({ ...state.weeks, [e.detail.week]: e.detail.offers }));
  // iOS Safari only applies :active (the tiles' press feedback) once a page listens for touches.
  document.addEventListener("touchstart", () => {}, { passive: true });

  loadData()
    .then((d) => { bind(); showData(d); })
    .catch((e) => {
      document.getElementById("status").textContent =
        "No offers yet: the daily update hasn't run. (" + e.message + ")";
    });
})();
