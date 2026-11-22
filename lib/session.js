// HTTP side of accounts, shared by functions/api/account/: JSON bodies, the session cookie
// and the signed-in user of a request.
import { SESSION_COOKIE, SESSION_SECONDS, sessionUser } from "./accounts.js";
import { reply } from "./password.js";

const MAX_BODY_BYTES = 80 * 1024;

/** The request's JSON body as { ok, body } or { ok: false, response } to send back. */
export async function readJson(request) {
  // Requiring JSON also blocks cross-site form posts (they can't send this content type).
  if (!(request.headers.get("Content-Type") || "").startsWith("application/json")) {
    return { ok: false, response: reply(415, "Send JSON.") };
  }
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return { ok: false, response: reply(413, "Too much data.") };
  try {
    return { ok: true, body: JSON.parse(text) };
  } catch (_) {
    return { ok: false, response: reply(400, "That is not valid JSON.") };
  }
}

export function sessionToken(request) {
  const cookies = (request.headers.get("Cookie") || "").split(";").map((c) => c.trim());
  const match = cookies.find((c) => c.startsWith(`${SESSION_COOKIE}=`));
  return match ? match.slice(SESSION_COOKIE.length + 1) : null;
}

export const currentUser = (request, kv) => sessionUser(kv, sessionToken(request));

// HttpOnly keeps scripts from reading the token; SameSite=Lax keeps other sites from using it.
export function withSessionCookie(response, token) {
  const maxAge = token ? SESSION_SECONDS : 0;
  response.headers.append("Set-Cookie",
    `${SESSION_COOKIE}=${token || ""}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=Lax`);
  return response;
}

export function json(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}
