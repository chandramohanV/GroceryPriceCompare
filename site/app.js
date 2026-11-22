(() => {
  "use strict";

  const STORE_NAMES = { ah: "Albert Heijn", lidl: "Lidl", aldi: "Aldi" };
  // Category codes come from scraper/match.py (CATEGORIES).
  const CATEGORY_ICON = {
    fruit: "🍎", groente: "🥦", vlees: "🥩", vis: "🐟", zuivel: "🧀", granen: "🥣", koffie: "☕",
  };
  const UPLOADED_OFFERS_URL = "/api/offers";
  const STATIC_OFFERS_URLS = ["data/offers.json", "../data/offers.json"];
  const UNIT_LABEL = { kg: "per kg", l: "per litre", stuk: "per piece" };
  const DEFAULT_MEMBER_LABEL = "with card";
  const LANG_STORAGE_KEY = "lang";
  const eur = (n) => n == null ? "–" : "€" + n.toFixed(2).replace(".", ",");
  const state = { cat: "all", q: "", sort: "compare", lang: readSavedLang(), data: null };

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

  // The language choice is a per-viewer convenience; storage can be blocked
  // (private windows), in which case we simply default to English.
  function readSavedLang() {
    try { return localStorage.getItem(LANG_STORAGE_KEY) === "nl" ? "nl" : "en"; } catch (_) { return "en"; }
  }

  function saveLang(lang) {
    try { localStorage.setItem(LANG_STORAGE_KEY, lang); } catch (_) { /* choice just isn't remembered */ }
  }

  // Offer text in the chosen language, falling back to the store's Dutch original.
  function offerText(o, field) {
    const original = field === "note" ? o.extras && o.extras.note : o[field];
    return (state.lang === "en" && o.en && o.en[field]) || original;
  }

  const productName = (c) => (state.lang === "en" && c.product_en) || c.product;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function storeStatusText(s) {
    if (s.ok) return `${s.name}: ${s.matched} offers`;
    if (s.carried_over) return `${s.name}: ${s.carried_over} offers (from your last import)`;
    return `${s.name}: not available this run`;
  }

  function renderStatus(d) {
    const box = document.getElementById("status");
    box.textContent = "";
    for (const [key, s] of Object.entries(d.stores)) {
      const hasOffers = s.ok || s.carried_over > 0;
      const chip = el("span", "chip" + (hasOffers ? "" : " bad"));
      chip.append(el("span", "dot"));
      chip.append(storeStatusText(s));
      if (!s.ok) chip.title = s.error || "";
      box.append(chip);
    }
    const when = new Date(d.generated_at);
    document.getElementById("updated").textContent =
      "Last updated " + when.toLocaleString("en-GB", { dateStyle: "full", timeStyle: "short" }) + ".";
  }

  function discountPct(o) {
    const now = Math.min(...[o.price, o.member_price].filter((x) => x != null));
    if (!o.old_price || !isFinite(now)) return 0;
    return Math.round((1 - now / o.old_price) * 100);
  }

  function row(o, isBest, unit) {
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
    const shown = o.price != null ? o.price : o.member_price;
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

  function render() {
    const d = state.data;
    const byKey = Object.fromEntries(d.offers.map((o) => [o.key, o]));
    const list = document.getElementById("list");
    const tpl = document.getElementById("card-tpl");
    const q = state.q.trim().toLowerCase();

    let rows = d.comparisons.filter((c) => {
      if (state.cat !== "all" && c.category !== state.cat) return false;
      return !q || searchableTexts(c, byKey).some((s) => s.includes(q));
    });

    const maxDisc = (c) => Math.max(0, ...c.offer_ids.map((k) => discountPct(byKey[k])));
    if (state.sort === "name") rows.sort((a, b) => productName(a).localeCompare(productName(b), state.lang));
    if (state.sort === "saving") rows.sort((a, b) => maxDisc(b) - maxDisc(a));

    list.textContent = "";
    for (const c of rows) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector("h2").textContent = productName(c);
      node.querySelector(".tag").textContent = comparisonTag(c);
      const ul = node.querySelector(".rows");
      for (const k of c.offer_ids) {
        const o = byKey[k];
        if (!o) continue;
        const isBest = c.compared && `${c.best.store}:${c.best.id}` === k;
        ul.append(row(o, isBest, c.unit));
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

  function bind() {
    bindSegment("cat", (b) => { state.cat = b.dataset.cat; });
    bindSegment("lang", (b) => { state.lang = b.dataset.lang; saveLang(state.lang); });
    const langGroup = document.getElementById("lang");
    markSelected(langGroup, langGroup.querySelector(`[data-lang="${state.lang}"]`));
    document.getElementById("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
    document.getElementById("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
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
