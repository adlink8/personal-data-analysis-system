// preload.cjs
//
// Self-contained CommonJS preload for the Phase 61 conversation-first desktop
// shell (Plan 61-11 Task 3). Electron 43 loads sandboxed preload scripts as
// plain CommonJS without an ESM context, so this file cannot `import` the ESM
// `desktop-api-schema.mjs` and sandboxed `require` cannot load arbitrary local
// project files. The channel allowlist, per-intent payload schemas, ID
// grammars and `parseDesktopInput` below are therefore a byte-for-byte mirror
// of the canonical `desktop-api-schema.mjs` parsing contract. The main process
// re-validates every envelope (defense in depth), so any drift here cannot
// widen the authority surface.
//
// `buildBridge(ipcRenderer)` is a pure, injectable seam: the Wave 0 Node tests
// import it directly and feed a mock ipcRenderer. Malformed input is rejected
// by `parseDesktopInput` INSIDE preload, before any IPC invoke fires.
"use strict";

const DESKTOP_API_SCHEMA = "pi-desktop-api-v1";

// Named channel allowlist (mirror of desktop-api-schema.mjs CHANNELS).
const CHANNELS = Object.freeze({
  "harness:last-conversation": "last-conversation",
  "harness:recent-conversations": "recent-list",
  "harness:select-conversation": "conversation-select",
  "harness:new-conversation": "conversation-new",
  "harness:project-scopes": "project-scope-list",
  "harness:select-project-scope": "project-scope-select",
  "harness:conversation-turn": "turn",
  "harness:turn-cancel": "cancel",
  "harness:turn-resume": "resume",
  "harness:turn-reconcile": "reconcile",
  "harness:candidate-review": "review",
  "harness:proactive-state": "proactive-read",
  "harness:proactive-controls": "proactive-controls",
  "harness:proactive-dismiss": "proactive-dismiss",
  "harness:proactive-undo": "proactive-undo",
});

const BRIDGE_METHODS = Object.freeze([
  "getLastConversation",
  "listRecentConversations",
  "selectConversation",
  "newConversation",
  "listProjectScopes",
  "selectProjectScope",
  "sendTurn",
  "cancelTurn",
  "resumeTurn",
  "reconcileTurn",
  "reviewCandidate",
  "getProactiveState",
  "updateProactiveControls",
  "dismissProactive",
  "undoProactiveDismissal",
]);

const BRIDGE_METHOD_TO_CHANNEL = Object.freeze({
  getLastConversation: "harness:last-conversation",
  listRecentConversations: "harness:recent-conversations",
  selectConversation: "harness:select-conversation",
  newConversation: "harness:new-conversation",
  listProjectScopes: "harness:project-scopes",
  selectProjectScope: "harness:select-project-scope",
  sendTurn: "harness:conversation-turn",
  cancelTurn: "harness:turn-cancel",
  resumeTurn: "harness:turn-resume",
  reconcileTurn: "harness:turn-reconcile",
  reviewCandidate: "harness:candidate-review",
  getProactiveState: "harness:proactive-state",
  updateProactiveControls: "harness:proactive-controls",
  dismissProactive: "harness:proactive-dismiss",
  undoProactiveDismissal: "harness:proactive-undo",
});

// Error type compatible with DesktopSchemaError (code + field + intent).
class DesktopSchemaError extends TypeError {
  constructor(code, field, intent) {
    super(code);
    this.name = "DesktopSchemaError";
    this.code = code;
    this.field = field;
    this.intent = intent || null;
  }
}

function fail(code, field, intent) {
  throw new DesktopSchemaError(code, field, intent);
}

// Identifier grammars (mirror of desktop-api-schema.mjs ID_GRAMMARS).
const IDENTIFIER_CORE = "[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}";
const ID_GRAMMARS = Object.freeze({
  conversation: { re: new RegExp(`^conversation_${IDENTIFIER_CORE}$`), label: "conversationId" },
  "project-scope": { re: new RegExp(`^project_scope_${IDENTIFIER_CORE}$`), label: "projectScopeId" },
  task: { re: new RegExp(`^pi_task_${IDENTIFIER_CORE}$`), label: "taskId" },
  candidate: { re: new RegExp(`^candidate_${IDENTIFIER_CORE}$`), label: "candidateId" },
  "proactive-item": { re: new RegExp(`^proactive_item_${IDENTIFIER_CORE}$`), label: "itemId" },
  feedback: { re: new RegExp(`^feedback_${IDENTIFIER_CORE}$`), label: "feedbackId" },
});

function assertScopedId(id, kind) {
  const grammar = ID_GRAMMARS[kind];
  if (!grammar) fail("unknown_id_kind", kind);
  if (typeof id !== "string" || !grammar.re.test(id)) fail("invalid_id", grammar.label, kind);
  return id;
}

// Per-intent payload schemas (mirror of desktop-api-schema.mjs).
const INTENT_PAYLOAD_SCHEMAS = Object.freeze({
  "last-conversation": Object.freeze({ keys: [], required: [] }),
  "recent-list": Object.freeze({ keys: [], required: [] }),
  "project-scope-list": Object.freeze({ keys: [], required: [] }),
  "conversation-select": Object.freeze({ keys: ["conversationId"], required: ["conversationId"] }),
  "conversation-new": Object.freeze({ keys: ["projectScopeId"], required: [] }),
  "project-scope-select": Object.freeze({ keys: ["projectScopeId"], required: ["projectScopeId"] }),
  turn: Object.freeze({ keys: ["conversationId", "text", "projectScopeId"], required: ["conversationId", "text"] }),
  cancel: Object.freeze({ keys: ["taskId"], required: ["taskId"] }),
  resume: Object.freeze({ keys: ["taskId"], required: ["taskId"] }),
  reconcile: Object.freeze({ keys: ["taskId"], required: ["taskId"] }),
  review: Object.freeze({ keys: ["candidateId", "action", "version", "checksum"], required: ["candidateId", "action", "version"] }),
  "proactive-read": Object.freeze({ keys: ["projectScopeId"], required: [] }),
  "proactive-controls": Object.freeze({ keys: ["scope", "category", "enabled", "quietHours"], required: ["scope", "category", "enabled"] }),
  "proactive-dismiss": Object.freeze({ keys: ["itemId", "reason"], required: ["itemId"] }),
  "proactive-undo": Object.freeze({ keys: ["feedbackId"], required: ["feedbackId"] }),
});

