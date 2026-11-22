// Tests for lib/accounts.js and lib/session.js, run with `npm test` (Node's built-in runner).
import assert from "node:assert/strict";
import { beforeEach, describe, test } from "node:test";

import {
  checkLogin, createAccount, endSession, loadUserData, passwordProblem, saveUserData,
  sessionUser, startSession, userDataProblem, usernameProblem,
} from "../../lib/accounts.js";
import { readJson, sessionToken, withSessionCookie } from "../../lib/session.js";

const INVITE = "family-2026";

/** In-memory stand-in for a Cloudflare KV namespace; remembers each key's TTL. */
function memoryKv() {
  const values = new Map();
  const ttls = new Map();
  return {
    values, ttls,
    async get(key) { return values.has(key) ? values.get(key) : null; },
    async put(key, value, options = {}) { values.set(key, value); ttls.set(key, options.expirationTtl); },
    async delete(key) { values.delete(key); ttls.delete(key); },
  };
}

const signUp = (kv, fields = {}) => createAccount(
  kv, { username: "Sam", password: "correct horse", invite: INVITE, ...fields }, INVITE);

const validData = () => ({
  prefs: { stores: ["lidl", "dirk"], theme: "dark", lang: "nl" },
  list: [{ id: "lidl:1", text: "Mango", store: "lidl", price: 0.99, detail: "1 Stk.", done: false },
         { id: "own:1", text: "Bread", done: true }],
});

describe("sign-up", () => {
  let kv;
  beforeEach(() => { kv = memoryKv(); });

  test("creates a lower-case account and stores only a salted hash", async () => {
    assert.deepEqual(await signUp(kv), { ok: true, username: "sam" });
    const record = JSON.parse(kv.values.get("user:sam"));
    assert.ok(record.salt && record.hash);
    assert.ok(!kv.values.get("user:sam").includes("correct horse"));
  });

  test("needs the invite code", async () => {
    const result = await signUp(kv, { invite: "guess" });
    assert.equal(result.status, 403);
    assert.equal(kv.values.size, 0);
  });

  test("is switched off until an invite code is configured", async () => {
    const result = await createAccount(kv, { username: "sam", password: "correct horse" }, undefined);
    assert.equal(result.status, 501);
  });

  test("refuses a taken username, whatever its case", async () => {
    await signUp(kv);
    assert.equal((await signUp(kv, { username: "SAM" })).status, 409);
  });

  test("checks username and password rules", async () => {
    assert.equal((await signUp(kv, { username: "a b" })).status, 400);
    assert.equal((await signUp(kv, { password: "short" })).status, 400);
  });
});

describe("username and password rules", () => {
  test("usernames", () => {
    assert.equal(usernameProblem("sam.v-2"), null);
    assert.ok(usernameProblem("ab"));
    assert.ok(usernameProblem("-sam"));
    assert.ok(usernameProblem("x".repeat(33)));
  });

  test("passwords", () => {
    assert.equal(passwordProblem("12345678"), null);
    assert.ok(passwordProblem("1234567"));
    assert.ok(passwordProblem(undefined));
    assert.ok(passwordProblem("x".repeat(201)));
  });
});

describe("login", () => {
  let kv;
  beforeEach(async () => { kv = memoryKv(); await signUp(kv); });

  test("accepts the right password, ignoring username case", async () => {
    assert.deepEqual(await checkLogin(kv, { username: " SAM ", password: "correct horse" }),
      { ok: true, username: "sam" });
  });

  test("gives the same answer for a wrong password and an unknown user", async () => {
    const wrongPassword = await checkLogin(kv, { username: "sam", password: "nope nope" });
    const unknownUser = await checkLogin(kv, { username: "alex", password: "nope nope" });
    assert.deepEqual(wrongPassword, unknownUser);
    assert.equal(wrongPassword.status, 401);
  });

  test("locks the account for a while after ten wrong passwords", async () => {
    for (let i = 0; i < 10; i++) await checkLogin(kv, { username: "sam", password: "wrong pass" });
    const locked = await checkLogin(kv, { username: "sam", password: "correct horse" });
    assert.equal(locked.status, 429);
    assert.equal(kv.ttls.get("failures:sam"), 15 * 60);
  });

  test("a successful login resets the failure count", async () => {
    await checkLogin(kv, { username: "sam", password: "wrong pass" });
    await checkLogin(kv, { username: "sam", password: "correct horse" });
    assert.equal(kv.values.has("failures:sam"), false);
  });
});

