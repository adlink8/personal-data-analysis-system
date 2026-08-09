// app.mjs
//
// Phase 61 Plan 61-11 Task 2 (GREEN): conversation-first desktop renderer for
// the local Electron shell. This module is a dependency-free presentation
// layer:
//
//   - All 15 exported view-model functions are pure and importable under plain
//     Node so the renderer contract tests run without Electron or a network.
//   - All DOM work happens only inside `startRenderer`, which is invoked solely
//     when a document/window actually exists.
//   - The only authority surface is the named preload bridge `window.harness`;
//     there is no generic transport or storage surface.
//   - Selected display text lives only in ephemeral renderer memory and is
//     never persisted, logged as body text, or written to a conversation store.
//   - New sessions render as empty/runtime-scoped views; they are never
//     labelled canonical history.
//   - SQLite cards render only the checksum-validated server `statement_display`
//     (single approved descriptor); raw SQL, physical schema, parameter values
//     and renderer-supplied display text are rejected by construction.
//
// The checksum digest below is a synchronous browser-safe SHA-256 over the
// recursive-key-sort compact JSON used by the Python authority
// (`evidence_sqlite_tool.py::query_checksum`) and by the shared desktop schema
// `canonicalJson`, so the renderer validates the exact same binding without
// importing any Node-only module.

export const RENDERER_VIEW_MODEL = "pi-renderer-view-model-v1";
const THREAD_VIEW_SCHEMA = "pi-conversation-thread-view-v1";

// The single approved Phase 61 descriptor (Plan 61-04/61-05). The parameter
// set is stored sorted because that is the ordering bound into the checksum;
// the statement display keeps the descriptor's declared parameter order.
const APPROVED_QUERY = Object.freeze({
  queryId: "conversation.evidence_messages.v1",
  version: "1.0.0",
  parameterNames: Object.freeze(["after", "limit", "session_id"]),
  statementDisplay: "conversation.evidence_messages.v1(session_id, after, limit)",
});

const NON_SUCCESS_STATUSES = new Set([
  "cancelled", "outcome_unknown", "error", "failed", "rejected", "denied",
  "stale", "cancelled_requested", "pending", "route_provider_unavailable",
]);

// ---------------------------------------------------------------------------
// Checksum binding: synchronous browser-safe SHA-256 (FIPS 180-4) over the
// shared canonical-JSON serialization. Matches Python `_canonical_json` +
// `query_checksum` byte-for-byte.
// ---------------------------------------------------------------------------
const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]);

function rotr(value, shift) {
  return ((value >>> shift) | (value << (32 - shift))) >>> 0;
}

function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const length = data.length;
  const bitLength = length * 8;
  const paddedLength = (((length + 8) >> 6) + 1) << 6;
  const padded = new Uint8Array(paddedLength);
  padded.set(data);
  padded[length] = 0x80;
  const view = new DataView(padded.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000));
  view.setUint32(paddedLength - 4, bitLength >>> 0);
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const w = new Uint32Array(64);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(offset + i * 4);
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }
    let a = h[0];
    let b = h[1];
    let c = h[2];
    let d = h[3];
    let e = h[4];
    let f = h[5];
    let g = h[6];
    let hh = h[7];
    for (let i = 0; i < 64; i += 1) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const t1 = (hh + s1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const t2 = (s0 + maj) >>> 0;
      hh = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    h[0] = (h[0] + a) >>> 0;
    h[1] = (h[1] + b) >>> 0;
    h[2] = (h[2] + c) >>> 0;
    h[3] = (h[3] + d) >>> 0;
    h[4] = (h[4] + e) >>> 0;
    h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0;
    h[7] = (h[7] + hh) >>> 0;
  }
  let out = "";
  for (let i = 0; i < 8; i += 1) out += h[i].toString(16).padStart(8, "0");
  return out;
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function checksumDigest(value) {
  return sha256Hex(canonicalJson(value));
}

// ---------------------------------------------------------------------------
// Safe copy helpers (plain JSON data only).
// ---------------------------------------------------------------------------
function cloneSafe(value) {
  if (Array.isArray(value)) return value.map(cloneSafe);
  if (value !== null && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value)) out[key] = cloneSafe(value[key]);
    return out;
  }
  return value;
}

function pickFields(object, keys) {
  const out = {};
  for (const key of keys) {
    if (object[key] !== undefined) out[key] = object[key];
  }
  return out;
}

// Bounded, primitive-only evidence rows. Nested raw bodies never cross into the
// view model; parameter values and secrets are not legitimate row fields.
function safeRows(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.slice(0, 100).map((row) => {
    if (row === null || typeof row !== "object") return {};
    const out = {};
    for (const [key, value] of Object.entries(row)) {
      if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        out[key] = value;
      }
    }
    return out;
  });
}

// ---------------------------------------------------------------------------
// ConversationThreadView projection: re-projects the already-sanitized server
// view onto the safe shape and deep-copies it so the renderer can never mutate
// canonical data or leak thinking/raw bodies through message fields.
// ---------------------------------------------------------------------------
const THREAD_STATES = new Set(["empty", "ready", "stale", "partial"]);
const FRESHNESS_STATUSES = new Set(["current", "stale", "unknown"]);

function normalizeThreadView(view) {
  const source = view ?? {};
  const messages = Array.isArray(source.messages) ? source.messages : [];
  const normalizedMessages = messages.map((message) => {
    const out = {
      messageId: message.messageId,
      role: message.role === "user" ? "user" : "assistant",
      displayText: message.displayText,
      createdAt: message.createdAt,
    };
    if (typeof message.sourceRef === "string") out.sourceRef = message.sourceRef;
    if (Array.isArray(message.evidenceRefs)) out.evidenceRefs = [...message.evidenceRefs];
    return out;
  });
  const pagination = { hasMore: source.pagination?.hasMore === true };
  if (typeof source.pagination?.nextCursor === "string") pagination.nextCursor = source.pagination.nextCursor;
  const freshness = {
    source: source.freshness?.source ? { ...source.freshness.source } : null,
    canonical: source.freshness?.canonical ? { ...source.freshness.canonical } : null,
    status: FRESHNESS_STATUSES.has(source.freshness?.status) ? source.freshness.status : "unknown",
  };
  return {
    schema: THREAD_VIEW_SCHEMA,
    conversationId: source.conversationId,
    state: THREAD_STATES.has(source.state) ? source.state : "ready",
    messages: normalizedMessages,
    pagination,
    truncated: source.truncated === true,
    freshness,
    updatedAt: source.updatedAt,
  };
}

