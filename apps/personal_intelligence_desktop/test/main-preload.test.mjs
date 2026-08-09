// main-preload.test.mjs
//
// Wave 0 desktop boundary contract for Plan 61-02 (Phase 61).
//
// Two layers:
//   A. Pure schema/normalizer/guard tests against ../src/desktop-api-schema.mjs
//      (Task 1 deliverable) — these PASS in this task.
//   B. Main/preload wiring contract tests against ../src/main.mjs and
//      ../src/preload.cjs (implemented in Task 3). While those modules are
//      absent the lazy import below records the load error and every contract
//      assertion FAILS (RED) with a message pointing at the missing Task 3
//      implementation — the plan's `done` criterion is "tests fail for missing
//      implementation rather than silently passing".
//
// No live Electron window and no network provider are touched; everything runs
// under plain `node --test` in well under 60 seconds.
import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

import {
  DESKTOP_API_SCHEMA,
  THREAD_VIEW_SCHEMA,
  CHANNELS,
  ALLOWED_CHANNELS,
  INTENTS,
  BRIDGE_METHODS,
  ID_KINDS,
  isSafeId,
  assertScopedId,
  parseDesktopInput,
  validateChannel,
  containsForbiddenFields,
  digest,
  toSafeEnvelope,
  toSafeError,
  ROUTE_PROVIDER_UNAVAILABLE,
  normalizeConversationThreadView,
  assertSecureWindowConfig,
  SECURE_WINDOW_CONFIG,
  RESTRICTIVE_CSP,
  assertRestrictiveCsp,
  validateIpcSender,
  senderUrlFromEvent,
  denyNavigation,
  denyNewWindow,
  denyPermissionRequest,
  assertNoRawIpcExposure,
  assertBridgeShape,
  DesktopSchemaError,
} from "../src/desktop-api-schema.mjs";

// Sentinel values prove that no raw body/secret can leak through any envelope,
// view model or error projection produced by this boundary.
export const SECRET_SENTINEL = `SECRET_${randomUUID()}`;
export const RAW_BODY_SENTINEL = `RAW_BODY_${randomUUID()}`;

// --- Task 3 modules are loaded lazily; until they exist these contracts RED.
let mainModule = null;
let mainLoadError = null;
try {
  mainModule = await import("../src/main.mjs");
} catch (error) {
  mainLoadError = error;
}

let preloadModule = null;
let preloadLoadError = null;
try {
  preloadModule = await import("../src/preload.cjs");
} catch (error) {
  preloadLoadError = error;
}

const mainMissing = () =>
  `main.mjs is not implemented yet (Task 3 must create apps/personal_intelligence_desktop/src/main.mjs). Load error: ${mainLoadError?.message ?? "module loaded"}`;
const preloadMissing = () =>
  `preload.cjs is not implemented yet (Task 3 must create apps/personal_intelligence_desktop/src/preload.cjs). Load error: ${preloadLoadError?.message ?? "module loaded"}`;

// Fake sender/event and ipc fixtures (no Electron required).
function mockEvent(senderUrl) {
  return { senderFrame: { url: senderUrl } };
}

function mockIpcMain() {
  const handlers = new Map();
  return {
    handle: (channel, handler) => handlers.set(channel, handler),
    handlers,
  };
}

function mockIpcRenderer() {
  const calls = [];
  return {
    invoke: (channel, value) => {
      calls.push({ channel, value });
      return { ok: true, status: "ok", data: null };
    },
    calls,
  };
}

const LOCAL_RENDERER_URL = "file:///C:/App/personal_intelligence_desktop/renderer/index.html";

function validPayloads(intent) {
  switch (intent) {
    case "last-conversation":
    case "recent-list":
    case "project-scope-list":
      return [undefined, null, {}];
    case "conversation-select":
      return [{ conversationId: "conversation_001" }];
    case "conversation-new":
      return [{}, { projectScopeId: "project_scope_alpha" }];
    case "project-scope-select":
      return [{ projectScopeId: "project_scope_alpha" }];
    case "turn":
      return [{ conversationId: "conversation_001", text: "Show recent project evidence" }];
    case "cancel":
    case "resume":
    case "reconcile":
      return [{ taskId: "pi_task_conversation_turn_001" }];
    case "review":
      return [{ candidateId: "candidate_001", action: "accept", version: 2, checksum: "a".repeat(64) }];
    case "proactive-read":
      return [{}, { projectScopeId: "project_scope_alpha" }];
    case "proactive-controls":
      return [{ scope: "project", category: "reflection-candidate", enabled: true, quietHours: { enabled: true, start: "22:00", end: "07:00" } }];
    case "proactive-dismiss":
      return [{ itemId: "proactive_item_001", reason: "read later" }];
    case "proactive-undo":
      return [{ feedbackId: "feedback_001" }];
    default:
      return [];
  }
}

// ===========================================================================
// A. Pure schema / normalizer / guard contract (passes in Task 1)
// ===========================================================================

test("A1: only allowlisted named channels exist and map to fixed intents", () => {
  assert.equal(ALLOWED_CHANNELS.length, Object.keys(CHANNELS).length);
  assert.equal(ALLOWED_CHANNELS.length, INTENTS.length);
  for (const channel of ALLOWED_CHANNELS) {
    assert.ok(channel.startsWith("harness:"), `channel ${channel} must use harness: namespace`);
    assert.ok(INTENTS.includes(CHANNELS[channel]), `channel ${channel} must map to a known intent`);
    assert.equal(validateChannel(channel), CHANNELS[channel]);
  }
  assert.equal(validateChannel("harness:conversation-turn"), "turn");
  assert.equal(validateChannel("harness:candidate-review"), "review");
});