describe("sessions", () => {
  test("a token signs in until the session ends, and only its hash is stored", async () => {
    const kv = memoryKv();
    const token = await startSession(kv, "sam");
    assert.equal(await sessionUser(kv, token), "sam");
    assert.ok([...kv.values.keys()].every((key) => !key.includes(token)));
    assert.equal(kv.ttls.get([...kv.values.keys()][0]), 30 * 24 * 60 * 60);
    await endSession(kv, token);
    assert.equal(await sessionUser(kv, token), null);
  });

  test("no token, no user", async () => {
    assert.equal(await sessionUser(memoryKv(), null), null);
  });
});

describe("saved list and preferences", () => {
  test("round trip", async () => {
    const kv = memoryKv();
    assert.deepEqual(await saveUserData(kv, "sam", validData()), { ok: true });
    assert.deepEqual(await loadUserData(kv, "sam"), validData());
  });

  test("a new account starts empty", async () => {
    assert.deepEqual(await loadUserData(memoryKv(), "sam"), { prefs: {}, list: [] });
  });

  test("unknown fields are not stored", async () => {
    const kv = memoryKv();
    await saveUserData(kv, "sam", { ...validData(), extra: "x" });
    assert.equal(JSON.parse(kv.values.get("data:sam")).extra, undefined);
  });

  test("rejects bad shapes with a reason", () => {
    const cases = [
      null,
      { prefs: {}, list: "milk" },
      { prefs: { theme: "neon" }, list: [] },
      { prefs: { stores: ["LIDL!"] }, list: [] },
      { prefs: {}, list: [{ id: "1", text: "Milk" }] },               // no done flag
      { prefs: {}, list: [{ id: "1", text: "", done: false }] },
      { prefs: {}, list: [{ id: "1", text: "Milk", done: false, price: "cheap" }] },
    ];
    for (const data of cases) assert.ok(userDataProblem(data), JSON.stringify(data));
  });

  test("limits the list length", () => {
    const list = Array.from({ length: 301 }, (_, i) => ({ id: `own:${i}`, text: "x", done: false }));
    assert.match(userDataProblem({ prefs: {}, list }), /300/);
  });
});

describe("HTTP helpers", () => {
  const request = (headers, body = "") => new Request("https://x.test/api", { method: "POST", headers, body });

  test("reads the session cookie among others", () => {
    assert.equal(sessionToken(request({ Cookie: "a=1; session=abc; b=2" })), "abc");
    assert.equal(sessionToken(request({})), null);
  });

  test("sets a secure, script-proof cookie and clears it on sign-out", () => {
    const set = withSessionCookie(new Response(), "abc").headers.get("Set-Cookie");
    assert.match(set, /^session=abc; Path=\/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax$/);
    const cleared = withSessionCookie(new Response(), null).headers.get("Set-Cookie");
    assert.match(cleared, /^session=; Path=\/; Max-Age=0;/);
  });

  test("only accepts JSON bodies", async () => {
    const form = await readJson(request({ "Content-Type": "application/x-www-form-urlencoded" }, "a=1"));
    assert.equal(form.response.status, 415);
    const broken = await readJson(request({ "Content-Type": "application/json" }, "{"));
    assert.equal(broken.response.status, 400);
    const good = await readJson(request({ "Content-Type": "application/json" }, '{"a":1}'));
    assert.deepEqual(good, { ok: true, body: { a: 1 } });
  });
});
