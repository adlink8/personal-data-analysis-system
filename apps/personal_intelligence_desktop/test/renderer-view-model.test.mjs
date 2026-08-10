// renderer-view-model.test.mjs
//
// Phase 61 Plan 61-11 Task 1 (RED): executable presentation contract for the
// conversation-first desktop renderer view-model. Targets
// `../src/renderer/app.mjs` which Task 2 must implement (index.html/app.mjs/
// styles.css). While that module is absent every contract assertion FAILS with
// a message pointing at the missing view-model implementation (RED), so the
// renderer boundary is executable before any DOM/presentation code exists.
//
// Nothing here touches a live Electron window, a network provider or private
// data: the bridge is injected and every fixture is deterministic and
// sanitized.
//
// ===========================================================================
// CONTRACT — `src/renderer/app.mjs` MUST export (implemented in Task 2):
//
//   export const RENDERER_VIEW_MODEL = "pi-renderer-view-model-v1";
//
//   export function navigateStartup(bridge)
//     -> { schema, ok, last, recent, recentStatus, scopes, scopesStatus }
//        Calls EXACTLY getLastConversation(), listRecentConversations(),
//        listProjectScopes() in that order. `last` is { state, status, thread? }
//        where thread is a safe deep copy; on non-success last.state is
//        "unavailable" with status preserved and thread absent. `recent` and
//        `scopes` are arrays of safe deep copies; `recentStatus`/`scopesStatus`
//        carry the envelope status truthfully.
//
//   export function listScopes(bridge)
//     -> { schema, ok, status, items }  // calls exactly listProjectScopes()
//        items are metadata-only { projectScopeId, label, threadCount,
//        lastActivityAt, freshness } safe copies.
//
//   export function selectScope(bridge, { projectScopeId })
//     -> { schema, ok, status, selectedScope, recentThreads }
//        Calls exactly selectProjectScope({ projectScopeId }); never mutates
//        canonical data; non-success keeps ok=false and selectedScope=null.
//
//   export function newConversation(bridge, { projectScopeId })
//     -> { schema, ok, status, session, thread, canonicalHistory }
//        Calls exactly newConversation({ projectScopeId }); session is ONLY
//        empty Kernel Session metadata { sessionId, projectScopeId, createdAt,
//        status: "empty" }; thread is an empty view; canonicalHistory is always
//        false and no canonical-history label may appear.
//
//   export function selectConversation(bridge, { conversationId })
//     -> { schema, ok, status, thread }   // calls exactly selectConversation()
//
//   export function threadViewModel(view)   // safe deep copy with explicit
//        empty/stale/partial/paginated states and two-leg freshness
//
//   export function answerViewModel(answer)
//     -> { schema, ok, status, isSuccess, statusText?, disclosures,
//          toolRow, liveRegion, errorRole? }
//        disclosures.{basis,freshness,limitations} have label/collapsed/text;
//        freshness exposes sourceLeg+canonicalLeg separately; toolRow is
//        collapsed with skillName/effect/resultStatus/receiptCount; cancelled
//        and outcome_unknown are never isSuccess.
//
//   export function validateStatementDisplay(receipt)
//     -> { ok, display?, code? }
//        Recomputes the checksum over { query_id, version, parameter_names
//        (sorted), statement_display } via the shared schema digest and accepts
//        only an exact binding; any tamper rejects.
//
//   export function expandSqliteCard(receipt)
//     -> { schema, ok, status, cardTitle: "SQLite · 只读查询",
//          expansionTitle: "受控查询",
//          statementLabel: "已执行的脱敏 allowlisted statement",
//          statementDisplay, rows, rowCount, durationMs, truncated, receiptId,
//          databaseId, queryId, descriptorVersion, queryChecksum, freshness }
//        statementDisplay is EXACTLY receipt.statement_display and only after
//        validateStatementDisplay passes; rejected receipts never render SQL.
//
//   export function candidateReviewViewModel(receipt)
//     -> { schema, ok, cardTitle: "待审核候选",
//          disclosure: "AI 生成的候选，尚未成为事实",
//          actions: ["查看候选证据","编辑候选","接受候选","忽略候选"],
//          hasBatchAccept: false, confirmModal, conflictModal, receiptId,
//          projectionVersion, candidateId }
//        conflictModal.options are exactly the four keep_existing /
//        replace_existing / coexist_by_context / defer_judgment triples with
//        consequence text; unknown/missing disposition rejects.
//
//   export function projectionViewModel(projection)
//     -> { schema, label: "派生个人模型", projectionId, version,
//          provenanceClass: "inference", scope, validFrom, validTo, observedAt,
//          confidence, uncertainty, supportCount, conflictCount, evidenceRefs,
//          conflicts, supersession, freshness, limitations, corrigible: true }
//        never a "个人事实" or stable personality label.
//
//   export function proactiveViewModel(state)
//     -> { schema, escalation, quiet, controls, cluster, dismissal }
//        quiet.quietUntilLabel echoes "静默至 HH:MM"; controls.categories keys
//        are exactly sync/briefing/reflection-candidate; cluster.mergedLabel is
//        "已合并 N 条同簇证据"; dismissal keeps the append-only feedbackId.
//
//   export function commandPaletteViewModel(input)
//     -> { schema, ok, shortcut: "Ctrl/Cmd+K", commands: [
//            { id: "receipt.open", label: "查看 receipt" },
//            { id: "proactive.manage", label: "管理主动提醒" } ] }
//        The two-action set is exact; anything else rejects.
//
//   export function createLayerManager()
//     -> { open({ id, trigger }), peek(), close(), depth() }
//        strict LIFO: Esc closes modal -> drawer -> palette; close() returns
//        the closed layer's { id, trigger } so focus returns to the trigger.
//
// `app.mjs` must run DOM work only when a document/window exists (guard the
// bootstrap) and must contain NO generic transport/storage: no fetch(), no
// XMLHttpRequest, no WebSocket, no ipcRenderer, no localStorage/sessionStorage/
// indexedDB/navigator.sendBeacon, and no console.log/console.info of body text.
// ===========================================================================
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

