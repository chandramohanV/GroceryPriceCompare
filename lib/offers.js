// Shape checks for the offers documents functions/api/offers.js saves, so a bad upload can't
// break the site for everyone.

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/** The offers.json the site renders (see scraper/pipeline.py build_payload). */
export function isOffersPayload(payload) {
  return isObject(payload)
    && typeof payload.generated_at === "string"
    && isObject(payload.stores)
    && Array.isArray(payload.offers)
    && Array.isArray(payload.comparisons);
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
