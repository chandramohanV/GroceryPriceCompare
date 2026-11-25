// Cloudflare Pages Function at /mcp: a read-only MCP server (Streamable HTTP, stateless) over this week's
// and next week's offers, so Claude (web, desktop or mobile, as a custom connector) can answer questions about them.
//
// POST one JSON-RPC message; the reply is JSON (no streaming or sessions). No login: the offers are public.
// Bindings (see wrangler.toml): OFFERS is the KV namespace functions/api/offers.js saves to; ASSETS serves data/.
import { PARSE_ERROR, errorResponse, handleMessage } from "../lib/mcp.js";

const KV_KEY_BY_WEEK = { this: "offers", next: "offers-next" };
const STATIC_FILE_BY_WEEK = { this: "/data/offers.json", next: "/data/offers-next.json" };
const MAX_REQUEST_BYTES = 64 * 1024;
const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };

function readJson(text) {
  try {
    return text ? JSON.parse(text) : null;
  } catch (_) {
    // Not JSON: Pages answers a missing data file with index.html, so this counts as missing.
    return null;
  }
}

async function staticOffers(request, env, week) {
  const response = await env.ASSETS.fetch(new URL(STATIC_FILE_BY_WEEK[week], request.url));
  return response.ok ? readJson(await response.text()) : null;
}

/** That week's offers: the saved ones (KV) or the deployed static file, whichever is newer (as the site does). */
function weekLoader(request, env) {
  return async (week) => {
    const [saved, deployed] = await Promise.all([
      env.OFFERS.get(KV_KEY_BY_WEEK[week]).then(readJson),
      staticOffers(request, env, week),
    ]);
    const candidates = [saved, deployed].filter(Boolean);
    return candidates.length ? candidates.reduce((a, b) => (a.generated_at >= b.generated_at ? a : b)) : null;
  };
}

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });

export async function onRequestPost({ request, env }) {
  const text = await request.text();
  if (text.length > MAX_REQUEST_BYTES) return json(errorResponse(null, PARSE_ERROR, "Request too large"), 413);
  let message;
  try {
    message = JSON.parse(text);
  } catch (_) {
    return json(errorResponse(null, PARSE_ERROR, "Request body is not valid JSON"), 400);
  }
  const reply = await handleMessage(message, weekLoader(request, env));
  return reply ? json(reply) : new Response(null, { status: 202 });
}

// Stateless: no server-to-client stream (GET) and no sessions to end (DELETE).
export function onRequest() {
  return new Response("This MCP server only accepts POST.", { status: 405, headers: { Allow: "POST" } });
}
