// Tests for lib/offers.js (upload shape checks), run with `npm test`.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { MAX_UPLOAD_BYTES, isOffersPayload, readUpload } from "../../lib/offers.js";

const PAYLOAD = Object.freeze({ generated_at: "2026-11-22T05:00:00+00:00", stores: {}, offers: [], comparisons: [] });

const uploadOf = (text) => new Request("https://site.invalid/api/offers", { method: "POST", body: text });

describe("isOffersPayload", () => {
  test("accepts the payload the pipeline builds", () => assert.equal(isOffersPayload(PAYLOAD), true));
  test("rejects a missing offers list", () => assert.equal(isOffersPayload({ ...PAYLOAD, offers: null }), false));
  test("rejects stores given as a list", () => assert.equal(isOffersPayload({ ...PAYLOAD, stores: [] }), false));
});

describe("readUpload", () => {
  test("returns the document and its raw text", async () => {
    const text = JSON.stringify(PAYLOAD);
    const result = await readUpload(uploadOf(text), isOffersPayload, "an offers.json document");
    assert.deepEqual(result, { ok: true, document: PAYLOAD, body: text });
  });
  test("rejects invalid JSON", async () => {
    const result = await readUpload(uploadOf("{"), isOffersPayload, "an offers.json document");
    assert.deepEqual(result, { ok: false, status: 400, message: "Upload is not valid JSON" });
  });
  test("rejects the wrong shape and names what was expected", async () => {
    const result = await readUpload(uploadOf(JSON.stringify({ offers: [] })), isOffersPayload, "an offers.json document");
    assert.deepEqual(result, { ok: false, status: 400, message: "Upload is not an offers.json document" });
  });
  test("rejects uploads over the size limit", async () => {
    const result = await readUpload(uploadOf("x".repeat(MAX_UPLOAD_BYTES + 1)), isOffersPayload, "an offers.json document");
    assert.equal(result.status, 413);
  });
});
