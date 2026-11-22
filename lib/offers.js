// Shape checks for the offer documents the Pages Functions save (functions/api/offers.js and
// next-week.js), so a bad upload can't break the site for everyone.

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isIsoDate = (value) => typeof value === "string" && ISO_DATE_RE.test(value);

/** The offers.json the site renders (see scraper/pipeline.py build_payload). */
export function isOffersPayload(payload) {
  return isObject(payload)
    && typeof payload.generated_at === "string"
    && isObject(payload.stores)
    && Array.isArray(payload.offers)
    && Array.isArray(payload.comparisons);
}

/** Offers uploaded ahead of their week (see scraper/held.py hold). */
export function isHeldOffers(held) {
  return isObject(held)
    && typeof held.store === "string" && typeof held.label === "string"
    && isIsoDate(held.valid_from) && isIsoDate(held.valid_to) && held.valid_from <= held.valid_to
    && Array.isArray(held.offers) && held.offers.length > 0;
}

/** The upload as { ok, document, body (the raw text to store) } or { ok: false, status, message }. */
export async function readUpload(request, isValid, expected) {
  const body = await request.text();
  if (body.length > MAX_UPLOAD_BYTES) return { ok: false, status: 413, message: "Upload is too large" };
  let document;
  try {
    document = JSON.parse(body);
  } catch (_) {
    return { ok: false, status: 400, message: "Upload is not valid JSON" };
  }
  if (!isValid(document)) return { ok: false, status: 400, message: `Upload is not ${expected}` };
  return { ok: true, document, body };
}
