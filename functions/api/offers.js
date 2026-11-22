// Cloudflare Pages Function at /api/offers: this week's offers, or next week's with ?week=next.
//
// GET  returns the saved offers.json of that week (404 if nothing is saved yet).
// POST replaces it; needs "Authorization: Bearer <UPLOAD_PASSWORD>". Called by
//      the site's AH upload form and by the daily refresh (scraper/publish.py).
//
// Bindings (see wrangler.toml): OFFERS is a KV namespace, UPLOAD_PASSWORD a secret.
import { isOffersPayload, readUpload } from "../../lib/offers.js";
import { hasUploadPassword, reply } from "../../lib/password.js";

const KEY_BY_WEEK = { this: "offers", next: "offers-next" };

/** The KV key for the request's ?week= (default this week), or null for an unknown week. */
function offersKey(request) {
  const week = new URL(request.url).searchParams.get("week") || "this";
  return Object.hasOwn(KEY_BY_WEEK, week) ? KEY_BY_WEEK[week] : null;
}

export async function onRequestGet({ request, env }) {
  const key = offersKey(request);
  if (!key) return reply(400, "week must be this or next");
  const saved = await env.OFFERS.get(key);
  if (!saved) return reply(404, "No saved offers yet");
  return new Response(saved, {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function onRequestPost({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  const key = offersKey(request);
  if (!key) return reply(400, "week must be this or next");
  const upload = await readUpload(request, isOffersPayload, "an offers.json document");
  if (!upload.ok) return reply(upload.status, upload.message);
  await env.OFFERS.put(key, upload.body);
  return reply(200, "Saved");
}