test("A2: unknown action/channel is rejected", () => {
  for (const channel of ["harness:arbitrary-action", "harness:rm-rf", "ipcRenderer.invoke", "send", "harness:fetch", "harness:open-window"]) {
    assert.throws(() => validateChannel(channel), (error) => error.code === "unknown_channel");
    assert.throws(() => parseDesktopInput(channel, {}), (error) => error.code === "unknown_channel");
  }
});

test("A3: endpoint/path override and raw secret/body keys are rejected in intents", () => {
  const attacks = [
    { conversationId: "conversation_001", text: "hi", endpoint: "http://127.0.0.1:9999/steal" },
    { conversationId: "conversation_001", text: "hi", path: "/v1/tasks", url: "https://evil.example" },
    { conversationId: "conversation_001", text: "hi", sql: "DROP TABLE pi_kernel_sessions" },
    { conversationId: "conversation_001", text: "hi", secret: SECRET_SENTINEL, token: "sk-abc", credential: "user:pass" },
    { conversationId: "conversation_001", text: "hi", command: "rm -rf /", provider: "attacker" },
    { conversationId: "conversation_001", text: "hi", body: RAW_BODY_SENTINEL, prompt: "override", completion: "override" },
  ];
  for (const payload of attacks) {
    assert.throws(
      () => parseDesktopInput("harness:conversation-turn", payload),
      (error) => error.code === "unknown_key" || error.code === "forbidden_inline_field",
      `turn payload ${JSON.stringify(payload)} must be rejected`,
    );
  }
});

test("A4: malformed inputs are rejected (null, arrays, scalars, empty text)", () => {
  assert.throws(() => parseDesktopInput("harness:conversation-turn", 42), (e) => e.code === "invalid_type");
  assert.throws(() => parseDesktopInput("harness:conversation-turn", "hi"), (e) => e.code === "invalid_type");
  assert.throws(() => parseDesktopInput("harness:conversation-turn", ["conversation_001", "hi"]), (e) => e.code === "invalid_type");
  assert.throws(() => parseDesktopInput("harness:conversation-turn", { conversationId: "conversation_001" }), (e) => e.code === "missing_required");
  assert.throws(() => parseDesktopInput("harness:conversation-turn", { conversationId: "conversation_001", text: "   " }), (e) => e.code === "invalid_text");
  assert.throws(() => parseDesktopInput("harness:conversation-turn", { conversationId: "conversation_001", text: "x".repeat(16001) }), (e) => e.code === "invalid_text");
  assert.throws(() => parseDesktopInput("harness:select-conversation", {}), (e) => e.code === "missing_required");
});

test("A5: schema-shaped inputs for every intent normalize to fixed envelopes", () => {
  for (const channel of ALLOWED_CHANNELS) {
    const intent = CHANNELS[channel];
    for (const raw of validPayloads(intent)) {
      const normalized = parseDesktopInput(channel, raw);
      assert.equal(normalized.schema, DESKTOP_API_SCHEMA);
      assert.equal(normalized.intent, intent);
      assert.ok(!containsForbiddenFields(normalized), `${channel} normalized payload must not carry forbidden fields`);
    }
  }
});

test("A6: preload-normalized envelopes are re-validated by main (defense in depth)", () => {
  const first = parseDesktopInput("harness:conversation-turn", { conversationId: "conversation_001", text: "hi" });
  const second = parseDesktopInput("harness:conversation-turn", first);
  assert.deepEqual(second, first);
  assert.throws(
    () => parseDesktopInput("harness:conversation-turn", { ...first, endpoint: "http://127.0.0.1:1/x" }),
    (e) => e.code === "unknown_key",
  );
  // A normalized envelope cannot be replayed onto a different channel.
  assert.throws(() => parseDesktopInput("harness:turn-cancel", first), (e) => e.code === "unknown_key");
});

const VALID_IDS_BY_KIND = {
  conversation: "conversation_001",
  "project-scope": "project_scope_alpha",
  task: "pi_task_conversation_turn_001",
  candidate: "candidate_001",
  "proactive-item": "proactive_item_001",
  feedback: "feedback_001",
};

test("A7: invalid and foreign IDs are rejected per kind", () => {
  for (const kind of ID_KINDS) {
    assert.ok(isSafeId(VALID_IDS_BY_KIND[kind], kind), `kind ${kind} accepts its namespace`);
    assert.doesNotThrow(() => assertScopedId(VALID_IDS_BY_KIND[kind], kind));
  }
  const invalidIds = [
    "https://evil.example/conversation_001",
    "../../etc/passwd",
    "conversation_001; DROP TABLE pi_kernel_sessions",
    "conversation ",
    "conversation_001\u0000",
    "",
    "SELECT * FROM agentsview_messages",
    "abc-123",
    "*",
    "conversation_1:secret@host",
  ];
  for (const id of invalidIds) {
    for (const kind of ["conversation", "project-scope", "task", "candidate", "proactive-item", "feedback"]) {
      assert.throws(
        () => assertScopedId(id, kind),
        (e) => e.code === "invalid_id",
        `${JSON.stringify(id)} must be rejected as ${kind}`,
      );
    }
  }
  // Foreign = syntactically valid but not owned by the current scope.
  assert.throws(
    () => assertScopedId("conversation_002", "conversation", { allowlist: new Set(["conversation_001"]) }),
    (e) => e.code === "foreign_id",
  );
  assert.doesNotThrow(() => assertScopedId("conversation_001", "conversation", { allowlist: new Set(["conversation_001"]) }));
});

