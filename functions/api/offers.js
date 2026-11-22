// Cloudflare Pages Function at /api/offers.
//
// GET  returns the saved offers.json (404 if nothing is saved yet).
// POST replaces it; needs "Authorization: Bearer <UPLOAD_PASSWORD>". Called by
//      the site's AH upload form and by the daily refresh (scraper/publish.py).
//
// Bindings (see wrangler.toml): OFFERS is a KV namespace, UPLOAD_PASSWORD a secret.
import { isOffersPayload, readUpload } from "../../lib/offers.js";
import { hasUploadPassword, reply } from "../../lib/password.js";

const OFFERS_KEY = "offers";

export async function onRequestGet({ env }) {
  const saved = await env.OFFERS.get(OFFERS_KEY);
  if (!saved) return reply(404, "No saved offers yet");
  return new Response(saved, {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function onRequestPost({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  const upload = await readUpload(request, isOffersPayload, "an offers.json document");
  if (!upload.ok) return reply(upload.status, upload.message);
  await env.OFFERS.put(OFFERS_KEY, upload.body);
  return reply(200, "Saved");
}
