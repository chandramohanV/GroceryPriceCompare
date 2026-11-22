// Cloudflare Pages Function at /api/account/signup: create an account with the invite code
// and sign in. Body: { username, password, invite }. Bindings: USERS (KV), INVITE_CODE (secret).
import { createAccount, startSession } from "../../../lib/accounts.js";
import { reply } from "../../../lib/password.js";
import { json, readJson, withSessionCookie } from "../../../lib/session.js";

export async function onRequestPost({ request, env }) {
  const input = await readJson(request);
  if (!input.ok) return input.response;
  const result = await createAccount(env.USERS, input.body, env.INVITE_CODE);
  if (!result.ok) return reply(result.status, result.message);
  const token = await startSession(env.USERS, result.username);
  return withSessionCookie(json(201, { username: result.username }), token);
}
