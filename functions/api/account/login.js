// Cloudflare Pages Function at /api/account/login: check the password and start a session.
// Body: { username, password }. Binding: USERS (KV).
import { checkLogin, startSession } from "../../../lib/accounts.js";
import { reply } from "../../../lib/password.js";
import { json, readJson, withSessionCookie } from "../../../lib/session.js";

export async function onRequestPost({ request, env }) {
  const input = await readJson(request);
  if (!input.ok) return input.response;
  const result = await checkLogin(env.USERS, input.body);
  if (!result.ok) return reply(result.status, result.message);
  const token = await startSession(env.USERS, result.username);
  return withSessionCookie(json(200, { username: result.username }), token);
}
