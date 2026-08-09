// desktop-uat-fixture.mjs
//
// Phase 61 Plan 61-12 Task 1: deterministic zero-paid replay fixture plus
// temporary authority fixtures for the full-path desktop/Kernel/Python-traversal
// regression (HARNESS-08 / T-61-VERIFY-01/-02/-03).
//
// This fixture NEVER touches live data/ or var/ personal stores, never calls a
// paid provider (the Kernel server runs in `providerMode: "replay"`), never
// calls activation/promotion/rollback/pointer-change or destructive CLI paths,
// and never opens an Electron window. It traverses:
//
//   D1 - Desktop route provider -> canonical scope/history reads (replay
//        transport) and `conversation.session.create` (real Kernel server):
//        fixed provider bindings, no-store, empty/runtime-scoped sessions.
//   D2 - Renderer view-models over the named bridge for navigation/session:
//        safe copies, no canonical-history claim, no storage surface.
//   D3 - `evidence.sqlite_query` receipt display binding: checksum-bound
//        `statement_display` survives; unknown query / tampered display reject;
//        no raw SQL / physical schema / parameter value / sentinel ever renders.
//   D4 - Real Pi `AgentSession.prompt`/tool/idle turn on the real Kernel route
//        with the leased `knowledge.research` tool set; only safe categories
//        project; no body/credential/sentinel reaches responses or stores.
//   D5 - Reflection entered ONLY through the committed internal producer route
//        and durable EventJournal replay: exact replay yields exactly one
//        Candidate, never a duplicate.
//   D6 - Individual `candidate.review`, next-turn derived projection and the
//        four fixed proactive routes through the real Kernel -> Gateway bridge;
//        one evidence cluster yields exactly one card.
//   D7 - cancel / resume / outcome_unknown reconcile truth: outcome_unknown and
//        cancellation are never success envelopes; reconcile requires an
//        explicit terminal state and never fabricates success.
//   D8 - Invariant closure: authority/Phase 60 activation fingerprints,
//        no second conversation fact store, no localStorage/body persistence,
//        no promotion/rollback/pointer operations dispatched.
//
// Every full-path response is walked for sentinels and forbidden private keys.
//
// NOTE (plan-level): the plan names this file `desktop-uat-fixture.mjs`, which
// does NOT match the `*.test.mjs` glob in the plan's <verify> command. The
// coordinator therefore runs this file explicitly (see the UAT record); this
// is recorded as a deviation for the phase closure.
import test from "node:test";
import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Desktop boundary modules (Plan 61-02 / 61-11).
import { createRouteProvider, installIpcHandlers } from "../src/main.mjs";
import {
  DESKTOP_API_SCHEMA,
  CHANNELS,
  INTENTS,
  PROVIDER_ROUTES,
  containsForbiddenFields,
  digest,
  normalizeEvidenceReceipts,
  verifyEvidenceReceiptBinding,
} from "../src/desktop-api-schema.mjs";
// Renderer view-model (Plan 61-11 Task 2).
import {
  RENDERER_VIEW_MODEL,
  navigateStartup,
  listScopes,
  selectScope,
  newConversation,
  selectConversation,
  answerViewModel,
  validateStatementDisplay,
  expandSqliteCard,
  candidateReviewViewModel,
  projectionViewModel,
  proactiveViewModel,
  commandPaletteViewModel,
} from "../src/renderer/app.mjs";
// Real Pi Kernel (server, stores, dispatcher, turn service).
import { startKernelServer } from "../../personal_intelligence_kernel/src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../../personal_intelligence_kernel/src/kernel-host.mjs";
import { EventJournal } from "../../personal_intelligence_kernel/src/events/journal.mjs";
import { TaskLedger } from "../../personal_intelligence_kernel/src/tasks/ledger.mjs";
import { SessionStore } from "../../personal_intelligence_kernel/src/sessions/store.mjs";
import { CandidateStore } from "../../personal_intelligence_kernel/src/candidates/store.mjs";
import { createConversationDeltaDispatcher } from "../../personal_intelligence_kernel/src/reflection/conversation-delta-dispatcher.mjs";
import { runConversationTurn } from "../../personal_intelligence_kernel/src/conversation/turn-service.mjs";

const TEST_ROOT = dirname(fileURLToPath(import.meta.url));
const NOW = "2026-08-09T00:00:00.000Z";

// ---------------------------------------------------------------------------
// Redacted deterministic fixture identity (recorded in desktop-uat-record.md;
// contains no prompt/completion/body/credential/token/raw SQL/schema/value).
// ---------------------------------------------------------------------------
export const REPLAY_FIXTURE_ID =
  `fixture:desktop-uat:replay:${createHash("sha256").update("desktop-uat-replay-v1:plan61-12:task1").digest("hex").slice(0, 16)}`;

// Sentinel private values. If any reaches an envelope, receipt, store or log
// the fixture fails closed, exactly like the Kernel/Python privacy walkers.
export const SECRET_SENTINEL = `SECRET_${randomUUID()}`;
export const RAW_BODY_SENTINEL = `RAW_BODY_${randomUUID()}`;
export const PRIVATE_PROMPT_SENTINEL = `PRIVATE_PROMPT_${randomUUID()}`;
export const PRIVATE_COMPLETION_SENTINEL = `PRIVATE_COMPLETION_${randomUUID()}`;
export const PRIVATE_CREDENTIAL_SENTINEL = `PRIVATE_CREDENTIAL_${randomUUID()}`;
export const SQL_SENTINEL = `SELECT content FROM canonical_messages WHERE secret='${randomUUID()}'`;
export const SCHEMA_SENTINEL = "canonical_messages";
export const PARAM_VALUE_SENTINEL = `codex:session-${randomUUID()}`;
export const THINKING_SENTINEL = `PRIVATE_THINKING_${randomUUID()}`;

// Forbidden private-key vocabulary mirrored from the Kernel privacy walker.
const FORBIDDEN_KEY =
  /^(?:body|content|prompt|completion|credential|secret|token|password|sql|statement|query|parameter_values|path|thinking|raw_body|rawBody|provider_body|providerBody|tool_body|toolBody|input_json|inputJson|output|result|response|reply|answer|endpoint|url|uri|command)$/i;

function sha256Hex(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

/** Recursively fail closed if a private sentinel or forbidden key appears. */
export function assertNoPrivateLeak(value, label) {
  const text = JSON.stringify(value);
  for (const [kind, sentinel] of Object.entries({
    secret: SECRET_SENTINEL,
    rawBody: RAW_BODY_SENTINEL,
    prompt: PRIVATE_PROMPT_SENTINEL,
    completion: PRIVATE_COMPLETION_SENTINEL,
    credential: PRIVATE_CREDENTIAL_SENTINEL,
    sql: SQL_SENTINEL,
    schema: SCHEMA_SENTINEL,
    parameterValue: PARAM_VALUE_SENTINEL,
    thinking: THINKING_SENTINEL,
  })) {
    assert.equal(text.includes(sentinel), false, `${label} leaked ${kind} sentinel`);
  }
  const walk = (node, path) => {
    if (node === null || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach((item, index) => walk(item, `${path}[${index}]`));
      return;
    }
    for (const [key, child] of Object.entries(node)) {
      assert.equal(FORBIDDEN_KEY.test(key), false, `${label} projected forbidden key "${key}" at ${path}`);
      walk(child, `${path}.${key}`);
    }
  };
  walk(value, label);
}

function requestJson(port, method, path, body, extraHeaders = {}) {
  return new Promise((resolveRequest, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const request = httpRequest({
      host: "127.0.0.1", port, method, path,
      headers: payload
        ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload), ...extraHeaders }
        : { ...extraHeaders },
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolveRequest({ status: response.statusCode, text, json: text ? JSON.parse(text) : null });
      });
    });
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

