// Cloudflare Pages Function at /api/account/data: the signed-in person's grocery list and
// preferences. GET returns { username, data }; PUT saves { prefs, list }. Binding: USERS (KV).
import { loadUserData, saveUserData } from "../../../lib/accounts.js";
import { reply } from "../../../lib/password.js";
import { currentUser, json, readJson } from "../../../lib/session.js";

const NOT_SIGNED_IN = "Not signed in.";

export async function onRequestGet({ request, env }) {
  const username = await currentUser(request, env.USERS);
  if (!username) return reply(401, NOT_SIGNED_IN);
  return json(200, { username, data: await loadUserData(env.USERS, username) });
}

export async function onRequestPut({ request, env }) {
  const username = await currentUser(request, env.USERS);
  if (!username) return reply(401, NOT_SIGNED_IN);
  const input = await readJson(request);
  if (!input.ok) return input.response;
  const result = await saveUserData(env.USERS, username, input.body);
  return result.ok ? reply(200, "Saved") : reply(result.status, result.message);
}