test("A8: cancelled or outcome_unknown envelopes never normalize to success", () => {
  for (const status of ["cancelled", "outcome_unknown"]) {
    const envelope = toSafeEnvelope({ ok: true, status, data: { conversationId: "conversation_001" } });
    assert.equal(envelope.ok, false, `${status} must not become success`);
    assert.equal(envelope.status, status, `${status} status must stay truthful`);
    assert.ok(envelope.error && typeof envelope.error.code === "string");
    assert.equal(envelope.data, null, "no success data may ride a non-success envelope");
  }
  // An honest success stays a success.
  const success = toSafeEnvelope({ ok: true, status: "succeeded", data: { conversationId: "conversation_001" } });
  assert.equal(success.ok, true);
  assert.deepEqual(success.data, { conversationId: "conversation_001" });
  // Failed/denied also stay truthful.
  assert.equal(toSafeEnvelope({ ok: false, status: "denied", error: { code: "denied" } }).ok, false);
  assert.equal(toSafeEnvelope({ ok: false, status: "failed", error: { code: "failed" } }).error.code, "failed");
});

test("A9: raw error/body/secret keys are rejected and errors project only safe codes", () => {
  assert.throws(
    () => toSafeEnvelope({ ok: false, status: "error", error: { code: "e", rawBody: RAW_BODY_SENTINEL, secret: SECRET_SENTINEL, stack: "at x" } }),
    (e) => e.code === "forbidden_inline_field",
  );
  const safe = toSafeError({ code: "E_BAD", message: "boom", rawBody: RAW_BODY_SENTINEL, secret: SECRET_SENTINEL, stack: "at x" });
  assert.equal(safe.code, "E_BAD");
  assert.equal(safe.message, "boom");
  assert.ok(!JSON.stringify(safe).includes(RAW_BODY_SENTINEL));
  assert.ok(!JSON.stringify(safe).includes(SECRET_SENTINEL));
  assert.ok(!("stack" in safe));
});

test("A10: ConversationThreadView privacy ceiling — only normalized user/assistant displayText", () => {
  const now = "2026-08-09T00:00:00.000Z";
  const base = {
    conversationId: "conversation_001",
    state: "ready",
    messages: [
      { messageId: "m1", role: "user", displayText: "Ask about history", createdAt: now, sourceRef: "session_1" },
      { messageId: "m2", role: "assistant", displayText: "Here is the evidence", createdAt: now, sourceRef: "session_1", evidenceRefs: ["ev_1", "ev_2"] },
    ],
    pagination: { hasMore: true, nextCursor: "cursor_9" },
    truncated: true,
    freshness: { source: { checkedAt: now, backlog: 0 }, canonical: { checkedAt: now, backlog: 2 }, status: "current" },
    updatedAt: now,
  };
  const view = normalizeConversationThreadView(base);
  assert.equal(view.schema, THREAD_VIEW_SCHEMA);
  assert.equal(view.conversationId, "conversation_001");
  assert.equal(view.state, "ready");
  assert.equal(view.messages.length, 2);
  assert.deepEqual(Object.keys(view.messages[0]), ["messageId", "role", "displayText", "createdAt", "sourceRef"]);
  assert.deepEqual(Object.keys(view.messages[1]), ["messageId", "role", "displayText", "createdAt", "sourceRef", "evidenceRefs"]);
  assert.equal(view.pagination.hasMore, true);
  assert.equal(view.truncated, true);
  assert.equal(view.freshness.canonical.backlog, 2);
  // Raw provider thinking/bodies/diagnostics never cross the bridge.
  const tainted = [
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, thinking: "private chain" }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, input_json: RAW_BODY_SENTINEL }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, provider_body: RAW_BODY_SENTINEL }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, tool_body: RAW_BODY_SENTINEL }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, diagnostic: { internal: "x" } }] },
    { ...base, messages: [{ messageId: "m1", role: "tool", displayText: "ok", createdAt: now }] },
    { ...base, messages: [{ messageId: "m1", role: "system", displayText: "ok", createdAt: now }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, secret: SECRET_SENTINEL }] },
    { ...base, messages: [{ messageId: "m1", role: "assistant", displayText: "ok", createdAt: now, endpoint: "http://127.0.0.1:1/" }] },
  ];
  for (const taintedView of tainted) {
    assert.throws(() => normalizeConversationThreadView(taintedView), `tainted view must be rejected: ${JSON.stringify(taintedView.messages[0])}`);
  }
});

