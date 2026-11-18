// Cloudflare Pages Function at /api/offers.
//
// GET  returns the saved offers.json (404 if nothing is saved yet).
// POST replaces it; needs "Authorization: Bearer <UPLOAD_PASSWORD>". Called by
//      the site's AH upload form and by the weekly refresh (scraper/publish.py).
//
// Bindings (see wrangler.toml): OFFERS is a KV namespace, UPLOAD_PASSWORD a secret.
import { hasUploadPassword, reply } from "../../lib/password.js";

const OFFERS_KEY = "offers";
const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;

// The shape the site renders (see scraper/pipeline.py build_payload).
function isOffersPayload(payload) {
  return payload !== null && typeof payload === "object"
    && typeof payload.generated_at === "string"
    && payload.stores !== null && typeof payload.stores === "object"
    && Array.isArray(payload.offers)
    && Array.isArray(payload.comparisons);
}

export async function onRequestGet({ env }) {
  const saved = await env.OFFERS.get(OFFERS_KEY);
  if (!saved) return reply(404, "No saved offers yet");
  return new Response(saved, {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function onRequestPost({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");

  const body = await request.text();
  if (body.length > MAX_UPLOAD_BYTES) return reply(413, "Upload is too large");
  let payload;
  try {
    payload = JSON.parse(body);
  } catch (_) {
    return reply(400, "Upload is not valid JSON");
  }
  if (!isOffersPayload(payload)) return reply(400, "Upload is not an offers.json document");

  await env.OFFERS.put(OFFERS_KEY, body);
  return reply(200, "Saved");
}
