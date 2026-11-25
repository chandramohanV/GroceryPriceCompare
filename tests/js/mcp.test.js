// Tests for the MCP server: the protocol (lib/mcp.js) and the Pages Function wiring (functions/mcp.js), run with `npm test`.
import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { onRequest, onRequestPost } from "../../functions/mcp.js";
import { PROTOCOL_VERSIONS, argumentProblem, handleMessage, listTools } from "../../lib/mcp.js";
import { PAYLOAD } from "./offers-fixture.js";

const thisWeekOnly = async (week) => (week === "this" ? PAYLOAD : null);
const request = (method, params, id = 1) => ({ jsonrpc: "2.0", id, method, params });
const callTool = (name, args) => handleMessage(request("tools/call", { name, arguments: args }), thisWeekOnly);
const parsedText = (reply) => JSON.parse(reply.result.content[0].text);

describe("initialize", () => {
  test("agrees on the client's version when supported", async () => {
    const reply = await handleMessage(request("initialize", { protocolVersion: "2025-03-26" }), thisWeekOnly);
    assert.equal(reply.result.protocolVersion, "2025-03-26");
    assert.deepEqual(reply.result.capabilities, { tools: { listChanged: false } });
  });
  test("offers the newest version for an unknown one", async () => {
    const reply = await handleMessage(request("initialize", { protocolVersion: "1999-01-01" }), thisWeekOnly);
    assert.equal(reply.result.protocolVersion, PROTOCOL_VERSIONS[0]);
  });
});

describe("messages", () => {
  test("a notification gets no reply", async () => {
    assert.equal(await handleMessage({ jsonrpc: "2.0", method: "notifications/initialized" }, thisWeekOnly), null);
  });
  test("ping answers", async () => assert.deepEqual((await handleMessage(request("ping"), thisWeekOnly)).result, {}));
  test("an unknown method is an error", async () => {
    assert.equal((await handleMessage(request("resources/list"), thisWeekOnly)).error.code, -32601);
  });
  test("a batch or non-JSON-RPC message is an invalid request", async () => {
    assert.equal((await handleMessage([request("ping")], thisWeekOnly)).error.code, -32600);
  });
});

describe("tools/list", () => {
  test("lists the five read-only tools without their code", async () => {
    const { tools } = (await handleMessage(request("tools/list"), thisWeekOnly)).result;
    assert.deepEqual(tools.map((t) => t.name), ["get_overview", "list_products", "search_offers", "compare_product", "best_deals"]);
    assert.ok(tools.every((t) => t.annotations.readOnlyHint && !("run" in t) && t.inputSchema.type === "object"));
  });
});

describe("argumentProblem", () => {
  const { inputSchema } = listTools().find((t) => t.name === "compare_product");
  test("accepts valid arguments", () => assert.equal(argumentProblem(inputSchema, { product: "Cheese", stores: ["Lidl"] }), null));
  test("names a missing, unknown or wrongly typed argument", () => {
    assert.equal(argumentProblem(inputSchema, {}), "missing product");
    assert.equal(argumentProblem(inputSchema, { product: "x", colour: "red" }), "unknown argument colour");
    assert.equal(argumentProblem(inputSchema, { product: "x", stores: "Lidl" }), "stores must be a list of strings");
    assert.equal(argumentProblem(inputSchema, { product: "x", week: "last" }), "week must be one of this, next");
  });
  test("checks limits", () => {
    const search = listTools().find((t) => t.name === "search_offers").inputSchema;
    assert.equal(argumentProblem(search, { limit: 0 }), "limit must be at least 1");
    assert.equal(argumentProblem(search, { limit: 1.5 }), "limit must be a whole number");
  });
});

describe("tools/call", () => {
  test("answers with the query result as JSON text", async () => {
    const result = parsedText(await callTool("compare_product", { product: "Cheese" }));
    assert.equal(result.best_store, "Aldi");
  });
  test("applies the default limit", async () => {
    assert.equal(parsedText(await callTool("search_offers", {})).offers.length, 4);
  });
  test("reports bad arguments as a tool error the model can read", async () => {
    const reply = await callTool("search_offers", { limit: "ten" });
    assert.equal(reply.result.isError, true);
    assert.match(reply.result.content[0].text, /limit must be a whole number/);
  });
  test("reports an unknown product as a tool error", async () => {
    const reply = await callTool("compare_product", { product: "Milk" });
    assert.equal(reply.result.isError, true);
  });
  test("says when next week has no offers yet", async () => {
    const reply = await callTool("get_overview", { week: "next" });
    assert.equal(reply.result.isError, true);
    assert.match(reply.result.content[0].text, /next week/);
  });
  test("an unknown tool is a protocol error", async () => {
    assert.equal((await callTool("delete_offers", {})).error.code, -32602);
  });
});

// ---------- functions/mcp.js with fake Cloudflare bindings ----------
const OLDER = { ...PAYLOAD, generated_at: "2026-11-20T05:00:00+00:00", offers: [] };

function fakeEnv({ saved = {}, files = {} }) {
  return {
    OFFERS: { get: async (key) => (saved[key] ? JSON.stringify(saved[key]) : null) },
    ASSETS: {
      // Like Pages: a missing file is answered with the site's index.html.
      fetch: async (url) => (files[new URL(url).pathname]
        ? new Response(JSON.stringify(files[new URL(url).pathname]))
        : new Response("<!doctype html>", { status: 200 })),
    },
  };
}
const post = (body) => new Request("https://site.invalid/mcp", { method: "POST", body: typeof body === "string" ? body : JSON.stringify(body) });
const overviewVia = async (env) => {
  const reply = await (await onRequestPost({ request: post(request("tools/call", { name: "get_overview", arguments: {} })), env })).json();
  return JSON.parse(reply.result.content[0].text);
};

describe("functions/mcp.js", () => {
  test("uses the saved offers when they are newer than the deployed file", async () => {
    const env = fakeEnv({ saved: { offers: PAYLOAD }, files: { "/data/offers.json": OLDER } });
    assert.equal((await overviewVia(env)).generated_at, PAYLOAD.generated_at);
  });
  test("uses the deployed file when nothing is saved", async () => {
    const env = fakeEnv({ files: { "/data/offers.json": OLDER } });
    assert.equal((await overviewVia(env)).generated_at, OLDER.generated_at);
  });
  test("treats the index.html fallback as no offers", async () => {
    const env = fakeEnv({});
    const response = await onRequestPost({ request: post(request("tools/call", { name: "get_overview", arguments: { week: "next" } })), env });
    assert.equal((await response.json()).result.isError, true);
  });
  test("accepts a notification with 202 and no body", async () => {
    const response = await onRequestPost({ request: post({ jsonrpc: "2.0", method: "notifications/initialized" }), env: fakeEnv({}) });
    assert.deepEqual([response.status, await response.text()], [202, ""]);
  });
  test("rejects a body that isn't JSON", async () => {
    const response = await onRequestPost({ request: post("{"), env: fakeEnv({}) });
    assert.deepEqual([response.status, (await response.json()).error.code], [400, -32700]);
  });
  test("rejects an oversized body", async () => {
    const response = await onRequestPost({ request: post("x".repeat(65 * 1024)), env: fakeEnv({}) });
    assert.equal(response.status, 413);
  });
  test("other methods get 405", () => {
    const response = onRequest();
    assert.deepEqual([response.status, response.headers.get("Allow")], [405, "POST"]);
  });
});
