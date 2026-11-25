// Answers questions about one week's offers document (offers.json, built by scraper/pipeline.py) for the MCP server.

// Category codes from scraper/match.py (CATEGORIES), named as on the site's filter chips.
export const CATEGORY_NAMES = Object.freeze({
  fruit: "Fruit", groente: "Vegetables", vlees: "Meat", vis: "Fish", zuivel: "Dairy & eggs",
  granen: "Cereals", koffie: "Coffee", diepvries: "Frozen",
});
const UNIT_LABEL = Object.freeze({ kg: "per kg", l: "per litre", stuk: "per piece" });

/** Thrown for a question the data can't answer (unknown store, product or category); its message is for the user. */
export class QueryError extends Error {}

const lower = (text) => String(text ?? "").toLowerCase();
const withoutEmpty = (object) => Object.fromEntries(
  Object.entries(object).filter(([, value]) => value !== null && value !== undefined && value !== ""));

function storeName(payload, store) {
  return payload.stores[store]?.name ?? store;
}

/** Store keys for names or keys such as "Albert Heijn", "ah" or "lidl"; throws listing the valid ones. */
export function resolveStores(payload, names) {
  return names.map((name) => {
    const wanted = lower(name).trim();
    const match = Object.entries(payload.stores)
      .find(([key, info]) => key === wanted || lower(info.name) === wanted);
    if (!match) {
      const valid = Object.entries(payload.stores).map(([key, info]) => `${info.name} (${key})`).join(", ");
      throw new QueryError(`Unknown store "${name}". Stores: ${valid}.`);
    }
    return match[0];
  });
}

/** The category code for a code or English name such as "zuivel" or "Dairy & eggs". */
export function resolveCategory(name) {
  const wanted = lower(name).trim();
  const match = Object.entries(CATEGORY_NAMES)
    .find(([code, label]) => code === wanted || lower(label) === wanted || lower(label).split(" ")[0] === wanted);
  if (!match) throw new QueryError(`Unknown category "${name}". Categories: ${Object.values(CATEGORY_NAMES).join(", ")}.`);
  return match[0];
}

/** One offer in English with the Dutch original, without the fields only the site needs. */
export function describeOffer(payload, offer) {
  const en = offer.en ?? {};
  return withoutEmpty({
    store: storeName(payload, offer.store),
    name: en.name ?? offer.name,
    name_nl: en.name && en.name !== offer.name ? offer.name : null,
    product: en.product ?? offer.product,
    category: CATEGORY_NAMES[offer.category] ?? offer.category,
    quantity: en.quantity_text ?? offer.quantity_text,
    price: offer.price,
    old_price: offer.old_price > offer.price ? offer.old_price : null,
    member_price: offer.member_price,
    member_label: en.member_label ?? offer.member_label,
    deal: en.deal_text ?? offer.deal_text,
    effective_price: offer.effective_price,
    unit_price: offer.unit_price,
    unit: UNIT_LABEL[offer.qty_unit],
    valid_from: offer.valid_from,
    valid_to: offer.valid_to,
    url: offer.url,
  });
}

/** The verdict (best store, saving) for a comparison, among only the given stores when there are any. */
function verdictFor(payload, comparison, stores) {
  if (!stores.length) return comparison;
  const key = [...stores].sort().join(",");
  return payload.verdicts_by_store_set?.[key]?.[comparison.product] ?? null;
}

function describeVerdict(payload, verdict) {
  if (!verdict?.best) return { compared: false };
  return withoutEmpty({
    compared: verdict.compared,
    best_store: storeName(payload, verdict.best.store),
    best_unit_price: verdict.best.unit_price,
    unit: UNIT_LABEL[verdict.unit],
    saving_pct: verdict.saving_pct,
  });
}

function dateRange(offers) {
  const from = offers.map((o) => o.valid_from).filter(Boolean).sort();
  const to = offers.map((o) => o.valid_to).filter(Boolean).sort();
  return { valid_from: from[0] ?? null, valid_to: to[to.length - 1] ?? null };
}

