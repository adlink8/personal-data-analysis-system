// desktop-api-schema.mjs
//
// Pure desktop IPC schema, safe-envelope normalizers and injectable
// main-handler guards for the Phase 61 conversation-first Electron shell
// (Plan 61-02). This module has NO Electron import and NO network access so
// the Wave 0 Node tests can exercise every negative under plain `node --test`.
//
// Responsibilities:
//   - Named-channel allowlist (intent -> fixed channel name). The renderer can
//     only invoke these exact names through preload; main registers exactly
//     these handlers.
//   - Per-intent payload validation (exact keys, strict identifier grammar,
//     bounded strings, fixed enums). Endpoint/path overrides and raw
//     body/secret/credential keys are rejected by construction.
//   - Safe envelope projection `{ok,status,error:{code,message},data}`.
//     A cancelled or outcome_unknown envelope can never normalize to success.
//   - ConversationThreadView privacy ceiling: only normalized user/assistant
//     display messages (stable messageId, role, displayText, createdAt,
//     source/evidence ref, pagination/truncation, freshness, explicit
//     empty/stale/partial states). Thinking, raw Tool/provider/input bodies,
//     credentials and private diagnostics fail closed.
//   - Injectable guards consumed by Task 3 main/preload: secure window config,
//     restrictive CSP, navigation/new-window/permission denial, IPC sender
//     validation and no-raw-IPC bridge assertions.
//
// ID namespace contract: providers bound by later plans must present identities
// in these namespaces; the desktop shell never exposes kernel-internal IDs.
import { createHash } from "node:crypto";

export const DESKTOP_API_SCHEMA = "pi-desktop-api-v1";
export const THREAD_VIEW_SCHEMA = "pi-conversation-thread-view-v1";

