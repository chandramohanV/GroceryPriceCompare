// The MCP server's protocol: tool definitions, argument checks and JSON-RPC replies (wired up in functions/mcp.js).
import {
  QueryError, bestDeals, compareProduct, listProducts, overview, searchOffers,
} from "./offer-queries.js";

// Newest first; an older client gets its own version back if it is listed here.
export const PROTOCOL_VERSIONS = Object.freeze(["2025-06-18", "2025-03-26", "2024-11-05"]);
export const SERVER_INFO = Object.freeze({ name: "grocery-deals", version: "1.0.0" });
const INSTRUCTIONS = [
  "Weekly grocery offers (supermarket deals) in the Netherlands at Albert Heijn, Lidl, Aldi, Dirk and Jumbo.",
  "Prices are in euros. price is the shelf price; member_price needs the store's free loyalty card",
  "(Lidl Plus, AH Bonuskaart); effective_price is the lowest price per pack after deals such as",
  "'1+1 free' or '2 for 3.50' and card prices; unit_price is effective_price per kg, litre or piece.",
  "A product is compared only when at least two stores price it in the same unit; saving_pct is how",
  "much cheaper the best store is than the next cheapest store. Use week 'next' for next week's offers,",
  "which stores publish during the week. Start with get_overview when unsure what is on offer.",
].join(" ");

const JSON_RPC = Object.freeze({ PARSE_ERROR: -32700, INVALID_REQUEST: -32600, METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602 });
// A protocol-level failure, answered as a JSON-RPC error rather than a tool result.
class RpcError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 100;

const WEEK = { type: "string", enum: ["this", "next"], default: "this", description: "This week's or next week's offers." };
const STORE = { type: "string", description: "Store name or key, e.g. \"Albert Heijn\", \"ah\", \"lidl\"." };
const STORES = {
  type: "array", items: { type: "string" },
  description: "Only compare these stores (names or keys), e.g. [\"Lidl\", \"Aldi\"] for the stores you shop at.",
};
const CATEGORY = {
  type: "string",
  description: "Fruit, Vegetables, Meat, Fish, Dairy & eggs, Cereals, Coffee or Frozen.",
};
const LIMIT = { type: "integer", minimum: 1, maximum: MAX_LIMIT, default: DEFAULT_LIMIT, description: "Most results to return." };

const readOnly = (title) => ({ title, readOnlyHint: true, openWorldHint: false });

// Each tool: its MCP definition and the query that answers it.
const TOOLS = [
  {
    name: "get_overview",
    description: "When the offers were fetched, their valid dates, each store's number of offers and "
      + "whether it is up to date, and the offers per category. Call this first to see what is available.",
    inputSchema: { type: "object", properties: { week: WEEK } },
    annotations: readOnly("Offers overview"),
    run: (payload) => overview(payload),
  },
  {
    name: "list_products",
    description: "Every product on offer (e.g. Cheese, Apples, Minced meat) with the stores offering it and, "
      + "where it can be compared, the cheapest store and its saving.",
    inputSchema: { type: "object", properties: { week: WEEK, category: CATEGORY, store: STORE } },
    annotations: readOnly("List products"),
    run: (payload, args) => listProducts(payload, args),
  },
  {
    name: "search_offers",
    description: "Find offers by words in their English or Dutch name (e.g. \"cheese\", \"kaas\", \"organic eggs\"), "
      + "cheapest per unit first. Leave query empty to list all offers of a store or category.",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string", description: "Words that must all appear in the name." }, week: WEEK, store: STORE, category: CATEGORY, limit: LIMIT },
    },
    annotations: readOnly("Search offers"),
    run: (payload, args) => searchOffers(payload, { ...args, limit: args.limit ?? DEFAULT_LIMIT }),
  },
  {
    name: "compare_product",
    description: "All stores' offers for one product side by side, cheapest per unit first, with the best store "
      + "and how much cheaper it is. Give stores to compare only the shops you go to.",
    inputSchema: {
      type: "object",
      properties: { product: { type: "string", description: "Product in English or Dutch, e.g. \"Cheese\" or \"Kaas\"." }, week: WEEK, stores: STORES },
      required: ["product"],
    },
    annotations: readOnly("Compare a product"),
    run: (payload, args) => compareProduct(payload, args),
  },
  {
    name: "best_deals",
    description: "Products where one store is clearly cheapest per unit, biggest saving first. "
      + "Give stores to only weigh the shops you go to.",
    inputSchema: { type: "object", properties: { week: WEEK, stores: STORES, category: CATEGORY, limit: LIMIT } },
    annotations: readOnly("Best deals"),
    run: (payload, args) => bestDeals(payload, { ...args, limit: args.limit ?? DEFAULT_LIMIT }),
  },
];
const TOOL_BY_NAME = new Map(TOOLS.map((tool) => [tool.name, tool]));