test("A11: explicit empty/stale/partial thread states stay truthful", () => {
  const now = "2026-08-09T00:00:00.000Z";
  const empty = normalizeConversationThreadView({
    conversationId: "conversation_001", state: "empty", messages: [],
    pagination: { hasMore: false }, truncated: false,
    freshness: { status: "unknown" }, updatedAt: now,
  });
  assert.equal(empty.state, "empty");
  assert.deepEqual(empty.messages, []);
  const stale = normalizeConversationThreadView({
    conversationId: "conversation_001", state: "stale", messages: [],
    pagination: { hasMore: false }, truncated: false,
    freshness: { source: { checkedAt: now, backlog: 4 }, canonical: { checkedAt: now, backlog: 9 }, status: "stale" }, updatedAt: now,
  });
  assert.equal(stale.state, "stale");
  const partial = normalizeConversationThreadView({
    conversationId: "conversation_001", state: "partial",
    messages: [{ messageId: "m1", role: "assistant", displayText: "part", createdAt: now }],
    pagination: { hasMore: true }, truncated: true,
    freshness: { status: "unknown" }, updatedAt: now,
  });
  assert.equal(partial.state, "partial");
  // Empty state with messages is a contract violation.
  assert.throws(
    () => normalizeConversationThreadView({
      conversationId: "conversation_001", state: "empty",
      messages: [{ messageId: "m1", role: "assistant", displayText: "part", createdAt: now }],
      pagination: { hasMore: false }, truncated: false, freshness: { status: "unknown" }, updatedAt: now,
    }),
    (e) => e.code === "empty_state_with_messages",
  );
  // Stale can never be labelled current.
  assert.throws(
    () => normalizeConversationThreadView({
      conversationId: "conversation_001", state: "stale", messages: [],
      pagination: { hasMore: false }, truncated: false, freshness: { status: "current" }, updatedAt: now,
    }),
    (e) => e.code === "stale_state_claimed_current",
  );
  // Partial without pagination/truncation markers is a contract violation.
  assert.throws(
    () => normalizeConversationThreadView({
      conversationId: "conversation_001", state: "partial", messages: [],
      pagination: { hasMore: false }, truncated: false, freshness: { status: "unknown" }, updatedAt: now,
    }),
    (e) => e.code === "partial_state_without_pagination",
  );
});

test("A12: sentinel proof — navigation/recovery/proactive data is redacted and non-success stays truthful", () => {
  // Proactive read of a foreign item must fail closed, never silently succeed.
  assert.throws(
    () => assertScopedId("proactive_item_999", "proactive-item", { allowlist: new Set(["proactive_item_001"]) }),
    (e) => e.code === "foreign_id",
  );
  // Recovery envelopes carrying raw bodies are rejected before projection.
  assert.throws(
    () => toSafeEnvelope({ ok: false, status: "outcome_unknown", error: { code: "outcome_unknown", rawBody: RAW_BODY_SENTINEL } }),
    (e) => e.code === "forbidden_inline_field",
  );
  // ROUTE_PROVIDER_UNAVAILABLE is the only envelope a route may return before
  // Plan 61-10 binds providers; it is truthful and carries no data.
  assert.equal(ROUTE_PROVIDER_UNAVAILABLE.ok, false);
  assert.equal(ROUTE_PROVIDER_UNAVAILABLE.status, "route_provider_unavailable");
  assert.equal(ROUTE_PROVIDER_UNAVAILABLE.error.code, "ROUTE_PROVIDER_UNAVAILABLE");
  assert.equal(ROUTE_PROVIDER_UNAVAILABLE.data, null);
  assert.ok(!JSON.stringify(ROUTE_PROVIDER_UNAVAILABLE).includes(SECRET_SENTINEL));
  assert.ok(!JSON.stringify(ROUTE_PROVIDER_UNAVAILABLE).includes(RAW_BODY_SENTINEL));
});

test("A13: secure window config guard demands nodeIntegration false, contextIsolation true, sandbox true", () => {
  assert.equal(SECURE_WINDOW_CONFIG.nodeIntegration, false);
  assert.equal(SECURE_WINDOW_CONFIG.contextIsolation, true);
  assert.equal(SECURE_WINDOW_CONFIG.sandbox, true);
  const config = assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, preload: "/C:/App/personal_intelligence_desktop/src/preload.cjs" });
  assert.ok(config.preload.endsWith("preload.cjs"));
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, nodeIntegration: true }), (e) => e.code === "node_integration_must_be_false");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, contextIsolation: false }), (e) => e.code === "context_isolation_must_be_true");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, sandbox: false }), (e) => e.code === "sandbox_must_be_true");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, webSecurity: false }), (e) => e.code === "web_security_must_be_enabled");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, allowRunningInsecureContent: true }), (e) => e.code === "insecure_content_forbidden");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, webviewTag: true }), (e) => e.code === "webview_tag_forbidden");
  assert.throws(() => assertSecureWindowConfig({ ...SECURE_WINDOW_CONFIG, preload: "https://evil.example/preload.cjs" }), (e) => e.code === "preload_must_be_local");
});

test("A14: restrictive local CSP contract", () => {
  assertRestrictiveCsp(RESTRICTIVE_CSP); // the constant itself must satisfy the contract
  assert.ok(RESTRICTIVE_CSP.includes("default-src 'self'"));
  assert.ok(!RESTRICTIVE_CSP.includes("'unsafe-eval'"));
  assert.ok(!/https?:/.test(RESTRICTIVE_CSP));
  assert.throws(() => assertRestrictiveCsp("default-src *"), (e) => e.code === "csp_must_default_self");
  assert.throws(() => assertRestrictiveCsp("default-src 'self'; script-src 'self' 'unsafe-eval'"), (e) => e.code === "csp_must_be_restrictive");
  assert.throws(() => assertRestrictiveCsp("default-src 'self'; connect-src https://api.example.com"), (e) => e.code === "csp_must_be_restrictive");
});