import {
  BRIDGE_METHODS,
  THREAD_VIEW_SCHEMA,
  ROUTE_PROVIDER_UNAVAILABLE,
  toSafeEnvelope,
  containsForbiddenFields,
  digest,
} from "../src/desktop-api-schema.mjs";

// --- Task 2 module is loaded lazily; until it exists these contracts RED.
let appModule = null;
let appLoadError = null;
try {
  appModule = await import("../src/renderer/app.mjs");
} catch (error) {
  appLoadError = error;
}

const viewModelMissing = () =>
  "RED: renderer view-model must be implemented in apps/personal_intelligence_desktop/src/renderer/app.mjs (Task 2). Load error: "
  + (appLoadError?.message ?? "module loaded");

export const SECRET_SENTINEL = `SECRET_${randomUUID()}`;
export const RAW_BODY_SENTINEL = `RAW_BODY_${randomUUID()}`;

const RENDERER_VIEW_MODEL = "pi-renderer-view-model-v1";
const NOW = "2026-08-09T00:00:00.000Z";

// ---------------------------------------------------------------------------
// Deterministic sanitized fixtures
// ---------------------------------------------------------------------------

// The only Phase 61 approved query (Plan 61-04): descriptor identity and the
// sorted parameter-name set are part of the checksum binding.
export const QUERY_ID = "conversation.evidence_messages.v1";
export const DESCRIPTOR_VERSION = "1.0.0";
export const EVIDENCE_PARAMETER_NAMES = ["session_id", "after", "limit"];
export const STATEMENT_DISPLAY = "conversation.evidence_messages.v1(session_id, after, limit)";

// Mirrors the Python authority's `query_checksum`: sha256 over canonical JSON
// of { query_id, version, parameter_names (sorted), statement_display } using
// the same recursive-key-sort compact serialization the desktop schema digest
// uses (desktop-api-schema canonicalJson == Python _canonical_json format).
function bindQueryChecksum(overrides = {}) {
  return digest({
    query_id: overrides.query_id ?? QUERY_ID,
    version: overrides.version ?? DESCRIPTOR_VERSION,
    parameter_names: [...(overrides.parameter_names ?? EVIDENCE_PARAMETER_NAMES)].sort(),
    statement_display: overrides.statement_display ?? STATEMENT_DISPLAY,
  });
}

function makeSqliteReceipt(overrides = {}) {
  const statement_display = overrides.statement_display ?? STATEMENT_DISPLAY;
  const query_id = overrides.query_id ?? QUERY_ID;
  const version = overrides.version ?? DESCRIPTOR_VERSION;
  const parameter_names = overrides.parameter_names ?? [...EVIDENCE_PARAMETER_NAMES];
  const query_checksum = overrides.query_checksum ?? bindQueryChecksum({
    statement_display, query_id, version, parameter_names,
  });
  return {
    receipt_id: "evidence:0123456789abcdef",
    database_id: "pi_evidence",
    source: "canonical",
    query_id,
    descriptor_version: version,
    statement_display,
    parameter_names: [...parameter_names].sort(),
    query_checksum,
    row_count: 2,
    limit: 50,
    truncated: false,
    bytes: 512,
    duration_ms: 3,
    status: "success",
    binding: { database_id: "pi_evidence", source: "canonical", schema_checksum: "s", snapshot_id: "snapshot:s" },
    freshness: { source: "canonical", latest_message_timestamp: NOW },
    rows: [
      { session_id: "session_1", message_id: "m1", after: NOW, limit: 50 },
      { session_id: "session_1", message_id: "m2", after: NOW, limit: 50 },
    ],
    ...overrides,
  };
}

function makeThreadView(overrides = {}) {
  return {
    conversationId: "conversation_001",
    state: "ready",
    messages: [
      { messageId: "m1", role: "user", displayText: "请查找最近的证据", createdAt: NOW, sourceRef: "session_1" },
      { messageId: "m2", role: "assistant", displayText: "已检索已授权资料。", createdAt: NOW, sourceRef: "session_1", evidenceRefs: ["ev_1"] },
    ],
    pagination: { hasMore: false },
    truncated: false,
    freshness: {
      source: { checkedAt: NOW, backlog: 0 },
      canonical: { checkedAt: NOW, backlog: 2 },
      status: "current",
    },
    updatedAt: NOW,
    ...overrides,
  };
}

function makeRecentItem(overrides = {}) {
  return {
    conversationId: "conversation_001",
    title: "近期证据回顾",
    projectScopeId: "project_scope_alpha",
    lastActivityAt: NOW,
    freshness: { status: "current" },
    selected: false,
    ...overrides,
  };
}