// ---------------------------------------------------------------------------
// Envelope reading: a safe `{ok,status,error,data}` envelope from the named
// bridge stays truthful; a non-ok envelope never fabricates data.
// ---------------------------------------------------------------------------
function readEnvelope(envelope) {
  if (envelope !== null && typeof envelope === "object" && envelope.ok === true) {
    return {
      ok: true,
      status: typeof envelope.status === "string" ? envelope.status : "ok",
      data: envelope.data ?? null,
    };
  }
  return {
    ok: false,
    status: envelope !== null && typeof envelope === "object" && typeof envelope.status === "string"
      ? envelope.status
      : "error",
    data: null,
  };
}

// ---------------------------------------------------------------------------
// Navigation view-models
// ---------------------------------------------------------------------------

export function navigateStartup(bridge) {
  const last = readEnvelope(bridge.getLastConversation());
  const recent = readEnvelope(bridge.listRecentConversations());
  const scopes = readEnvelope(bridge.listProjectScopes());
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: last.ok && recent.ok && scopes.ok,
    last: { state: "unavailable", status: last.status },
    recent: [],
    recentStatus: recent.status,
    scopes: [],
    scopesStatus: scopes.status,
  };
  if (last.ok && last.data) {
    try {
      const thread = normalizeThreadView(last.data);
      out.last = { state: thread.state, status: last.status, thread };
    } catch {
      out.ok = false;
      out.last = { state: "unavailable", status: "invalid_thread" };
    }
  }
  if (recent.ok && Array.isArray(recent.data?.items)) {
    out.recent = recent.data.items.map(recentItemProjection);
  }
  if (scopes.ok && Array.isArray(scopes.data?.items)) {
    out.scopes = scopes.data.items.map(scopeItemProjection);
  }
  return out;
}

export function listScopes(bridge) {
  const envelope = readEnvelope(bridge.listProjectScopes());
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: envelope.ok,
    status: envelope.status,
    items: [],
  };
  if (envelope.ok && Array.isArray(envelope.data?.items)) {
    out.items = envelope.data.items.map(scopeItemProjection);
  }
  return out;
}

export function selectScope(bridge, { projectScopeId }) {
  const envelope = readEnvelope(bridge.selectProjectScope({ projectScopeId }));
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: envelope.ok,
    status: envelope.status,
    selectedScope: null,
    recentThreads: [],
  };
  if (envelope.ok && envelope.data && typeof envelope.data === "object") {
    const selected = envelope.data.selected_scope ?? envelope.data.selectedScope;
    if (selected && typeof selected === "object") {
      out.selectedScope = {
        projectScopeId: selected.project_scope_id ?? selected.projectScopeId,
        label: selected.label,
        threadCount: selected.thread_count ?? selected.threadCount,
        lastActivityAt: selected.last_activity_at ?? selected.lastActivityAt,
        freshness: selected.freshness ? cloneSafe(selected.freshness) : { status: "unknown" },
      };
    }
    const recentThreads = envelope.data.recent_threads ?? envelope.data.recentThreads;
    if (Array.isArray(recentThreads)) out.recentThreads = recentThreads.map(recentItemProjection);
  }
  return out;
}

export function newConversation(bridge, { projectScopeId }) {
  const envelope = readEnvelope(bridge.newConversation({ projectScopeId }));
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: envelope.ok,
    status: envelope.status,
    session: null,
    thread: null,
    canonicalHistory: false,
  };
  if (envelope.ok && envelope.data && typeof envelope.data === "object") {
    const session = envelope.data.session;
    if (session && typeof session === "object") {
      out.session = {
        sessionId: session.session_id,
        projectScopeId: session.project_scope_id,
        createdAt: session.created_at,
        status: session.status,
      };
    }
    const threadData = envelope.data.thread;
    if (threadData && typeof threadData === "object") {
      try {
        out.thread = normalizeThreadView(threadData);
      } catch {
        out.ok = false;
        out.thread = null;
      }
    }
  }
  return out;
}

export function selectConversation(bridge, { conversationId }) {
  const envelope = readEnvelope(bridge.selectConversation({ conversationId }));
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: envelope.ok,
    status: envelope.status,
    thread: null,
  };
  if (envelope.ok && envelope.data) {
    try {
      out.thread = normalizeThreadView(envelope.data);
    } catch {
      out.ok = false;
      out.status = "invalid_thread";
      out.thread = null;
    }
  }
  return out;
}

export function threadViewModel(view) {
  try {
    const thread = normalizeThreadView(view);
    return { schema: RENDERER_VIEW_MODEL, ok: true, status: "ok", thread };
  } catch {
    return { schema: RENDERER_VIEW_MODEL, ok: false, status: "invalid_thread", thread: null };
  }
}

// ---------------------------------------------------------------------------
// Scope / recent item projections (metadata only, safe copies).
// ---------------------------------------------------------------------------
function scopeItemProjection(item) {
  if (item === null || typeof item !== "object") {
    return { projectScopeId: null, label: null, threadCount: 0, lastActivityAt: null, freshness: { status: "unknown" } };
  }
  return {
    projectScopeId: item.project_scope_id,
    label: item.label,
    threadCount: item.thread_count,
    lastActivityAt: item.last_activity_at,
    freshness: item.freshness ? cloneSafe(item.freshness) : { status: "unknown" },
  };
}

function recentItemProjection(item) {
  if (item === null || typeof item !== "object") return {};
  return pickFields(item, ["conversationId", "title", "projectScopeId", "lastActivityAt", "selected", "freshness"]);
}

// ---------------------------------------------------------------------------
// Answer view-model: dual-leg freshness, default-collapsed disclosures,
// collapsed tool row, truthful cancel/outcome_unknown.
// ---------------------------------------------------------------------------
function legSummary(leg) {
  if (leg === null || typeof leg !== "object") return "未提供水位";
  return `检查于 ${leg.checkedAt ?? "?"}，积压 ${leg.backlog ?? 0}`;
}