// ---------------------------------------------------------------------------
// Named channel allowlist. Keyed by exact channel name -> intent. This is the
// single source of truth for preload (bridge method -> channel) and main
// (handler registration allowlist).
// ---------------------------------------------------------------------------
export const CHANNELS = Object.freeze({
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

export const ALLOWED_CHANNELS = Object.freeze(Object.keys(CHANNELS));
export const INTENTS = Object.freeze(Object.values(CHANNELS));

// Fixed provider route identity (Plan 61-11 Task 3): each desktop intent maps
// to exactly one canonical provider name. The renderer can never select a
// provider, endpoint or path; this map is the single source of truth that the
// main-process route map and the preload bridge both bind to.
export const PROVIDER_ROUTES = Object.freeze({
  "last-conversation": "conversation.thread.last",
  "recent-list": "conversation.thread.recent",
  "conversation-select": "conversation.thread.select",
  "conversation-new": "conversation.session.create",
  "project-scope-list": "conversation.project_scopes.list",
  "project-scope-select": "conversation.project_scope.select",
  turn: "conversation.turn",
  cancel: "conversation.cancel",
  resume: "conversation.resume",
  reconcile: "conversation.reconcile",
  review: "candidate.review",
  "proactive-read": "proactive.state.get",
  "proactive-controls": "proactive.controls.update",
  "proactive-dismiss": "proactive.dismiss",
  "proactive-undo": "proactive.dismiss.undo",
});

// The only bridge methods preload may expose (one per channel, camelCase).
export const BRIDGE_METHODS = Object.freeze([
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

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------
export class DesktopSchemaError extends TypeError {
  constructor(code, field, message = code, intent = null) {
    super(message);
    this.name = "DesktopSchemaError";
    this.code = code;
    this.field = field;
    this.intent = intent;
  }
}

function fail(code, field, intent = null) {
  throw new DesktopSchemaError(code, field, code, intent);
}

// ---------------------------------------------------------------------------
// Identifier grammars. Foreign or malformed IDs never reach an authority.
// ---------------------------------------------------------------------------
const IDENTIFIER_CORE = "[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}";
export const ID_GRAMMARS = Object.freeze({
  conversation: { re: new RegExp(`^conversation_${IDENTIFIER_CORE}$`), label: "conversationId" },
  "project-scope": { re: new RegExp(`^project_scope_${IDENTIFIER_CORE}$`), label: "projectScopeId" },
  task: { re: new RegExp(`^pi_task_${IDENTIFIER_CORE}$`), label: "taskId" },
  candidate: { re: new RegExp(`^candidate_${IDENTIFIER_CORE}$`), label: "candidateId" },
  "proactive-item": { re: new RegExp(`^proactive_item_${IDENTIFIER_CORE}$`), label: "itemId" },
  feedback: { re: new RegExp(`^feedback_${IDENTIFIER_CORE}$`), label: "feedbackId" },
});
export const ID_KINDS = Object.freeze(Object.keys(ID_GRAMMARS));

export function isSafeId(id, kind) {
  const grammar = ID_GRAMMARS[kind];
  if (!grammar) return false;
  return typeof id === "string" && grammar.re.test(id);
}

export function assertScopedId(id, kind, { allowlist } = {}) {
  const grammar = ID_GRAMMARS[kind];
  if (!grammar) fail("unknown_id_kind", kind);
  if (typeof id !== "string" || !grammar.re.test(id)) {
    fail("invalid_id", grammar.label, kind);
  }
  if (allowlist && !allowlist.has(id)) fail("foreign_id", grammar.label, kind);
  return id;
}

// ---------------------------------------------------------------------------
// Forbidden-field scan (fail closed). Any provider/view payload that carries a
// raw body, secret, endpoint, SQL, tool body, thinking/diagnostic or kernel
// internal key is rejected before it can cross the bridge.
// ---------------------------------------------------------------------------
const FORBIDDEN_FIELD_RE =
  /^(?:thinking|thoughts|reasoning|thought|chain_of_thought|chain-of-thought|raw|raw_body|rawBody|body|content|prompt|completion|input_json|inputJson|provider_body|providerBody|provider|tool_body|toolBody|tool_call|toolCall|tool_result|toolResult|trace|stack|stack_trace|diagnostic|diagnostics|credential|credentials|secret|secrets|token|password|api_key|apiKey|endpoint|url|uri|path|command|sql|statement|query|parameter_values|parameterValues|params|hidden|internal|model_output|modelOutput|response_body|responseBody|request_body|requestBody|receipt_body|receiptBody|session_trajectory|trajectory|output|result|response|reply|answer)$/i;

export function containsForbiddenFields(value, path = "value") {
  if (value === null || typeof value !== "object") return false;
  if (Array.isArray(value)) {
    for (const [index, child] of value.entries()) {
      if (containsForbiddenFields(child, `${path}[${index}]`)) return true;
    }
    return false;
  }
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_FIELD_RE.test(key)) return true;
    if (containsForbiddenFields(child, `${path}.${key}`)) return true;
  }
  return false;
}

function record(value, field) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail("invalid_type", field);
}

// ---------------------------------------------------------------------------
// Intent payload schemas
// ---------------------------------------------------------------------------
const UTC_INSTANT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const SHA256_RE = /^[a-f0-9]{64}$/;
const HHMM_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const CANDIDATE_ACTIONS = new Set(["accept", "edit", "ignore"]);
const PROACTIVE_SCOPES = new Set(["global", "project"]);
const PROACTIVE_CATEGORIES = new Set(["sync", "briefing", "reflection-candidate"]);

export const INTENT_PAYLOAD_SCHEMAS = Object.freeze({
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

function validateQuietHours(value) {
  record(value, "quietHours");
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
  record(payload, "input");
  const allowed = new Set(spec.keys);
  for (const key of Object.keys(payload)) {
    if (!allowed.has(key)) fail("unknown_key", key, intent);
  }
  const normalized = { schema: DESKTOP_API_SCHEMA, intent };
  // Validate every provided key BEFORE asserting required keys: a malformed or
  // foreign provided ID must be rejected as such (e.g. invalid_id), never
  // masked by a generic missing_required for a different field.
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

// Accept either the raw renderer value or an already-normalized envelope that
// preload produced (preload parses then sends; main re-validates both).
export function parseDesktopInput(channel, value) {
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

// ---------------------------------------------------------------------------
// Safe envelope projection. A cancelled/outcome_unknown/failed envelope can
// never normalize to success; raw error/body/secret keys fail closed.
// ---------------------------------------------------------------------------
export const NON_SUCCESS_STATUSES = Object.freeze([
  "cancelled", "outcome_unknown", "error", "failed", "rejected", "denied",
  "stale", "cancelled_requested", "pending", "route_provider_unavailable",
]);

export function toSafeError(error) {
  if (error instanceof DesktopSchemaError) {
    const out = { code: error.code };
    if (error.field) out.field = error.field;
    return out;
  }
  if (error !== null && typeof error === "object") {
    const code = typeof error.code === "string" ? error.code.slice(0, 128) : "error";
    const message = typeof error.message === "string" ? error.message.slice(0, 200) : "";
    return { code, ...(message ? { message } : {}) };
  }
  return { code: "error" };
}

export function toSafeEnvelope(result) {
  record(result, "envelope");
  if (containsForbiddenFields(result, "envelope")) fail("forbidden_inline_field", "envelope");
  const status = typeof result.status === "string" ? result.status : "ok";
  const ok = result.ok === true && !NON_SUCCESS_STATUSES.includes(status);
  const envelope = { schema: DESKTOP_API_SCHEMA, ok, status, error: null, data: null };
  if (ok) {
    envelope.data = "data" in result ? result.data : null;
  } else {
    envelope.error = toSafeError(result.error === undefined ? { code: status } : result.error);
  }
  return envelope;
}

// Main returns this until Plan 61-10 binds fixed local route providers.
export const ROUTE_PROVIDER_UNAVAILABLE = Object.freeze(toSafeEnvelope({
  ok: false,
  status: "route_provider_unavailable",
  error: { code: "ROUTE_PROVIDER_UNAVAILABLE", message: "Route provider is not bound yet (Plan 61-10)." },
}));

// ---------------------------------------------------------------------------
// ConversationThreadView privacy ceiling
// ---------------------------------------------------------------------------
const THREAD_STATES = new Set(["empty", "ready", "stale", "partial"]);
const FRESHNESS_STATUSES = new Set(["current", "stale", "unknown"]);

function assertIso(value, field) {
  if (typeof value !== "string" || !UTC_INSTANT_RE.test(value)) fail("invalid_timestamp", field);
  return value;
}

function normalizeDisplayMessage(message) {
  record(message, "message");
  if (containsForbiddenFields(message, "message")) fail("forbidden_inline_field", "message");
  const role = message.role;
  if (role !== "user" && role !== "assistant") fail("forbidden_role", "role");
  if (typeof message.messageId !== "string" || message.messageId.length < 1 || message.messageId.length > 128) {
    fail("invalid_message_id", "messageId");
  }
  if (typeof message.displayText !== "string" || message.displayText.length < 1 || message.displayText.length > 20000) {
    fail("invalid_display_text", "displayText");
  }
  const normalized = {
    messageId: message.messageId,
    role,
    displayText: message.displayText,
    createdAt: assertIso(message.createdAt, "createdAt"),
  };
  if ("sourceRef" in message) {
    if (typeof message.sourceRef !== "string" || message.sourceRef.length > 200) fail("invalid_source_ref", "sourceRef");
    normalized.sourceRef = message.sourceRef;
  }
  if ("evidenceRefs" in message) {
    if (
      !Array.isArray(message.evidenceRefs) || message.evidenceRefs.length > 32
      || message.evidenceRefs.some((ref) => typeof ref !== "string" || ref.length > 200)
    ) {
      fail("invalid_evidence_refs", "evidenceRefs");
    }
    normalized.evidenceRefs = [...message.evidenceRefs];
  }
  return normalized;
}

function normalizeFreshness(freshness) {
  record(freshness, "freshness");
  const status = freshness.status;
  if (!FRESHNESS_STATUSES.has(status)) fail("invalid_freshness_status", "freshness.status");
  const normalized = { source: null, canonical: null, status };
  for (const leg of ["source", "canonical"]) {
    if (leg in freshness) {
      const value = freshness[leg];
      record(value, `freshness.${leg}`);
      if (typeof value.checkedAt !== "string" || !UTC_INSTANT_RE.test(value.checkedAt)) fail("invalid_timestamp", `freshness.${leg}.checkedAt`);
      if (!Number.isInteger(value.backlog) || value.backlog < 0) fail("invalid_backlog", `freshness.${leg}.backlog`);
      normalized[leg] = { checkedAt: value.checkedAt, backlog: value.backlog };
    }
  }
  return normalized;
}

export function normalizeConversationThreadView(view) {
  record(view, "view");
  if (containsForbiddenFields(view, "view")) fail("forbidden_inline_field", "view");
  const conversationId = assertScopedId(view.conversationId, "conversation");
  const state = view.state ?? "ready";
  if (!THREAD_STATES.has(state)) fail("invalid_thread_state", "state");
  const messages = Array.isArray(view.messages) ? view.messages.map(normalizeDisplayMessage) : [];
  if (state === "empty" && messages.length > 0) fail("empty_state_with_messages", "messages");
  const pagination = { hasMore: false };
  if (view.pagination !== undefined && view.pagination !== null) {
    record(view.pagination, "pagination");
    if (typeof view.pagination.hasMore !== "boolean") fail("invalid_boolean", "pagination.hasMore");
    pagination.hasMore = view.pagination.hasMore;
    if ("nextCursor" in view.pagination) {
      if (typeof view.pagination.nextCursor !== "string" || view.pagination.nextCursor.length > 200) {
        fail("invalid_cursor", "pagination.nextCursor");
      }
      pagination.nextCursor = view.pagination.nextCursor;
    }
  }
  const truncated = view.truncated === true;
  if (state === "partial" && !pagination.hasMore && !truncated) {
    fail("partial_state_without_pagination", "state");
  }
  const freshness = normalizeFreshness(view.freshness);
  if (state === "stale" && freshness.status === "current") {
    fail("stale_state_claimed_current", "freshness.status");
  }
  return {
    schema: THREAD_VIEW_SCHEMA,
    conversationId,
    state,
    messages,
    pagination,
    truncated,
    freshness,
    updatedAt: assertIso(view.updatedAt, "updatedAt"),
  };
}

// ---------------------------------------------------------------------------
// Electron hardening guards (injectable; consumed by Task 3 main/preload).
// ---------------------------------------------------------------------------
export const SECURE_WINDOW_CONFIG = Object.freeze({
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
  webSecurity: true,
  allowRunningInsecureContent: false,
  webviewTag: false,
});

export function assertSecureWindowConfig(config) {
  record(config, "config");
  if (config.nodeIntegration !== false) fail("node_integration_must_be_false", "nodeIntegration");
  if (config.contextIsolation !== true) fail("context_isolation_must_be_true", "contextIsolation");
  if (config.sandbox !== true) fail("sandbox_must_be_true", "sandbox");
  if (config.webSecurity === false) fail("web_security_must_be_enabled", "webSecurity");
  if (config.allowRunningInsecureContent === true) fail("insecure_content_forbidden", "allowRunningInsecureContent");
  if (config.webviewTag === true) fail("webview_tag_forbidden", "webviewTag");
  if (typeof config.preload !== "string" || config.preload.includes("://") || !/preload\.(?:mjs|cjs|js)$/.test(config.preload)) {
    fail("preload_must_be_local", "preload");
  }
  return { ...SECURE_WINDOW_CONFIG, preload: config.preload };
}

// Restrictive local-only CSP: default-src 'self', no remote sources, no
// eval. connect-src 'none' because the renderer reaches authorities only via
// the named preload bridge, never arbitrary loopback fetch.
export const RESTRICTIVE_CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
  + "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
  + "frame-ancestors 'none'; connect-src 'none'; upgrade-insecure-requests";

export function assertRestrictiveCsp(csp) {
  if (typeof csp !== "string") fail("csp_must_be_string", "csp");
  if (!csp.includes("default-src 'self'")) fail("csp_must_default_self", "csp");
  if (/https?:/.test(csp) || csp.includes("'unsafe-eval'") || /connect-src\s+\*/.test(csp)) {
    fail("csp_must_be_restrictive", "csp");
  }
  return csp;
}

export function senderUrlFromEvent(event) {
  record(event, "event");
  if (event.senderFrame && typeof event.senderFrame.url === "string") return event.senderFrame.url;
  if (event.sender && typeof event.sender.getURL === "function") return event.sender.getURL();
  fail("sender_url_unavailable", "event");
}

// The renderer is a local file: asset. Task 3 main additionally pins the exact
// app path via `allowedFilePrefix`; the schema default rejects remote/opaque
// schemes outright.
export function validateIpcSender(senderUrl, { allowedOriginPrefix = "file://", allowedFilePrefix } = {}) {
  if (typeof senderUrl !== "string" || !senderUrl.startsWith(allowedOriginPrefix)) {
    fail("untrusted_sender", "sender");
  }
  if (/^(?:https?|data|javascript|chrome|devtools|about):/i.test(senderUrl)) fail("untrusted_sender", "sender");
  if (allowedFilePrefix !== undefined && !senderUrl.startsWith(allowedFilePrefix)) {
    fail("untrusted_sender", "sender");
  }
  return senderUrl;
}

export function denyNavigation(event) {
  if (event !== null && typeof event === "object" && typeof event.preventDefault === "function") event.preventDefault();
  return false;
}

export function denyNewWindow() {
  return { action: "deny" };
}

export function denyPermissionRequest(webContents, permission, callback) {
  if (typeof callback === "function") callback(false);
  return false;
}

const GENERIC_IPC_KEYS = new Set(["send", "invoke", "sendSync", "sendTo", "postMessage", "on", "once", "removeListener", "ipcRenderer"]);

export function assertNoRawIpcExposure(bridge) {
  record(bridge, "bridge");
  for (const key of Object.keys(bridge)) {
    if (GENERIC_IPC_KEYS.has(key)) fail("raw_ipc_exposed", key);
  }
  return bridge;
}

export function assertBridgeShape(bridge) {
  assertNoRawIpcExposure(bridge);
  const actual = Object.keys(bridge).sort();
  const expected = [...BRIDGE_METHODS].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("bridge_method_mismatch", "bridge");
  }
  return bridge;
}

// ---------------------------------------------------------------------------
// Small helpers reused by Task 3 main for idempotency/fingerprint metadata.
// ---------------------------------------------------------------------------
export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function digest(value) {
  return createHash("sha256").update(canonicalJson(value)).digest("hex");
}

// ---------------------------------------------------------------------------
// Evidence receipt statement_display binding (Plan 61-11 Task 3).
//
// `statement_display` is the only display text a controlled-query receipt may
// carry, and only when the checksum binds the query ID, descriptor version,
// sorted parameter-name set and the display string itself. The main process
// re-verifies the binding before any receipt display crosses the bridge; a
// mismatch drops the display so raw SQL/physical material can never be
// normalized into a renderer-visible field.
// ---------------------------------------------------------------------------
export function verifyEvidenceReceiptBinding(receipt) {
  if (receipt === null || typeof receipt !== "object" || Array.isArray(receipt)) return false;
  const version = typeof receipt.version === "string" ? receipt.version : receipt.descriptor_version;
  if (
    typeof receipt.query_id !== "string" || typeof version !== "string"
    || !Array.isArray(receipt.parameter_names)
    || receipt.parameter_names.some((name) => typeof name !== "string")
    || typeof receipt.statement_display !== "string"
    || typeof receipt.query_checksum !== "string"
  ) {
    return false;
  }
  const expected = digest({
    query_id: receipt.query_id,
    version,
    parameter_names: [...receipt.parameter_names].sort(),
    statement_display: receipt.statement_display,
  });
  return expected === receipt.query_checksum;
}

/**
 * Normalize a provider response so every evidence receipt exposes
 * `statement_display` only when its checksum binding verifies. Returns a deep
 * safe copy; unverifiable receipts keep their identity fields but drop the
 * display (never a raw SQL/physical surface).
 */
export function normalizeEvidenceReceipts(value) {
  if (Array.isArray(value)) return value.map(normalizeEvidenceReceipts);
  if (value === null || typeof value !== "object") return value;
  const out = {};
  for (const [key, child] of Object.entries(value)) {
    if (key === "statement_display") {
      // Fail closed: display text only crosses when the receipt binding verifies.
      out[key] = verifyEvidenceReceiptBinding(value) ? child : null;
      continue;
    }
    out[key] = normalizeEvidenceReceipts(child);
  }
  return out;
}

// ---------------------------------------------------------------------------
// validateChannel: channel allowlist lookup.
// ---------------------------------------------------------------------------
export function validateChannel(channel) {
  const intent = CHANNELS[channel];
  if (!intent) fail("unknown_channel", "channel");
  return intent;
}
