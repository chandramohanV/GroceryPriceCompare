// Each person's preferences (stores, theme, language) and grocery list.
// Signed out, they live in this browser only; signed in, they are saved to the
// person's account (functions/api/account/). Loaded in <head> so the chosen
// theme applies before the page is drawn. Other scripts use window.userState.
window.userState = (() => {
  "use strict";

  const LOCAL_KEY = "grocery-user-state";
  const LEGACY_LANG_KEY = "lang"; // where app.js used to keep the language choice
  const API = "/api/account";
  const SAVE_DELAY_MS = 600; // batch quick changes (ticking several items) into one save
  const THEMES = ["auto", "light", "dark"];

  const listeners = new Set();
  let username = null;
  let data = readLocal();
  let saveTimer = null;

  // ---------- browser storage (can be blocked, e.g. private windows) ----------
  function readLocal() {
    try {
      const saved = JSON.parse(localStorage.getItem(LOCAL_KEY));
      if (saved && Array.isArray(saved.list)) return { prefs: saved.prefs || {}, list: saved.list };
      return { prefs: { lang: localStorage.getItem(LEGACY_LANG_KEY) || undefined }, list: [] };
    } catch (_) {
      return { prefs: {}, list: [] }; /* nothing stored or storage blocked: start empty */
    }
  }

  function writeLocal(value) {
    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(value)); } catch (_) { /* just not remembered */ }
  }

  // ---------- theme ----------
  function applyTheme() {
    const theme = THEMES.includes(data.prefs.theme) ? data.prefs.theme : "auto";
    if (theme === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }

  // ---------- server ----------
  async function request(path, options = {}) {
    const resp = await fetch(API + path, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json" } : {},
      credentials: "same-origin",
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.message || `The server answered HTTP ${resp.status}.`);
    return body;
  }

  function saveToAccount() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      request("/data", { method: "PUT", body: JSON.stringify(data) })
        .catch((e) => notify({ saveError: e.message }));
    }, SAVE_DELAY_MS);
  }

  // ---------- changes ----------
  function notify(extra = {}) {
    for (const listener of listeners) listener({ username, data, ...extra });
  }

  function commit(next) {
    data = next;
    applyTheme();
    if (username) saveToAccount(); else writeLocal(data);
    notify();
  }

  const setPrefs = (changes) => commit({ ...data, prefs: { ...data.prefs, ...changes } });
  const setList = (list) => commit({ ...data, list });

  function addItem(item) {
    if (data.list.some((i) => i.id === item.id)) return;
    setList([...data.list, { ...item, done: false }]);
  }

  const hasItem = (id) => data.list.some((i) => i.id === id);
  const removeItem = (id) => setList(data.list.filter((i) => i.id !== id));
  const toggleItem = (id) => setList(data.list.map((i) => (i.id === id ? { ...i, done: !i.done } : i)));
  const clearDone = () => setList(data.list.filter((i) => !i.done));

  // ---------- accounts ----------
  // The list made before signing in is added to the account's list, so nothing is lost.
  function adoptAccount(name, saved) {
    const local = data;
    const savedIds = new Set(saved.list.map((i) => i.id));
    username = name;
    writeLocal({ prefs: local.prefs, list: [] });
    const merged = {
      prefs: { ...local.prefs, ...saved.prefs },
      list: [...saved.list, ...local.list.filter((i) => !savedIds.has(i.id))],
    };
    if (merged.list.length !== saved.list.length) commit(merged);
    else { data = merged; applyTheme(); notify(); }
  }

  async function signIn(name, password) {
    const { username: signedIn } = await request("/login", {
      method: "POST", body: JSON.stringify({ username: name, password }) });
    const { data: saved } = await request("/data");
    adoptAccount(signedIn, saved);
  }

  async function signUp(name, password, invite) {
    const { username: created } = await request("/signup", {
      method: "POST", body: JSON.stringify({ username: name, password, invite }) });
    adoptAccount(created, { prefs: {}, list: [] });
  }

  async function signOut() {
    clearTimeout(saveTimer);
    await request("/logout", { method: "POST" }).catch(() => { /* the cookie expires anyway */ });
    username = null;
    data = readLocal();
    applyTheme();
    notify();
  }

  // Restores a signed-in session on page load; without the account API (local server) this is a no-op.
  async function restore() {
    try {
      const { username: name, data: saved } = await request("/data");
      adoptAccount(name, saved);
    } catch (_) {
      notify(); /* signed out, or no account API here */
    }
  }

  applyTheme();

  return {
    get username() { return username; },
    get prefs() { return data.prefs; },
    get list() { return data.list; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    setPrefs, addItem, hasItem, removeItem, toggleItem, clearDone,
    signIn, signUp, signOut, restore,
    THEMES,
  };
})();