/** The tools as tools/list returns them. */
export function listTools() {
  return TOOLS.map(({ run, ...definition }) => definition);
}

function checkValue(name, schema, value) {
  if (schema.type === "string" && typeof value !== "string") return `${name} must be a string`;
  if (schema.enum && !schema.enum.includes(value)) return `${name} must be one of ${schema.enum.join(", ")}`;
  if (schema.type === "integer" && !Number.isInteger(value)) return `${name} must be a whole number`;
  if (schema.minimum !== undefined && value < schema.minimum) return `${name} must be at least ${schema.minimum}`;
  if (schema.maximum !== undefined && value > schema.maximum) return `${name} must be at most ${schema.maximum}`;
  if (schema.type === "array" && !(Array.isArray(value) && value.every((v) => typeof v === "string"))) {
    return `${name} must be a list of strings`;
  }
  return null;
}

/** The arguments' problems against the tool's input schema, as one message, or null when they are fine. */
export function argumentProblem(schema, args) {
  if (args === null || typeof args !== "object" || Array.isArray(args)) return "arguments must be an object";
  const missing = (schema.required ?? []).filter((name) => args[name] === undefined);
  if (missing.length) return `missing ${missing.join(", ")}`;
  const unknown = Object.keys(args).filter((name) => !Object.hasOwn(schema.properties, name));
  if (unknown.length) return `unknown argument ${unknown.join(", ")}`;
  const problems = Object.entries(args).map(([name, value]) => checkValue(name, schema.properties[name], value));
  return problems.filter(Boolean).join("; ") || null;
}

const textResult = (text, isError = false) => ({ content: [{ type: "text", text }], ...(isError ? { isError } : {}) });
const NO_OFFERS_TEXT = {
  this: "No offers are saved yet: the daily refresh hasn't run.",
  next: "No offers for next week yet. Stores publish next week's offers during the week (Albert Heijn on Friday); try again later.",
};

async function callTool(params, loadWeek) {
  const tool = TOOL_BY_NAME.get(params?.name);
  if (!tool) throw new RpcError(JSON_RPC.INVALID_PARAMS, `Unknown tool: ${params?.name}`);
  const args = params.arguments ?? {};
  const problem = argumentProblem(tool.inputSchema, args);
  if (problem) return textResult(`Invalid arguments for ${tool.name}: ${problem}.`, true);
  const week = args.week ?? "this";
  const payload = await loadWeek(week);
  if (!payload) return textResult(NO_OFFERS_TEXT[week], true);
  try {
    return textResult(JSON.stringify(tool.run(payload, args)));
  } catch (error) {
    if (error instanceof QueryError) return textResult(error.message, true);
    throw error;
  }
}

function initialize(params) {
  const requested = params?.protocolVersion;
  return {
    protocolVersion: PROTOCOL_VERSIONS.includes(requested) ? requested : PROTOCOL_VERSIONS[0],
    capabilities: { tools: { listChanged: false } },
    serverInfo: SERVER_INFO,
    instructions: INSTRUCTIONS,
  };
}

const METHODS = {
  initialize: (params) => initialize(params),
  ping: () => ({}),
  "tools/list": () => ({ tools: listTools() }),
  "tools/call": (params, loadWeek) => callTool(params, loadWeek),
};

const isRequest = (message) => message !== null && typeof message === "object" && !Array.isArray(message)
  && message.jsonrpc === "2.0" && typeof message.method === "string";

/**
 * Answers one JSON-RPC message. Returns the response, or null for a notification (no reply).
 * loadWeek(week) resolves to that week's offers document, or null when there is none.
 */
export async function handleMessage(message, loadWeek) {
  if (!isRequest(message)) return errorResponse(null, JSON_RPC.INVALID_REQUEST, "Expected one JSON-RPC 2.0 request");
  const isNotification = message.id === undefined;
  if (isNotification) return null;
  const method = Object.hasOwn(METHODS, message.method) ? METHODS[message.method] : null;
  if (!method) return errorResponse(message.id, JSON_RPC.METHOD_NOT_FOUND, `Method not found: ${message.method}`);
  try {
    return { jsonrpc: "2.0", id: message.id, result: await method(message.params, loadWeek) };
  } catch (error) {
    if (error instanceof RpcError) return errorResponse(message.id, error.code, error.message);
    throw error;
  }
}

/** A JSON-RPC error reply. */
export function errorResponse(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

export const PARSE_ERROR = JSON_RPC.PARSE_ERROR;