test("A15: IPC sender validation rejects untrusted senders", () => {
  const APP_FILE_PREFIX = "file:///C:/App/personal_intelligence_desktop/";
  assert.equal(validateIpcSender(LOCAL_RENDERER_URL), LOCAL_RENDERER_URL);
  assert.equal(validateIpcSender(LOCAL_RENDERER_URL, { allowedFilePrefix: APP_FILE_PREFIX }), LOCAL_RENDERER_URL);
  assert.equal(senderUrlFromEvent(mockEvent(LOCAL_RENDERER_URL)), LOCAL_RENDERER_URL);
  for (const bad of [
    "https://evil.example/index.html",
    "http://127.0.0.1:8080/index.html",
    "data:text/html,<script>1</script>",
    "javascript:alert(1)",
    "about:blank",
    "",
  ]) {
    assert.throws(() => validateIpcSender(bad), (e) => e.code === "untrusted_sender", `${bad} must be rejected`);
    // The event URL is still extractable, but the extracted URL must be rejected.
    assert.equal(senderUrlFromEvent(mockEvent(bad)), bad);
    assert.throws(() => validateIpcSender(senderUrlFromEvent(mockEvent(bad))), (e) => e.code === "untrusted_sender");
  }
  // A local file: sender outside the app directory is still untrusted when the
  // main process pins the app prefix.
  assert.throws(
    () => validateIpcSender("file:///C:/Windows/System32/notepad.exe", { allowedFilePrefix: APP_FILE_PREFIX }),
    (e) => e.code === "untrusted_sender",
  );
});

test("A16: navigation, new-window and permission requests are denied", () => {
  let prevented = false;
  const event = { preventDefault: () => { prevented = true; } };
  assert.equal(denyNavigation(event), false);
  assert.equal(prevented, true);
  assert.deepEqual(denyNewWindow(), { action: "deny" });
  let allowed = true;
  assert.equal(denyPermissionRequest({}, "clipboard-read", (value) => { allowed = value; }), false);
  assert.equal(allowed, false);
});

test("A17: no raw ipcRenderer / generic IPC is exposed through a bridge", () => {
  assertNoRawIpcExposure(Object.fromEntries(BRIDGE_METHODS.map((name) => [name, () => undefined])));
  for (const key of ["ipcRenderer", "invoke", "send", "on", "postMessage"]) {
    assert.throws(
      () => assertNoRawIpcExposure({ ...Object.fromEntries(BRIDGE_METHODS.map((name) => [name, () => undefined])), [key]: () => undefined }),
      (e) => e.code === "raw_ipc_exposed",
    );
  }
  // The bridge must expose exactly the named methods, nothing more.
  assertBridgeShape(Object.fromEntries(BRIDGE_METHODS.map((name) => [name, () => undefined])));
  assert.throws(
    () => assertBridgeShape({ getLastConversation: () => undefined, sendTurn: () => undefined }),
    (e) => e.code === "bridge_method_mismatch",
  );
});

// ===========================================================================
// B. Main/preload wiring contract (RED until Task 3 implements main/preload)
// ===========================================================================

test("B1: main.mjs provides a hardened BrowserWindow config", () => {
  assert.ok(mainModule, mainMissing());
  const config = mainModule.createWindowConfig();
  assertSecureWindowConfig(config);
  assert.equal(config.nodeIntegration, false);
  assert.equal(config.contextIsolation, true);
  assert.equal(config.sandbox, true);
  assert.ok(config.preload.endsWith("preload.cjs"), "preload must point only at the local preload.cjs");
});

test("B2: main.mjs enforces a restrictive local CSP", () => {
  assert.ok(mainModule, mainMissing());
  assertRestrictiveCsp(mainModule.CSP);
});

test("B3: main.mjs installs navigation/new-window/permission denials", () => {
  assert.ok(mainModule, mainMissing());
  assert.equal(typeof mainModule.installWindowGuards, "function", "main.mjs must export installWindowGuards(webContents, session)");
  const calls = [];
  const webContents = {
    on: (event, handler) => calls.push([event, handler]),
    preventDefault: () => {},
  };
  const session = { setPermissionRequestHandler: (handler) => calls.push(["setPermissionRequestHandler", handler]) };
  mainModule.installWindowGuards({ webContents, session });
  const events = calls.map(([event]) => event);
  assert.ok(events.includes("will-navigate"), "will-navigate must be denied");
  assert.ok(events.includes("will-redirect"), "will-redirect must be denied");
  assert.ok(events.includes("will-attach-webview"), "webview attach must be denied");
  assert.ok(events.includes("setPermissionRequestHandler"), "permission requests must be denied");
  // The handlers must actually deny (return false / callback(false)).
  for (const [event, handler] of calls) {
    if (event === "will-navigate") {
      let prevented = false;
      handler({ preventDefault: () => { prevented = true; } });
      assert.equal(prevented, true, "navigation must be prevented");
    } else if (event === "will-attach-webview") {
      const detail = { webPreferences: {} };
      const out = handler({ preventDefault: () => {}, webPreferences: detail.webPreferences }, detail);
      if (out !== undefined) assert.deepEqual(out, { action: "deny" });
    } else if (event === "setPermissionRequestHandler") {
      let allowed = true;
      handler({}, "notifications", (value) => { allowed = value; });
      assert.equal(allowed, false, "permission requests must be denied");
    }
  }
});

