(() => {
  "use strict";

  const STORE_NAMES = { ah: "Albert Heijn", lidl: "Lidl" };
  const UNIT_LABEL = { kg: "per kg", l: "per liter", stuk: "per stuk" };
  const eur = (n) => n == null ? "–" : "€" + n.toFixed(2).replace(".", ",");
  const state = { cat: "all", q: "", sort: "compare", data: null };

  // Works both on GitHub Pages (data/ next to index.html) and locally (../data/)
  async function loadData() {
    for (const url of ["data/offers.json", "../data/offers.json"]) {
      try {
        const r = await fetch(url, { cache: "no-store" });
        if (r.ok) return r.json();
      } catch (_) { /* try next */ }
    }
    throw new Error("Could not load offers.json");
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function renderStatus(d) {
    const box = document.getElementById("status");
    box.textContent = "";
    for (const [key, s] of Object.entries(d.stores)) {
      const chip = el("span", "chip" + (s.ok ? "" : " bad"));
      chip.append(el("span", "dot"));
      chip.append(s.ok
        ? `${s.name}: ${s.produce} fruit & veg offers`
        : `${s.name}: not available this run`);
      if (!s.ok) chip.title = s.error || "";
      box.append(chip);
    }
    const when = new Date(d.generated_at);
    document.getElementById("updated").textContent =
      "Last updated " + when.toLocaleString("nl-NL", { dateStyle: "full", timeStyle: "short" }) + ".";
  }

  function discountPct(o) {
    const now = Math.min(...[o.price, o.member_price].filter((x) => x != null));
    if (!o.old_price || !isFinite(now)) return 0;
    return Math.round((1 - now / o.old_price) * 100);
  }

  function row(o, isBest, unit) {
    const li = el("li", "row" + (isBest ? " best" : ""));

    const img = el("img", "thumb");
    img.loading = "lazy";
    img.alt = o.name;
    img.referrerPolicy = "no-referrer";
    const placeholder = () => {
      const ph = el("div", "thumb ph", o.category === "fruit" ? "🍎" : "🥦");
      ph.setAttribute("aria-hidden", "true");
      img.replaceWith(ph);
    };
    img.addEventListener("error", placeholder);
    li.append(img);
    if (o.image) img.src = o.image; else placeholder();

    const meta = el("div", "meta");
    meta.append(el("div", "store " + o.store, STORE_NAMES[o.store] || o.store));
    const name = el(o.url ? "a" : "span", "name", o.name);
    if (o.url) { name.href = o.url; name.target = "_blank"; name.rel = "noopener"; }
    name.title = o.name;
    meta.append(name);
    const details = [o.quantity_text, o.extras && o.extras.note].filter(Boolean).join(" · ");
    if (details) meta.append(el("div", "small", details));
    const badges = el("div", "badges");
    if (isBest) badges.append(el("span", "badge best", "Best deal"));
    if (o.deal_text) badges.append(el("span", "badge", o.deal_text));
    if (badges.childElementCount) meta.append(badges);
    li.append(meta);

    const price = el("div", "price");
    const line = el("div");
    const shown = o.price != null ? o.price : o.member_price;
    if (o.old_price && o.old_price > shown) line.append(el("span", "old", eur(o.old_price)));
    line.append(el("span", "now", eur(shown)));
    price.append(line);
    if (o.price != null && o.member_price != null && o.member_price < o.price) {
      price.append(el("span", "member", `${eur(o.member_price)} ${o.member_label || "met kaart"}`));
    } else if (o.price == null && o.member_label) {
      price.append(el("span", "member", o.member_label));
    }
    if (o.unit_price != null) {
      price.append(el("span", "unit", `${eur(o.unit_price)} ${UNIT_LABEL[o.qty_unit] || ""}`));
    }
    li.append(price);
    return li;
  }

  function render() {
    const d = state.data;
    const byKey = Object.fromEntries(d.offers.map((o) => [o.key, o]));
    const list = document.getElementById("list");
    const tpl = document.getElementById("card-tpl");
    const q = state.q.trim().toLowerCase();

    let rows = d.comparisons.filter((c) => {
      if (state.cat !== "all" && c.category !== state.cat) return false;
      if (!q) return true;
      if (c.product.toLowerCase().includes(q)) return true;
      return c.offer_ids.some((k) => byKey[k] && byKey[k].name.toLowerCase().includes(q));
    });

    const maxDisc = (c) => Math.max(0, ...c.offer_ids.map((k) => discountPct(byKey[k])));
    if (state.sort === "name") rows.sort((a, b) => a.product.localeCompare(b.product, "nl"));
    if (state.sort === "saving") rows.sort((a, b) => maxDisc(b) - maxDisc(a));

    list.textContent = "";
    for (const c of rows) {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector("h2").textContent = c.product;
      const tag = node.querySelector(".tag");
      tag.textContent = c.stores.length > 1
        ? (c.saving_pct ? `${STORE_NAMES[c.best.store]} ${c.saving_pct}% cheaper` : "Compared")
        : `Only at ${STORE_NAMES[c.stores[0]]}`;
      const ul = node.querySelector(".rows");
      for (const k of c.offer_ids) {
        const o = byKey[k];
        if (!o) continue;
        const isBest = c.stores.length > 1 && c.best && `${c.best.store}:${c.best.id}` === k;
        ul.append(row(o, isBest, c.unit));
      }
      list.append(node);
    }
    document.getElementById("empty").hidden = rows.length > 0;
  }

  function bind() {
    document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(".seg button").forEach((x) => {
        x.classList.toggle("on", x === b);
        x.setAttribute("aria-selected", x === b);
      });
      state.cat = b.dataset.cat;
      render();
    }));
    document.getElementById("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
    document.getElementById("sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  }

  loadData()
    .then((d) => { state.data = d; renderStatus(d); bind(); render(); })
    .catch((e) => {
      document.getElementById("status").textContent =
        "No offers yet: the daily update hasn't run. (" + e.message + ")";
    });
})();