function basisText(basis) {
  const count = typeof basis.sourceCount === "number"
    ? basis.sourceCount
    : (Array.isArray(basis.sourceIdentities) ? basis.sourceIdentities.length : 0);
  const identities = Array.isArray(basis.sourceIdentities) ? basis.sourceIdentities.join("、") : "";
  return `来源 ${count} 个${identities ? `：${identities}` : ""}`;
}

function freshnessText(freshness) {
  const parts = [];
  if (freshness.sourceLeg) parts.push(`source 水位 ${legSummary(freshness.sourceLeg)}`);
  if (freshness.canonicalLeg) parts.push(`canonical 水位 ${legSummary(freshness.canonicalLeg)}`);
  if (typeof freshness.status === "string") parts.push(`状态 ${freshness.status}`);
  return parts.join("；") || "未提供新鲜度";
}

function safeLeg(leg) {
  if (leg === null || typeof leg !== "object") return null;
  return {
    checkedAt: leg.checkedAt,
    backlog: leg.backlog,
  };
}

function buildDisclosures(disclosures) {
  const out = {};
  if (disclosures !== null && typeof disclosures === "object") {
    if (disclosures.basis && typeof disclosures.basis === "object") {
      out.basis = {
        label: "依据",
        collapsed: true,
        text: basisText(disclosures.basis),
      };
    }
    if (disclosures.freshness && typeof disclosures.freshness === "object") {
      const freshness = disclosures.freshness;
      out.freshness = {
        label: "新鲜度",
        collapsed: true,
        text: freshnessText(freshness),
        sourceLeg: safeLeg(freshness.sourceLeg),
        canonicalLeg: safeLeg(freshness.canonicalLeg),
        status: freshness.status,
      };
    }
    if (typeof disclosures.limitations === "string") {
      out.limitations = {
        label: "限制",
        collapsed: true,
        text: disclosures.limitations,
      };
    }
  }
  return out;
}

function buildToolRow(toolRow) {
  if (toolRow === null || typeof toolRow !== "object") {
    return {
      label: "已使用受限能力",
      collapsed: true,
      skillName: "未选择 Skill",
      effect: "read-only",
      resultStatus: "unknown",
      receiptCount: 0,
    };
  }
  const receiptCount = typeof toolRow.receiptCount === "number"
    ? toolRow.receiptCount
    : (Array.isArray(toolRow.receipts) ? toolRow.receipts.length : 0);
  return {
    label: "已使用受限能力",
    collapsed: true,
    skillName: typeof toolRow.skillName === "string" ? toolRow.skillName : "未选择 Skill",
    effect: typeof toolRow.effect === "string" ? toolRow.effect : "read-only",
    resultStatus: typeof toolRow.resultStatus === "string" ? toolRow.resultStatus : "unknown",
    receiptCount,
  };
}

function statusTextFor(status) {
  switch (status) {
    case "cancelled":
      return "已取消：没有写入，也没有保留部分结果。";
    case "outcome_unknown":
      return "操作结果不确定：需要 reconcile 核对后再继续。";
    case "error":
    case "failed":
      return "操作未完成：发生错误。没有发生未授权变更。请重试或查看系统状态。";
    default:
      return "操作未完成：没有发生未授权变更。请重试或查看系统状态。";
  }
}