test("B4: main.mjs opens no new windows", () => {
  assert.ok(mainModule, mainMissing());
  assert.equal(typeof mainModule.denyNewWindow, "function");
  assert.deepEqual(mainModule.denyNewWindow(), { action: "deny" });
});

test("B5: main.mjs registers exactly the allowlisted named channels and no generic handlers", () => {
  assert.ok(mainModule, mainMissing());
  const ipcMain = mockIpcMain();
  const registered = mainModule.installIpcHandlers({ ipcMain, routeProvider: null });
  const channels = [...ipcMain.handlers.keys()].sort();
  assert.deepEqual(channels, [...ALLOWED_CHANNELS].sort(), "handler set must equal the named allowlist exactly");
  assert.ok(!channels.some((channel) => !ALLOWED_CHANNELS.includes(channel)), "no non-allowlisted channel may be registered");
  if (registered !== undefined) assert.deepEqual([...registered].sort(), [...ALLOWED_CHANNELS].sort());
});

test("B6: main.mjs rejects unknown channels and untrusted senders at the handler seam", async () => {
  assert.ok(mainModule, mainMissing());
  const ipcMain = mockIpcMain();
  mainModule.installIpcHandlers({ ipcMain, routeProvider: null });
  const handler = ipcMain.handlers.get("harness:conversation-turn");
  assert.equal(typeof handler, "function");
  // Untrusted sender is denied before any provider work.
  const denied = await handler(mockEvent("https://evil.example/index.html"), { conversationId: "conversation_001", text: "hi" });
  assert.equal(denied.ok, false);
  assert.equal(denied.status, "denied");
  assert.equal(denied.error.code, "untrusted_sender");
  assert.equal(denied.data, null);
  // Unknown channel was never registered (asserted in B5); a direct call must fail.
  assert.equal(ipcMain.handlers.has("harness:fetch"), false);
});

test("B7: main.mjs validates intent schema and returns ROUTE_PROVIDER_UNAVAILABLE before providers exist", async () => {
  assert.ok(mainModule, mainMissing());
  const ipcMain = mockIpcMain();
  mainModule.installIpcHandlers({ ipcMain, routeProvider: null });
  const handler = ipcMain.handlers.get("harness:conversation-turn");
  // Schema-valid, trusted-sender request must not bind a provider or claim success.
  const response = await handler(mockEvent(LOCAL_RENDERER_URL), { conversationId: "conversation_001", text: "Show evidence" });
  assert.equal(response.ok, false);
  assert.equal(response.status, "route_provider_unavailable");
  assert.equal(response.error.code, "ROUTE_PROVIDER_UNAVAILABLE");
  assert.equal(response.data, null);
  // Malformed payload is rejected before any provider work.
  const malformed = await handler(mockEvent(LOCAL_RENDERER_URL), { conversationId: "conversation_001", endpoint: "http://127.0.0.1:1/x" });
  assert.equal(malformed.ok, false);
  assert.equal(malformed.status, "denied");
  assert.ok(malformed.error && typeof malformed.error.code === "string");
  assert.equal(malformed.data, null);
});

test("B8: preload.cjs exposes only the named bridge methods and no raw IPC", () => {
  assert.ok(preloadModule, preloadMissing());
  assert.equal(typeof preloadModule.buildBridge, "function", "preload.cjs must export buildBridge(ipcRenderer)");
  const ipcRenderer = mockIpcRenderer();
  const bridge = preloadModule.buildBridge(ipcRenderer);
  assertBridgeShape(bridge);
  assertNoRawIpcExposure(bridge);
  assert.deepEqual(Object.keys(bridge).sort(), [...BRIDGE_METHODS].sort());
});

test("B9: preload bridge methods parse through the schema and invoke only fixed channels", () => {
  assert.ok(preloadModule, preloadMissing());
  const ipcRenderer = mockIpcRenderer();
  const bridge = preloadModule.buildBridge(ipcRenderer);
  bridge.sendTurn({ conversationId: "conversation_001", text: "hi" });
  bridge.cancelTurn({ taskId: "pi_task_conversation_turn_001" });
  bridge.getProactiveState({ projectScopeId: "project_scope_alpha" });
  assert.deepEqual(ipcRenderer.calls.map((call) => call.channel), [
    "harness:conversation-turn",
    "harness:turn-cancel",
    "harness:proactive-state",
  ]);
  // Malformed input is rejected inside preload before any IPC invoke happens.
  const before = ipcRenderer.calls.length;
  assert.throws(() => bridge.sendTurn({ conversationId: "conversation_001", endpoint: "http://127.0.0.1:1/x" }), (e) => e.code === "unknown_key");
  assert.throws(() => bridge.reviewCandidate({ candidateId: "https://evil.example" }), (e) => e.code === "invalid_id");
  assert.equal(ipcRenderer.calls.length, before, "no IPC may fire for malformed input");
});

// ===========================================================================
// C. Three navigation/session actions (Plan 61-11 Task 1 RED contract, evolved
//    by Task 3 GREEN). The desktop maps listProjectScopes ->
//    conversation.project_scopes.list, selectProjectScope ->
//    conversation.project_scope.select, and newConversation ->
//    conversation.session.create. Task 3 binds these to the unexported
//    localhost-only route map: every channel dispatches to exactly its fixed
//    provider, stays loopback-only, and never lets a renderer field select an
//    endpoint/provider. Unknown/foreign/stale inputs fail closed before any
//    provider work, and an unavailable provider is truthful (never a
//    fabricated scope/session, never the pre-binding ROUTE_PROVIDER_UNAVAILABLE
//    sentinel, which remains pinned by B7 for the null seam).
// ===========================================================================

