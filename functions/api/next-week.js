// Cloudflare Pages Function at /api/next-week (legacy, Nov 2026): next week's AH offers as they
// were held before next week got its own offers set (/api/offers?week=next).
//
// GET    returns the held document (404 once there is none).
// DELETE drops it; needs "Authorization: Bearer <UPLOAD_PASSWORD>".
// The daily refresh (scraper/publish.py) moves a held document into next week's set and deletes it
// here. Remove this file and LEGACY_HELD_PATH in publish.py once GET answers 404.
//
// Bindings (see wrangler.toml): OFFERS is a KV namespace, UPLOAD_PASSWORD a secret.
import { hasUploadPassword, reply } from "../../lib/password.js";

const HELD_KEY = "next-week";

export async function onRequestGet({ env }) {
  const saved = await env.OFFERS.get(HELD_KEY);
  if (!saved) return reply(404, "No offers held for next week");
  return new Response(saved, {
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function onRequestDelete({ request, env }) {
  if (!(await hasUploadPassword(request, env))) return reply(401, "Wrong password");
  await env.OFFERS.delete(HELD_KEY);
  return reply(200, "Dropped");
}
