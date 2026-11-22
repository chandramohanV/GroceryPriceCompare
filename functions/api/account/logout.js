// Cloudflare Pages Function at /api/account/logout: end the session and clear its cookie.
import { endSession } from "../../../lib/accounts.js";
import { reply } from "../../../lib/password.js";
import { sessionToken, withSessionCookie } from "../../../lib/session.js";

export async function onRequestPost({ request, env }) {
  await endSession(env.USERS, sessionToken(request));
  return withSessionCookie(reply(200, "Signed out"), null);
}
