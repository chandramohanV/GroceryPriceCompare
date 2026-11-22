// Cloudflare Pages Function at /api/next-week: next week's AH offers, uploaded ahead.
//
// GET    returns the held offers (404 if none are held).
// POST   holds new ones, replacing any held before; needs "Authorization: Bearer <UPLOAD_PASSWORD>".
// DELETE drops them; same password. The daily refresh (scraper/publish.py) swaps them into
//        /api/offers on the first morning of their week, then deletes them here.
//
// Bindings (see wrangler.toml): OFFERS is a KV namespace, UPLOAD_PASSWORD a secret.
import { isHeldOffers, readUpload } from "../../lib/offers.js";
import { hasUploadPassword, reply } from "../../lib/password.js";

const HELD_KEY = "next-week";

export async function onRequestGet({ env }) {
  const saved = await env.OFFERS.get(HELD_KEY);
  if (!saved) return reply(404, "No offers held for next week");
  return new Response(saved, {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function onRequestPost({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  const upload = await readUpload(request, isHeldOffers, "a next-week offers document");
  if (!upload.ok) return reply(upload.status, upload.message);
  await env.OFFERS.put(HELD_KEY, upload.body);
  return reply(200, "Held for next week");
}

export async function onRequestDelete({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  await env.OFFERS.delete(HELD_KEY);
  return reply(200, "Dropped");
}