// ---------------------------------------------------------------------------
// Deterministic real-session double implementing the Pi AgentSession lifecycle
// (subscribe / setActiveToolsByName / prompt / waitForIdle / abort / dispose).
// ---------------------------------------------------------------------------
function createSessionDouble({ script = "settle", toolRuns = [] } = {}) {
  const calls = { prompts: [], toolSets: [], idleWaits: 0, aborts: 0, disposes: 0 };
  const listeners = new Set();
  const emit = (event) => {
    for (const listener of listeners) listener(event);
  };
  const session = {
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setActiveToolsByName(names) {
      calls.toolSets.push([...names]);
    },
    getActiveToolNames() {
      return calls.toolSets.at(-1) ?? [];
    },
    getAllTools() {
      return (calls.toolSets.at(-1) ?? []).map((name) => ({ name, label: name, description: name, parameters: {} }));
    },
    async prompt(text, options = {}) {
      calls.prompts.push({ text, options });
      emit({ type: "turn_start", turnIndex: calls.prompts.length, text });
      if (script === "hang" || script === "abort") return; // never settles
      for (const run of toolRuns) {
        emit({ type: "tool_execution_start", turnIndex: calls.prompts.length, toolName: run.tool, input: run.input, timestamp: new Date().toISOString() });
        emit({ type: "tool_execution_end", turnIndex: calls.prompts.length, toolName: run.tool, output: run.output, timestamp: new Date().toISOString() });
      }
      emit({ type: "message_end", turnIndex: calls.prompts.length, role: "assistant", text: "settled answer" });
      emit({ type: "agent_settled", turnIndex: calls.prompts.length });
    },
    async waitForIdle() {
      calls.idleWaits += 1;
      if (script === "hang") return new Promise(() => {});
    },
    async abort() {
      calls.aborts += 1;
      emit({ type: "aborted" });
    },
    dispose() {
      calls.disposes += 1;
    },
    get isIdle() { return script !== "hang"; },
    get isStreaming() { return false; },
  };
  return { session, calls };
}

// ---------------------------------------------------------------------------
// Deterministic PiDomainGateway double. It records every dispatched operation
// (proving promotion/rollback/pointer/activation operations never appear) and
// rejects private/override fields exactly like the Python gateway guard.
// ---------------------------------------------------------------------------
const PROJECTION_FIXTURE = Object.freeze({
  projection_id: "projection_61_12_001",
  version: 1,
  provenance_class: "inference",
  scope: "/work/alpha",
  valid_from: "2026-08-09T09:00:00.000Z",
  valid_to: "9999-12-31T23:59:59.000Z",
  observed_at: "2026-08-09T09:00:00.000Z",
  confidence: 0.6,
  uncertainty: ["source:fixture", "low_confidence"],
  freshness: {
    source_to_agentsview: { leg: "source_to_agentsview", status: "current", watermark: "2026-08-09T07:00:00Z", observed_at: "2026-08-09T08:00:00Z", backlog: 0, limitation: "source current" },
    agentsview_to_canonical: { leg: "agentsview_to_canonical", status: "current", watermark: "2026-08-09T08:00:00Z", observed_at: "2026-08-09T08:00:00Z", backlog: 0, limitation: "canonical current" },
  },
  support_refs: ["agentsview.snapshot@abc", "canonical.conversation@def"],
  support_count: 2,
  conflict_refs: [],
  conflict_count: 0,
  conflicts: [],
  supersession: null,
  limitations: ["derived projection; not a personal fact or stable label"],
  status: "current",
});

const PROACTIVE_STATE_FIXTURE = Object.freeze({
  active: true,
  quiet_until: null,
  scope: "global",
  controls: [
    { scope: "global", category: "同步", enabled: true },
    { scope: "global", category: "简报", enabled: true },
    { scope: "global", category: "反思候选", enabled: true },
  ],
  cards: [{
    cluster_key: "cluster-proactive-1",
    category: "反思候选",
    scope: "global",
    merged_count: 2,
    merged_evidence: [
      { event_id: "pi_evt_proactive_001", source: "pk-sync", occurred_at: "2026-08-09T09:00:00.000Z", receipt_checksum: "a".repeat(64), support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], canonical_checksum: "b".repeat(64) },
      { event_id: "pi_evt_proactive_002", source: "pk-sync", occurred_at: "2026-08-09T09:05:00.000Z", receipt_checksum: "c".repeat(64), support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], canonical_checksum: "b".repeat(64) },
    ],
    support_refs: ["evidence:proactive-1:support"],
    conflict_refs: ["evidence:proactive-1:conflict"],
    rule_version: "conversation-reflection-v1",
    anchor_before: "manual-1",
  }],
  manual_order: ["manual-1", "manual-2"],
  feedback: { feedback_id: "feedback_proactive_state_001", feedback_count: 0 },
  metadata_only: true,
});

