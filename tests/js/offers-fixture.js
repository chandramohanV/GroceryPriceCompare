// A small offers.json (shape as scraper/pipeline.py builds it) shared by the MCP tests.

const offer = (fields) => ({
  price: null, old_price: null, member_price: null, member_label: null, deal_text: null,
  valid_from: "2026-11-23", valid_to: "2026-11-29", url: "https://store.invalid/p", image: null, ...fields,
});

export const PAYLOAD = Object.freeze({
  generated_at: "2026-11-23T05:00:00+00:00",
  stores: {
    lidl: { name: "Lidl", ok: true, scraped: 10, matched: 2 },
    aldi: { name: "Aldi", ok: true, scraped: 10, matched: 2 },
    ah: { name: "Albert Heijn", ok: false, error: "AHBlocked: ah.nl answered HTTP 403", carried_over: 1 },
  },
  offers: [
    offer({
      key: "lidl:1", store: "lidl", id: "1", name: "Goudse kaas", category: "zuivel", product: "Kaas",
      price: 5, member_price: 4, member_label: "met Lidl Plus", quantity_text: "400 g", qty_unit: "kg",
      effective_price: 4, unit_price: 10,
      en: { name: "Gouda cheese", product: "Cheese", member_label: "with Lidl Plus", quantity_text: "400 g" },
    }),
    offer({
      key: "aldi:2", store: "aldi", id: "2", name: "Kaasplakken", category: "zuivel", product: "Kaas",
      price: 4, old_price: 5, quantity_text: "500 g", qty_unit: "kg", effective_price: 4, unit_price: 8,
      en: { name: "Cheese slices", product: "Cheese" },
    }),
    offer({
      key: "ah:3", store: "ah", id: "3", name: "AH kaas", category: "zuivel", product: "Kaas",
      deal_text: "2e halve prijs", en: { name: "AH cheese", product: "Cheese", deal_text: "2nd half price" },
    }),
    offer({
      key: "aldi:4", store: "aldi", id: "4", name: "Elstar appels", category: "fruit", product: "Appels",
      price: 2, quantity_text: "1 kg", qty_unit: "kg", effective_price: 2, unit_price: 2,
      en: { name: "Elstar apples", product: "Apples" },
    }),
  ],
  comparisons: [
    {
      product: "Kaas", product_en: "Cheese", category: "zuivel", unit: "kg", stores: ["ah", "aldi", "lidl"],
      compared: true, offer_ids: ["aldi:2", "lidl:1", "ah:3"],
      best: { store: "aldi", id: "2", unit_price: 8 }, saving_pct: 20,
    },
    {
      product: "Appels", product_en: "Apples", category: "fruit", unit: "kg", stores: ["aldi"],
      compared: false, offer_ids: ["aldi:4"], best: { store: "aldi", id: "4", unit_price: 2 }, saving_pct: null,
    },
  ],
  verdicts_by_store_set: {
    lidl: { Kaas: { unit: "kg", compared: false, best: { store: "lidl", id: "1", unit_price: 10 }, saving_pct: null } },
    "ah,lidl": { Kaas: { unit: "kg", compared: false, best: { store: "lidl", id: "1", unit_price: 10 }, saving_pct: null } },
    "aldi,lidl": { Kaas: { unit: "kg", compared: true, best: { store: "aldi", id: "2", unit_price: 8 }, saving_pct: 20 } },
  },
});
