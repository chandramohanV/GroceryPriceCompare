// Tests for lib/offers.js (upload shape checks), run with `npm test`.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { MAX_UPLOAD_BYTES, isHeldOffers, isOffersPayload, readUpload } from "../../lib/offers.js";

const HELD = Object.freeze({
  store: "ah", label: "Albert Heijn", valid_from: "2026-11-23", valid_to: "2026-11-29",
  saved_at: "2026-11-20T09:00:00+00:00", scraped: 1, matched: 1,
  offers: [{ store: "ah", id: "wi1", name: "AH Witlof" }],
});
const PAYLOAD = Object.freeze({ generated_at: "2026-11-22T05:00:00+00:00", stores: {}, offers: [], comparisons: [] });

const uploadOf = (text) => new Request("https://site.invalid/api/next-week", { method: "POST", body: text });

describe("isOffersPayload", () => {
  test("accepts the payload the pipeline builds", () => assert.equal(isOffersPayload(PAYLOAD), true));
  test("rejects a missing offers list", () => assert.equal(isOffersPayload({ ...PAYLOAD, offers: null }), false));
  test("rejects stores given as a list", () => assert.equal(isOffersPayload({ ...PAYLOAD, stores: [] }), false));
});

describe("isHeldOffers", () => {
  test("accepts a held week", () => assert.equal(isHeldOffers(HELD), true));
  test("rejects no offers", () => assert.equal(isHeldOffers({ ...HELD, offers: [] }), false));
  test("rejects a date that isn't ISO", () => assert.equal(isHeldOffers({ ...HELD, valid_from: "23-11-2026" }), false));
  test("rejects a week ending before it starts", () => {
    assert.equal(isHeldOffers({ ...HELD, valid_to: "2026-11-22" }), false);
  });
  test("rejects a missing store", () => assert.equal(isHeldOffers({ ...HELD, store: undefined }), false));
  test("rejects null", () => assert.equal(isHeldOffers(null), false));
});

describe("readUpload", () => {
  test("returns the document and its raw text", async () => {
    const text = JSON.stringify(HELD);
    const result = await readUpload(uploadOf(text), isHeldOffers, "held offers");
    assert.deepEqual(result, { ok: true, document: HELD, body: text });
  });
  test("rejects invalid JSON", async () => {
    const result = await readUpload(uploadOf("{"), isHeldOffers, "held offers");
    assert.deepEqual(result, { ok: false, status: 400, message: "Upload is not valid JSON" });
  });
  test("rejects the wrong shape and names what was expected", async () => {
    const result = await readUpload(uploadOf(JSON.stringify(PAYLOAD)), isHeldOffers, "held offers");
    assert.deepEqual(result, { ok: false, status: 400, message: "Upload is not held offers" });
  });
  test("rejects uploads over the size limit", async () => {
    const result = await readUpload(uploadOf("x".repeat(MAX_UPLOAD_BYTES + 1)), isHeldOffers, "held offers");
    assert.equal(result.status, 413);
  });
});