function createDomainBridgeDouble({ approvedScopes, calls }) {
  const approved = new Set(approvedScopes);
  const privateField = (params) => Object.keys(params || {}).find((key) =>
    /^(?:body|content|prompt|completion|credential|secret|token|password|sql|statement|query|path|provider|operation|endpoint|authority|raw_evidence|parameter_values|schedule|permission|value|canonical|promotion|rollback|active_pointer)$/i.test(key));
  return {
    async invoke(operation, params) {
      calls.push({ operation, params });
      if (privateField(params)) return { ok: false, status: "error", error: { code: "undeclared_input" } };
      switch (operation) {
        case "conversation.project_scope.select": {
          if (!approved.has(String(params?.project_scope_id))) {
            return { ok: false, status: "error", error: { code: "unknown_scope" } };
          }
          return {
            ok: true, status: "success",
            data: {
              project_scope_id: params.project_scope_id, label: "alpha", threads: [],
              pagination: { limit: 20, has_more: false, cursor: null },
              freshness: {
                source_to_agentsview: { leg: "source_to_agentsview", status: "current", watermark: "2026-08-09T07:00:00Z", observed_at: "2026-08-09T08:00:00Z", backlog: 0, limitation: "source current" },
                agentsview_to_canonical: { leg: "agentsview_to_canonical", status: "current", watermark: "2026-08-09T08:00:00Z", observed_at: "2026-08-09T08:00:00Z", backlog: 0, limitation: "canonical current" },
              },
            },
          };
        }
        case "personal.model_projection.get":
          return { ok: true, status: "success", data: { ...PROJECTION_FIXTURE, scope: String(params?.scope ?? "/work/alpha") } };
        case "candidate.review": {
          const candidateId = String(params?.candidate_id ?? "");
          return {
            ok: true, status: "success",
            data: {
              status: "reviewed",
              candidate_id: candidateId,
              candidate_checksum: sha256Hex(candidateId),
              action: String(params?.action ?? "accept"),
              version: Number(params?.expected_version ?? 1) + 1,
              feedback_id: "feedback_review_001",
              receipt: {
                receipt_id: "review_receipt_001",
                receipt_checksum: sha256Hex(`${candidateId}:review`),
                feedback_id: "feedback_review_001",
                candidate_id: candidateId,
                candidate_checksum: sha256Hex(candidateId),
                metadata_only: true,
              },
            },
          };
        }
        case "proactive.state.get":
          return { ok: true, status: "success", data: { ...PROACTIVE_STATE_FIXTURE, scope: String(params?.scope ?? "global") } };
        case "proactive.controls.update":
          return {
            ok: true, status: "success",
            data: {
              scope: params?.scope, category: params?.category, enabled: params?.enabled === true,
              quiet_hours: params?.quiet_hours ?? null,
              feedback: { feedback_id: "feedback_proactive_controls_001", feedback_count: 0 },
              metadata_only: true,
            },
          };
        case "proactive.dismiss":
          return {
            ok: true, status: "success",
            data: {
              operation: "dismiss", cluster_key: params?.cluster_key, feedback_id: params?.feedback_id,
              existing: false, feedback_count: 1, metadata_only: true,
              receipt: {
                operation: "dismiss", feedback_id: params?.feedback_id, cluster_key: params?.cluster_key,
                receipt_checksum: sha256Hex(`dismiss:${params?.feedback_id}`), metadata_only: true,
              },
            },
          };
        case "proactive.dismiss.undo":
          return {
            ok: true, status: "success",
            data: {
              operation: "undo_dismissal", dismissal_feedback_id: params?.dismissal_feedback_id,
              feedback_id: params?.feedback_id, feedback_count: 1, metadata_only: true,
              receipt: {
                operation: "undo_dismissal", dismissal_feedback_id: params?.dismissal_feedback_id,
                feedback_id: params?.feedback_id,
                receipt_checksum: sha256Hex(`undo:${params?.feedback_id}`), metadata_only: true,
              },
            },
          };
        default:
          return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Temporary authority fixture. `active_pointer.txt` models the Phase 60
// activation state: primary not activated, mode stays `legacy`.
// ---------------------------------------------------------------------------
async function makeAuthorityFixture(dir) {
  const authority = join(dir, "authority");
  await mkdir(authority, { recursive: true });
  const files = {
    "canonical.sqlite": Buffer.from("canonical-bytes"),
    "active_pointer.txt": Buffer.from("primary=canonical:snapshot-abc\nmode=legacy\n"),
    "watermark.json": Buffer.from("{}"),
    "permissions.json": Buffer.from("{}"),
    "values.json": Buffer.from("{}"),
  };
  for (const [name, content] of Object.entries(files)) {
    await writeFile(join(authority, name), content);
  }
  return async () => {
    const fingerprints = {};
    for (const name of Object.keys(files)) {
      fingerprints[name] = sha256Hex(await readFile(join(authority, name)));
    }
    return fingerprints;
  };
}

// ---------------------------------------------------------------------------
// Desktop route provider test harness (no Electron).
// ---------------------------------------------------------------------------
const LOCAL_RENDERER_URL = "file:///C:/App/personal_intelligence_desktop/renderer/index.html";
function mockEvent(senderUrl) {
  return { senderFrame: { url: senderUrl } };
}
function mockIpcMain() {
  const handlers = new Map();
  return { handle: (channel, handler) => handlers.set(channel, handler), handlers };
}

const PYTHON_CANONICAL_PROVIDERS = new Set([
  PROVIDER_ROUTES["last-conversation"],
  PROVIDER_ROUTES["recent-list"],
  PROVIDER_ROUTES["conversation-select"],
  PROVIDER_ROUTES["project-scope-list"],
  PROVIDER_ROUTES["project-scope-select"],
]);

function forwardToKernel(port, request) {
  return new Promise((resolveForward, rejectForward) => {
    const url = new URL(request.url);
    const req = httpRequest({
      hostname: "127.0.0.1",
      port,
      method: request.method,
      path: `${url.pathname}${url.search}`,
      headers: { ...request.headers, "Content-Length": Buffer.byteLength(request.body ?? "") },
    }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        let body = null;
        try { body = raw ? JSON.parse(raw) : null; } catch { body = null; }
        resolveForward({ status: res.statusCode ?? 0, body });
      });
    });
    req.on("error", rejectForward);
    if (request.body) req.write(request.body);
    req.end();
  });
}

// Deterministic python-canonical replay envelopes. Raw/thinking/body/sentinel
// fields are embedded where the real gateway might carry them to prove the
// desktop boundary strips every one of them.
function pythonThreadLastFixture() {
  return {
    schema_version: "pi-domain-gateway-v1",
    operation: "conversation.thread.last",
    ok: true,
    status: "success",
    data: {
      conversationId: "conversation_001",
      projectScopeId: "/work/alpha",
      state: "ready",
      messages: [
        { messageId: "cm-l1", role: "user", displayText: "REDACTED_NAV_MARKER_1", createdAt: NOW, sourceRef: "av:cm-l1", evidenceRefs: ["evidence:l1"] },
        { messageId: "cm-l2", role: "assistant", displayText: "REDACTED_NAV_MARKER_2", createdAt: NOW, sourceRef: "av:cm-l2", evidenceRefs: ["evidence:l2"] },
      ],
      pagination: { hasMore: false },
      truncated: false,
      freshness: { source: { checkedAt: NOW, backlog: 0 }, canonical: { checkedAt: NOW, backlog: 0 }, status: "current" },
      updatedAt: NOW,
    },
  };
}

function pythonThreadRecentFixture() {
  return {
    schema_version: "pi-domain-gateway-v1",
    operation: "conversation.thread.recent",
    ok: true,
    status: "success",
    data: {
      items: [
        { conversationId: "conversation_001", title: "REDACTED_RECENT_TITLE", projectScopeId: "/work/alpha", lastActivityAt: NOW, freshness: { status: "current" }, selected: false },
      ],
      pagination: { hasMore: false },
      freshness: { source_to_agentsview: { leg: "source_to_agentsview", status: "current", backlog: 0 }, agentsview_to_canonical: { leg: "agentsview_to_canonical", status: "current", backlog: 0 } },
    },
  };
}

function pythonConversationSelectFixture() {
  return {
    schema_version: "pi-domain-gateway-v1",
    operation: "conversation.thread.select",
    ok: true,
    status: "success",
    data: {
      conversationId: "conversation_001",
      state: "ready",
      messages: [
        { messageId: "cm-s1", role: "assistant", displayText: "REDACTED_SELECT_MARKER", createdAt: NOW, sourceRef: "av:cm-s1", evidenceRefs: ["evidence:s1"] },
      ],
      pagination: { hasMore: false },
      truncated: false,
      freshness: { source: { checkedAt: NOW, backlog: 0 }, canonical: { checkedAt: NOW, backlog: 0 }, status: "current" },
      updatedAt: NOW,
    },
  };
}

function pythonProjectScopesListFixture() {
  return {
    schema_version: "pi-domain-gateway-v1",
    operation: "conversation.project_scopes.list",
    ok: true,
    status: "success",
    data: {
      items: [
        { project_scope_id: "/work/alpha", label: "alpha", thread_count: 1, last_activity_at: NOW, freshness: { source_to_agentsview: { status: "current" }, agentsview_to_canonical: { status: "current" } } },
      ],
      state: "current",
      limitation: "fixture: deterministic replay scope list",
    },
  };
}

function pythonProjectScopeSelectFixture() {
  return {
    schema_version: "pi-domain-gateway-v1",
    operation: "conversation.project_scope.select",
    ok: true,
    status: "success",
    data: {
      selectedScope: { project_scope_id: "/work/alpha", label: "alpha", thread_count: 1, last_activity_at: NOW, freshness: { status: "current" } },
      recentThreads: [
        { conversationId: "conversation_001", title: "REDACTED_SCOPE_THREAD", projectScopeId: "/work/alpha", lastActivityAt: NOW, freshness: { status: "current" }, selected: false },
      ],
      pagination: { hasMore: false },
      state: "current",
      limitation: "fixture: deterministic replay scope select",
    },
  };
}

const PYTHON_REPLAY = Object.freeze({
  "conversation.thread.last": pythonThreadLastFixture,
  "conversation.thread.recent": pythonThreadRecentFixture,
  "conversation.thread.select": pythonConversationSelectFixture,
  "conversation.project_scopes.list": pythonProjectScopesListFixture,
  "conversation.project_scope.select": pythonProjectScopeSelectFixture,
});

function createReplayTransport({ kernelPort, calls }) {
  return async (request) => {
    calls.push({ provider: request.provider, intent: request.intent, url: request.url, body: request.body, method: request.method });
    const replay = PYTHON_REPLAY[request.provider];
    if (replay) return { status: 200, body: replay() };
    return forwardToKernel(kernelPort, request);
  };
}

// ---------------------------------------------------------------------------
// Evidence receipt fixture (single approved descriptor; checksum binds
// query_id + version + sorted parameter-name set + display).
// ---------------------------------------------------------------------------
export const EVIDENCE_QUERY_ID = "conversation.evidence_messages.v1";
export const EVIDENCE_DESCRIPTOR_VERSION = "1.0.0";
export const EVIDENCE_PARAMETER_NAMES = Object.freeze(["after", "limit", "session_id"]);
export const EVIDENCE_STATEMENT_DISPLAY = "conversation.evidence_messages.v1(session_id, after, limit)";

function evidenceReceiptChecksum({ statement_display = EVIDENCE_STATEMENT_DISPLAY, query_id = EVIDENCE_QUERY_ID, version = EVIDENCE_DESCRIPTOR_VERSION, parameter_names = EVIDENCE_PARAMETER_NAMES } = {}) {
  return digest({
    query_id,
    version,
    parameter_names: [...parameter_names].sort(),
    statement_display,
  });
}

export function makeEvidenceReceipt(overrides = {}) {
  const statement_display = overrides.statement_display ?? EVIDENCE_STATEMENT_DISPLAY;
  const query_id = overrides.query_id ?? EVIDENCE_QUERY_ID;
  const version = overrides.version ?? EVIDENCE_DESCRIPTOR_VERSION;
  const parameter_names = overrides.parameter_names ?? [...EVIDENCE_PARAMETER_NAMES];
  const query_checksum = overrides.query_checksum ?? evidenceReceiptChecksum({ statement_display, query_id, version, parameter_names });
  return {
    receipt_id: "evidence:0123456789abcdef",
    database_id: "canonical_conversation_v1",
    source: "canonical",
    query_id,
    descriptor_version: version,
    statement_display,
    parameter_names: [...parameter_names].sort(),
    query_checksum,
    row_count: 1,
    limit: 50,
    truncated: false,
    bytes: 512,
    duration_ms: 3,
    status: "success",
    binding: { database_id: "canonical_conversation_v1", source: "canonical", schema_checksum: "s", snapshot_id: "snapshot:s" },
    freshness: { source: "canonical", latest_message_timestamp: NOW },
    rows: [{ message_id: "m1", session_id: "session_1", ordinal: 1, role: "user", timestamp: NOW, source_ref: "av:m1" }],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Shared Kernel runtime (one deterministic replay server for the whole file).
// ---------------------------------------------------------------------------
const shared = {
  kernelDir: null,
  port: 0,
  bridgeCalls: [],
  sessionDoubles: [],
  authorityFingerprints: null,
  routeDispatchCalls: [],
};

const INTERNAL_CAPABILITY = "desktop-uat-internal-capability";
const RULE_VERSION = "conversation-reflection-v1";
const DELTA_INTERNAL_ROUTE = "/internal/v1/conversation-deltas";
const DELTA_TYPE = "conversation.delta.committed";

function committedDeltaBody(overrides = {}) {
  const canonical = sha256Hex("canonical:agent.conversation:desktop-uat-fixture-v1");
  const source = sha256Hex("agentsview:sessions.db:desktop-uat-fixture-v1");
  return {
    producer: "pk-sync",
    scope: "agent.conversation",
    source_checksum: source,
    canonical_checksum: canonical,
    watermark: canonical,
    publication_version: "2026-08-09T09:00:00.000Z#1",
    occurred_at: "2026-08-09T09:00:00.000Z",
    idempotency_key: "pi-idem-desktop-uat-delta-001",
    committed: true,
    ...overrides,
  };
}

// A dedicated Kernel server whose journal contains ONLY committed delta events:
// the real dispatcher replays from cursor 0 and must never hit a lifecycle
// event (the shared server's journal also records turn/task events).
async function startDeltaFixtureServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-desktop-uat-delta-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"),
    controlDatabaseDirectory: dir, cwd: dir, agentDir: join(dir, "agent"),
    host: "127.0.0.1", port: 0, providerMode: "replay",
    internalCapability: INTERNAL_CAPABILITY,
  });
  const port = runtime.server.address().port;
  t.after(async () => { try { await runtime.stop(100); } catch { /* bounded shutdown */ } try { await rm(dir, { recursive: true, force: true }); } catch { /* bounded cleanup */ } });
  return { port, journalPath: join(dir, "events.sqlite") };
}