test("C1: three navigation/session actions map to fixed intents and fixed preload channels", () => {
  assert.equal(CHANNELS["harness:project-scopes"], "project-scope-list");
  assert.equal(CHANNELS["harness:select-project-scope"], "project-scope-select");
  assert.equal(CHANNELS["harness:new-conversation"], "conversation-new");
  // The provider intents are the exact named Plan 61-05 contracts.
  const projectScopeListIntent = INTENTS.includes("project-scope-list");
  const projectScopeSelectIntent = INTENTS.includes("project-scope-select");
  const conversationNewIntent = INTENTS.includes("conversation-new");
  assert.ok(projectScopeListIntent && projectScopeSelectIntent && conversationNewIntent);

  assert.ok(preloadModule, preloadMissing());
  const ipcRenderer = mockIpcRenderer();
  const bridge = preloadModule.buildBridge(ipcRenderer);
  bridge.listProjectScopes();
  bridge.selectProjectScope({ projectScopeId: "project_scope_alpha" });
  bridge.newConversation({ projectScopeId: "project_scope_alpha" });
  assert.deepEqual(ipcRenderer.calls.map((call) => call.channel), [
    "harness:project-scopes",
    "harness:select-project-scope",
    "harness:new-conversation",
  ]);
  // The parsed values carry the fixed named intent, never a generic channel.
  const [list, select, create] = ipcRenderer.calls.map((call) => call.value);
  assert.equal(list.schema, DESKTOP_API_SCHEMA);
  assert.equal(list.intent, "project-scope-list");
  assert.equal(select.intent, "project-scope-select");
  assert.equal(select.projectScopeId, "project_scope_alpha");
  assert.equal(create.intent, "conversation-new");
  assert.equal(create.projectScopeId, "project_scope_alpha");
  assert.equal(create.conversationId, undefined, "new conversation must not carry a canonical conversationId");
});

test("C2: unknown/foreign/stale scope inputs are rejected or stay truthful", () => {
  // Unknown scope namespace is invalid at the schema boundary.
  assert.throws(
    () => parseDesktopInput("harness:select-project-scope", { projectScopeId: "not-a-scope" }),
    (e) => e.code === "invalid_id",
  );
  assert.throws(
    () => parseDesktopInput("harness:new-conversation", { projectScopeId: "https://evil.example/scope" }),
    (e) => e.code === "invalid_id",
  );
  // Foreign scope = syntactically valid but not owned by the current scope.
  assert.throws(
    () => assertScopedId("project_scope_999", "project-scope", { allowlist: new Set(["project_scope_alpha"]) }),
    (e) => e.code === "foreign_id",
  );
  assert.doesNotThrow(() => assertScopedId("project_scope_alpha", "project-scope", { allowlist: new Set(["project_scope_alpha"]) }));
  // Endpoint/path/secret overrides in scope/session actions are rejected.
  for (const [channel, payload] of [
    ["harness:select-project-scope", { projectScopeId: "project_scope_alpha", endpoint: "http://127.0.0.1:1/x" }],
    ["harness:new-conversation", { projectScopeId: "project_scope_alpha", url: "https://evil.example" }],
    ["harness:project-scopes", { provider: "attacker" }],
  ]) {
    assert.throws(() => parseDesktopInput(channel, payload), (e) => e.code === "unknown_key");
  }
  // A stale/denied scope envelope can never normalize to success.
  for (const status of ["stale", "denied", "route_provider_unavailable", "outcome_unknown"]) {
    const envelope = toSafeEnvelope({ ok: false, status, error: { code: status } });
    assert.equal(envelope.ok, false, `${status} must never normalize to success`);
    assert.equal(envelope.status, status);
    assert.equal(envelope.data, null, `no data may ride a ${status} scope envelope`);
  }
});