function makeScopeList(overrides = {}) {
  return {
    items: [
      { project_scope_id: "project_scope_alpha", label: "Alpha", thread_count: 3, last_activity_at: NOW, freshness: { status: "current" } },
      { project_scope_id: "project_scope_beta", label: "Beta", thread_count: 0, last_activity_at: NOW, freshness: { status: "unknown" } },
    ],
    ...overrides,
  };
}

function makeEmptySession() {
  return {
    session: { session_id: "session_2", project_scope_id: "project_scope_alpha", created_at: NOW, status: "empty" },
    thread: {
      conversationId: "conversation_002", state: "empty", messages: [],
      pagination: { hasMore: false }, truncated: false,
      freshness: { status: "unknown" }, updatedAt: NOW,
    },
  };
}

function makeAnswer(overrides = {}) {
  return {
    role: "assistant",
    displayText: "已基于已授权资料回答。",
    status: "succeeded",
    disclosures: {
      basis: { sourceCount: 2, sourceIdentities: ["conversation_001", "evidence:0123456789abcdef"] },
      freshness: {
        sourceLeg: { checkedAt: NOW, backlog: 0 },
        canonicalLeg: { checkedAt: NOW, backlog: 2 },
        status: "current",
      },
      limitations: "结论不覆盖未授权或未索引的资料范围。",
    },
    toolRow: {
      skillName: "knowledge.research",
      effect: "read-only",
      resultStatus: "succeeded",
      receiptCount: 1,
      receipts: [makeSqliteReceipt()],
    },
    ...overrides,
  };
}

function makeReviewReceipt(overrides = {}) {
  return {
    candidate_id: "candidate_001",
    action: "accept",
    status: "conflict_disposition_required",
    expected_version: 2,
    high_impact: true,
    conflict_count: 1,
    conflict_disposition: null,
    receipt_id: "review:abcdef",
    projection_version: 3,
    ...overrides,
  };
}

function makeProjection(overrides = {}) {
  return {
    projection_id: "projection_001",
    version: 3,
    provenance_class: "inference",
    scope: "project_scope_alpha",
    valid_from: NOW,
    valid_to: "2026-08-16T00:00:00.000Z",
    observed_at: NOW,
    confidence: 0.72,
    uncertainty: 0.15,
    supporting_evidence_count: 2,
    conflicting_evidence_count: 1,
    evidence_refs: ["ev_1", "ev_2"],
    conflicts: [{ ref: "ref:conflict", disposition: "coexist_by_context" }],
    supersession: { superseded_by: null },
    freshness: { status: "current" },
    limitations: ["只代表已授权、已索引范围"],
    status: "active",
    ...overrides,
  };
}

function makeProactiveState(overrides = {}) {
  return {
    scope: "project",
    active: true,
    quiet: { active: true, quiet_until: "22:00" },
    categories: {
      sync: { enabled: true, scope: "project" },
      briefing: { enabled: false, scope: "global" },
      "reflection-candidate": { enabled: true, scope: "project" },
    },
    clusters: [{
      item_id: "proactive_item_001",
      merged_count: 3,
      evidence_refs: ["ev_1", "ev_2", "ev_3"],
      support_count: 2,
      conflict_count: 1,
      status: "pending",
    }],
    feedback: { feedback_id: "feedback_001" },
    ...overrides,
  };
}