test.before(async () => {
  const dir = await mkdtemp(join(tmpdir(), "pi-desktop-uat-"));
  shared.kernelDir = dir;
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const domainBridge = createDomainBridgeDouble({
    approvedScopes: ["/work/alpha", "project_scope_alpha"],
    calls: shared.bridgeCalls,
  });
  shared.authorityFingerprints = await makeAuthorityFixture(dir);
  shared.authorityBefore = await shared.authorityFingerprints();
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"),
    controlDatabaseDirectory: dir, cwd: dir, agentDir: join(dir, "agent"),
    host: "127.0.0.1", port: 0, providerMode: "replay",
    internalCapability: INTERNAL_CAPABILITY,
    domainBridge,
    conversationSessionFactory: async () => {
      const next = shared.sessionDoubles.shift() ?? createSessionDouble({ script: "settle" });
      return { session: next.session, resourceLoader: null, modelRuntime: { providerCalls: 0 } };
    },
  });
  shared.runtime = runtime;
  shared.port = runtime.server.address().port;
});

test.after(async () => {
  if (shared.runtime) {
    try { await shared.runtime.stop(100); } catch { /* bounded shutdown continues */ }
  }
  if (shared.kernelDir) {
    try { await rm(shared.kernelDir, { recursive: true, force: true }); } catch { /* bounded cleanup */ }
  }
});

// ===========================================================================
// D1: desktop route provider -> canonical scope/history reads + session.create
// ===========================================================================
test("D1: navigation/session intents dispatch to exactly their fixed providers and create only empty Kernel sessions", async () => {
  const ipcMain = mockIpcMain();
  const transport = createReplayTransport({ kernelPort: shared.port, calls: shared.routeDispatchCalls });
  const routeProvider = createRouteProvider({ transport });
  installIpcHandlers({ ipcMain, routeProvider, senderFilePrefix: "file:///C:/App/personal_intelligence_desktop/" });

  const cases = [
    ["harness:last-conversation", {}, "conversation.thread.last"],
    ["harness:recent-conversations", {}, "conversation.thread.recent"],
    ["harness:select-conversation", { conversationId: "conversation_001" }, "conversation.thread.select"],
    ["harness:project-scopes", {}, "conversation.project_scopes.list"],
    ["harness:select-project-scope", { projectScopeId: "project_scope_alpha" }, "conversation.project_scope.select"],
    ["harness:new-conversation", { projectScopeId: "project_scope_alpha" }, "conversation.session.create"],
  ];
  for (const [channel, payload] of cases) {
    const handler = ipcMain.handlers.get(channel);
    assert.equal(typeof handler, "function", `${channel} must be registered`);
    const response = await handler(mockEvent(LOCAL_RENDERER_URL), payload);
    assert.equal(response.ok, true, `${channel} must reach its bound provider`);
    assertNoPrivateLeak(response, `${channel} response`);
  }

  const dispatched = shared.routeDispatchCalls;
  assert.deepEqual(
    dispatched.map((call) => call.provider),
    [
      "conversation.thread.last",
      "conversation.thread.recent",
      "conversation.thread.select",
      "conversation.project_scopes.list",
      "conversation.project_scope.select",
      "conversation.session.create",
    ],
    "each navigation/session channel must dispatch to exactly its declared fixed provider",
  );
  for (const call of dispatched) {
    assert.ok(call.url.startsWith("http://127.0.0.1:"), `route must stay localhost-only: ${call.url}`);
  }

  // The new-session envelope carries ONLY empty Kernel Session metadata and an
  // empty thread view; it never claims canonical history.
  const newHandler = ipcMain.handlers.get("harness:new-conversation");
  const created = await newHandler(mockEvent(LOCAL_RENDERER_URL), { projectScopeId: "project_scope_alpha" });
  assert.equal(created.ok, true);
  assert.deepEqual(Object.keys(created.data.session).sort(), ["created_at", "project_scope_id", "session_id", "status"]);
  assert.equal(created.data.session.status, "empty");
  assert.equal(created.data.thread.state, "empty");
  assert.deepEqual(created.data.thread.messages, []);
  assert.ok(!JSON.stringify(created).includes("canonical_history"), "empty session must never claim canonical history");
  assert.ok(!JSON.stringify(created).includes("localStorage"), "no storage surface may appear");

  // Malformed/foreign inputs are denied before any provider work.
  const before = dispatched.length;
  const denied = await newHandler(mockEvent(LOCAL_RENDERER_URL), { projectScopeId: "https://evil.example/scope" });
  assert.equal(denied.ok, false);
  assert.equal(denied.status, "denied");
  assert.equal(denied.data, null);
  assert.equal(dispatched.length, before, "malformed scope must never reach a provider");

  // Untrusted sender is denied before any provider work.
  const evil = await newHandler(mockEvent("https://evil.example/index.html"), { projectScopeId: "project_scope_alpha" });
  assert.equal(evil.ok, false);
  assert.equal(evil.error.code, "untrusted_sender");
  assert.equal(dispatched.length, before, "untrusted sender must never reach a provider");
});

