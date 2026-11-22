// User accounts for saving grocery lists and preferences: invite-only sign-up,
// password login and cookie sessions.
//
// Storage is passed in (a Cloudflare KV namespace, or anything with the same
// get/put/delete methods), so this logic runs and is tested outside Cloudflare.
// Keys: user:<name> (password hash), data:<name> (list and preferences),
// session:<sha256 of token> (name), failures:<name> (failed logins).

const PBKDF2_ITERATIONS = 100_000; // the most Cloudflare Workers allows
const SALT_BYTES = 16;
const SESSION_TOKEN_BYTES = 32;
const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{2,31}$/;
const PASSWORD_LENGTH = { min: 8, max: 200 };
const LOGIN_LOCK = { maxFailures: 10, seconds: 15 * 60 };
export const SESSION_COOKIE = "session";
export const SESSION_SECONDS = 30 * 24 * 60 * 60;

// Limits for what a person can save, so one account can't fill the store.
const DATA_LIMITS = { bytes: 64 * 1024, listItems: 300, textLength: 200, stores: 10 };
const THEMES = ["auto", "light", "dark"];
const LANGUAGES = ["en", "nl"];
const STORE_KEY_RE = /^[a-z]{1,16}$/;

const ok = (fields = {}) => ({ ok: true, ...fields });
const fail = (status, message) => ({ ok: false, status, message });

// ---------- encoding and hashing ----------
const toBase64 = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)));
const fromBase64 = (text) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
const randomBytes = (n) => crypto.getRandomValues(new Uint8Array(n));

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function hashPassword(password, salt, iterations = PBKDF2_ITERATIONS) {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations }, key, 256);
  return toBase64(bits);
}

// Compares in constant time so a hash can't be guessed by timing the reply.
async function sameHash(a, b) {
  const [x, y] = await Promise.all([a, b].map((text) =>
    crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))));
  const left = new Uint8Array(x);
  const right = new Uint8Array(y);
  let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left[i] ^ right[i];
  return difference === 0;
}

// ---------- validation ----------
export const normalizeUsername = (name) => String(name ?? "").trim().toLowerCase();

export function usernameProblem(username) {
  if (USERNAME_RE.test(username)) return null;
  return "Usernames are 3–32 characters: letters, digits, dots, dashes or underscores.";
}

export function passwordProblem(password) {
  if (typeof password !== "string" || password.length < PASSWORD_LENGTH.min) {
    return `Passwords need at least ${PASSWORD_LENGTH.min} characters.`;
  }
  if (password.length > PASSWORD_LENGTH.max) return "That password is too long.";
  return null;
}

const isShortText = (v) => typeof v === "string" && v.length > 0 && v.length <= DATA_LIMITS.textLength;
const isOptional = (v, check) => v === undefined || v === null || check(v);

function listItemProblem(item) {
  if (item === null || typeof item !== "object") return "a list item is not an object";
  if (!isShortText(item.id) || !isShortText(item.text)) return "a list item needs an id and a text";
  if (typeof item.done !== "boolean") return "a list item needs done: true or false";
  if (!isOptional(item.store, (s) => STORE_KEY_RE.test(s))) return "a list item has an unknown store";
  if (!isOptional(item.price, Number.isFinite)) return "a list item price is not a number";
  if (!isOptional(item.detail, isShortText)) return "a list item detail is too long";
  return null;
}

function prefsProblem(prefs) {
  if (prefs === null || typeof prefs !== "object") return "prefs is not an object";
  const { stores, theme, lang } = prefs;
  const validStores = Array.isArray(stores) && stores.length <= DATA_LIMITS.stores
    && stores.every((s) => STORE_KEY_RE.test(s));
  if (!isOptional(stores, () => validStores)) return "prefs.stores must be a list of store keys";
  if (!isOptional(theme, (t) => THEMES.includes(t))) return `prefs.theme must be one of ${THEMES}`;
  if (!isOptional(lang, (l) => LANGUAGES.includes(l))) return `prefs.lang must be one of ${LANGUAGES}`;
  return null;
}