const UTC_INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const SHA256_RE = /^[a-f0-9]{64}$/;
const HHMM_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const CANDIDATE_ACTIONS = new Set(["accept", "edit", "ignore"]);
const PROACTIVE_SCOPES = new Set(["global", "project"]);
const PROACTIVE_CATEGORIES = new Set(["sync", "briefing", "reflection-candidate"]);

function validateQuietHours(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail("invalid_type", "quietHours");
  const allowed = new Set(["enabled", "start", "end"]);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) fail("unknown_key", `quietHours.${key}`);
  }
  if ("enabled" in value && typeof value.enabled !== "boolean") fail("invalid_boolean", "quietHours.enabled");
  for (const field of ["start", "end"]) {
    if (field in value && (typeof value[field] !== "string" || !HHMM_RE.test(value[field]))) {
      fail("invalid_time", `quietHours.${field}`);
    }
  }
  return { ...value };
}

const PAYLOAD_VALIDATORS = Object.freeze({
  conversationId: (value) => assertScopedId(value, "conversation"),
  projectScopeId: (value) => assertScopedId(value, "project-scope"),
  taskId: (value) => assertScopedId(value, "task"),
  candidateId: (value) => assertScopedId(value, "candidate"),
  itemId: (value) => assertScopedId(value, "proactive-item"),
  feedbackId: (value) => assertScopedId(value, "feedback"),
  text: (value) => {
    if (typeof value !== "string" || value.trim().length < 1 || value.length > 16000) fail("invalid_text", "text");
    return value;
  },
  action: (value) => {
    if (!CANDIDATE_ACTIONS.has(value)) fail("invalid_action", "action");
    return value;
  },
  version: (value) => {
    if (!Number.isInteger(value) || value < 0) fail("invalid_version", "version");
    return value;
  },
  checksum: (value) => {
    if (typeof value !== "string" || !SHA256_RE.test(value)) fail("invalid_checksum", "checksum");
    return value;
  },
  scope: (value) => {
    if (!PROACTIVE_SCOPES.has(value)) fail("invalid_proactive_scope", "scope");
    return value;
  },
  category: (value) => {
    if (!PROACTIVE_CATEGORIES.has(value)) fail("invalid_category", "category");
    return value;
  },
  enabled: (value) => {
    if (typeof value !== "boolean") fail("invalid_boolean", "enabled");
    return value;
  },
  quietHours: validateQuietHours,
  reason: (value) => {
    if (typeof value !== "string" || value.length > 256) fail("invalid_reason", "reason");
    return value;
  },
});

function parsePayload(intent, payload) {
  const spec = INTENT_PAYLOAD_SCHEMAS[intent];
  if (!spec) fail("unknown_intent", "intent", intent);
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) fail("invalid_type", "input");
  const allowed = new Set(spec.keys);
  for (const key of Object.keys(payload)) {
    if (!allowed.has(key)) fail("unknown_key", key, intent);
  }
  const normalized = { schema: DESKTOP_API_SCHEMA, intent };
  for (const key of spec.keys) {
    if (key in payload && payload[key] !== undefined) {
      normalized[key] = PAYLOAD_VALIDATORS[key](payload[key]);
    }
  }
  for (const key of spec.required) {
    if (!(key in payload)) fail("missing_required", key, intent);
  }
  return normalized;
}

function validateChannel(channel) {
  const intent = CHANNELS[channel];
  if (!intent) fail("unknown_channel", "channel");
  return intent;
}

function parseDesktopInput(channel, value) {
  const intent = validateChannel(channel);
  if (
    value !== null && typeof value === "object" && !Array.isArray(value)
    && value.schema === DESKTOP_API_SCHEMA && value.intent === intent
  ) {
    const { schema: _schema, intent: _intent, ...payload } = value;
    return parsePayload(intent, payload);
  }
  if (value === undefined || value === null) return parsePayload(intent, {});
  return parsePayload(intent, value);
}

function buildBridge(ipcRenderer) {
  const bridge = {};
  for (const method of BRIDGE_METHODS) {
    const channel = BRIDGE_METHOD_TO_CHANNEL[method];
    if (!channel || !(channel in CHANNELS)) {
      throw new Error(`preload bridge method ${method} has no allowlisted channel`);
    }
    bridge[method] = (value) => ipcRenderer.invoke(channel, parseDesktopInput(channel, value));
  }
  return Object.freeze(bridge);
}

module.exports = { buildBridge };
// Redundant assignment guarantees the CommonJS static analyzer exposes
// `buildBridge` as a named export for the Node ESM test importer.
module.exports.buildBridge = buildBridge;

// Electron runtime entry: expose the named bridge as `window.harness`. Guarded
// on the Electron runtime version so this module stays importable (and the
// tested seam stays pure) under plain `node --test`, where no Electron exists.
if (typeof process !== "undefined" && process.versions && process.versions.electron) {
  const { contextBridge, ipcRenderer } = require("electron");
  contextBridge.exposeInMainWorld("harness", buildBridge(ipcRenderer));
}