function makePaletteInput(overrides = {}) {
  return {
    source: "ctrlOrCmd+k",
    commands: ["receipt.open", "proactive.manage"],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Injected bridge spy: only the 15 named methods exist. Any attempt by the
// view-model to use a generic transport (fetch/invoke/localStorage/...) fails.
// ---------------------------------------------------------------------------
function makeMockBridge(overrides = {}) {
  const calls = [];
  const bridge = {};
  for (const method of BRIDGE_METHODS) {
    bridge[method] = (value) => {
      calls.push({ method, value });
      if (typeof overrides[method] === "function") return overrides[method](value);
      return { ok: true, status: "ok", data: null };
    };
  }
  return { bridge, calls };
}

function assertOnlyNamedMethods(calls) {
  assert.ok(calls.every((call) => BRIDGE_METHODS.includes(call.method)), "view-model may only call named bridge methods");
}

// ===========================================================================
// R1: startup navigation reads
// ===========================================================================
test("R1: startup view-model calls exactly the three named navigation reads and returns safe copies", () => {
  assert.ok(appModule, viewModelMissing());
  const thread = makeThreadView();
  const recent = { items: [makeRecentItem()] };
  const scopes = makeScopeList();
  const { bridge, calls } = makeMockBridge({
    getLastConversation: () => toSafeEnvelope({ ok: true, status: "ok", data: thread }),
    listRecentConversations: () => toSafeEnvelope({ ok: true, status: "ok", data: recent }),
    listProjectScopes: () => toSafeEnvelope({ ok: true, status: "ok", data: scopes }),
  });

  const result = appModule.navigateStartup(bridge);
  assert.equal(result.schema, RENDERER_VIEW_MODEL);
  assert.deepEqual(calls.map((call) => call.method), ["getLastConversation", "listRecentConversations", "listProjectScopes"]);
  assertOnlyNamedMethods(calls);
  assert.equal(result.ok, true);

  // Safe copy: mutating the view model must not reach the bridge fixture data.
  result.last.thread.messages[0].displayText = "MUTATED";
  result.scopes[0].label = "MUTATED";
  result.recent[0].title = "MUTATED";
  assert.notEqual(thread.messages[0].displayText, "MUTATED", "view model must be a deep copy of the bridge response");
  assert.notEqual(scopes.items[0].label, "MUTATED");
  assert.notEqual(recent.items[0].title, "MUTATED");
  // The view-model output itself never carries forbidden fields.
  assert.ok(!containsForbiddenFields(result), "startup view model must stay within the safe projection");
});

// ===========================================================================
// R2: empty / stale / partial / paginated states stay truthful (safe copy)
// ===========================================================================
test("R2: navigation view-models preserve empty/stale/partial/paginated truth and never fake current", () => {
  assert.ok(appModule, viewModelMissing());

  // Empty thread (new/runtime-scoped) stays empty.
  const emptyThread = makeThreadView({ state: "empty", messages: [], freshness: { status: "unknown" } });
  const { bridge: b1, calls: c1 } = makeMockBridge({
    getLastConversation: () => toSafeEnvelope({ ok: true, status: "ok", data: emptyThread }),
    listRecentConversations: () => toSafeEnvelope({ ok: true, status: "ok", data: { items: [] } }),
    listProjectScopes: () => toSafeEnvelope({ ok: true, status: "ok", data: { items: [] } }),
  });
  const startup = appModule.navigateStartup(b1);
  assert.equal(startup.last.state, "empty", "empty thread state must be preserved");
  assertOnlyNamedMethods(c1);

  // Partial + paginated thread read is preserved (stable IDs + truncation).
  const partial = makeThreadView({
    state: "partial",
    messages: [{ messageId: "m1", role: "assistant", displayText: "部分结果", createdAt: NOW }],
    pagination: { hasMore: true, nextCursor: "cursor_9" },
    truncated: true,
  });
  const { bridge: b2 } = makeMockBridge({
    selectConversation: () => toSafeEnvelope({ ok: true, status: "ok", data: partial }),
  });
  const selected = appModule.selectConversation(b2, { conversationId: "conversation_001" });
  assert.equal(selected.thread.state, "partial");
  assert.equal(selected.thread.pagination.hasMore, true);
  assert.equal(selected.thread.pagination.nextCursor, "cursor_9");
  assert.equal(selected.thread.truncated, true);
  assert.equal(selected.thread.messages[0].messageId, "m1");

  // Stale scope rows keep an explicit unknown/stale status, never current.
  const staleScopes = makeScopeList({ items: [
    { project_scope_id: "project_scope_alpha", label: "Alpha", thread_count: 3, last_activity_at: NOW, freshness: { status: "stale" } },
  ] });
  const { bridge: b3 } = makeMockBridge({ listProjectScopes: () => toSafeEnvelope({ ok: true, status: "ok", data: staleScopes }) });
  const scopesVm = appModule.listScopes(b3);
  assert.equal(scopesVm.items[0].freshness.status, "stale", "a stale scope must never be labelled current");
});

// ===========================================================================
// R3: new conversation -> empty Kernel Session metadata only, no history
// ===========================================================================
test("R3: newConversation returns only empty Kernel Session metadata and an empty view, never canonical history", () => {
  assert.ok(appModule, viewModelMissing());
  const empty = makeEmptySession();
  const { bridge, calls } = makeMockBridge({
    newConversation: () => toSafeEnvelope({ ok: true, status: "ok", data: empty }),
  });

  const result = appModule.newConversation(bridge, { projectScopeId: "project_scope_alpha" });
  assert.deepEqual(calls.map((call) => call.method), ["newConversation"]);
  assert.equal(calls[0].value.projectScopeId, "project_scope_alpha");
  assertOnlyNamedMethods(calls);
  assert.equal(result.schema, RENDERER_VIEW_MODEL);
  assert.equal(result.ok, true);

  // Session is ONLY governed empty metadata: sessionId/projectScopeId/createdAt/status.
  assert.deepEqual(result.session, {
    sessionId: "session_2",
    projectScopeId: "project_scope_alpha",
    createdAt: NOW,
    status: "empty",
  });
  assert.equal(result.thread.state, "empty", "new session thread view must be empty");
  assert.deepEqual(result.thread.messages, []);
  // The new session must never be labelled canonical history.
  assert.equal(result.canonicalHistory, false);
  assert.ok(!JSON.stringify(result).includes("canonical_history"), "new session must not claim canonical history");
});

// ===========================================================================
// R4: no canonical mutation / persistence, truthful non-success envelopes
// ===========================================================================
test("R4: navigation view-models never mutate canonical data, persist nothing, and stay truthful on non-success", () => {
  assert.ok(appModule, viewModelMissing());

  // Pre-binding ROUTE_PROVIDER_UNAVAILABLE must not fabricate any scope/session.
  const { bridge: b1, calls: c1 } = makeMockBridge({
    getLastConversation: () => ROUTE_PROVIDER_UNAVAILABLE,
    listRecentConversations: () => ROUTE_PROVIDER_UNAVAILABLE,
    listProjectScopes: () => ROUTE_PROVIDER_UNAVAILABLE,
  });
  const unavailable = appModule.navigateStartup(b1);
  assert.equal(unavailable.ok, false, "unavailable providers must not claim success");
  assert.equal(unavailable.last.state, "unavailable");
  assert.equal(unavailable.last.status, "route_provider_unavailable");
  assert.equal(unavailable.recentStatus, "route_provider_unavailable");
  assert.equal(unavailable.scopesStatus, "route_provider_unavailable");
  assert.deepEqual(unavailable.recent, [], "no fabricated recent list");
  assert.deepEqual(unavailable.scopes, [], "no fabricated scope list");
  assertOnlyNamedMethods(c1);

  // selectScope on a denied/foreign scope stays denied with no selected scope.
  const { bridge: b2 } = makeMockBridge({
    selectProjectScope: () => toSafeEnvelope({ ok: false, status: "denied", error: { code: "foreign_id" } }),
  });
  const denied = appModule.selectScope(b2, { projectScopeId: "project_scope_999" });
  assert.equal(denied.ok, false);
  assert.equal(denied.status, "denied");
  assert.equal(denied.selectedScope, null, "a denied scope must not fabricate a selected scope");

  // newConversation before providers bind: no fabricated session at all.
  const { bridge: b3 } = makeMockBridge({ newConversation: () => ROUTE_PROVIDER_UNAVAILABLE });
  const noSession = appModule.newConversation(b3, { projectScopeId: "project_scope_alpha" });
  assert.equal(noSession.ok, false);
  assert.equal(noSession.session, null, "no session metadata may be fabricated before the provider binds");

  // No persistence/transport surface may appear in any view-model output.
  const outputs = JSON.stringify([unavailable, denied, noSession, appModule.listScopes({ listProjectScopes: () => ROUTE_PROVIDER_UNAVAILABLE })]);
  for (const token of ["localStorage", "sessionStorage", "indexedDB", "ipcRenderer", "fetch(", "sendBeacon", "disk", "persist"]) {
    assert.ok(!outputs.includes(token), `view model must not expose a ${token} persistence/transport surface`);
  }
});

// ===========================================================================
// R5: SQLite card labels + exactly server statement_display
// ===========================================================================
test("R5: SQLite card expansion is labelled 受控查询/已执行的脱敏 allowlisted statement and renders exactly statement_display", () => {
  assert.ok(appModule, viewModelMissing());
  const receipt = makeSqliteReceipt();
  const card = appModule.expandSqliteCard(receipt);
  assert.equal(card.schema, RENDERER_VIEW_MODEL);
  assert.equal(card.ok, true);
  assert.equal(card.cardTitle, "SQLite · 只读查询");
  assert.equal(card.expansionTitle, "受控查询");
  assert.equal(card.statementLabel, "已执行的脱敏 allowlisted statement");
  // The expansion surface renders EXACTLY the server-derived display.
  assert.equal(card.statementDisplay, receipt.statement_display);
  assert.equal(card.queryId, QUERY_ID);
  assert.equal(card.descriptorVersion, DESCRIPTOR_VERSION);
  assert.equal(card.queryChecksum, receipt.query_checksum);
  assert.equal(card.rowCount, 2);
  assert.equal(card.durationMs, 3);
  assert.equal(card.truncated, false);
  assert.equal(card.receiptId, receipt.receipt_id);
  assert.equal(card.databaseId, receipt.database_id);
});

// ===========================================================================
// R6: checksum binding rejects tamper / renderer-supplied display
// ===========================================================================
test("R6: statement_display renders only after checksum/query/version/name-set validation; tamper rejects", () => {
  assert.ok(appModule, viewModelMissing());
  const original = makeSqliteReceipt();

  // Valid receipt: exactly the bound display.
  const valid = appModule.validateStatementDisplay(original);
  assert.equal(valid.ok, true);
  assert.equal(valid.display, original.statement_display);

  // Tampered display (checksum unchanged) -> reject, never render the tampered text.
  const tamperedDisplay = makeSqliteReceipt({ statement_display: STATEMENT_DISPLAY.replace("limit)", "extra)") });
  const badDisplay = appModule.validateStatementDisplay(tamperedDisplay);
  assert.equal(badDisplay.ok, false, "tampered statement_display must be rejected");
  const card = appModule.expandSqliteCard(tamperedDisplay);
  assert.equal(card.ok, false, "a tampered receipt must not render");
  assert.equal(card.statementDisplay, null, "tampered display must never be rendered");

  // Tampered query ID / version / parameter-name set -> reject.
  const badQuery = makeSqliteReceipt({ query_id: "conversation.evidence_messages.v9" });
  assert.equal(appModule.validateStatementDisplay(badQuery).ok, false, "tampered query id must reject");
  const badVersion = makeSqliteReceipt({ version: "9.9.9" });
  assert.equal(appModule.validateStatementDisplay(badVersion).ok, false, "tampered version must reject");
  const badNames = makeSqliteReceipt({ parameter_names: ["session_id", "after", "secret_extra"] });
  assert.equal(appModule.validateStatementDisplay(badNames).ok, false, "changed parameter-name set must reject");

  // A renderer-supplied display is impossible by contract: the function takes
  // only the receipt and never accepts an override argument.
  const overridden = appModule.validateStatementDisplay(original, "renderer-chosen display");
  assert.equal(overridden.display, original.statement_display, "renderer-supplied display override must be ignored");
});

// ===========================================================================
// R7: raw SQL / physical schema / parameter values / sentinels reject
// ===========================================================================
test("R7: controlled-query card rejects raw SQL, physical schema, parameter values and sentinel leakage", () => {
  assert.ok(appModule, viewModelMissing());
  const hostile = makeSqliteReceipt({
    physical_table: "agent_conversations",
    column_names: ["session_id", "message_body"],
    sql: "SELECT body FROM agent_conversations WHERE secret=1",
    parameter_values: [SECRET_SENTINEL],
    raw_body: RAW_BODY_SENTINEL,
    statement_display: `SELECT * FROM agent_conversations -- ${SECRET_SENTINEL}`,
  });
  const rejected = appModule.expandSqliteCard(hostile);
  assert.equal(rejected.ok, false, "a receipt carrying physical/raw/sentinel material must reject");
  const serialized = JSON.stringify(rejected);
  assert.ok(!serialized.includes(SECRET_SENTINEL), "secret sentinel must never reach the view model");
  assert.ok(!serialized.includes(RAW_BODY_SENTINEL), "raw body sentinel must never reach the view model");
  assert.ok(!serialized.includes("SELECT"), "raw SQL must never be rendered");
  assert.ok(!serialized.includes("agent_conversations"), "physical schema must never be rendered");
});

// ===========================================================================
// R8: answer disclosures + collapsed tool row
// ===========================================================================
test("R8: answers disclose 依据/新鲜度/限制 and collapse tool rows without leaking thinking/raw bodies", () => {
  assert.ok(appModule, viewModelMissing());
  const answer = makeAnswer();
  const vm = appModule.answerViewModel(answer);
  assert.equal(vm.schema, RENDERER_VIEW_MODEL);
  assert.equal(vm.ok, true);
  assert.equal(vm.status, "succeeded");
  assert.equal(vm.isSuccess, true);

  // Three default-collapsed disclosure blocks with the exact UI-SPEC labels.
  assert.deepEqual(Object.keys(vm.disclosures).sort(), ["basis", "freshness", "limitations"]);
  assert.equal(vm.disclosures.basis.label, "依据");
  assert.equal(vm.disclosures.freshness.label, "新鲜度");
  assert.equal(vm.disclosures.limitations.label, "限制");
  for (const block of Object.values(vm.disclosures)) assert.equal(block.collapsed, true, "disclosures must be default-collapsed");

  // Dual freshness is two separate legs, never a scalar current/complete claim.
  assert.equal(typeof vm.disclosures.freshness.sourceLeg.checkedAt, "string");
  assert.equal(typeof vm.disclosures.freshness.sourceLeg.backlog, "number");
  assert.equal(typeof vm.disclosures.freshness.canonicalLeg.checkedAt, "string");
  assert.equal(vm.disclosures.freshness.canonicalLeg.backlog, 2);
  assert.ok(!("current" in vm.disclosures.freshness && typeof vm.disclosures.freshness.current === "string"), "freshness must not be flattened to a scalar");

  // Tool row is collapsed with skill/effect/status/receipt count only.
  assert.equal(vm.toolRow.label, "已使用受限能力");
  assert.equal(vm.toolRow.collapsed, true);
  assert.equal(vm.toolRow.skillName, "knowledge.research");
  assert.equal(vm.toolRow.effect, "read-only");
  assert.equal(vm.toolRow.resultStatus, "succeeded");
  assert.equal(vm.toolRow.receiptCount, 1);
  assert.equal(vm.liveRegion, "polite");

  // Thinking/raw tool/provider bodies and secrets are never disclosed.
  const tainted = makeAnswer({
    thinking: "private chain of thought",
    tool_body: RAW_BODY_SENTINEL,
    provider_body: RAW_BODY_SENTINEL,
    credential: SECRET_SENTINEL,
  });
  const safeVm = appModule.answerViewModel(tainted);
  const serialized = JSON.stringify(safeVm);
  assert.ok(!serialized.includes(SECRET_SENTINEL), "secret must not leak through answer disclosure");
  assert.ok(!serialized.includes(RAW_BODY_SENTINEL), "raw tool/provider body must not leak");
  assert.ok(!serialized.includes("private chain"), "thinking must not leak");
});

// ===========================================================================
// R9: cancellation / outcome_unknown truth
// ===========================================================================
test("R9: cancelled and outcome_unknown turn states never render as success", () => {
  assert.ok(appModule, viewModelMissing());

  const cancelled = appModule.answerViewModel(makeAnswer({ status: "cancelled" }));
  assert.equal(cancelled.ok, false);
  assert.equal(cancelled.isSuccess, false, "a cancelled turn must never render as success");
  assert.equal(cancelled.status, "cancelled");
  assert.equal(cancelled.statusText, "已取消：没有写入，也没有保留部分结果。");
  assert.equal(cancelled.errorRole, "alert");

  const unknown = appModule.answerViewModel(makeAnswer({ status: "outcome_unknown" }));
  assert.equal(unknown.isSuccess, false, "outcome_unknown must never render as success");
  assert.equal(unknown.status, "outcome_unknown");
  assert.ok(unknown.statusText.includes("reconcile") || unknown.statusText.includes("不确定结果"),
    "outcome_unknown must surface a reconcile hint");

  const error = appModule.answerViewModel(makeAnswer({ status: "error", error: { code: "internal_error" } }));
  assert.equal(error.isSuccess, false);
  assert.equal(error.errorRole, "alert");
  assert.ok(!JSON.stringify(error).includes(RAW_BODY_SENTINEL));
});

// ===========================================================================
// R10: per-item Candidate review with strict four-option conflict modal
// ===========================================================================
test("R10: Candidate review is per-item with the strict four-option conflict modal and no batch acceptance", () => {
  assert.ok(appModule, viewModelMissing());
  const vm = appModule.candidateReviewViewModel(makeReviewReceipt());
  assert.equal(vm.ok, true);
  assert.equal(vm.cardTitle, "待审核候选");
  assert.equal(vm.disclosure, "AI 生成的候选，尚未成为事实");
  assert.deepEqual(vm.actions, ["查看候选证据", "编辑候选", "接受候选", "忽略候选"]);
  assert.equal(vm.hasBatchAccept, false, "batch acceptance must never exist");
  assert.equal(vm.candidateId, "candidate_001");
  assert.equal(vm.receiptId, "review:abcdef");

  // Explicit confirmation modal copy per UI-SPEC.
  assert.deepEqual(vm.confirmModal, {
    title: "接受候选？",
    body: "这会把审核版本送入现有受控 Candidate/canonical 流程，并更新派生个人模型投影；不会把 AI 原稿直接写成事实。",
    acceptLabel: "确认接受候选",
    cancelLabel: "返回候选修改",
  });

  // Conflict modal exposes exactly the four value/label/consequence triples.
  const options = vm.conflictModal.options.map((option) => [option.value, option.label, option.consequence]);
  assert.deepEqual(options, [
    ["keep_existing", "保留旧结论", "保持既有受控结论不变，仅保留本次审核与证据"],
    ["replace_existing", "用新结论取代", "仅经受控审核路径将审核版本作为后续派生投影的候选，不直接写成事实"],
    ["coexist_by_context", "按情境共存", "保留两个有来源的情境化结论，不宣称单一通用结论"],
    ["defer_judgment", "暂不判断", "不更新派生投影，保留证据与审核反馈待后续处理"],
  ]);

  // Unknown/missing disposition must reject.
  for (const disposition of ["replace_all", "accept_all", "unknown", ""]) {
    const bad = makeReviewReceipt({ conflict_disposition: disposition });
    let rejected = false;
    try {
      const out = appModule.candidateReviewViewModel(bad);
      rejected = out !== null && typeof out === "object" && out.ok === false;
    } catch {
      rejected = true;
    }
    assert.ok(rejected, `unknown conflict disposition ${JSON.stringify(disposition)} must reject`);
  }
});

// ===========================================================================
// R11: versioned derived Projection, not a personal fact
// ===========================================================================
test("R11: Projection view-model stays a corrigible derived context, never a personal fact", () => {
  assert.ok(appModule, viewModelMissing());
  const vm = appModule.projectionViewModel(makeProjection());
  assert.equal(vm.schema, RENDERER_VIEW_MODEL);
  assert.equal(vm.label, "派生个人模型");
  assert.equal(vm.projectionId, "projection_001");
  assert.equal(vm.version, 3);
  assert.equal(vm.provenanceClass, "inference");
  assert.equal(vm.confidence, 0.72);
  assert.equal(vm.uncertainty, 0.15);
  assert.equal(vm.supportCount, 2);
  assert.equal(vm.conflictCount, 1);
  assert.equal(vm.corrigible, true, "projection must stay corrigible");
  assert.equal(vm.supersession.superseded_by, null);
  assert.equal(vm.freshness.status, "current");
  assert.ok(vm.limitations.length > 0, "projection must disclose limitations");

  const serialized = JSON.stringify(vm);
  assert.ok(!serialized.includes("个人事实"), "projection must never be labelled a personal fact");
  assert.ok(!serialized.includes("稳定人格"), "projection must never be a stable personality label");
});

// ===========================================================================
// R12: deterministic proactive quiet/control/cluster/dismissal semantics
// ===========================================================================
test("R12: proactive view-model keeps deterministic quiet/control/cluster/dismissal semantics", () => {
  assert.ok(appModule, viewModelMissing());
  const vm = appModule.proactiveViewModel(makeProactiveState());
  assert.equal(vm.schema, RENDERER_VIEW_MODEL);
  // Quiet badge echoes 静默至 HH:MM from the saved quiet hours.
  assert.deepEqual(vm.quiet, { active: true, quietUntilLabel: "静默至 22:00" });
  // Exactly the three deterministic categories with scope per category.
  assert.deepEqual(Object.keys(vm.controls.categories).sort(), ["briefing", "reflection-candidate", "sync"]);
  assert.equal(vm.controls.categories.sync.label, "同步");
  assert.equal(vm.controls.categories.briefing.label, "简报");
  assert.equal(vm.controls.categories["reflection-candidate"].label, "反思候选");
  // One card per evidence cluster with a merged-count disclosure.
  assert.equal(vm.cluster.mergedLabel, "已合并 3 条同簇证据");
  assert.equal(vm.cluster.itemId, "proactive_item_001");
  assert.equal(vm.cluster.supportCount, 2);
  assert.equal(vm.cluster.conflictCount, 1);
  // Append-only dismissal feedback identity is retained.
  assert.deepEqual(vm.dismissal, { feedbackId: "feedback_001" });
  // Escalation ladder is 静默 badge -> 行内卡 -> 抽屉 -> 需要确认才 modal.
  assert.deepEqual(vm.escalation, ["静默 badge", "行内卡", "抽屉", "需要确认才 modal"]);

  const serialized = JSON.stringify(vm);
  assert.ok(!serialized.includes("已调度"), "proactive UI must not claim scheduling");
  assert.ok(!serialized.includes("自动执行"), "proactive UI must not claim autonomous execution");
});

// ===========================================================================
// R13: two-action command palette (Ctrl/Cmd+K)
// ===========================================================================
test("R13: Ctrl/Cmd+K palette exposes exactly receipt.open and proactive.manage", () => {
  assert.ok(appModule, viewModelMissing());
  const vm = appModule.commandPaletteViewModel(makePaletteInput());
  assert.equal(vm.schema, RENDERER_VIEW_MODEL);
  assert.equal(vm.ok, true);
  assert.equal(vm.shortcut, "Ctrl/Cmd+K");
  assert.deepEqual(vm.commands, [
    { id: "receipt.open", label: "查看 receipt" },
    { id: "proactive.manage", label: "管理主动提醒" },
  ]);

  // Any command outside the fixed two-action set rejects.
  for (const commands of [
    ["receipt.open", "proactive.manage", "admin.exec"],
    ["receipt.open"],
    ["proactive.manage", "receipt.open"],
    ["shell.escape"],
  ]) {
    let rejected = false;
    try {
      const out = appModule.commandPaletteViewModel(makePaletteInput({ commands }));
      rejected = out !== null && typeof out === "object" && out.ok === false;
    } catch {
      rejected = true;
    }
    assert.ok(rejected, `palette commands ${JSON.stringify(commands)} must reject`);
  }
});

// ===========================================================================
// R14: focus trap, Esc order, focus restoration
// ===========================================================================
test("R14: layer manager traps focus, Esc closes palette->drawer->modal, and focus returns to the trigger", () => {
  assert.ok(appModule, viewModelMissing());
  const layers = appModule.createLayerManager();
  const paletteTrigger = { id: "command-palette-trigger" };
  const drawerTrigger = { id: "receipt-drawer-trigger" };
  const modalTrigger = { id: "conflict-modal-trigger" };

  layers.open({ id: "command-palette", trigger: paletteTrigger });
  layers.open({ id: "evidence-drawer", trigger: drawerTrigger });
  layers.open({ id: "conflict-modal", trigger: modalTrigger });

  // Focus trap: the topmost layer owns keyboard focus until it closes.
  assert.equal(layers.peek().id, "conflict-modal");
  assert.equal(layers.depth(), 3);

  // Esc closes the top layer first and returns focus to ITS trigger.
  assert.deepEqual(layers.close(), { id: "conflict-modal", trigger: modalTrigger });
  assert.equal(layers.peek().id, "evidence-drawer");
  assert.deepEqual(layers.close(), { id: "evidence-drawer", trigger: drawerTrigger });
  // Palette closes last.
  assert.deepEqual(layers.close(), { id: "command-palette", trigger: paletteTrigger });
  assert.equal(layers.depth(), 0);
});

// ===========================================================================
// R15: no generic IPC / fetch / storage / body logging transport
// ===========================================================================
test("R15: renderer source contains no generic IPC/fetch/storage transport or selected-text logging", () => {
  assert.ok(appModule, viewModelMissing());
  const source = readFileSync(new URL("../src/renderer/app.mjs", import.meta.url), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
  const forbidden = [
    "fetch(",
    "XMLHttpRequest",
    "WebSocket(",
    "ipcRenderer",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "navigator.sendBeacon",
    "console.log(",
    "console.info(",
  ];
  for (const token of forbidden) {
    assert.ok(!source.includes(token), `renderer source must not use ${token}`);
  }
  assert.ok(source.includes("window.harness") || source.includes("harness"), "renderer must reach authorities only through the named harness bridge");
});

// ---------------------------------------------------------------------------
// R16: settings view-model projects provider settings safely.
// ---------------------------------------------------------------------------
test("R16: settingsViewModel projects provider settings without exposing the apiKey", () => {
  assert.ok(appModule, viewModelMissing());
  const view = appModule.settingsViewModel({
    schema: "pi-provider-config-v1",
    provider: "openai-compatible",
    mode: "openai-compatible",
    base_url: "https://example.com/v1",
    model: "test-model",
    api_key_present: true,
    secret_path: "var/secrets/pi-provider.api.dpapi.txt",
  });
  assert.equal(view.ok, true);
  assert.equal(view.provider, "openai-compatible");
  assert.equal(view.providerLabel, "通用 OpenAI 兼容");
  assert.equal(view.baseUrl, "https://example.com/v1");
  assert.equal(view.model, "test-model");
  assert.equal(view.apiKeyPresent, true);
  assert.ok(!("apiKeyValue" in view), "view-model never carries the key value");

  // Missing/unset settings fall back to replay and no key.
  const empty = appModule.settingsViewModel(null);
  assert.equal(empty.provider, "replay");
  assert.equal(empty.apiKeyPresent, false);
  assert.equal(empty.baseUrl, "");
});