/** When the offers were fetched, which stores are in, and how many offers each category has. */
export function overview(payload) {
  const countBy = (field, value) => payload.offers.filter((o) => o[field] === value).length;
  return {
    generated_at: payload.generated_at,
    currency: "EUR",
    ...dateRange(payload.offers),
    stores: Object.entries(payload.stores).map(([key, info]) => withoutEmpty({
      key, name: info.name, offers: countBy("store", key),
      status: info.ok ? "fresh" : "not refreshed (offers from the last successful fetch)",
      error: info.ok ? null : info.error,
    })),
    categories: Object.entries(CATEGORY_NAMES)
      .map(([code, name]) => ({ name, offers: countBy("category", code) }))
      .filter((c) => c.offers > 0),
    products: payload.comparisons.length,
    products_compared: payload.comparisons.filter((c) => c.compared).length,
  };
}

/** Every product on offer this week, optionally in one category or at one store. */
export function listProducts(payload, { category, store } = {}) {
  const code = category ? resolveCategory(category) : null;
  const [storeKey] = store ? resolveStores(payload, [store]) : [];
  return payload.comparisons
    .filter((c) => (!code || c.category === code) && (!storeKey || c.stores.includes(storeKey)))
    .map((c) => withoutEmpty({
      product: c.product_en ?? c.product,
      product_nl: c.product_en && c.product_en !== c.product ? c.product : null,
      category: CATEGORY_NAMES[c.category] ?? c.category,
      stores: c.stores.map((s) => storeName(payload, s)),
      ...describeVerdict(payload, c),
    }));
}

function matchesQuery(offer, words) {
  const text = lower([offer.name, offer.product, offer.en?.name, offer.en?.product].join(" "));
  return words.every((word) => text.includes(word));
}

/** Offers whose English or Dutch name contains every word of the query, cheapest per unit first. */
export function searchOffers(payload, { query = "", store, category, limit }) {
  const words = lower(query).split(/\s+/).filter(Boolean);
  const code = category ? resolveCategory(category) : null;
  const [storeKey] = store ? resolveStores(payload, [store]) : [];
  const found = payload.offers
    .filter((o) => (!storeKey || o.store === storeKey) && (!code || o.category === code) && matchesQuery(o, words))
    .sort((a, b) => (a.unit_price ?? Infinity) - (b.unit_price ?? Infinity));
  return { total: found.length, offers: found.slice(0, limit).map((o) => describeOffer(payload, o)) };
}

function findComparison(payload, product) {
  const wanted = lower(product).trim();
  const names = (c) => [lower(c.product), lower(c.product_en)];
  const exact = payload.comparisons.find((c) => names(c).includes(wanted));
  if (exact) return exact;
  const partial = payload.comparisons.filter((c) => names(c).some((name) => name.includes(wanted)));
  if (partial.length === 1) return partial[0];
  const options = (partial.length ? partial : payload.comparisons).map((c) => c.product_en ?? c.product);
  const hint = partial.length ? "Did you mean one of" : "Products on offer";
  throw new QueryError(`No single product matches "${product}". ${hint}: ${options.join(", ")}.`);
}

/** All offers for one product side by side, cheapest per unit first, with the best store. */
export function compareProduct(payload, { product, stores = [] }) {
  const comparison = findComparison(payload, product);
  const storeKeys = resolveStores(payload, stores);
  const byKey = new Map(payload.offers.map((o) => [o.key, o]));
  const offers = comparison.offer_ids
    .map((key) => byKey.get(key))
    .filter((o) => o && (!storeKeys.length || storeKeys.includes(o.store)));
  return {
    product: comparison.product_en ?? comparison.product,
    product_nl: comparison.product,
    category: CATEGORY_NAMES[comparison.category] ?? comparison.category,
    ...describeVerdict(payload, verdictFor(payload, comparison, storeKeys)),
    offers: offers.map((o) => describeOffer(payload, o)),
  };
}

/** Products where one store is clearly cheapest, biggest saving over the next store first. */
export function bestDeals(payload, { stores = [], category, limit }) {
  const storeKeys = resolveStores(payload, stores);
  const code = category ? resolveCategory(category) : null;
  return payload.comparisons
    .filter((c) => !code || c.category === code)
    .map((c) => ({ comparison: c, verdict: verdictFor(payload, c, storeKeys) }))
    .filter(({ verdict }) => verdict?.compared && verdict.saving_pct)
    .sort((a, b) => b.verdict.saving_pct - a.verdict.saving_pct)
    .slice(0, limit)
    .map(({ comparison, verdict }) => ({
      product: comparison.product_en ?? comparison.product,
      category: CATEGORY_NAMES[comparison.category] ?? comparison.category,
      ...describeVerdict(payload, verdict),
    }));
}