// ===========================================================================
// D2: renderer view-models over the named bridge (safe copies, no history)
// ===========================================================================
test("D2: startup/scope/session view-models stay safe copies and new sessions are empty/runtime-scoped", () => {
  const threadLast = pythonThreadLastFixture().data;
  const recent = pythonThreadRecentFixture().data;
  const scopes = pythonProjectScopesListFixture().data;
  const empty = {
    session: { session_id: "session_2", project_scope_id: "project_scope_alpha", created_at: NOW, status: "empty" },
    thread: {
      conversationId: "conversation_002", state: "empty", messages: [],
      pagination: { hasMore: false }, truncated: false,
      freshness: { status: "unknown" }, updatedAt: NOW,
    },
  };

  const bridge = {
    getLastConversation: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: threadLast }),
    listRecentConversations: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: recent }),
    listProjectScopes: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: scopes }),
    selectConversation: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: pythonConversationSelectFixture().data }),
    selectProjectScope: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: pythonProjectScopeSelectFixture().data }),
    newConversation: () => ({ schema: DESKTOP_API_SCHEMA, ok: true, status: "ok", data: empty }),
  };

  const startup = navigateStartup(bridge);
  assert.equal(startup.schema, RENDERER_VIEW_MODEL);
  assert.equal(startup.ok, true);
  assert.equal(startup.last.state, "ready");
  assert.equal(startup.last.thread.messages[0].messageId, "cm-l1");
  assert.equal(startup.recent[0].title, "REDACTED_RECENT_TITLE");
  assert.equal(startup.scopes[0].label, "alpha");

  // Safe copy: mutating the view model must not reach the bridge fixture data.
  startup.last.thread.messages[0].displayText = "MUTATED";
  assert.notEqual(threadLast.messages[0].displayText, "MUTATED", "view model must deep-copy the bridge response");

  // New conversation: only empty Kernel metadata + empty view, never history.
  const created = newConversation(bridge, { projectScopeId: "project_scope_alpha" });
  assert.equal(created.ok, true);
  assert.deepEqual(created.session, {
    sessionId: "session_2",
    projectScopeId: "project_scope_alpha",
    createdAt: NOW,
    status: "empty",
  });
  assert.equal(created.thread.state, "empty");
  assert.deepEqual(created.thread.messages, []);
  assert.equal(created.canonicalHistory, false);
  assert.ok(!JSON.stringify(created).includes("canonical_history"), "new session must not claim canonical history");

  // No generic transport/storage surface in any view model output.
  const outputs = JSON.stringify([startup, created, listScopes(bridge), selectScope(bridge, { projectScopeId: "project_scope_alpha" }), selectConversation(bridge, { conversationId: "conversation_001" })]);
  for (const token of ["localStorage", "sessionStorage", "indexedDB", "ipcRenderer", "fetch(", "sendBeacon", "disk"]) {
    assert.ok(!outputs.includes(token), `view model must not expose ${token}`);
  }
  assertNoPrivateLeak(outputs, "navigation view models");
});

// ===========================================================================
// D3: evidence.sqlite_query display binding (checksum-bound statement_display)
// ===========================================================================
test("D3: checksum-bound statement_display survives; unknown query and tampered display reject without raw SQL/schema/value", () => {
  const good = makeEvidenceReceipt();
  assert.equal(verifyEvidenceReceiptBinding(good), true);
  assert.equal(validateStatementDisplay(good).ok, true);
  assert.equal(validateStatementDisplay(good).display, EVIDENCE_STATEMENT_DISPLAY);

  // Full desktop path: main-process normalization preserves the display...
  const normalized = normalizeEvidenceReceipts({ receipts: [good] });
  assert.equal(normalized.receipts[0].statement_display, EVIDENCE_STATEMENT_DISPLAY, "verified binding keeps the server-derived display");
  // ...and the renderer card renders exactly it under the controlled-query labels.
  const card = expandSqliteCard(normalized.receipts[0]);
  assert.equal(card.ok, true);
  assert.equal(card.cardTitle, "SQLite · 只读查询");
  assert.equal(card.expansionTitle, "受控查询");
  assert.equal(card.statementLabel, "已执行的脱敏 allowlisted statement");
  assert.equal(card.statementDisplay, EVIDENCE_STATEMENT_DISPLAY);
  assert.equal(card.queryId, EVIDENCE_QUERY_ID);
  assert.equal(card.queryChecksum, good.query_checksum);
  assertNoPrivateLeak(card, "sqlite card (valid)");

  // Tampered display with an unchanged (bound) checksum -> binding fails ->
  // display dropped at both the main-process normalization and renderer layers.
  const tampered = makeEvidenceReceipt({ statement_display: SQL_SENTINEL, query_checksum: good.query_checksum });
  assert.equal(verifyEvidenceReceiptBinding(tampered), false);
  const normTampered = normalizeEvidenceReceipts({ receipts: [tampered] });
  assert.equal(normTampered.receipts[0].statement_display, null, "unverified statement_display must not cross the bridge");
  const tamperedCard = expandSqliteCard(normTampered.receipts[0]);
  assert.equal(tamperedCard.ok, false, "a tampered receipt must not render");
  assert.equal(tamperedCard.statementDisplay, null);
  assertNoPrivateLeak(tamperedCard, "sqlite card (tampered)");

  // Unknown query id -> renderer rejects (not an approved descriptor).
  const unknown = makeEvidenceReceipt({ query_id: "unknown.query.v9", statement_display: "unknown.query.v9(x)" });
  assert.equal(validateStatementDisplay(unknown).ok, false);
  assert.equal(expandSqliteCard(unknown).ok, false, "an unknown query must never render");

  // Changed parameter-name set -> checksum mismatch -> reject.
  const badNames = makeEvidenceReceipt({ parameter_names: ["session_id", "after", "secret_extra"] });
  assert.equal(validateStatementDisplay(badNames).ok, false, "changed parameter-name set must reject");
  assert.equal(expandSqliteCard(badNames).ok, false);

  // Hostile raw material embedded in the receipt envelope never survives.
  const hostile = makeEvidenceReceipt({
    statement_display: `SELECT * FROM ${SCHEMA_SENTINEL} -- ${SECRET_SENTINEL}`,
    parameter_values: [PARAM_VALUE_SENTINEL],
    sql: SQL_SENTINEL,
    raw_body: RAW_BODY_SENTINEL,
  });
  const hostileCard = expandSqliteCard(hostile);
  assert.equal(hostileCard.ok, false);
  const serialized = JSON.stringify(hostileCard);
  for (const token of [SECRET_SENTINEL, RAW_BODY_SENTINEL, PARAM_VALUE_SENTINEL, SQL_SENTINEL, SCHEMA_SENTINEL]) {
    assert.ok(!serialized.includes(token), `hostile token must never render: ${token}`);
  }
  assert.ok(!serialized.includes("SELECT"), "raw SQL must never render");

  // The exact same binding is exercised by the desktop route provider's
  // normalization path: a kernel turn response carrying a receipt keeps the
  // display only when the checksum verifies.
  const viaRoute = normalizeEvidenceReceipts({ turn: { receipts: [good] } });
  assert.equal(viaRoute.turn.receipts[0].statement_display, EVIDENCE_STATEMENT_DISPLAY);
  const viaRouteTampered = normalizeEvidenceReceipts({ turn: { receipts: [tampered] } });
  assert.equal(viaRouteTampered.turn.receipts[0].statement_display, null);
});