test("C3: three navigation/session channels dispatch to exactly the fixed providers after binding", async () => {
  assert.ok(mainModule, mainMissing());
  const dispatched = [];
  // Recording transport: proves each channel reaches exactly its declared
  // fixed provider route and never a renderer-selected endpoint/provider.
  const transport = async (request) => {
    dispatched.push(request);
    return { status: 200, body: { ok: true, status: "success", data: { ok: true } } };
  };
  const ipcMain = mockIpcMain();
  const routeProvider = mainModule.createRouteProvider({ transport });
  mainModule.installIpcHandlers({ ipcMain, routeProvider });
  const cases = [
    ["harness:project-scopes", {}, "conversation.project_scopes.list"],
    ["harness:select-project-scope", { projectScopeId: "project_scope_alpha" }, "conversation.project_scope.select"],
    ["harness:new-conversation", { projectScopeId: "project_scope_alpha" }, "conversation.session.create"],
  ];
  for (const [channel, payload] of cases) {
    const handler = ipcMain.handlers.get(channel);
    assert.equal(typeof handler, "function", `${channel} must be registered`);
    const response = await handler(mockEvent(LOCAL_RENDERER_URL), payload);
    assert.equal(response.ok, true, `${channel} must reach its bound provider`);
  }
  assert.deepEqual(
    dispatched.map((request) => request.provider),
    ["conversation.project_scopes.list", "conversation.project_scope.select", "conversation.session.create"],
    "each channel must dispatch to exactly its declared fixed provider",
  );
  // Every route stays localhost-only and carries no-store; no renderer field
  // can influence the URL (endpoint/provider overrides are schema-denied and
  // never reach the transport).
  for (const request of dispatched) {
    assert.ok(request.url.startsWith("http://127.0.0.1:"), `route must stay localhost-only: ${request.url}`);
    assert.equal(request.headers["Cache-Control"], "no-store");
    assert.ok(!JSON.stringify(request.body).includes("endpoint"), "no endpoint override may reach the transport");
  }
  // Malformed/foreign scope input is denied before any provider work.
  const before = dispatched.length;
  const malformed = await ipcMain.handlers.get("harness:select-project-scope")(
    mockEvent(LOCAL_RENDERER_URL),
    { projectScopeId: "SELECT * FROM agent_conversations" },
  );
  assert.equal(malformed.ok, false);
  assert.equal(malformed.status, "denied");
  assert.ok(malformed.error && typeof malformed.error.code === "string");
  assert.equal(malformed.data, null);
  assert.equal(dispatched.length, before, "malformed scope must never reach a provider");
  // Unavailable provider is truthful: no fabricated scope/session and never the
  // pre-binding ROUTE_PROVIDER_UNAVAILABLE sentinel.
  const failingIpc = mockIpcMain();
  const failingProvider = mainModule.createRouteProvider({
    transport: async () => { throw Object.assign(new Error("ECONNREFUSED"), { code: "provider_transport_error" }); },
  });
  mainModule.installIpcHandlers({ ipcMain: failingIpc, routeProvider: failingProvider });
  const unavailable = await failingIpc.handlers.get("harness:new-conversation")(
    mockEvent(LOCAL_RENDERER_URL),
    { projectScopeId: "project_scope_alpha" },
  );
  assert.equal(unavailable.ok, false, "unavailable provider must not fabricate success");
  assert.notEqual(unavailable.status, "route_provider_unavailable", "bound provider no longer uses the pre-binding sentinel");
  assert.equal(unavailable.data, null, "no empty-session claim when the provider is unreachable");
  assert.ok(!JSON.stringify(unavailable).includes("canonical"), "must never claim canonical history");
});

test("C4: main normalizes statement_display only when the receipt checksum binding verifies", async () => {
  assert.ok(mainModule, mainMissing());
  // The exact approved Phase 61 evidence descriptor; checksum binds query ID,
  // version, sorted parameter-name set and the display string (same canonical
  // digest used by the renderer view-model and the Python authority).
  const QUERY_ID = "conversation.evidence_messages.v1";
  const VERSION = "1.0.0";
  const NAMES = ["session_id", "after", "limit"];
  const DISPLAY = "conversation.evidence_messages.v1(session_id, after, limit)";
  const makeReceipt = (statement_display, query_checksum) => ({
    receipt_id: "evidence:0123456789abcdef",
    database_id: "pi_evidence",
    source: "canonical",
    query_id: QUERY_ID,
    descriptor_version: VERSION,
    statement_display,
    parameter_names: [...NAMES],
    query_checksum,
    row_count: 2,
    status: "success",
    freshness: { source: "canonical", latest_message_timestamp: "2026-08-09T00:00:00.000Z" },
  });
  const goodChecksum = digest({
    query_id: QUERY_ID,
    version: VERSION,
    parameter_names: [...NAMES].sort(),
    statement_display: DISPLAY,
  });

  const ipcMain = mockIpcMain();
  const transport = async () => ({ status: 200, body: { ok: true, status: "success", data: { receipts: [makeReceipt(DISPLAY, goodChecksum)] } } });
  mainModule.installIpcHandlers({ ipcMain, routeProvider: mainModule.createRouteProvider({ transport }) });
  const okResponse = await ipcMain.handlers.get("harness:conversation-turn")(
    mockEvent(LOCAL_RENDERER_URL),
    { conversationId: "conversation_001", text: "Show evidence" },
  );
  assert.equal(okResponse.ok, true);
  assert.equal(okResponse.data.receipts[0].statement_display, DISPLAY, "verified binding keeps the server-derived display");

  // Tampered display with an unchanged checksum must drop the display (never a
  // raw/physical SQL surface crosses the bridge).
  const tamperIpc = mockIpcMain();
  const tamperTransport = async () => ({ status: 200, body: { ok: true, status: "success", data: { receipts: [makeReceipt("SELECT * FROM agent_conversations", goodChecksum)] } } });
  mainModule.installIpcHandlers({ ipcMain: tamperIpc, routeProvider: mainModule.createRouteProvider({ transport: tamperTransport }) });
  const tamperedResponse = await tamperIpc.handlers.get("harness:conversation-turn")(
    mockEvent(LOCAL_RENDERER_URL),
    { conversationId: "conversation_001", text: "Show evidence" },
  );
  assert.equal(tamperedResponse.ok, true);
  assert.equal(tamperedResponse.data.receipts[0].statement_display, null, "unverified statement_display must not cross the bridge");
  assert.ok(!JSON.stringify(tamperedResponse).includes("SELECT *"), "raw SQL must never reach the renderer view model");
});

// Keep the boundary honest: no test here may depend on a live Electron window
// or a network provider; the whole file must finish well under 60 seconds.