/** Why saved data is unacceptable, or null when it's fine. */
export function userDataProblem(data) {
  if (data === null || typeof data !== "object") return "Expected { prefs, list }.";
  if (JSON.stringify(data).length > DATA_LIMITS.bytes) return "Your list is too long to save.";
  if (!Array.isArray(data.list)) return "list must be an array.";
  if (data.list.length > DATA_LIMITS.listItems) return `Lists can hold ${DATA_LIMITS.listItems} items.`;
  const problem = prefsProblem(data.prefs) || data.list.map(listItemProblem).find(Boolean);
  return problem ? `Can't save: ${problem}.` : null;
}

// ---------- accounts ----------
export async function createAccount(kv, { username, password, invite }, inviteCode) {
  if (!inviteCode) return fail(501, "Sign-up isn't set up yet (INVITE_CODE is missing).");
  if (!(await sameHash(String(invite ?? ""), inviteCode))) return fail(403, "That invite code is not right.");
  const name = normalizeUsername(username);
  const problem = usernameProblem(name) || passwordProblem(password);
  if (problem) return fail(400, problem);
  if (await kv.get(`user:${name}`)) return fail(409, "That username is taken; pick another one.");

  const salt = randomBytes(SALT_BYTES);
  const record = {
    salt: toBase64(salt),
    hash: await hashPassword(password, salt),
    iterations: PBKDF2_ITERATIONS,
    created: new Date().toISOString(),
  };
  await kv.put(`user:${name}`, JSON.stringify(record));
  return ok({ username: name });
}

async function recordFailure(kv, name) {
  const failures = Number(await kv.get(`failures:${name}`)) || 0;
  await kv.put(`failures:${name}`, String(failures + 1), { expirationTtl: LOGIN_LOCK.seconds });
}

export async function checkLogin(kv, { username, password }) {
  const name = normalizeUsername(username);
  const wrong = fail(401, "Wrong username or password.");
  if (usernameProblem(name) || typeof password !== "string") return wrong;
  if ((Number(await kv.get(`failures:${name}`)) || 0) >= LOGIN_LOCK.maxFailures) {
    return fail(429, "Too many wrong passwords. Try again in 15 minutes.");
  }
  const saved = await kv.get(`user:${name}`);
  if (!saved) return wrong;
  const record = JSON.parse(saved);
  const hash = await hashPassword(password, fromBase64(record.salt), record.iterations);
  if (!(await sameHash(hash, record.hash))) {
    await recordFailure(kv, name);
    return wrong;
  }
  await kv.delete(`failures:${name}`);
  return ok({ username: name });
}

// ---------- sessions ----------
// Only a hash of the token is stored, so a leaked store can't be used to sign in.
export async function startSession(kv, username) {
  const token = toBase64(randomBytes(SESSION_TOKEN_BYTES)).replace(/[+/=]/g, "");
  await kv.put(`session:${await sha256Hex(token)}`, username, { expirationTtl: SESSION_SECONDS });
  return token;
}

export async function sessionUser(kv, token) {
  if (!token) return null;
  return kv.get(`session:${await sha256Hex(token)}`);
}

export async function endSession(kv, token) {
  if (token) await kv.delete(`session:${await sha256Hex(token)}`);
}

// ---------- saved data ----------
export const EMPTY_USER_DATA = Object.freeze({ prefs: {}, list: [] });

export async function loadUserData(kv, username) {
  const saved = await kv.get(`data:${username}`);
  return saved ? JSON.parse(saved) : EMPTY_USER_DATA;
}

export async function saveUserData(kv, username, data) {
  const problem = userDataProblem(data);
  if (problem) return fail(400, problem);
  await kv.put(`data:${username}`, JSON.stringify({ prefs: data.prefs, list: data.list }));
  return ok();
}
