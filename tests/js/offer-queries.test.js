// Tests for lib/offer-queries.js (the MCP server's answers), run with `npm test`.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import {
  QueryError, bestDeals, compareProduct, describeOffer, listProducts, overview, resolveCategory, resolveStores,
  searchOffers,
} from "../../lib/offer-queries.js";
import { PAYLOAD } from "./offers-fixture.js";

const LIMIT = 20;

describe("resolveStores", () => {
  test("accepts keys and names in any case", () => assert.deepEqual(resolveStores(PAYLOAD, ["LIDL", "albert heijn"]), ["lidl", "ah"]));
  test("names the valid stores for an unknown one", () => {
    assert.throws(() => resolveStores(PAYLOAD, ["Jumbo"]), (e) => e instanceof QueryError && e.message.includes("Lidl (lidl)"));
  });
});

describe("resolveCategory", () => {
  test("accepts the code, the English name or its first word", () => {
    assert.deepEqual(["zuivel", "Dairy & eggs", "dairy"].map(resolveCategory), ["zuivel", "zuivel", "zuivel"]);
  });
  test("rejects an unknown category", () => assert.throws(() => resolveCategory("Bakery"), QueryError));
});

describe("describeOffer", () => {
  test("gives English names with the Dutch original and drops empty fields", () => {
    assert.deepEqual(describeOffer(PAYLOAD, PAYLOAD.offers[0]), {
      store: "Lidl", name: "Gouda cheese", name_nl: "Goudse kaas", product: "Cheese", category: "Dairy & eggs",
      quantity: "400 g", price: 5, member_price: 4, member_label: "with Lidl Plus", effective_price: 4,
      unit_price: 10, unit: "per kg", valid_from: "2026-11-23", valid_to: "2026-11-29", url: "https://store.invalid/p",
    });
  });
  test("keeps the old price only when it is higher", () => assert.equal(describeOffer(PAYLOAD, PAYLOAD.offers[1]).old_price, 5));
});

describe("overview", () => {
  const result = overview(PAYLOAD);
  test("counts offers per store and flags a store that wasn't refreshed", () => {
    assert.deepEqual(result.stores.map((s) => [s.name, s.offers, s.status.startsWith("fresh")]),
      [["Lidl", 1, true], ["Aldi", 2, true], ["Albert Heijn", 1, false]]);
  });
  test("lists only categories with offers", () => {
    assert.deepEqual(result.categories, [{ name: "Fruit", offers: 1 }, { name: "Dairy & eggs", offers: 3 }]);
  });
  test("counts the products and how many compare", () => assert.deepEqual([result.products, result.products_compared], [2, 1]));
  test("gives each store its usual offer week, ignoring an offer that runs for months", () => {
    const longRunning = { ...PAYLOAD.offers[1], key: "aldi:9", valid_from: "2026-01-07", valid_to: "2026-12-22" };
    const aldi = overview({ ...PAYLOAD, offers: [...PAYLOAD.offers, longRunning] }).stores.find((s) => s.key === "aldi");
    assert.deepEqual([aldi.valid_from, aldi.valid_to], ["2026-11-23", "2026-11-29"]);
  });
});

describe("listProducts", () => {
  test("lists every product with its best store", () => {
    assert.deepEqual(listProducts(PAYLOAD)[0], {
      product: "Cheese", product_nl: "Kaas", category: "Dairy & eggs", stores: ["Albert Heijn", "Aldi", "Lidl"],
      compared: true, best_store: "Aldi", best_unit_price: 8, unit: "per kg", saving_pct: 20,
    });
  });
  test("filters by category and store", () => {
    assert.deepEqual(listProducts(PAYLOAD, { category: "fruit" }).map((p) => p.product), ["Apples"]);
    assert.deepEqual(listProducts(PAYLOAD, { store: "lidl" }).map((p) => p.product), ["Cheese"]);
  });
});

describe("searchOffers", () => {
  test("matches English or Dutch words, cheapest per unit first, unpriced last", () => {
    const result = searchOffers(PAYLOAD, { query: "cheese", limit: LIMIT });
    assert.deepEqual(result.offers.map((o) => o.store), ["Aldi", "Lidl", "Albert Heijn"]);
    assert.equal(searchOffers(PAYLOAD, { query: "kaas", limit: LIMIT }).total, 3);
  });
  test("needs every word to match", () => assert.equal(searchOffers(PAYLOAD, { query: "gouda slices", limit: LIMIT }).total, 0));
  test("an empty query lists a store's offers", () => {
    assert.deepEqual(searchOffers(PAYLOAD, { store: "Aldi", limit: LIMIT }).offers.map((o) => o.name), ["Elstar apples", "Cheese slices"]);
  });
  test("reports the total even when the limit cuts the list", () => {
    const result = searchOffers(PAYLOAD, { query: "", limit: 1 });
    assert.deepEqual([result.total, result.offers.length], [4, 1]);
  });
});

describe("compareProduct", () => {
  test("puts every store's offer side by side with the best store", () => {
    const result = compareProduct(PAYLOAD, { product: "kaas" });
    assert.deepEqual([result.product, result.best_store, result.saving_pct], ["Cheese", "Aldi", 20]);
    assert.deepEqual(result.offers.map((o) => o.store), ["Aldi", "Lidl", "Albert Heijn"]);
  });
  test("judges only the given stores", () => {
    const result = compareProduct(PAYLOAD, { product: "Cheese", stores: ["Lidl", "ah"] });
    assert.deepEqual([result.best_store, result.compared, result.offers.length], ["Lidl", false, 2]);
  });
  test("accepts part of a name when only one product matches", () => {
    assert.equal(compareProduct(PAYLOAD, { product: "apple" }).product, "Apples");
  });
  test("lists the products when nothing matches", () => {
    assert.throws(() => compareProduct(PAYLOAD, { product: "Milk" }), (e) => e instanceof QueryError && e.message.includes("Cheese, Apples"));
  });
});

describe("bestDeals", () => {
  test("lists only compared products with a saving", () => {
    assert.deepEqual(bestDeals(PAYLOAD, { limit: LIMIT }), [{
      product: "Cheese", category: "Dairy & eggs", compared: true, best_store: "Aldi", best_unit_price: 8, unit: "per kg", saving_pct: 20,
    }]);
  });
  test("weighs only the given stores", () => {
    assert.deepEqual(bestDeals(PAYLOAD, { stores: ["Lidl", "Albert Heijn"], limit: LIMIT }), []);
    assert.equal(bestDeals(PAYLOAD, { stores: ["Aldi", "Lidl"], limit: LIMIT }).length, 1);
  });
  test("filters by category", () => assert.deepEqual(bestDeals(PAYLOAD, { category: "Fruit", limit: LIMIT }), []));
});
