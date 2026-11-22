(() => {
  "use strict";

  const STORE_NAMES = window.STORE_NAMES;
  // Category codes come from scraper/match.py (CATEGORIES).
  const CATEGORY_ICON = {
    fruit: "🍎", groente: "🥦", vlees: "🥩", vis: "🐟", zuivel: "🧀", granen: "🥣", koffie: "☕",
  };
  const UPLOADED_OFFERS_URL = "/api/offers";
  const STATIC_OFFERS_URLS = ["data/offers.json", "../data/offers.json"];
  const UNIT_LABEL = { kg: "per kg", l: "per litre", stuk: "per piece" };
  const DEFAULT_MEMBER_LABEL = "with card";
  // Used when a saved payload predates per-store verdicts: show offers without picking a winner.
  const NO_VERDICT = { unit: null, compared: false, best: null, saving_pct: null };
  const eur = (n) => n == null ? "–" : "€" + n.toFixed(2).replace(".", ",");
  const user = window.userState;
  const state = { cat: "all", q: "", sort: "compare", data: null };
  const lang = () => (user.prefs.lang === "nl" ? "nl" : "en");

  async function fetchJson(url) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      return r.ok ? await r.json() : null;
    } catch (_) {
      return null; /* missing here: the caller tries the next source */
    }
  }

  // Static offers.json works both when deployed (data/ next to index.html) and locally (../data/)
  async function loadStaticData() {
    for (const url of STATIC_OFFERS_URLS) {
      const data = await fetchJson(url);
      if (data) return data;
    }
    return null;
  }

  // The last AH upload lives in Cloudflare KV; the daily scrape is a static file.
  // Show whichever is newer. Locally and on GitHub Pages there is no API.
  async function loadData() {
    const [uploaded, scraped] = await Promise.all([fetchJson(UPLOADED_OFFERS_URL), loadStaticData()]);
    const candidates = [uploaded, scraped].filter(Boolean);
    if (!candidates.length) throw new Error("Could not load offers.json");
    return candidates.reduce((a, b) => (a.generated_at >= b.generated_at ? a : b));
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

  function offerCountText(d, store) {
    const count = d.offers.filter((o) => o.store === store).length;
    const status = d.stores[store];
    const carriedOver = status && !status.ok;
    return `${count} offer${count === 1 ? "" : "s"}${carriedOver ? " · from last import" : ""}`;
  }

  // Stores that failed this run and have no offers still get a (disabled) tile, so the gap is visible.
  function storeTile(d, store, isOn) {
    const isAvailable = availableStores(d).includes(store);
    const tile = el("button", `store-tile ${store}${isOn ? " on" : ""}`);
    tile.type = "button";
    tile.disabled = !isAvailable;
    tile.setAttribute("aria-pressed", isOn);
    const avatar = el("span", "store-avatar", storeInitials(STORE_NAMES[store]));
    avatar.setAttribute("aria-hidden", "true");
    const check = icon("check_circle");
    check.classList.add("store-check");
    tile.append(avatar, check, el("span", "store-tile-name", STORE_NAMES[store]),
      el("span", "store-tile-count", isAvailable ? offerCountText(d, store) : "Not available this run"));
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
    const li = el("li", "row" + (isBest ? " best" : ""));
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
    meta.append(el("div", "store " + o.store, STORE_NAMES[o.store] || o.store));
    const hasLink = isWebUrl(o.url);
    const name = el(hasLink ? "a" : "span", "name", offerName);
    if (hasLink) { name.href = o.url; name.target = "_blank"; name.rel = "noopener"; }
    name.title = o.name;
    meta.append(name);
    const details = [offerText(o, "quantity_text"), offerText(o, "note")].filter(Boolean).join(" · ");
    if (details) meta.append(el("div", "small", details));
    const badges = el("div", "badges");
    if (isBest) badges.append(el("span", "badge best", "Best deal"));
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
    document.getElementById("empty").hidden = rows.length > 0;
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

  function bind() {
    bindSegment("cat", (b) => { state.cat = b.dataset.cat; });
    bindSegment("lang", (b) => { user.setPrefs({ lang: b.dataset.lang }); });
    showLanguage();
    document.getElementById("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
    document.getElementById("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
    document.getElementById("stores-all").addEventListener("click", selectAllStores);
    // Signing in, picking stores or changing the list all change what the cards show.
    user.subscribe(() => { showLanguage(); render(); });
  }

  // Shared with upload.js: it reads the shown offers and sends back new ones.
  function showData(d) {
    state.data = d;
    renderStatus(d);
    render();
    document.dispatchEvent(new CustomEvent("offers-shown", { detail: d }));
  }

  document.addEventListener("offers-uploaded", (e) => showData(e.detail));

  loadData()
    .then((d) => { bind(); showData(d); })
    .catch((e) => {
      document.getElementById("status").textContent =
        "No offers yet: the daily update hasn't run. (" + e.message + ")";
    });
})();