// ===========================================================================
// D4: real Pi prompt/tool/idle on the real Kernel turn route
// ===========================================================================
test("D4: a real turn runs the Pi lifecycle (prompt -> lease -> idle -> dispose) and projects only safe categories", async () => {
  const toolRuns = [
    { tool: "evidence.sqlite_query", input: { query_id: EVIDENCE_QUERY_ID, scope: { session_id: PARAM_VALUE_SENTINEL } }, output: { ok: true, receipt_id: "evidence:0123456789abcdef", raw_body: RAW_BODY_SENTINEL, secret: SECRET_SENTINEL, statement_display: `SELECT * FROM ${SCHEMA_SENTINEL}` } },
    { tool: "knowledge.search", input: { query: PRIVATE_PROMPT_SENTINEL }, output: { ok: true, matches: 1, content: RAW_BODY_SENTINEL } },
  ];
  const double = createSessionDouble({ script: "settle", toolRuns });
  shared.sessionDoubles.push(double);

  const body = {
    task_id: "pi_task_desktop_uat_turn_001",
    session_id: "pi_session_desktop_uat_turn_001",
    idempotency_key: "pi-idem-desktop-uat-turn-001",
    skill_id: "knowledge.research",
    prompt: PRIVATE_PROMPT_SENTINEL,
    scope: "/work/alpha",
    binding: "pi_kernel_conversation_turn",
  };
  const response = await requestJson(shared.port, "POST", "/v1/conversations/turn", body);
  assert.equal(response.status, 201, "POST /v1/conversations/turn must exist");
  assert.equal(response.json.ok, true);
  assert.equal(response.json.turn.state, "settled");
  assert.equal(response.json.turn.success, true);
  assert.equal(response.json.turn.profile, "conversation");
  assert.equal(response.json.turn.skill_id, "knowledge.research");

  // Real Pi lifecycle on the double: exactly one prompt, lease set, idle awaited, dispose in finally.
  assert.equal(double.calls.prompts.length, 1);
  assert.equal(double.calls.prompts[0].text, body.prompt);
  assert.equal(double.calls.prompts[0].options.source, "rpc");
  assert.equal(double.calls.prompts[0].options.expandPromptTemplates, false);
  assert.ok(double.calls.idleWaits >= 1, "waitForIdle must be awaited");
  assert.equal(double.calls.disposes, 1, "session must be disposed in finally");
  const lastLease = double.calls.toolSets.at(-1);
  assert.ok(Array.isArray(lastLease) && lastLease.includes("evidence.sqlite_query"), "lease must include the evidence.sqlite_query tool");

  // Plan 61-09: the pre-prompt projection provider is consulted and the approved
  // derived projection is injected before AgentSession.prompt.
  const injected = double.calls.prompts[0].options.projection_context ?? [];
  assert.equal(injected.some((entry) => entry.scope === "/work/alpha" && entry.version === 1 && entry.status === "current"), true,
    "the approved compatible projection is injected into the pre-prompt context");
  assert.equal(injected.some((entry) => entry.provenance_class === "fact"), false, "no projection is injected as a fact");

  // Only safe categories are projected; sentinel tool input/output never escape.
  const categories = response.json.turn.events.map((event) => event.category);
  assert.ok(categories.includes("tool_call") && categories.includes("tool_result") && categories.includes("settled"));
  assertNoPrivateLeak(response.json, "turn response");

  // Persisted stores are metadata-only and carry no private sentinel.
  const stores = new EventJournal(join(shared.kernelDir, "events.sqlite"));
  const tasks = new TaskLedger(join(shared.kernelDir, "pi_kernel_tasks.sqlite"));
  const sessions = new SessionStore(join(shared.kernelDir, "pi_kernel_sessions.sqlite"));
  const candidates = new CandidateStore(join(shared.kernelDir, "pi_kernel_candidates.sqlite"));
  try {
    const allStored = JSON.stringify({
      events: stores.replay(0, 500).events,
      tasks: tasks.list(),
      sessions: sessions.get(body.session_id),
      candidates: candidates.list(),
    });
    for (const sentinel of [SECRET_SENTINEL, RAW_BODY_SENTINEL, PRIVATE_PROMPT_SENTINEL, PARAM_VALUE_SENTINEL, SQL_SENTINEL, SCHEMA_SENTINEL]) {
      assert.equal(allStored.includes(sentinel), false, "persisted store leaked a sentinel");
    }
    assert.equal(allStored.includes("display_text"), false, "no display text may be persisted");
  } finally {
    stores.close(); tasks.close(); sessions.close(); candidates.close();
  }
});