export function answerViewModel(answer) {
  const status = answer !== null && typeof answer === "object" && typeof answer.status === "string"
    ? answer.status
    : "error";
  const isSuccess = !NON_SUCCESS_STATUSES.has(status);
  const out = {
    schema: RENDERER_VIEW_MODEL,
    ok: isSuccess,
    status,
    isSuccess,
    disclosures: buildDisclosures(answer?.disclosures),
    toolRow: buildToolRow(answer?.toolRow),
    liveRegion: isSuccess ? "polite" : "alert",
  };
  if (!isSuccess) {
    out.statusText = statusTextFor(status);
    out.errorRole = "alert";
    const errorCode = typeof answer?.error?.code === "string" ? answer.error.code : null;
    if (errorCode) out.errorCode = errorCode;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Controlled-query card: only the checksum-validated server statement_display.
// ---------------------------------------------------------------------------
export function validateStatementDisplay(receipt) {
  if (receipt === null || typeof receipt !== "object") {
    return { ok: false, code: "invalid_receipt" };
  }
  const queryId = receipt.query_id;
  const version = typeof receipt.version === "string" ? receipt.version : receipt.descriptor_version;
  const statementDisplay = receipt.statement_display;
  const names = Array.isArray(receipt.parameter_names) ? [...receipt.parameter_names].sort() : null;
  if (
    typeof queryId !== "string" || typeof version !== "string"
    || !names || typeof statementDisplay !== "string" || typeof receipt.query_checksum !== "string"
  ) {
    return { ok: false, code: "missing_binding_fields" };
  }
  const recomputed = checksumDigest({
    query_id: queryId,
    version,
    parameter_names: names,
    statement_display: statementDisplay,
  });
  if (recomputed !== receipt.query_checksum) {
    return { ok: false, code: "checksum_mismatch" };
  }
  // Only the single approved Phase 61 descriptor may render.
  if (queryId !== APPROVED_QUERY.queryId) return { ok: false, code: "unapproved_query" };
  if (version !== APPROVED_QUERY.version) return { ok: false, code: "unapproved_version" };
  if (names.join(",") !== APPROVED_QUERY.parameterNames.join(",")) return { ok: false, code: "unapproved_parameter_set" };
  if (statementDisplay !== APPROVED_QUERY.statementDisplay) return { ok: false, code: "display_mismatch" };
  return { ok: true, display: statementDisplay };
}

export function expandSqliteCard(receipt) {
  const base = {
    schema: RENDERER_VIEW_MODEL,
    cardTitle: "SQLite · 只读查询",
    expansionTitle: "受控查询",
    statementLabel: "已执行的脱敏 allowlisted statement",
  };
  const validation = validateStatementDisplay(receipt);
  if (!validation.ok) {
    return {
      ...base,
      ok: false,
      status: "rejected",
      statementDisplay: null,
      rows: [],
      rowCount: 0,
      durationMs: null,
      truncated: false,
      receiptId: null,
      databaseId: null,
      queryId: null,
      descriptorVersion: null,
      queryChecksum: null,
      freshness: null,
    };
  }
  return {
    ...base,
    ok: true,
    status: typeof receipt.status === "string" ? receipt.status : "ok",
    statementDisplay: validation.display,
    rows: safeRows(receipt.rows),
    rowCount: typeof receipt.row_count === "number" ? receipt.row_count : (Array.isArray(receipt.rows) ? receipt.rows.length : 0),
    durationMs: receipt.duration_ms,
    truncated: receipt.truncated === true,
    receiptId: receipt.receipt_id,
    databaseId: receipt.database_id,
    queryId: receipt.query_id,
    descriptorVersion: receipt.descriptor_version,
    queryChecksum: receipt.query_checksum,
    freshness: receipt.freshness ? cloneSafe(receipt.freshness) : null,
  };
}

// ---------------------------------------------------------------------------
// Candidate review: per-item, four-option conflict modal, no batch accept.
// ---------------------------------------------------------------------------
const CONFLICT_OPTIONS = Object.freeze([
  Object.freeze({
    value: "keep_existing",
    label: "保留旧结论",
    consequence: "保持既有受控结论不变，仅保留本次审核与证据",
  }),
  Object.freeze({
    value: "replace_existing",
    label: "用新结论取代",
    consequence: "仅经受控审核路径将审核版本作为后续派生投影的候选，不直接写成事实",
  }),
  Object.freeze({
    value: "coexist_by_context",
    label: "按情境共存",
    consequence: "保留两个有来源的情境化结论，不宣称单一通用结论",
  }),
  Object.freeze({
    value: "defer_judgment",
    label: "暂不判断",
    consequence: "不更新派生投影，保留证据与审核反馈待后续处理",
  }),
]);

const CANDIDATE_ACTIONS = Object.freeze(["查看候选证据", "编辑候选", "接受候选", "忽略候选"]);

export function candidateReviewViewModel(receipt) {
  if (receipt === null || typeof receipt !== "object") {
    return { schema: RENDERER_VIEW_MODEL, ok: false, code: "invalid_receipt" };
  }
  const disposition = receipt.conflict_disposition ?? null;
  if (disposition !== null && !CONFLICT_OPTIONS.some((option) => option.value === disposition)) {
    return { schema: RENDERER_VIEW_MODEL, ok: false, code: "unknown_conflict_disposition" };
  }
  return {
    schema: RENDERER_VIEW_MODEL,
    ok: true,
    cardTitle: "待审核候选",
    disclosure: "AI 生成的候选，尚未成为事实",
    actions: [...CANDIDATE_ACTIONS],
    hasBatchAccept: false,
    confirmModal: {
      title: "接受候选？",
      body: "这会把审核版本送入现有受控 Candidate/canonical 流程，并更新派生个人模型投影；不会把 AI 原稿直接写成事实。",
      acceptLabel: "确认接受候选",
      cancelLabel: "返回候选修改",
    },
    conflictModal: {
      title: "解决候选冲突",
      options: CONFLICT_OPTIONS.map((option) => ({ ...option })),
    },
    receiptId: receipt.receipt_id,
    projectionVersion: receipt.projection_version,
    candidateId: receipt.candidate_id,
  };
}

// ---------------------------------------------------------------------------
// Derived personal-model projection (corrigible, never a personal fact).
// ---------------------------------------------------------------------------
export function projectionViewModel(projection) {
  if (projection === null || typeof projection !== "object") {
    return { schema: RENDERER_VIEW_MODEL, ok: false, code: "invalid_projection" };
  }
  return {
    schema: RENDERER_VIEW_MODEL,
    ok: true,
    label: "派生个人模型",
    projectionId: projection.projection_id,
    version: projection.version,
    provenanceClass: projection.provenance_class,
    scope: projection.scope,
    validFrom: projection.valid_from,
    validTo: projection.valid_to,
    observedAt: projection.observed_at,
    confidence: projection.confidence,
    uncertainty: projection.uncertainty,
    supportCount: projection.supporting_evidence_count,
    conflictCount: projection.conflicting_evidence_count,
    evidenceRefs: Array.isArray(projection.evidence_refs) ? [...projection.evidence_refs] : [],
    conflicts: Array.isArray(projection.conflicts) ? cloneSafe(projection.conflicts) : [],
    supersession: projection.supersession ? cloneSafe(projection.supersession) : { superseded_by: null },
    freshness: projection.freshness ? cloneSafe(projection.freshness) : { status: "unknown" },
    limitations: Array.isArray(projection.limitations) ? [...projection.limitations] : [],
    corrigible: true,
  };
}

// ---------------------------------------------------------------------------
// Deterministic proactive view-model.
// ---------------------------------------------------------------------------
const PROACTIVE_CATEGORIES = Object.freeze({
  sync: "同步",
  briefing: "简报",
  "reflection-candidate": "反思候选",
});

export function proactiveViewModel(state) {
  const source = state ?? {};
  const quiet = source.quiet !== null && typeof source.quiet === "object" ? source.quiet : null;
  const quietActive = quiet?.active === true;
  const categories = {};
  for (const [id, label] of Object.entries(PROACTIVE_CATEGORIES)) {
    const control = source.categories?.[id];
    categories[id] = {
      label,
      enabled: control?.enabled === true,
      scope: typeof control?.scope === "string" ? control.scope : "project",
    };
  }
  const cluster = Array.isArray(source.clusters) && source.clusters.length > 0 ? source.clusters[0] : null;
  return {
    schema: RENDERER_VIEW_MODEL,
    ok: true,
    escalation: ["静默 badge", "行内卡", "抽屉", "需要确认才 modal"],
    quiet: {
      active: quietActive,
      quietUntilLabel: quietActive && typeof quiet?.quiet_until === "string"
        ? `静默至 ${quiet.quiet_until}`
        : "未静默",
    },
    controls: { categories },
    cluster: cluster && typeof cluster === "object" ? {
      mergedLabel: `已合并 ${cluster.merged_count} 条同簇证据`,
      itemId: cluster.item_id,
      supportCount: cluster.support_count,
      conflictCount: cluster.conflict_count,
      status: cluster.status,
    } : null,
    dismissal: {
      feedbackId: source.feedback?.feedback_id ?? null,
    },
  };
}

// ---------------------------------------------------------------------------
// Two-action command palette (Ctrl/Cmd+K).
// ---------------------------------------------------------------------------
const FIXED_PALETTE = Object.freeze([
  Object.freeze({ id: "receipt.open", label: "查看 receipt" }),
  Object.freeze({ id: "proactive.manage", label: "管理主动提醒" }),
]);

export function commandPaletteViewModel(input) {
  const commands = input?.commands;
  const exact = Array.isArray(commands)
    && commands.length === FIXED_PALETTE.length
    && commands.every((command, index) => command === FIXED_PALETTE[index].id);
  if (!exact) {
    return { schema: RENDERER_VIEW_MODEL, ok: false, code: "invalid_command_set" };
  }
  return {
    schema: RENDERER_VIEW_MODEL,
    ok: true,
    shortcut: "Ctrl/Cmd+K",
    commands: FIXED_PALETTE.map((command) => ({ ...command })),
  };
}

// ---------------------------------------------------------------------------
// Strict LIFO layer manager: Esc closes palette -> drawer -> modal and focus
// returns to the closed layer's trigger.
// ---------------------------------------------------------------------------
export function createLayerManager() {
  const stack = [];
  return {
    open({ id, trigger }) {
      const layer = { id, trigger: trigger ?? null };
      stack.push(layer);
      return layer;
    },
    peek() {
      return stack.length > 0 ? stack[stack.length - 1] : null;
    },
    close() {
      if (stack.length === 0) return null;
      return stack.pop();
    },
    depth() {
      return stack.length;
    },
  };
}

// ===========================================================================
// DOM bootstrap — runs only when a document/window exists. All presentation
// only; authority stays on the named preload bridge.
// ===========================================================================
function startRenderer(win, doc) {
  const harness = window.harness;
  if (!harness) {
    console.error("harness bridge is unavailable; renderer stays inert.");
    return;
  }
  const $ = (id) => doc.getElementById(id);
  const layers = createLayerManager();
  const runtime = {
    conversationId: null,
    projectScopeId: null,
    sessionId: null,
    conflictDisposition: null,
    lastReceipt: null,
    ephemeral: [],
  };

  function el(tagName, className, text) {
    const node = doc.createElement(tagName);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clearList(id) {
    const list = $(id);
    if (list) list.replaceChildren();
    return list;
  }

  function live(text) {
    const node = $("live-region");
    if (node) node.textContent = text;
  }

  function alert(text) {
    const node = $("alert-region");
    if (node) node.textContent = text;
  }

  function setThreadTitle(text) {
    const node = $("thread-title");
    if (node) node.textContent = text;
  }

  function setThreadMeta(text) {
    const node = $("thread-meta");
    if (node) node.textContent = text;
  }

  function formatTime(iso) {
    if (typeof iso !== "string") return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString("zh-CN", { hour12: false });
  }

  function openLayer(id, trigger) {
    layers.open({ id, trigger });
    const node = $(id);
    if (node) {
      node.hidden = false;
      const focusTarget = node.querySelector("[data-autofocus]") ?? node;
      focusTarget.focus();
    }
    live(`面板 ${id} 已打开`);
  }

  function closeTopLayer() {
    const closed = layers.close();
    if (!closed) return;
    const node = $(closed.id);
    if (node) {
      node.hidden = true;
    }
    if (closed.trigger && typeof closed.trigger.focus === "function") closed.trigger.focus();
    live("面板已关闭，焦点已回到触发控件");
  }

  // ---- thread rendering --------------------------------------------------
  function renderEmptyState(state) {
    const section = el("section", "empty-state");
    if (state === "empty") {
      section.append(el("h2", "empty-title", "从一段对话开始。"));
      section.append(el("p", "empty-body", "选择项目后提出问题；系统只会使用已授权且可追溯的资料。"));
    } else if (state === "stale") {
      section.append(el("p", "empty-body", "线程数据可能过期；顶栏与答案会显示两段新鲜度与积压。"));
    }
    return section;
  }

  function renderMessage(message) {
    const wrapper = el("article", `message message-${message.role}`);
    wrapper.setAttribute("data-message-id", message.messageId);
    wrapper.append(el("div", "message-body", message.displayText));
    const meta = el("div", "message-meta");
    if (message.createdAt) meta.append(el("span", "muted", formatTime(message.createdAt)));
    if (message.sourceRef) meta.append(el("span", "muted mono", message.sourceRef));
    wrapper.append(meta);
    return wrapper;
  }

  function renderThread(thread) {
    const container = $("messages");
    if (!container) return;
    container.replaceChildren();
    if (!thread) {
      setThreadTitle("从一段对话开始。");
      setThreadMeta("");
      container.append(renderEmptyState("empty"));
      return;
    }
    setThreadTitle(thread.conversationId ? `对话 ${thread.conversationId}` : "从一段对话开始。");
    const meta = [];
    if (thread.state) meta.push(`状态 ${thread.state}`);
    if (thread.freshness?.status) meta.push(`新鲜度 ${thread.freshness.status}`);
    if (thread.pagination?.hasMore) meta.push("还有更多");
    if (thread.truncated) meta.push("结果已截断");
    setThreadMeta(meta.join(" · "));
    for (const message of thread.messages) container.append(renderMessage(message));
    if (thread.messages.length === 0) container.append(renderEmptyState(thread.state));
    if (container.scrollTop !== undefined) container.scrollTop = container.scrollHeight;
  }

  function renderDisclosures(disclosures) {
    const group = el("div", "disclosures");
    if (!disclosures) return group;
    for (const block of [disclosures.basis, disclosures.freshness, disclosures.limitations]) {
      if (!block) continue;
      const details = el("details", "disclosure");
      details.open = false;
      const summary = el("summary", "disclosure-summary");
      summary.append(el("span", "disclosure-label", block.label));
      details.append(summary, el("div", "disclosure-text", block.text));
      group.append(details);
    }
    return group;
  }

  function renderToolRow(row) {
    const details = el("details", "tool-row");
    details.open = false;
    const summary = el("summary", "tool-row-summary");
    summary.append(el("span", "disclosure-label", row.label));
    summary.append(el(
      "span",
      "muted",
      `${row.skillName} · ${row.effect} · ${row.resultStatus} · ${row.receiptCount} 个 receipt`,
    ));
    details.append(summary);
    return details;
  }

  function renderSqliteCard(receipt) {
    const card = el("article", "card sqlite-card");
    const cardVm = expandSqliteCard(receipt);
    const header = el("header", "sqlite-card-header");
    header.append(el("h3", "card-title", "SQLite · 只读查询"));
    header.append(el("span", "card-status", "只读查询"));
    card.append(header);
    const metaRow = el("div", "sqlite-card-meta");
    if (typeof receipt?.duration_ms === "number") metaRow.append(el("span", "muted", `耗时 ${receipt.duration_ms}ms`));
    if (typeof receipt?.row_count === "number") metaRow.append(el("span", "muted", `返回 ${receipt.row_count} 行`));
    card.append(metaRow);
    const controls = el("div", "sqlite-card-controls");
    const expandButton = el("button", "btn-secondary", "展开 SQL");
    expandButton.type = "button";
    const evidenceButton = el("button", "btn-secondary", `查看 ${cardVm.rowCount} 条证据`);
    evidenceButton.type = "button";
    const receiptButton = el("button", "btn-secondary", "查看 receipt");
    receiptButton.type = "button";
    controls.append(expandButton, evidenceButton, receiptButton);
    card.append(controls);

    const expansion = el("section", "sqlite-expansion");
    expansion.hidden = true;
    expansion.setAttribute("aria-label", "受控查询");
    const expansionTitle = el("h4", "expansion-title", "受控查询");
    if (cardVm.ok) {
      expansion.append(expansionTitle);
      expansion.append(el("div", "statement-label", "已执行的脱敏 allowlisted statement"));
      const statement = el("code", "statement-display", cardVm.statementDisplay);
      expansion.append(statement);
      const identity = el("div", "muted mono");
      identity.textContent = `${cardVm.receiptId} · ${cardVm.databaseId} · checksum ${cardVm.queryChecksum}`;
      expansion.append(identity);
      runtime.lastReceipt = cardVm;
    } else {
      expansion.append(expansionTitle);
      expansion.append(el("p", "rejected-note", "查询未执行：显示内容未通过校验。请改为在已授权范围内提问。"));
    }
    card.append(expansion);

    expandButton.addEventListener("click", () => {
      expansion.hidden = !expansion.hidden;
    });
    receiptButton.addEventListener("click", () => {
      openLayer("receipt-drawer", receiptButton);
      const drawer = $("receipt-drawer");
      if (!drawer) return;
      drawer.replaceChildren();
      drawer.append(el("h3", "drawer-title", "查看 receipt"));
      if (cardVm.ok) {
        const identity = el("dl", "receipt-fields");
        for (const [key, value] of [
          ["操作名", "evidence.sqlite_query"],
          ["数据库", cardVm.databaseId],
          ["查询 ID", cardVm.queryId],
          ["描述符版本", cardVm.descriptorVersion],
          ["查询 checksum", cardVm.queryChecksum],
          ["行数", String(cardVm.rowCount)],
          ["耗时", cardVm.durationMs === null ? "—" : `${cardVm.durationMs}ms`],
          ["截断", cardVm.truncated ? "是" : "否"],
          ["receipt ID", cardVm.receiptId],
        ]) {
          identity.append(el("dt", "muted", key), el("dd", "", value));
        }
        drawer.append(identity);
      } else {
        drawer.append(el("p", "muted", "该 receipt 未通过校验，不显示内容。"));
      }
    });
    return card;
  }

  function renderAnswer(answered) {
    const container = $("messages");
    if (!container) return;
    const wrapper = el("article", "message message-assistant");
    const vm = answerViewModel(answered);
    const body = el("div", "message-body");
    if (vm.isSuccess) {
      body.textContent = typeof answered?.displayText === "string"
        ? answered.displayText
        : "已基于已授权资料回答。";
    } else {
      body.classList.add("message-error");
      body.textContent = vm.statusText ?? `操作未完成：${vm.status}。没有发生未授权变更。`;
    }
    wrapper.append(body);
    wrapper.append(renderDisclosures(vm.disclosures));
    if (vm.toolRow && vm.toolRow.receiptCount > 0) wrapper.append(renderToolRow(vm.toolRow));
    if (answered?.toolRow && Array.isArray(answered.toolRow.receipts)) {
      for (const receipt of answered.toolRow.receipts) wrapper.append(renderSqliteCard(receipt));
    }
    container.append(wrapper);
    container.scrollTop = container.scrollHeight;
    if (vm.isSuccess) live("消息已发送并收到回应");
    else alert(vm.statusText ?? "操作未完成");
  }

  // ---- candidate / conflict modal ----------------------------------------
  function renderCandidateCard(receipt) {
    const vm = candidateReviewViewModel(receipt);
    if (!vm.ok) return null;
    const card = el("article", "card candidate-card");
    card.append(el("h3", "card-title", vm.cardTitle));
    card.append(el("p", "muted", vm.disclosure));
    const actions = el("div", "candidate-actions");
    for (const action of vm.actions) {
      const button = el("button", "btn-secondary", action);
      button.type = "button";
      button.addEventListener("click", () => handleCandidateAction(vm, receipt, action, button));
      actions.append(button);
    }
    card.append(actions);
    return card;
  }

  function openConfirmModal(vm, receipt, trigger) {
    openLayer("confirm-modal", trigger);
    const modal = $("confirm-modal");
    if (!modal) return;
    modal.replaceChildren();
    modal.append(el("h3", "modal-title", vm.confirmModal.title));
    modal.append(el("p", "modal-body", vm.confirmModal.body));
    const actions = el("div", "modal-actions");
    const cancelButton = el("button", "btn-secondary", vm.confirmModal.cancelLabel);
    cancelButton.type = "button";
    const confirmButton = el("button", "btn-primary", vm.confirmModal.acceptLabel);
    confirmButton.type = "button";
    confirmButton.setAttribute("data-autofocus", "true");
    cancelButton.addEventListener("click", closeTopLayer);
    confirmButton.addEventListener("click", () => {
      harness.reviewCandidate({
        candidateId: receipt.candidate_id,
        action: "accept",
        version: receipt.expected_version ?? receipt.projection_version ?? 0,
      });
      closeTopLayer();
      live("已送交受控流程；不会把 AI 原稿直接写成事实。");
    });
    actions.append(cancelButton, confirmButton);
    modal.append(actions);
  }

  function openConflictModal(vm, receipt, trigger) {
    openLayer("conflict-modal", trigger);
    const modal = $("conflict-modal");
    if (!modal) return;
    modal.replaceChildren();
    modal.append(el("h3", "modal-title", "解决候选冲突"));
    modal.append(el("p", "muted", "高影响或存在冲突的候选必须逐项处理，不能批量接受。"));
    for (const option of vm.conflictModal.options) {
      const label = el("label", "conflict-option");
      const input = el("input");
      input.type = "radio";
      input.name = "conflict-disposition";
      input.value = option.value;
      label.append(input);
      const text = el("span", "conflict-option-text");
      text.append(el("strong", "conflict-option-label", option.label));
      text.append(el("span", "muted", option.consequence));
      label.append(text);
      modal.append(label);
    }
    const actions = el("div", "modal-actions");
    const cancelButton = el("button", "btn-secondary", "返回候选修改");
    cancelButton.type = "button";
    const confirmButton = el("button", "btn-primary", "确认接受候选");
    confirmButton.type = "button";
    confirmButton.setAttribute("data-autofocus", "true");
    cancelButton.addEventListener("click", () => {
      runtime.conflictDisposition = null;
      closeTopLayer();
    });
    confirmButton.addEventListener("click", () => {
      const selected = modal.querySelector("input[name=conflict-disposition]:checked");
      if (!selected) {
        alert("请选择一个冲突处理选项。");
        return;
      }
      runtime.conflictDisposition = selected.value;
      harness.reviewCandidate({
        candidateId: receipt.candidate_id,
        action: "accept",
        version: receipt.expected_version ?? receipt.projection_version ?? 0,
      });
      closeTopLayer();
      live("已提交受控流程；投影只在经受控审核路径后更新。");
    });
    actions.append(cancelButton, confirmButton);
    modal.append(actions);
  }

  function handleCandidateAction(vm, receipt, action, trigger) {
    if (action === "接受候选") {
      if (vm.conflictModal && vm.conflictModal.options.length > 0) {
        openConflictModal(vm, receipt, trigger);
      } else {
        openConfirmModal(vm, receipt, trigger);
      }
      return;
    }
    if (action === "忽略候选") {
      harness.reviewCandidate({
        candidateId: receipt.candidate_id,
        action: "ignore",
        version: receipt.expected_version ?? receipt.projection_version ?? 0,
      });
      live("已忽略候选；原始证据和审核记录仍可追溯。");
      return;
    }
    if (action === "查看候选证据") {
      openLayer("evidence-drawer", trigger);
      const drawer = $("evidence-drawer");
      if (drawer) {
        drawer.replaceChildren();
        drawer.append(el("h3", "drawer-title", "候选证据"));
        drawer.append(el("p", "muted", "支持与冲突证据按来源列出；来源缺失时显示“不能用推断补全”。"));
      }
      return;
    }
    if (action === "编辑候选") {
      openLayer("candidate-edit", trigger);
      const drawer = $("candidate-edit");
      if (drawer) {
        drawer.replaceChildren();
        drawer.append(el("h3", "drawer-title", "编辑候选"));
        drawer.append(el("p", "muted", "AI 原稿只读；审核版本将进入受控 Candidate/canonical 流程。"));
      }
    }
  }

  // ---- navigation handlers -----------------------------------------------
  function handleNewConversation() {
    const view = newConversation(harness, { projectScopeId: runtime.projectScopeId ?? undefined });
    if (!view.ok) {
      alert("操作未完成：无法创建新会话。没有发生未授权变更。");
      return;
    }
    runtime.sessionId = view.session?.sessionId ?? null;
    runtime.conversationId = view.thread?.conversationId ?? null;
    runtime.ephemeral = [];
    setThreadTitle("从一段对话开始。");
    setThreadMeta(view.session ? `会话 ${view.session.sessionId}` : "");
    const container = $("messages");
    if (container) {
      container.replaceChildren();
      container.append(renderEmptyState("empty"));
    }
    live("已新建会话；当前内容仅为运行时临时内容，不写入会话历史。");
  }

  function handleSelectConversation(conversationId, trigger) {
    const view = selectConversation(harness, { conversationId });
    if (view.ok && view.thread) {
      runtime.conversationId = conversationId;
      runtime.ephemeral = [];
      renderThread(view.thread);
    } else {
      alert(`操作未完成：${view.status}。没有发生未授权变更。`);
    }
  }

  function handleSelectScope(projectScopeId, trigger) {
    const view = selectScope(harness, { projectScopeId });
    if (!view.ok) {
      alert(`操作未完成：${view.status}。没有发生未授权变更。`);
      return;
    }
    runtime.projectScopeId = projectScopeId;
    live(`已选择项目 ${projectScopeId}`);
  }

  function sendMessage(text) {
    const trimmed = typeof text === "string" ? text.trim() : "";
    if (!trimmed) return;
    const container = $("messages");
    if (!container) return;
    runtime.ephemeral.push({ role: "user", displayText: trimmed });
    container.append(renderMessage({
      messageId: `local-${Date.now()}`,
      role: "user",
      displayText: trimmed,
      createdAt: new Date().toISOString(),
    }));
    const progress = el("div", "progress-line", "正在检索已授权资料");
    container.append(progress);
    const payload = { conversationId: runtime.conversationId, text: trimmed };
    if (runtime.projectScopeId) payload.projectScopeId = runtime.projectScopeId;
    const envelope = readEnvelope(harness.sendTurn(payload));
    progress.remove();
    if (envelope.ok && envelope.data && typeof envelope.data === "object") {
      if (Array.isArray(envelope.data.messages)) {
        renderThread(envelope.data);
      } else {
        const answer = { role: "assistant", status: "succeeded" };
        if (typeof envelope.data.displayText === "string") answer.displayText = envelope.data.displayText;
        if (envelope.data.disclosures) answer.disclosures = envelope.data.disclosures;
        if (envelope.data.toolRow) answer.toolRow = envelope.data.toolRow;
        if (Array.isArray(envelope.data.receipts) && answer.toolRow) answer.toolRow.receipts = envelope.data.receipts;
        renderAnswer(answer);
      }
    } else {
      renderAnswer({ role: "assistant", status: envelope.status });
    }
  }

  // ---- palette / proactive drawer ----------------------------------------
  function openCommandPalette() {
    if (layers.peek()?.id === "command-palette") {
      closeTopLayer();
      return;
    }
    const paletteVm = commandPaletteViewModel({ source: "ctrlOrCmd+k", commands: ["receipt.open", "proactive.manage"] });
    if (!paletteVm.ok) return;
    const trigger = $("command-palette-trigger") ?? doc.body;
    openLayer("command-palette", trigger);
    const list = $("palette-commands");
    if (list) {
      list.replaceChildren();
      for (const command of paletteVm.commands) {
        const button = el("button", "palette-command", command.label);
        button.type = "button";
        button.setAttribute("data-autofocus", "true");
        button.addEventListener("click", () => {
          closeTopLayer();
          if (command.id === "receipt.open" && runtime.lastReceipt) {
            openLayer("receipt-drawer", button);
            const drawer = $("receipt-drawer");
            if (drawer) drawer.replaceChildren();
          } else if (command.id === "proactive.manage") {
            openProactiveDrawer();
          } else {
            live("当前没有可查看的 receipt。");
          }
        });
        list.append(button);
      }
    }
  }

  function openProactiveDrawer() {
    const trigger = $("system");
    openLayer("proactive-drawer", trigger);
    const envelope = readEnvelope(harness.getProactiveState({ projectScopeId: runtime.projectScopeId ?? undefined }));
    const vm = proactiveViewModel(envelope.ok && envelope.data ? envelope.data : {});
    const drawer = $("proactive-drawer");
    if (!drawer) return;
    drawer.replaceChildren();
    drawer.append(el("h3", "drawer-title", "主动提醒"));
    drawer.append(el("div", "quiet-badge", vm.quiet.quietUntilLabel));
    const controls = el("div", "proactive-controls");
    for (const [category, control] of Object.entries(vm.controls.categories)) {
      const row = el("label", "control-row");
      row.append(el("span", "control-label", control.label));
      row.append(el("span", "muted", control.scope));
      const toggle = el("input");
      toggle.type = "checkbox";
      toggle.checked = control.enabled;
      toggle.addEventListener("change", () => {
        harness.updateProactiveControls({ scope: control.scope, category, enabled: toggle.checked });
        live(`主动提醒分类 ${control.label} 已${toggle.checked ? "启用" : "停用"}`);
      });
      row.append(toggle);
      controls.append(row);
    }
    drawer.append(controls);
    if (vm.cluster) {
      const cluster = el("div", "cluster-card");
      cluster.append(el("div", "cluster-label", vm.cluster.mergedLabel));
      cluster.append(el("div", "muted", `支持 ${vm.cluster.supportCount} · 冲突 ${vm.cluster.conflictCount}`));
      drawer.append(cluster);
    }
    const undoButton = el("button", "btn-secondary", "撤销忽略候选");
    undoButton.type = "button";
    undoButton.addEventListener("click", () => {
      if (vm.dismissal.feedbackId) {
        harness.undoProactiveDismissal({ feedbackId: vm.dismissal.feedbackId });
        live("已撤销忽略候选。");
      } else {
        alert("没有可撤销的忽略记录。");
      }
    });
    drawer.append(undoButton);
  }

  function openProjectionDrawer(trigger) {
    openLayer("projection-drawer", trigger);
    const drawer = $("projection-drawer");
    if (drawer) {
      drawer.replaceChildren();
      drawer.append(el("h3", "drawer-title", "派生个人模型"));
      drawer.append(el("p", "muted", "按时间演变查看同一推断的历史版本、适用情境、支持与冲突证据、有效时间和 supersession；没有总分或人格定论。"));
    }
  }

  // ---- startup + event wiring --------------------------------------------
  function startup() {
    const view = navigateStartup(harness);
    if (view.ok && view.last && view.last.thread) {
      runtime.conversationId = view.last.thread.conversationId;
      renderThread(view.last.thread);
    } else {
      renderThread(null);
      if (!view.ok) alert("导航读取暂不可用；请稍后重试或查看系统状态。");
    }
    renderRecent(view.recent);
    renderScopes(view.scopes);
  }

  function renderRecent(items) {
    const list = clearList("recent-list");
    if (!list) return;
    if (!Array.isArray(items) || items.length === 0) {
      list.append(el("li", "nav-empty", "暂无最近对话"));
      return;
    }
    for (const item of items) {
      const li = el("li");
      const button = el("button", "nav-item", item.title ?? "未命名对话");
      button.type = "button";
      button.title = item.lastActivityAt ? `最近活动 ${formatTime(item.lastActivityAt)}` : "";
      button.addEventListener("click", () => handleSelectConversation(item.conversationId, button));
      li.append(button);
      list.append(li);
    }
  }

  function renderScopes(items) {
    const list = clearList("scope-list");
    if (!list) return;
    if (!Array.isArray(items) || items.length === 0) {
      list.append(el("li", "nav-empty", "暂无项目"));
      return;
    }
    for (const item of items) {
      const li = el("li");
      const button = el("button", "nav-item");
      button.type = "button";
      button.append(el("span", "nav-item-label", item.label ?? "未命名项目"));
      button.append(el("span", "nav-item-status", item.freshness?.status ?? "unknown"));
      button.addEventListener("click", () => handleSelectScope(item.projectScopeId, button));
      li.append(button);
      list.append(li);
    }
  }

  function wireEvents() {
    const newButton = $("new-conversation");
    if (newButton) newButton.addEventListener("click", handleNewConversation);
    const composer = $("composer");
    if (composer) {
      composer.addEventListener("submit", (event) => {
        event.preventDefault();
        const input = $("composer-input");
        if (!input) return;
        const text = input.value;
        input.value = "";
        input.focus();
        sendMessage(text);
      });
    }
    const composerInput = $("composer-input");
    if (composerInput) {
      composerInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && composer) {
          event.preventDefault();
          composer.requestSubmit();
        }
      });
    }
    const personalModel = $("personal-model");
    if (personalModel) {
      personalModel.addEventListener("click", () => openProjectionDrawer(personalModel));
    }
    doc.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && layers.depth() > 0) {
        event.preventDefault();
        closeTopLayer();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        openCommandPalette();
      }
    });
  }

  wireEvents();
  startup();
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  startRenderer(window, document);
}