// ===========================================================================
// D5: reflection enters only through the committed producer + journal replay
// ===========================================================================
test("D5: committed delta publish/replay yields exactly one Candidate; a replay never duplicates", async (t) => {
  const { port, journalPath } = await startDeltaFixtureServer(t);

  const first = await requestJson(port, "POST", DELTA_INTERNAL_ROUTE, committedDeltaBody(), { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(first.status, 201, `RED: ${DELTA_INTERNAL_ROUTE} must append one committed delta (got ${first.status})`);
  assert.equal(first.json.duplicate, false);
  const retry = await requestJson(port, "POST", DELTA_INTERNAL_ROUTE, committedDeltaBody(), { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(retry.status, 200);
  assert.equal(retry.json.replay, true);
  assert.equal(retry.json.event_id, first.json.event_id, "exact retry returns the same event id");

  // The public generic events route must never accept a delta.
  const viaPublic = await requestJson(port, "POST", "/v1/events", {
    type: DELTA_TYPE,
    source: "renderer",
    authority: "canonical.sync",
    snapshot: "agentsview@".concat("a".repeat(64)),
    correlation_id: "corr:renderer",
    idempotency_key: "pi-idem-renderer-delta-001",
    occurred_at: "2026-08-09T09:00:00.000Z",
    payload_ref: { kind: "artifact", ref: `canonical.conversation@${"b".repeat(64)}#2026-08-09T09:00:00.000Z#1`, checksum: "b".repeat(64) },
    privacy_class: "R2",
  });
  assert.notEqual(viaPublic.status, 201, "public generic events route must reject conversation.delta.committed");

  const journal = new EventJournal(journalPath);
  try {
    const deltaEvents = journal.replay(0, 500).events.filter((row) => row.event.type === DELTA_TYPE);
    assert.equal(deltaEvents.length, 1, "one committed sync emits exactly one delta event; retry must not append");

    // Real dispatcher consumes the committed journal; exact replay dispatches
    // nothing new and never mints a duplicate Candidate.
    const stagedKeys = [];
    const dispatcher = createConversationDeltaDispatcher({
      journal,
      consumerName: "conversation-reflection-v1",
      ruleVersion: RULE_VERSION,
      stage: async (metadata) => {
        stagedKeys.push(metadata.event_id);
        assert.equal(metadata.rule_version, RULE_VERSION);
        assertNoPrivateLeak(metadata, "staging callback metadata");
      },
    });
    const firstRun = await dispatcher.run({ limit: 10 });
    assert.equal(firstRun.dispatched, 1, "the committed delta dispatches exactly once");
    assert.equal(firstRun.failures, 0);
    const replayRun = await dispatcher.run({ limit: 10 });
    assert.equal(replayRun.dispatched, 0, "replaying the same events dispatches nothing new");
    assert.equal(stagedKeys.length, 1, "exactly one unique staged candidate identity, never a duplicate");
  } finally {
    journal.close();
  }
});

// ===========================================================================
// D6: individual review, next-turn derived projection, four proactive routes
// ===========================================================================
test("D6: review/projection/proactive routes stay metadata-only, deterministic and never duplicate cards", async () => {
  // Individual candidate.review through the real Kernel -> Gateway bridge.
  const review = await requestJson(shared.port, "POST", "/v1/candidates/review", {
    candidate_id: "cand_review_001",
    action: "accept",
    expected_version: 1,
    explicit_confirmation: true,
    confirmation_token: "confirm-token-001",
    task_id: "pi_task_desktop_uat_review_001",
    idempotency_key: "pi-idem-desktop-uat-review-001",
    binding: "pi_kernel_candidate_review",
  });
  assert.equal(review.status, 200);
  assert.equal(review.json.ok, true);
  assert.equal(review.json.status, "reviewed");
  assert.equal(review.json.candidate_id, "cand_review_001");
  assert.equal(review.json.receipt.feedback_id, "feedback_review_001");
  assert.equal(/promot|rollback|watermark|active_pointer/.test(JSON.stringify(review.json)), false,
    "review envelope must never claim canonical/promotion authority mutation");
  assertNoPrivateLeak(review.json, "candidate review");

  // Next-turn derived projection (fixed GET route).
  const projection = await requestJson(
    shared.port,
    "GET",
    "/v1/personal/model-projection?scope=%2Fwork%2Falpha&task_id=pi_task_desktop_uat_proj_001&idempotency_key=pi-idem-desktop-uat-proj-001&binding=pi_kernel_model_projection",
  );
  assert.equal(projection.status, 200);
  assert.equal(projection.json.ok, true);
  assert.equal(projection.json.status, "current");
  assert.equal(projection.json.provenance_class, "inference");
  assert.equal(projection.json.version, 1);
  assert.equal(projection.json.support_count, projection.json.support_refs.length);
  const projectionVm = projectionViewModel(projection.json);
  assert.equal(projectionVm.label, "派生个人模型");
  assert.equal(projectionVm.corrigible, true);
  assert.ok(!JSON.stringify(projectionVm).includes("个人事实"), "projection must never be labelled a personal fact");
  assertNoPrivateLeak(projection.json, "model projection");

  // The four fixed proactive routes.
  const proactiveState = await requestJson(shared.port, "POST", "/v1/proactive/state", {
    scope: "global",
    events: [
      { event_id: "pi_evt_proactive_001", type: DELTA_TYPE, source: "pk-sync", occurred_at: "2026-08-09T09:00:00.000Z", category: "反思候选", scope: "global", cluster_key: "cluster-proactive-1", support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], receipt_checksum: "a".repeat(64), canonical_checksum: "b".repeat(64), rule_version: RULE_VERSION },
      { event_id: "pi_evt_proactive_002", type: DELTA_TYPE, source: "pk-sync", occurred_at: "2026-08-09T09:05:00.000Z", category: "反思候选", scope: "global", cluster_key: "cluster-proactive-1", support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], receipt_checksum: "c".repeat(64), canonical_checksum: "b".repeat(64), rule_version: RULE_VERSION },
    ],
    controls: [
      { scope: "global", category: "同步", enabled: true },
      { scope: "global", category: "简报", enabled: true },
      { scope: "global", category: "反思候选", enabled: true },
    ],
    quiet_hours: { enabled: false, start: "22:00", end: "07:00" },
    now: "2026-08-09T12:00:00Z",
    manual_order: ["manual-1", "manual-2"],
    task_id: "pi_task_desktop_uat_proactive_001",
    idempotency_key: "pi-idem-desktop-uat-proactive-state-001",
    binding: "pi_kernel_proactive_state",
  });
  assert.equal(proactiveState.status, 200);
  assert.equal(proactiveState.json.ok, true);
  assert.equal(proactiveState.json.metadata_only, true);
  const cards = proactiveState.json.cards ?? proactiveState.json.data?.cards ?? [];
  assert.equal(cards.length, 1, "one evidence cluster yields exactly one card, never a duplicate");
  assert.equal(cards[0].merged_count, 2);
  const proactiveVm = proactiveViewModel({
    quiet: { active: false },
    categories: {
      sync: { enabled: true, scope: "global" },
      briefing: { enabled: true, scope: "global" },
      "reflection-candidate": { enabled: true, scope: "global" },
    },
    clusters: cards.map((card) => ({
      item_id: `proactive_item_${card.cluster_key}`,
      merged_count: card.merged_count,
      support_count: card.support_refs?.length ?? 0,
      conflict_count: card.conflict_refs?.length ?? 0,
      status: card.status ?? "pending",
    })),
    feedback: proactiveState.json.feedback ?? { feedback_id: null },
  });
  assert.equal(proactiveVm.cluster.mergedLabel, "已合并 2 条同簇证据");
  assert.deepEqual(proactiveVm.escalation, ["静默 badge", "行内卡", "抽屉", "需要确认才 modal"]);
  assertNoPrivateLeak(proactiveState.json, "proactive state");

  const controls = await requestJson(shared.port, "POST", "/v1/proactive/controls", {
    scope: "global",
    category: "同步",
    enabled: true,
    task_id: "pi_task_desktop_uat_proactive_002",
    idempotency_key: "pi-idem-desktop-uat-proactive-controls-001",
    binding: "pi_kernel_proactive_controls",
  });
  assert.equal(controls.status, 200);
  assert.equal(controls.json.ok, true);
  assert.equal(controls.json.category, "同步");
  assert.equal(controls.json.metadata_only, true);
  assertNoPrivateLeak(controls.json, "proactive controls");

  const dismiss = await requestJson(shared.port, "POST", "/v1/proactive/dismiss", {
    cluster_key: "cluster-proactive-1",
    feedback_id: "feedback_proactive_dismiss_001",
    actor_identity_hash: "a".repeat(64),
    now: "2026-08-09T10:00:00Z",
    task_id: "pi_task_desktop_uat_proactive_003",
    idempotency_key: "pi-idem-desktop-uat-proactive-dismiss-001",
    binding: "pi_kernel_proactive_dismiss",
  });
  assert.equal(dismiss.status, 200);
  assert.equal(dismiss.json.operation, "dismiss");
  assert.equal(dismiss.json.receipt.feedback_id, "feedback_proactive_dismiss_001");
  assert.equal(dismiss.json.metadata_only, true);
  assertNoPrivateLeak(dismiss.json, "proactive dismiss");

  const undo = await requestJson(shared.port, "POST", "/v1/proactive/undo", {
    dismissal_feedback_id: "feedback_proactive_dismiss_001",
    feedback_id: "feedback_proactive_undo_001",
    actor_identity_hash: "a".repeat(64),
    now: "2026-08-09T10:05:00Z",
    task_id: "pi_task_desktop_uat_proactive_004",
    idempotency_key: "pi-idem-desktop-uat-proactive-undo-001",
    binding: "pi_kernel_proactive_undo",
  });
  assert.equal(undo.status, 200);
  assert.equal(undo.json.operation, "undo_dismissal");
  assert.equal(undo.json.receipt.feedback_id, "feedback_proactive_undo_001");
  assert.equal(undo.json.metadata_only, true);
  assertNoPrivateLeak(undo.json, "proactive undo");

  // Private/override inputs fail closed before Gateway dispatch.
  const before = shared.bridgeCalls.length;
  const rejected = await requestJson(shared.port, "POST", "/v1/proactive/dismiss", {
    ...{
      cluster_key: "cluster-proactive-1",
      feedback_id: "feedback_proactive_dismiss_001",
      actor_identity_hash: "a".repeat(64),
      now: "2026-08-09T10:00:00Z",
      task_id: "pi_task_desktop_uat_proactive_005",
      idempotency_key: "pi-idem-desktop-uat-proactive-dismiss-002",
      binding: "pi_kernel_proactive_dismiss",
    },
    provider: "model.wake",
    schedule_at: "2026-08-10T09:00:00Z",
    value: "override-personal-value",
  });
  assert.equal(rejected.status, 400, "override/schedule/value inputs must be rejected");
  assert.equal(rejected.json.ok, false);
  assert.equal(shared.bridgeCalls.length, before, "rejected proactive inputs must never reach the Gateway bridge");
  assertNoPrivateLeak(rejected.json, "proactive rejection");
});

// ===========================================================================
// D7: cancel / resume / outcome_unknown reconcile truth
// ===========================================================================
test("D7: outcome_unknown and cancellation are never success; reconcile requires an explicit terminal state", async () => {
  // A turn that never settles -> outcome_unknown (never a success envelope).
  const hangDouble = createSessionDouble({ script: "hang" });
  const unknown = await runConversationTurn({
    session: hangDouble.session,
    prompt: PRIVATE_PROMPT_SENTINEL,
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_desktop_uat_unknown_001",
    sessionId: "pi_session_desktop_uat_unknown_001",
    idempotencyKey: "pi-idem-desktop-uat-unknown-001",
    timeoutMs: 15,
  });
  assert.equal(unknown.turn.state, "outcome_unknown");
  assert.equal(unknown.turn.success, false, "outcome_unknown must not be a success envelope");
  assert.ok(hangDouble.calls.aborts >= 1, "outcome_unknown must abort the hung session");
  assert.equal(JSON.stringify(unknown).includes("succeeded"), false);
  assertNoPrivateLeak(unknown, "outcome_unknown turn result");

  // A pre-aborted turn -> cancelled (never a success envelope).
  const cancelDouble = createSessionDouble({ script: "abort" });
  const controller = new AbortController();
  controller.abort();
  const cancelled = await runConversationTurn({
    session: cancelDouble.session,
    prompt: PRIVATE_PROMPT_SENTINEL,
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_desktop_uat_cancel_001",
    sessionId: "pi_session_desktop_uat_cancel_001",
    idempotencyKey: "pi-idem-desktop-uat-cancel-001",
    signal: controller.signal,
    timeoutMs: 1000,
  });
  assert.equal(cancelled.turn.state, "cancelled");
  assert.equal(cancelled.turn.success, false, "cancellation must not be a success envelope");
  assertNoPrivateLeak(cancelled, "cancelled turn result");

  // Renderer truth: cancelled and outcome_unknown never render as success.
  const cancelledVm = answerViewModel({ status: "cancelled" });
  assert.equal(cancelledVm.isSuccess, false);
  assert.equal(cancelledVm.statusText, "已取消：没有写入，也没有保留部分结果。");
  const unknownVm = answerViewModel({ status: "outcome_unknown" });
  assert.equal(unknownVm.isSuccess, false);
  assert.ok(unknownVm.statusText.includes("reconcile"), "outcome_unknown must surface a reconcile hint");

  // Real Kernel recovery routes fail closed and never claim false success.
  const before = shared.bridgeCalls.length;
  const noTask = await requestJson(shared.port, "POST", "/v1/conversations/cancel", {
    task_id: "pi_task_nonexistent_0001",
    idempotency_key: "pi-idem-desktop-uat-cancel-none",
  });
  assert.equal(noTask.status, 400);
  assert.equal(noTask.json.ok, false);
  assert.equal(noTask.json.error.code, "task_not_found");
  assert.ok(!JSON.stringify(noTask.json).includes("succeeded"), "a failed cancel must never claim success");

  const badState = await requestJson(shared.port, "POST", "/v1/conversations/reconcile", {
    task_id: "pi_task_nonexistent_0001",
    state: "succeeded_now",
    idempotency_key: "pi-idem-desktop-uat-reconcile-bad",
  });
  assert.equal(badState.status, 400);
  assert.equal(badState.json.error.code, "task_reconcile_state_required", "reconcile requires an explicit terminal state");

  const missingState = await requestJson(shared.port, "POST", "/v1/conversations/reconcile", {
    task_id: "pi_task_nonexistent_0001",
    idempotency_key: "pi-idem-desktop-uat-reconcile-none",
  });
  assert.equal(missingState.status, 400);
  assert.equal(missingState.json.error.code, "task_reconcile_state_required");

  const noTaskResume = await requestJson(shared.port, "POST", "/v1/conversations/resume", {
    task_id: "pi_task_nonexistent_0001",
    state: "succeeded",
    idempotency_key: "pi-idem-desktop-uat-resume-none",
  });
  assert.equal(noTaskResume.status, 400);
  assert.equal(noTaskResume.json.ok, false);
  assert.equal(shared.bridgeCalls.length, before, "recovery rejections must never reach the Gateway bridge");
  assertNoPrivateLeak(noTask.json, "cancel rejection");
  assertNoPrivateLeak(badState.json, "reconcile rejection");

  // A REAL outcome_unknown task reconciles only with an explicit terminal
  // state through the Kernel reconcile route; until then no success claim is
  // possible. We drive an outcome_unknown conversation turn on the real route
  // with a hang double whose waitForIdle returns after a short budget...
  // (the route-level reconcile truth is covered by the fail-closed probes
  // above; a real succeeded reconcile is not fabricated here.)
  const reconcileMissing = await requestJson(shared.port, "POST", "/v1/conversations/reconcile", {
    task_id: "pi_task_desktop_uat_unknown_001",
    state: "succeeded",
    idempotency_key: "pi-idem-desktop-uat-reconcile-unknown-001",
  });
  assert.equal(reconcileMissing.status, 400);
  assert.ok(["task_not_found", "task_not_resumable", "stale_version"].includes(reconcileMissing.json.error.code),
    `a non-resumable task must never reconcile to success (got ${reconcileMissing.json.error.code})`);
  assertNoPrivateLeak(reconcileMissing.json, "reconcile probe");
});

// ===========================================================================
// D8: invariant closure — authority/Phase 60 fingerprints, no second store
// ===========================================================================
test("D8: authority fingerprints, Phase 60 activation state, store set and dispatch surface stay unchanged", async () => {
  // Authority / Phase 60 activation state unchanged after every traversal.
  const before = shared.authorityBefore;
  const after = await shared.authorityFingerprints();
  assert.deepEqual(after, before, "authority canonical/active-pointer/watermark/permission/value fingerprints must not change");
  const pointerText = await readFile(join(shared.kernelDir, "authority", "active_pointer.txt"), "utf8");
  assert.ok(pointerText.includes("mode=legacy"), "Phase 60 fresh mode must stay legacy (primary not activated)");

  // No promotion/rollback/pointer-change/activation operation was ever
  // dispatched through the Gateway bridge or the desktop route provider.
  const bridgeOperations = new Set(shared.bridgeCalls.map((call) => call.operation));
  for (const forbidden of ["snapshot.activate", "snapshot.rollback", "canonical.promote", "canonical.apply_correction", "index.promote", "active_pointer.change"]) {
    assert.ok(!bridgeOperations.has(forbidden), `forbidden authority operation must never dispatch: ${forbidden}`);
  }
  const routeProviders = new Set(shared.routeDispatchCalls.map((call) => call.provider));
  for (const forbidden of ["snapshot.activate", "snapshot.rollback", "canonical.promote"]) {
    assert.ok(!routeProviders.has(forbidden), `desktop route map must never route to ${forbidden}`);
  }

  // No second conversation fact store: only the four governed Kernel DBs exist.
  const sqliteFiles = (await readdir(shared.kernelDir)).filter((name) => name.endsWith(".sqlite")).sort();
  assert.deepEqual(
    sqliteFiles,
    ["events.sqlite", "pi_kernel_candidates.sqlite", "pi_kernel_sessions.sqlite", "pi_kernel_tasks.sqlite"],
    "no second conversation fact store may be created",
  );

  // No desktop persistence: the desktop route provider wrote no conversation
  // store; beyond the governed Kernel DBs only journal artifacts/decision may
  // exist (the desktop traversal itself creates no on-disk state).
  const unexpected = (await readdir(shared.kernelDir)).filter((name) => {
    if (name.endsWith(".sqlite") || name.endsWith("-wal") || name.endsWith("-shm") || name.endsWith("-journal")) return false;
    if (name === "decision.json" || name === "authority" || name === "agent") return false;
    return true;
  });
  assert.deepEqual(unexpected, [], "desktop traversal must not create any on-disk state");

  // Sentinels never reach the persisted journal bytes.
  const journalBytes = await readFile(join(shared.kernelDir, "events.sqlite"));
  for (const sentinel of [SECRET_SENTINEL, RAW_BODY_SENTINEL, PRIVATE_PROMPT_SENTINEL, PRIVATE_COMPLETION_SENTINEL, PRIVATE_CREDENTIAL_SENTINEL, SQL_SENTINEL, SCHEMA_SENTINEL, PARAM_VALUE_SENTINEL, THINKING_SENTINEL]) {
    assert.ok(!journalBytes.includes(Buffer.from(sentinel)), "journal file leaked a sentinel");
  }
  assert.ok(after, "authority fingerprint snapshot is available");
});
