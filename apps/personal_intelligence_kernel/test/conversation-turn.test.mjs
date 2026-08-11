// Wave 0 regression contract for Plan 61-03 "Real Pi lease-scoped conversation turn".
//
// This file is the RED test for Task 1. It is intentionally written against the
// Plan 61-03 Task 2 contract that does not exist yet:
//   - src/conversation/turn-service.mjs          -> runConversationTurn()
//   - src/runtime/conversation-session.mjs        -> per-turn real-session factory (route seam)
//   - resource-policy.mjs                         -> PROFILE_DEFINITIONS / resolveProfile /
//                                                    profileToolNames / deriveConversationLease
//   - kernel-host.mjs + server.mjs                -> POST /v1/conversations/turn dispatch
//
// Running it against the current provider-plus-SkillEngine implementation must FAIL:
// missing profiles, missing turn route, cross-profile visibility, an ordinary
// conversation mutation lease, or a restored implicit "replay" provider mode are all
// accepted as RED evidence.
//
// The deterministic real-session double implements the Pi AgentSession lifecycle
// (subscribe / setActiveToolsByName / prompt / waitForIdle / abort / dispose) with
// scripted tool-call/result and settled events that embed sentinel secrets. Every
// projection (turn envelope, Task/Session/Event/Candidate stores) must never expose
// body/prompt/completion/credential/secret values or keys.

import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readdirSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { startKernelServer } from "../src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";
import { createProjectDomainBridge } from "../src/tools/domain-bridge.mjs";
import { loadCapabilityRegistry } from "../src/tools/capability-registry.mjs";
import { skillChecksum } from "../src/skills/registry.mjs";
import { EventJournal } from "../src/events/journal.mjs";
import { TaskLedger } from "../src/tasks/ledger.mjs";
import { SessionStore } from "../src/sessions/store.mjs";
import { CandidateStore } from "../src/candidates/store.mjs";

const TEST_ROOT = dirname(fileURLToPath(import.meta.url));
const KERNEL_ROOT = resolve(TEST_ROOT, "..");
const REPO_ROOT = resolve(KERNEL_ROOT, "../..");
const SKILL_MANIFEST_PATH = join(REPO_ROOT, "governance/manifests/ai/pi-skills.json");

// ---------------------------------------------------------------------------
// Deterministic fixtures
// ---------------------------------------------------------------------------

const SKILLS = JSON.parse(await readFile(SKILL_MANIFEST_PATH, "utf8")).skills;
const RESEARCH_SKILL = SKILLS.find((skill) => skill.id === "knowledge.research");
const SUPPORT_SKILL = SKILLS.find((skill) => skill.id === "personal.daily_brief");
const OTHER_SKILL = SKILLS.find((skill) => skill.id === "decision.support");
const SNAPSHOT_RELEASE_SKILL = SKILLS.find((skill) => skill.id === "snapshot.release");
assert.ok(RESEARCH_SKILL, "knowledge.research manifest entry must exist");
assert.ok(SUPPORT_SKILL && OTHER_SKILL && SNAPSHOT_RELEASE_SKILL, "support/other/snapshot skill fixtures must exist");

// Registry facts used to pin the "read-only conversation lease" invariant.
const REGISTRY = loadCapabilityRegistry({ profile: "production" });
const READ_ONLY_OPERATIONS = new Set(
  REGISTRY.operations.filter((operation) => operation.side_effect_class === "none").map((operation) => operation.id),
);
// Candidate-staging (Reflection-only) and canonical/promotion/rollback/derived
// (Operator-only) operations must never enter an ordinary Conversation lease.
const REFLECTION_ONLY_OPERATIONS = Object.freeze(["knowledge.extract_l1", "knowledge.backfill", "ingestion.commit"]);
const OPERATOR_ONLY_OPERATIONS = Object.freeze(["snapshot.activate", "snapshot.rollback", "canonical.apply_correction"]);

// Sentinel private values. If any of these reaches a projection the test fails closed.
const SENTINELS = Object.freeze({
  prompt: "PRIVATE_PROMPT_SENTINEL_9f3a1c",
  toolInput: "PRIVATE_TOOL_INPUT_SENTINEL_7d2b4e",
  toolResult: "PRIVATE_TOOL_RESULT_SENTINEL_5c1d8a",
  completion: "PRIVATE_COMPLETION_SENTINEL_3e6f0b",
  credential: "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
  secret: "PRIVATE_SECRET_SENTINEL_1b5e7c",
});
// Mirrors the sessions/store.mjs private-body rejection vocabulary, exact-key form.
const FORBIDDEN_KEY = /^(?:body|content|prompt|completion|credential|secret)$/i;

function assertNoPrivateLeak(value, label) {
  const text = JSON.stringify(value);
  for (const [kind, sentinel] of Object.entries(SENTINELS)) {
    assert.equal(text.includes(sentinel), false, `${label} leaked ${kind} sentinel`);
  }
  const walk = (node, path) => {
    if (!node || typeof node !== "object") return;
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
      headers: payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload), ...extraHeaders } : { ...extraHeaders },
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

/**
 * Deterministic real-session double implementing the Pi AgentSession lifecycle:
 * subscribe / setActiveToolsByName / prompt / waitForIdle / abort / dispose.
 * script "settle" emits tool-call/result + message_end + agent_settled events;
 * script "hang" never settles (waitForIdle hangs); script "abort" never settles.
 */
function createSessionDouble({ script = "settle", toolRuns = [] } = {}) {
  const calls = { prompts: [], toolSets: [], idleWaits: 0, aborts: 0, disposes: 0 };
  const listeners = new Set();
  const emitted = [];
  let disposed = false;
  const emit = (event) => {
    emitted.push(event);
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
      disposed = true;
    },
    get isIdle() { return disposed || script !== "hang"; },
    get isStreaming() { return false; },
  };
  return { session, calls, emitted, get disposed() { return disposed; } };
}

// Future-module accessors so a missing module fails the specific test with a
// clear message instead of aborting the whole file.
async function importTurnService() {
  try {
    return await import("../src/conversation/turn-service.mjs");
  } catch (error) {
    assert.fail(`conversation/turn-service.mjs not implemented (expected RED): ${error.code ?? error.message}`);
  }
}

async function importPolicy() {
  try {
    return await import("../src/runtime/resource-policy.mjs");
  } catch (error) {
    assert.fail(`resource-policy.mjs profiles not implemented (expected RED): ${error.code ?? error.message}`);
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test("conversation turn route invokes the leased Pi session prompt and persists only safe receipts", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-conversation-turn-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");

  const toolRuns = [
    { tool: "knowledge.search", input: { query: SENTINELS.toolInput }, output: { ok: true, matches: 1, note: SENTINELS.toolResult } },
    { tool: "knowledge.get", input: { ref: "artifact:doc-1" }, output: { ok: true, title: "doc", content: SENTINELS.secret } },
  ];
  const double = createSessionDouble({ script: "settle", toolRuns });
  const sessionFactoryCalls = [];

  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    // Plan 61-03 Task 2 seam: the host accepts an injected conversation session
    // factory so deterministic tests supply the real-session double.
    conversationSessionFactory: async () => {
      sessionFactoryCalls.push(1);
      return { session: double.session, resourceLoader: null, modelRuntime: { providerCalls: 0 } };
    },
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  const body = {
    task_id: "pi_task_conversation_turn_001",
    session_id: "pi_session_conversation_turn_001",
    idempotency_key: "pi-idem-conversation-turn-001",
    skill_id: "knowledge.research",
    prompt: SENTINELS.prompt,
  };
  const response = await requestJson(port, "POST", "/v1/conversations/turn", body);
  assert.equal(response.status, 201, "POST /v1/conversations/turn must exist");
  assert.equal(response.json.ok, true);
  assert.equal(response.json.turn.state, "settled");
  assert.equal(response.json.turn.success, true);
  assert.equal(response.json.turn.task_id, body.task_id);
  assert.equal(response.json.turn.session_id, body.session_id);
  assert.equal(response.json.turn.profile, "conversation");
  assert.ok(response.json.turn.receipts, "turn must bind a sanitized receipt");
  assert.equal(sessionFactoryCalls.length, 1, "exactly one per-turn session must be created");

  // The route must own the real Pi lifecycle: prompt(source rpc) -> lease -> idle -> dispose.
  assert.equal(double.calls.prompts.length, 1);
  assert.equal(double.calls.prompts[0].text, body.prompt);
  assert.equal(double.calls.prompts[0].options.source, "rpc");
  assert.equal(double.calls.prompts[0].options.expandPromptTemplates, false);
  assert.ok(double.calls.idleWaits >= 1, "waitForIdle must be awaited");
  assert.equal(double.calls.disposes, 1, "session must be disposed in finally");

  // The active lease is exactly the conversation active set: every Skill tool is
  // present and every Reflection/Operator-only operation is absent (read-only).
  const lastLease = double.calls.toolSets.at(-1);
  assert.ok(Array.isArray(lastLease), "setActiveToolsByName must be called with the leased tool names");
  for (const tool of RESEARCH_SKILL.allowed_tools) {
    assert.ok(lastLease.includes(tool), `lease must include ${tool}`);
    assert.equal(READ_ONLY_OPERATIONS.has(tool), true, `${tool} must be read-only in the conversation lease`);
  }
  for (const tool of [...REFLECTION_ONLY_OPERATIONS, ...OPERATOR_ONLY_OPERATIONS]) {
    assert.equal(lastLease.includes(tool), false, `conversation lease must not include ${tool}`);
  }

  // No private sentinel or forbidden key reaches the response envelope.
  assertNoPrivateLeak(response.json, "turn response");
  assert.equal(response.text.includes(SENTINELS.prompt), false);
  assert.equal(response.text.includes(SENTINELS.toolInput), false);
  assert.equal(response.text.includes(SENTINELS.toolResult), false);

  await runtime.stop(100);
  const events = new EventJournal(join(dir, "events.sqlite"));
  const tasks = new TaskLedger(join(dir, "pi_kernel_tasks.sqlite"));
  const sessions = new SessionStore(join(dir, "pi_kernel_sessions.sqlite"));
  const candidates = new CandidateStore(join(dir, "pi_kernel_candidates.sqlite"));
  try {
    assert.equal(events.integrityCheck().ok, true);
    assert.equal(tasks.integrityCheck().ok, true);
    assert.equal(sessions.integrityCheck().ok, true);
    assert.equal(candidates.integrityCheck().ok, true);
    // Candidate staging must not be reachable from an ordinary conversation turn.
    assert.equal(candidates.list().length, 0, "conversation turn must not stage candidates");
    const eventRows = events.replay(0, 200).events;
    assert.ok(eventRows.length >= 1, "conversation turn must journal lifecycle events");
    const sessionRow = sessions.get(body.session_id);
    assert.ok(sessionRow, "conversation session metadata must be persisted");
    for (const row of eventRows) assertNoPrivateLeak(row, "event store");
    for (const task of tasks.list()) assertNoPrivateLeak(task, "task store");
    assertNoPrivateLeak(sessionRow, "session store");
    const allStored = JSON.stringify({ events: eventRows, tasks: tasks.list(), sessions: sessionRow, candidates: candidates.list() });
    for (const sentinel of Object.values(SENTINELS)) {
      assert.equal(allStored.includes(sentinel), false, "persisted store leaked sentinel");
    }
    assert.equal(allStored.includes("private"), false, "persisted store must be metadata-only");
  } finally {
    events.close(); tasks.close(); sessions.close(); candidates.close();
  }
});

test("turn-service projects only safe receipt categories from tool-call/result and settled events", async () => {
  const { runConversationTurn } = await importTurnService();
  assert.equal(typeof runConversationTurn, "function");

  const double = createSessionDouble({
    script: "settle",
    toolRuns: [
      { tool: "knowledge.search", input: { query: SENTINELS.toolInput }, output: { ok: true, hits: [{ id: "d1", text: SENTINELS.toolResult }] } },
      { tool: "knowledge.get", input: { ref: "artifact:d1" }, output: { ok: true, title: "t1", content: SENTINELS.secret } },
    ],
  });
  const result = await runConversationTurn({
    session: double.session,
    prompt: SENTINELS.prompt,
    activeToolNames: [...RESEARCH_SKILL.allowed_tools],
    profile: "conversation",
    taskId: "pi_task_turn_unit_001",
    sessionId: "pi_session_turn_unit_001",
    idempotencyKey: "pi-idem-turn-unit-001",
    skillId: RESEARCH_SKILL.id,
    skillChecksum: RESEARCH_SKILL.checksum,
    timeoutMs: 1000,
  });

  assert.equal(result.ok, true);
  assert.equal(result.turn.state, "settled");
  assert.equal(result.turn.success, true);
  assert.equal(result.turn.profile, "conversation");
  assert.equal(result.turn.skill_id, RESEARCH_SKILL.id);
  assert.equal(result.turn.receipts.skill_checksum, RESEARCH_SKILL.checksum);
  assert.equal(typeof result.turn.receipts.tool_count, "number");

  // The real lifecycle ran on the double.
  assert.equal(double.calls.prompts.length, 1);
  assert.equal(double.calls.prompts[0].options.source, "rpc");
  assert.equal(double.calls.prompts[0].options.expandPromptTemplates, false);
  assert.ok(double.calls.idleWaits >= 1);
  assert.equal(double.calls.disposes, 1);
  assert.equal(double.calls.toolSets.at(-1).length, RESEARCH_SKILL.allowed_tools.length);

  // Only safe categories are projected; raw tool input/output and prompt text never escape.
  const categories = result.turn.events.map((event) => event.category);
  assert.ok(categories.includes("tool_call"), "tool_call category must be projected");
  assert.ok(categories.includes("tool_result"), "tool_result category must be projected");
  assert.ok(categories.includes("settled"), "settled category must be projected");
  for (const event of result.turn.events) {
    assert.ok(["tool_call", "tool_result", "settled", "cancelled", "outcome_unknown", "failed"].includes(event.category), `unknown projected category ${event.category}`);
  }
  assertNoPrivateLeak(result.turn.events, "projected events");
  assertNoPrivateLeak(result, "turn result");
});

test("one runtime resolves Conversation/Reflection/Operator as three explicit profiles; unknown and cross-profile lookup fail closed", async () => {
  const policy = await importPolicy();
  const definitions = policy.PROFILE_DEFINITIONS;
  assert.ok(definitions, "resource-policy.mjs must export PROFILE_DEFINITIONS");

  const ids = Object.keys(definitions);
  for (const profileId of ["conversation", "reflection", "operator"]) {
    assert.ok(ids.includes(profileId), `missing explicit profile definition: ${profileId}`);
    assert.equal(definitions[profileId].id, profileId);
    assert.ok(Array.isArray(definitions[profileId].allowlist) && definitions[profileId].allowlist.length > 0, `${profileId} needs a non-empty allowlist`);
    assert.equal(typeof definitions[profileId].side_effect_class, "string");
    assert.ok(definitions[profileId].side_effect_class.length > 0, `${profileId} needs an explicit side_effect_class`);
  }
  assert.equal(new Set(ids.map((id) => definitions[id].id)).size, 3, "profile ids must be distinct");

  assert.equal(typeof policy.resolveProfile, "function");
  assert.equal(policy.resolveProfile("conversation"), definitions.conversation);
  assert.equal(policy.resolveProfile("administrator"), null, "unknown profile must resolve closed");

  assert.equal(typeof policy.profileToolNames, "function");
  assert.equal(policy.profileToolNames("administrator"), null, "unknown profile tool lookup must fail closed");
  const conversationTools = policy.profileToolNames("conversation");
  assert.ok(Array.isArray(conversationTools));
  // Cross-profile lookup must never union: operator/reflection-only tools are absent.
  for (const tool of OPERATOR_ONLY_OPERATIONS) {
    assert.equal(conversationTools.includes(tool), false, `conversation must not expose operator-only ${tool}`);
  }
  for (const tool of REFLECTION_ONLY_OPERATIONS) {
    assert.equal(conversationTools.includes(tool), false, `conversation must not expose reflection-only ${tool}`);
  }

  assert.equal(typeof policy.isProfileOperation, "function");
  assert.equal(policy.isProfileOperation("conversation", "snapshot.activate"), false);
  assert.equal(policy.isProfileOperation("conversation", "knowledge.extract_l1"), false);
  assert.equal(policy.isProfileOperation("operator", "snapshot.activate"), true);
});

test("Conversation active set derives from zero/one primary plus max one support skill; out-of-lease operations are rejected twice", async () => {
  const policy = await importPolicy();
  const derive = policy.deriveConversationLease;
  assert.equal(typeof derive, "function", "resource-policy.mjs must export deriveConversationLease");

  // Manifest integrity: the registry must reproduce the bound checksum.
  assert.equal(skillChecksum(RESEARCH_SKILL), RESEARCH_SKILL.checksum, "knowledge.research manifest checksum drift");

  const none = derive({ primarySkill: null, supportSkill: null });
  assert.equal(none.ok, true);
  assert.ok(Array.isArray(none.active_tool_names) && none.active_tool_names.length > 0, "zero-skill lease keeps the read-only conversation base");
  for (const tool of none.active_tool_names) {
    assert.equal(READ_ONLY_OPERATIONS.has(tool), true, `${tool} must be read-only in the base lease`);
  }

  const one = derive({ primarySkill: RESEARCH_SKILL });
  assert.equal(one.ok, true);
  for (const tool of RESEARCH_SKILL.allowed_tools) {
    assert.ok(one.active_tool_names.includes(tool), `lease must include ${tool}`);
  }

  const withSupport = derive({ primarySkill: RESEARCH_SKILL, supportSkill: SUPPORT_SKILL });
  assert.equal(withSupport.ok, true);
  for (const tool of SUPPORT_SKILL.allowed_tools) {
    assert.ok(withSupport.active_tool_names.includes(tool), `lease must include support ${tool}`);
  }

  const twoPrimary = derive({ primarySkill: [RESEARCH_SKILL, SUPPORT_SKILL] });
  assert.equal(twoPrimary.ok, false, "at most one primary skill");
  assert.equal(twoPrimary.reason, "at_most_one_primary");

  const twoSupport = derive({ primarySkill: RESEARCH_SKILL, supportSkill: [SUPPORT_SKILL, OTHER_SKILL] });
  assert.equal(twoSupport.ok, false, "at most one support skill");
  assert.equal(twoSupport.reason, "at_most_one_support");

  const tampered = derive({ primarySkill: { ...RESEARCH_SKILL, checksum: "t".repeat(64) } });
  assert.equal(tampered.ok, false, "checksum drift must fail closed");
  assert.equal(tampered.reason, "checksum_drift");

  const mutation = derive({ primarySkill: SNAPSHOT_RELEASE_SKILL });
  assert.equal(mutation.ok, false, "a promotion/rollback skill must not become a conversation lease");
  assert.equal(mutation.reason, "not_read_only");

  // Defense 1 - Kernel bridge: an out-of-lease operation is rejected before any gateway transport dispatch.
  const dispatchCalls = [];
  const bridge = createProjectDomainBridge({
    operations: one.active_tool_names,
    transport: async (payload) => {
      dispatchCalls.push(payload);
      return { status: 200, body: { ok: true } };
    },
  });
  await assert.rejects(
    () => bridge.invoke("snapshot.activate", { task_id: "pi_task_lease_001", idempotency_key: "pi-idem-lease-001", binding: "pi_kernel_skill" }),
    (error) => {
      assert.equal(error.code, "skill_tool_escalation");
      return true;
    },
  );
  assert.equal(dispatchCalls.length, 0, "out-of-lease operation must be rejected before gateway dispatch");

  // Defense 2 - Python gateway: the governed dispatch independently rejects unknown
  // operations (mirrors pi_domain_gateway.py unknown_operation; the real gateway is
  // verified by tests/contract/test_pi_domain_gateway.py).
  const gateway = createGatewayContract(one.active_tool_names);
  assert.throws(
    () => gateway.verify("snapshot.activate"),
    (error) => { assert.equal(error.code, "unknown_operation"); return true; },
  );
  for (const tool of one.active_tool_names) gateway.verify(tool);
});

test("ordinary Conversation cannot stage Candidate metadata or mutate canonical state; cancel/outcome_unknown are non-success", async () => {
  const policy = await importPolicy();
  const conversationTools = policy.profileToolNames("conversation");
  const reflectionTools = policy.profileToolNames("reflection");
  const operatorTools = policy.profileToolNames("operator");

  // Ordinary Conversation authority boundary: no candidate staging, no canonical
  // mutation, no promotion/rollback, no derived index/snapshot authority.
  for (const tool of [...REFLECTION_ONLY_OPERATIONS, ...OPERATOR_ONLY_OPERATIONS, "canonical.deduplicate", "index.build", "snapshot.prepare"]) {
    assert.equal(conversationTools.includes(tool), false, `conversation must not expose ${tool}`);
  }
  assert.ok(
    REFLECTION_ONLY_OPERATIONS.some((tool) => reflectionTools.includes(tool)),
    "reflection profile must include candidate-staging operations",
  );
  assert.ok(
    OPERATOR_ONLY_OPERATIONS.some((tool) => operatorTools.includes(tool)),
    "operator profile must include promotion/rollback operations",
  );
  assert.ok(operatorTools.includes("canonical.apply_correction") || operatorTools.includes("canonical.deduplicate"), "operator profile must include canonical mutation operations");

  // Cancellation is retained as non-success through the Pi lifecycle.
  const { runConversationTurn } = await importTurnService();
  const cancelDouble = createSessionDouble({ script: "abort" });
  const controller = new AbortController();
  controller.abort();
  const cancelled = await runConversationTurn({
    session: cancelDouble.session,
    prompt: SENTINELS.prompt,
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_cancel_001",
    sessionId: "pi_session_cancel_001",
    idempotencyKey: "pi-idem-cancel-001",
    signal: controller.signal,
    timeoutMs: 1000,
  });
  assert.equal(cancelled.ok, true);
  assert.equal(cancelled.turn.state, "cancelled");
  assert.equal(cancelled.turn.success, false, "cancellation must not be a success envelope");
  assert.equal(cancelDouble.calls.prompts.length, 0, "pre-aborted signal must not start an agent run");
  assert.ok(cancelDouble.calls.aborts >= 1);
  assert.equal(cancelDouble.calls.disposes, 1);
  assert.equal(JSON.stringify(cancelled).includes("succeeded"), false);
  assertNoPrivateLeak(cancelled, "cancelled turn result");

  // outcome_unknown (turn never settles within budget) requires reconciliation and
  // is never reported as success.
  const hangDouble = createSessionDouble({ script: "hang" });
  const unknown = await runConversationTurn({
    session: hangDouble.session,
    prompt: SENTINELS.prompt,
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_unknown_001",
    sessionId: "pi_session_unknown_001",
    idempotencyKey: "pi-idem-unknown-001",
    timeoutMs: 15,
  });
  assert.equal(unknown.turn.state, "outcome_unknown");
  assert.equal(unknown.turn.success, false, "outcome_unknown must not be a success envelope");
  assert.ok(hangDouble.calls.idleWaits >= 1);
  assert.ok(hangDouble.calls.aborts >= 1, "outcome_unknown must abort the hung session");
  assert.equal(hangDouble.calls.disposes, 1);
  assert.equal(JSON.stringify(unknown).includes("succeeded"), false);
  assertNoPrivateLeak(unknown, "outcome_unknown turn result");
});

test("providerMode stays undefined unless options/environment supplies it (user kernel-host regression)", async () => {
  const source = await readFile(join(KERNEL_ROOT, "src/kernel-host.mjs"), "utf8");
  const line = source.split(/\r?\n/).find((candidate) => /^\s*mode:\s*options\.providerMode/.test(candidate));
  assert.ok(line, "kernel-host provider adapter mode line not found");
  const trimmed = line.trim();
  assert.match(trimmed, /^mode:\s*options\.providerMode\s*\?\?\s*process\.env\.PI_KERNEL_PROVIDER_MODE,?$/,
    "providerMode must stay undefined unless options/environment supplies it");
  assert.equal(trimmed.includes('"replay"'), false, "the implicit replay default must not be restored");
  assert.equal(/providerMode\s*\?\?\s*process\.env\.PI_KERNEL_PROVIDER_MODE\s*\?\?\s*"replay"/.test(source), false);
  const fingerprint = createHash("sha256").update(trimmed).digest("hex");
  // Provider-mode config fingerprint for the Phase 61 regression gate record.
  console.log(`[provider-mode] fingerprint ${fingerprint}`);
});

/** Deterministic mirror of the Python gateway's unknown_operation guard. */
function createGatewayContract(operations) {
  const allowed = new Set(operations);
  return {
    verify(operation) {
      if (!allowed.has(operation)) {
        const error = new Error("unknown_operation");
        error.code = "unknown_operation";
        throw error;
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Plan 61-05 Task 1 RED contract: `conversation.session.create`
//
// The Kernel owns the named empty-session intent. It must first validate the
// requested project scope through the Python canonical `conversation.project_scope.select`
// provider, then create only governed empty Session metadata
// `{session_id, project_scope_id, created_at, status:"empty"}` plus an empty safe
// `ConversationThreadView`. It must never write canonical conversation bodies,
// Candidate, promotion, active pointer or desktop persistence, and it must never
// describe runtime text as canonical history.
//
// HTTP seam (Plan 61-05 Task 2): POST /v1/conversations/session on server.mjs
// dispatch, backed by src/conversation/session-service.mjs through kernel-host.mjs.
// This test is RED today: the route does not exist, so every request returns
// `route_not_found` (404) instead of the contract below.
// ---------------------------------------------------------------------------

test("conversation.session.create validates approved scope and creates only empty Session metadata (RED until 61-05 Task 2)", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-conversation-session-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");

  // Injected domain bridge stub: the Kernel must ask the Python canonical
  // `conversation.project_scope.select` provider before creating a session.
  const approvedScopes = new Set(["/work/alpha"]);
  const scopeCalls = [];
  const scopeBridge = {
    async invoke(operation, params) {
      scopeCalls.push({ operation, params });
      if (operation !== "conversation.project_scope.select") {
        return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
      if (!approvedScopes.has(params?.project_scope_id)) {
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
    },
  };

  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: scopeBridge,
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  const sqliteFiles = () => readdirSync(dir).filter((name) => name.endsWith(".sqlite")).sort();

  const createBody = {
    session_id: "pi_session_empty_001",
    project_scope_id: "/work/alpha",
    idempotency_key: "pi-idem-session-create-001",
    binding: "pi_kernel_session",
  };
  const response = await requestJson(port, "POST", "/v1/conversations/session", createBody);
  assert.equal(response.status, 201, "POST /v1/conversations/session must exist");
  assert.equal(response.json.ok, true);
  // Exactly the governed empty Session metadata; nothing else.
  assert.deepEqual(Object.keys(response.json.session).sort(), ["created_at", "project_scope_id", "session_id", "status"]);
  assert.equal(response.json.session.session_id, createBody.session_id);
  assert.equal(response.json.session.project_scope_id, createBody.project_scope_id);
  assert.equal(response.json.session.status, "empty");
  assert.ok(response.json.session.created_at, "created_at must be present");
  // Empty safe ConversationThreadView: no body, no history claim.
  assert.ok(Array.isArray(response.json.thread.messages) && response.json.thread.messages.length === 0, "the new session thread view is empty");
  assert.equal(response.json.thread.state, "empty");
  assert.ok(response.json.thread.limitation, "empty thread view must state its limitation");
  assertNoPrivateLeak(response.json, "session create response");

  // Approved scope validation happened exactly once through the canonical provider.
  assert.equal(scopeCalls.length, 1, "conversation.project_scope.select must validate the scope");
  assert.equal(scopeCalls[0].operation, "conversation.project_scope.select");
  assert.equal(scopeCalls[0].params.project_scope_id, createBody.project_scope_id);

  // An unapproved/foreign scope must be rejected and create nothing.
  const rejected = await requestJson(port, "POST", "/v1/conversations/session", {
    ...createBody, session_id: "pi_session_rejected_001", project_scope_id: "scope:not-approved",
    idempotency_key: "pi-idem-session-create-rejected",
  });
  assert.equal(rejected.status, 400, "unapproved scope must be rejected");
  assert.equal(rejected.json.ok, false);
  assertNoPrivateLeak(rejected.json, "rejected session response");

  // Missing idempotency_key/binding fail closed.
  for (const [label, malformed] of [
    ["no idempotency key", { ...createBody, session_id: "pi_session_malformed_001", idempotency_key: undefined }],
    ["no binding", { ...createBody, session_id: "pi_session_malformed_002", binding: undefined }],
  ]) {
    const bad = await requestJson(port, "POST", "/v1/conversations/session", malformed);
    assert.equal(bad.status, 400, `${label} must fail closed`);
    assert.equal(bad.json.ok, false);
  }

  // Runtime text in the request must never leak or be described as canonical history.
  const leaked = await requestJson(port, "POST", "/v1/conversations/session", {
    ...createBody, session_id: "pi_session_leak_001",
    idempotency_key: "pi-idem-session-create-leak", prompt: SENTINELS.prompt,
  });
  assert.equal(leaked.text.includes(SENTINELS.prompt), false, "request text must never leak into the response");

  await runtime.stop(100);
  const sessions = new SessionStore(join(dir, "pi_kernel_sessions.sqlite"));
  const candidates = new CandidateStore(join(dir, "pi_kernel_candidates.sqlite"));
  const tasks = new TaskLedger(join(dir, "pi_kernel_tasks.sqlite"));
  const events = new EventJournal(join(dir, "events.sqlite"));
  try {
    const row = sessions.get(createBody.session_id);
    assert.ok(row, "created session metadata must be persisted in the governed Session store");
    assert.equal(JSON.stringify(row).includes("display_text"), false, "no display text may be persisted");
    assert.equal(JSON.stringify(row).includes(SENTINELS.prompt), false, "no request body may be persisted");
    assertNoPrivateLeak(row, "session store row");
    assert.equal(candidates.list().length, 0, "session.create must never stage Candidate metadata");
    assert.equal(tasks.list().length, 0, "session.create must not create tasks");
    const allStored = JSON.stringify({
      sessions: sessions.get(createBody.session_id),
      candidates: candidates.list(), tasks: tasks.list(), events: events.replay(0, 500).events,
    });
    for (const sentinel of Object.values(SENTINELS)) {
      assert.equal(allStored.includes(sentinel), false, "session stores leaked sentinel");
    }
    assert.equal(allStored.includes("canonical history"), false, "empty session must never claim canonical history");
    // No second conversation fact store: only the four governed Kernel DBs exist.
    assert.deepEqual(
      sqliteFiles(),
      ["events.sqlite", "pi_kernel_candidates.sqlite", "pi_kernel_sessions.sqlite", "pi_kernel_tasks.sqlite"],
      "no second conversation fact store may be created",
    );
  } finally {
    sessions.close(); candidates.close(); tasks.close(); events.close();
  }
});

// ---------------------------------------------------------------------------
// Plan 61-08 Task 1 RED contract: fixed Candidate review route
// (`POST /v1/candidates/review` -> `candidate.review` Gateway binding).
//
// The Kernel owns one fixed review route. It validates the exact review request
// shape, dispatches ONLY `candidate.review` to the bound Gateway bridge (never
// an arbitrary endpoint/path/provider), and returns a metadata-only receipt
// envelope. Private/override fields, batch inputs and alternate paths are
// rejected before dispatch. The user-owned providerMode behavior regression
// above is untouched by this contract.
//
// This test is RED today: the route does not exist (404 route_not_found), so
// every route expectation below fails pointing at the missing Plan 61-08
// Task 2 dispatch, never at a syntax error.
// ---------------------------------------------------------------------------

const CANDIDATE_REVIEW_ROUTE = "/v1/candidates/review";

function sha256Hex(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

function candidateReviewBody(overrides = {}) {
  return {
    candidate_id: "cand_review_001",
    action: "accept",
    expected_version: 1,
    explicit_confirmation: true,
    confirmation_token: "confirm-token-001",
    task_id: "pi_task_review_001",
    idempotency_key: "pi-idem-review-001",
    binding: "pi_kernel_candidate_review",
    ...overrides,
  };
}

/** Gateway double: records every dispatch and mirrors the Python gateway guard. */
function createReviewBridge(records) {
  return {
    async invoke(operation, params) {
      records.push({ operation, params });
      if (operation !== "candidate.review") {
        return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
      const privateField = Object.keys(params || {}).find((key) => /^(?:body|content|prompt|completion|credential|secret|provider|operation|authority|path|sql|batch|candidate_ids)$/i.test(key));
      if (privateField) {
        return { ok: false, status: "error", error: { code: "undeclared_input" } };
      }
      return {
        ok: true, status: "success",
        data: {
          status: "reviewed",
          candidate_id: params.candidate_id,
          candidate_checksum: sha256Hex(params.candidate_id),
          action: params.action,
          version: 2,
          feedback_id: "feedback_review_001",
          receipt: {
            receipt_id: "review_receipt_001",
            receipt_checksum: sha256Hex(`${params.candidate_id}:review`),
            feedback_id: "feedback_review_001",
            candidate_id: params.candidate_id,
            candidate_checksum: sha256Hex(params.candidate_id),
            metadata_only: true,
          },
        },
      };
    },
  };
}

async function startCandidateReviewServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-candidate-review-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const bridgeCalls = [];
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: createReviewBridge(bridgeCalls),
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });
  return { port, bridgeCalls };
}

test("fixed POST /v1/candidates/review maps only to candidate.review through the KernelHost->Gateway binding", async (t) => {
  const { port, bridgeCalls } = await startCandidateReviewServer(t);
  const body = candidateReviewBody();
  const response = await requestJson(port, "POST", CANDIDATE_REVIEW_ROUTE, body);
  assert.notEqual(response.status, 404, "RED: POST /v1/candidates/review must exist (expected for 61-08 Task 1)");
  assert.ok([200, 201].includes(response.status), "a safe review success must be a 2xx envelope");
  assert.equal(response.json.ok, true);
  const payload = response.json.data ?? response.json;
  assert.equal(payload.status, "reviewed");
  assert.equal(payload.candidate_id, body.candidate_id);
  assert.equal(payload.receipt.feedback_id, "feedback_review_001", "the receipt binds the append-only feedback id");
  assertNoPrivateLeak(response.json, "candidate review response");

  // The route reaches the bound Gateway bridge exactly once and never another
  // endpoint/provider: this is a KernelHost/server -> Gateway binding, not a
  // direct Candidate helper.
  assert.equal(bridgeCalls.length, 1, "the route must dispatch exactly once to the bound Gateway bridge");
  assert.equal(bridgeCalls[0].operation, "candidate.review", "the fixed route maps ONLY to candidate.review");
  assert.equal(bridgeCalls[0].params.candidate_id, body.candidate_id);
  assert.equal(bridgeCalls[0].params.action, body.action);
  assert.equal(bridgeCalls[0].params.expected_version, 1);
  assert.equal(bridgeCalls[0].params.idempotency_key, body.idempotency_key);
  assert.equal(bridgeCalls[0].params.binding, body.binding);
  assert.equal(/promot|rollback|watermark|active_pointer/.test(JSON.stringify(response.json)), false,
    "the review envelope must never claim canonical/promotion authority mutation");
});

test("candidate review has exactly one fixed route; method/path/provider/private input fail closed", async (t) => {
  const { port, bridgeCalls } = await startCandidateReviewServer(t);
  const body = candidateReviewBody();

  // The fixed route is POST-only.
  const get = await requestJson(port, "GET", CANDIDATE_REVIEW_ROUTE);
  assert.equal(get.status, 405, "RED: POST /v1/candidates/review must exist and reject other methods (got 404/405)");
  assert.equal(get.json.error.code, "method_not_allowed");

  // Alternate paths must not exist (one fixed route, no endpoint override).
  for (const path of ["/v1/candidates/review/extra", "/v1/candidates/accept", "/v1/candidates/ignore", "/v1/review-candidates", "/v1/candidates"]) {
    const alt = await requestJson(port, "POST", path, body);
    assert.equal(alt.status, 404, `${path} must be route_not_found`);
    assert.equal(alt.json.error.code, "route_not_found");
  }

  // Private/override fields reject before Gateway dispatch (no provider override).
  const before = bridgeCalls.length;
  for (const [label, extra] of [
    ["private prompt", { prompt: SENTINELS.prompt }],
    ["private secret", { secret: SENTINELS.secret }],
    ["provider override", { provider: "model.wake" }],
    ["operation override", { operation: "canonical.promote" }],
    ["batch accept", { batch: true }],
  ]) {
    const rejected = await requestJson(port, "POST", CANDIDATE_REVIEW_ROUTE, { ...body, ...extra });
    assert.equal(rejected.status, 400, `${label} must be rejected by the fixed route (got ${rejected.status})`);
    assert.equal(rejected.json.ok, false);
    assertNoPrivateLeak(rejected.json, `${label} rejection`);
    assert.equal(rejected.text.includes(SENTINELS.prompt), false, `${label} must never leak request text`);
  }
  assert.equal(bridgeCalls.length, before, "private/override fields must never reach the Gateway bridge");
});

test("candidate review route rejects missing and malformed request bodies safely", async (t) => {
  const { port, bridgeCalls } = await startCandidateReviewServer(t);

  const noBody = await requestJson(port, "POST", CANDIDATE_REVIEW_ROUTE);
  assert.equal(noBody.status, 400, "RED: POST /v1/candidates/review must exist and reject missing bodies (got 404/400)");
  assert.equal(noBody.json.ok, false);
  assertNoPrivateLeak(noBody.json, "missing body rejection");

  const incomplete = await requestJson(port, "POST", CANDIDATE_REVIEW_ROUTE, { action: "accept" });
  assert.equal(incomplete.status, 400, "an incomplete review request must fail closed");
  assert.equal(incomplete.json.ok, false);

  assert.equal(bridgeCalls.length, 0, "a malformed review must never reach the Gateway bridge");
});

// ---------------------------------------------------------------------------
// Plan 61-09 Task 1 RED contract: fixed `personal.model_projection.get` route
// (GET /v1/personal/model-projection) and governed next-turn context injection
// (HARNESS-07).
//
// The Kernel owns ONE fixed read route. It validates the approved input
// vocabulary (scope/binding/task_id/idempotency_key), dispatches ONLY
// `personal.model_projection.get` to the bound Gateway bridge (never an
// arbitrary endpoint/path/provider), and returns a safe metadata-only
// projection envelope. Private/override fields and alternate paths are rejected
// before dispatch. The real turn-service pre-prompt context builder calls the
// provider with the turn's scope/binding and injects ONLY compatible current
// derived context before `AgentSession.prompt`; stale/unknown/conflicting/
// foreign-scope results are omitted with a limitation, never inferred as truth.
//
// This section is RED today: the route does not exist (404 route_not_found) and
// `runConversationTurn` has no projection context builder, so every expectation
// below fails pointing at the missing Plan 61-09 Task 2 dispatch/injection,
// never at a syntax error. The 61-03/61-05/61-08 tests above stay green.
// ---------------------------------------------------------------------------

const MODEL_PROJECTION_ROUTE = "/v1/personal/model-projection";
const MODEL_PROJECTION_OPERATION = "personal.model_projection.get";

function projectionFixture(scope, overrides = {}) {
  return {
    projection_id: "projection_61_09_001",
    version: 1,
    provenance_class: "inference",
    scope,
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
    ...overrides,
  };
}

/** Gateway double: records every dispatch and mirrors the Python gateway guard. */
function createProjectionBridge(records) {
  return {
    async invoke(operation, params) {
      records.push({ operation, params });
      if (operation !== MODEL_PROJECTION_OPERATION) {
        return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
      const privateField = Object.keys(params || {}).find((key) =>
        /^(?:body|content|prompt|completion|credential|secret|provider|operation|authority|endpoint|path|sql|raw_evidence|authority_override)$/i.test(key));
      if (privateField) {
        return { ok: false, status: "error", error: { code: "undeclared_input" } };
      }
      return { ok: true, status: "success", data: projectionFixture(String(params.scope ?? "")) };
    },
  };
}

async function startProjectionServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-model-projection-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const bridgeCalls = [];
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: createProjectionBridge(bridgeCalls),
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });
  return { port, bridgeCalls };
}

function projectionQuery(overrides = {}) {
  const params = {
    scope: "/work/alpha",
    task_id: "pi_task_projection_001",
    idempotency_key: "pi-idem-projection-001",
    binding: "pi_kernel_model_projection",
    ...overrides,
  };
  return Object.entries(params)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
    .join("&");
}

test("fixed GET /v1/personal/model-projection maps only to personal.model_projection.get through KernelHost->Gateway binding", async (t) => {
  const { port, bridgeCalls } = await startProjectionServer(t);
  const response = await requestJson(port, "GET", `${MODEL_PROJECTION_ROUTE}?${projectionQuery()}`);
  assert.notEqual(response.status, 404, "RED: GET /v1/personal/model-projection must exist (expected for 61-09 Task 1)");
  assert.equal(response.status, 200, "a safe projection read must be a 200 envelope");
  assert.equal(response.json.ok, true);
  const payload = response.json.data ?? response.json;
  assert.equal(payload.status, "current");
  assert.equal(payload.provenance_class, "inference", "a projection is an inference, never a fact");
  assert.equal(payload.scope, "/work/alpha");
  assert.equal(typeof payload.version, "number");
  assert.ok(Array.isArray(payload.support_refs) && payload.support_count === payload.support_refs.length);
  assert.ok(Array.isArray(payload.conflict_refs) && payload.conflict_count === payload.conflict_refs.length);
  assert.ok("supersession" in payload, "the projection records supersession");
  assert.ok(payload.limitations?.length > 0, "the projection states its limitations");
  assert.ok(payload.freshness?.source_to_agentsview && payload.freshness?.agentsview_to_canonical, "two typed freshness legs are returned");
  assertNoPrivateLeak(response.json, "model projection response");

  // The route reaches the bound Gateway bridge exactly once and never another
  // endpoint/provider: this is a KernelHost/server -> Gateway binding.
  assert.equal(bridgeCalls.length, 1, "the fixed route must dispatch exactly once to the bound Gateway bridge");
  assert.equal(bridgeCalls[0].operation, MODEL_PROJECTION_OPERATION, "the fixed route maps ONLY to personal.model_projection.get");
  assert.equal(bridgeCalls[0].params.scope, "/work/alpha");
  assert.equal(bridgeCalls[0].params.task_id, "pi_task_projection_001");
  assert.equal(bridgeCalls[0].params.idempotency_key, "pi-idem-projection-001");
  assert.equal(bridgeCalls[0].params.binding, "pi_kernel_model_projection");
  assert.equal(/promot|rollback|watermark|active_pointer|canonical\./.test(JSON.stringify(response.json)), false,
    "the projection envelope must never claim canonical/promotion authority mutation");
});

test("model projection has exactly one fixed route; method/path/provider/private input fail closed", async (t) => {
  const { port, bridgeCalls } = await startProjectionServer(t);
  const query = projectionQuery();

  // The fixed route is GET-only.
  const post = await requestJson(port, "POST", MODEL_PROJECTION_ROUTE, { scope: "/work/alpha" });
  assert.equal(post.status, 405, "RED: GET /v1/personal/model-projection must exist and reject other methods (got 404/405)");
  assert.equal(post.json.error.code, "method_not_allowed");

  // Alternate paths must not exist (one fixed route, no endpoint override).
  for (const path of [
    "/v1/personal/model-projection/extra",
    "/v1/personal/projections",
    "/v1/model-projection",
    "/v1/projections",
    "/v1/personal/model",
  ]) {
    const alt = await requestJson(port, "GET", `${path}?${query}`);
    assert.equal(alt.status, 404, `${path} must be route_not_found`);
    assert.equal(alt.json.error.code, "route_not_found");
  }

  // Private/override query inputs reject before Gateway dispatch (no provider override).
  const before = bridgeCalls.length;
  for (const [label, extra] of [
    ["private prompt", { prompt: SENTINELS.prompt }],
    ["private secret", { secret: SENTINELS.secret }],
    ["provider override", { provider: "model.wake" }],
    ["operation override", { operation: "canonical.promote" }],
    ["endpoint override", { endpoint: "http://127.0.0.1:9999" }],
    ["path override", { path: "/v1/canonical" }],
  ]) {
    const rejected = await requestJson(port, "GET", `${MODEL_PROJECTION_ROUTE}?${projectionQuery(extra)}`);
    assert.equal(rejected.status, 400, `${label} must be rejected by the fixed route (got ${rejected.status})`);
    assert.equal(rejected.json.ok, false);
    assertNoPrivateLeak(rejected.json, `${label} rejection`);
    assert.equal(rejected.text.includes(SENTINELS.prompt), false, `${label} must never leak request text`);
  }
  assert.equal(bridgeCalls.length, before, "private/override fields must never reach the Gateway bridge");
});

test("real turn session receives only approved compatible derived context before AgentSession.prompt", async (t) => {
  const { runConversationTurn } = await importTurnService();
  assert.equal(typeof runConversationTurn, "function");

  // Positive: one compatible current projection is injected before prompt.
  const providerCalls = [];
  const approvedProvider = async ({ scope, binding } = {}) => {
    providerCalls.push({ scope, binding });
    return { ok: true, status: "success", data: projectionFixture(scope) };
  };
  const double = createSessionDouble({ script: "settle" });
  const result = await runConversationTurn({
    session: double.session,
    prompt: SENTINELS.prompt,
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_projection_turn_001",
    sessionId: "pi_session_projection_turn_001",
    idempotencyKey: "pi-idem-projection-turn-001",
    scope: "/work/alpha",
    binding: "pi_kernel_conversation_turn",
    modelProjectionProvider: approvedProvider,
    timeoutMs: 1000,
  });
  assert.equal(result.ok, true);
  assert.equal(providerCalls.length, 1, "RED: turn-service must call personal.model_projection.get before prompt (expected for 61-09 Task 1)");
  assert.equal(providerCalls[0].scope, "/work/alpha", "the provider is called with the turn scope");
  assert.equal(providerCalls[0].binding, "pi_kernel_conversation_turn", "the provider is called with the turn binding");
  assert.equal(double.calls.prompts.length, 1);
  const promptOptions = double.calls.prompts[0].options;
  assert.ok(Array.isArray(promptOptions.projection_context), "RED: typed projection context must be built before AgentSession.prompt");
  const injected = promptOptions.projection_context;
  assert.equal(injected.some((entry) => entry.scope === "/work/alpha" && entry.version === 1 && entry.status === "current"), true,
    "the approved compatible projection is injected into the pre-prompt context");
  assert.equal(injected.some((entry) => entry.provenance_class === "fact"), false, "no projection is injected as a fact");
  assert.ok(result.turn.receipts.projection, "the safe receipt carries the projection summary");
  assert.equal(result.turn.receipts.projection.version, 1, "the receipt returns the projection version");
  assert.ok(result.turn.receipts.projection.freshness, "the receipt returns freshness");
  assert.ok(result.turn.receipts.projection.limitations, "the receipt returns limitations");
  assertNoPrivateLeak(result, "projection-aware turn result");

  // Negative: stale/unknown/conflicting/foreign results are omitted with a
  // limitation and never injected as current derived context.
  const negativeCases = {
    stale: { status: "stale", version: 1 },
    conflict: { status: "conflict", version: 2, conflict_refs: ["ref:conflict"], conflict_count: 1, conflicts: [{ ref: "ref:conflict", disposition: "coexist_by_context" }] },
    unknown: { status: "unknown", projection_id: null, version: 0, support_refs: [], support_count: 0 },
    foreign_scope: { scope: "scope:foreign" },
  };
  for (const [label, projectionOverride] of Object.entries(negativeCases)) {
    const negativeDouble = createSessionDouble({ script: "settle" });
    const negativeProvider = async ({ scope } = {}) => ({ ok: true, status: "success", data: projectionFixture(scope, projectionOverride) });
    const negative = await runConversationTurn({
      session: negativeDouble.session,
      prompt: SENTINELS.prompt,
      activeToolNames: ["knowledge.search"],
      profile: "conversation",
      taskId: `pi_task_projection_${label}_001`,
      sessionId: `pi_session_projection_${label}_001`,
      idempotencyKey: `pi-idem-projection-${label}-001`,
      scope: "/work/alpha",
      binding: "pi_kernel_conversation_turn",
      modelProjectionProvider: negativeProvider,
      timeoutMs: 1000,
    });
    const context = negativeDouble.calls.prompts[0]?.options?.projection_context ?? [];
    assert.equal(
      context.some((entry) => entry.scope === "/work/alpha" && (entry.status === "current" || entry.status === "uncertain")),
      false,
      `${label} derived context must never be injected as current compatible context`,
    );
    assert.ok(negative.turn.receipts.projection, `${label} receipt still carries a projection summary`);
    assert.ok(negative.turn.receipts.projection.limitations, `${label} omission must state a limitation`);
    assert.equal(negative.turn.receipts.projection.version, undefined, `${label} omission must not report a usable version`);
    assertNoPrivateLeak(negative, `${label} turn result`);
  }
});

// ---------------------------------------------------------------------------
// Plan 61-10 Task 1 RED contract: four fixed proactive routes
// (POST /v1/proactive/state, POST /v1/proactive/controls,
//  POST /v1/proactive/dismiss, POST /v1/proactive/undo).
//
// The Kernel owns four fixed deterministic proactive presentation bindings
// (D-23-D-25, HARNESS-05): getProactiveState -> proactive.state.get,
// updateProactiveControls -> proactive.controls.update,
// dismissProactive -> proactive.dismiss and undoProactiveDismissal ->
// proactive.dismiss.undo. Each route validates the exact request shape and
// dispatches ONLY its named Gateway provider -- never an arbitrary
// endpoint/path/provider. Scope is exactly "global" or an approved project
// identifier; category is exactly 同步/简报/反思候选. Responses are no-store
// metadata-only: active/quiet status, quiet_until, one card per evidence
// cluster with merged count and source/time/receipt/support/conflict refs,
// control state and append-only feedback ID. The Kernel validates request
// shape/identity/quiet-hour format/top-level category; the Gateway/adapter
// validates scope approval, the declared event/category vocabulary and
// feedback identity. Controls/dismiss/undo never schedule, change
// permissions/values or write canonical/promotion/rollback/watermark/
// active-pointer authority (T-61-PROACTIVE-02/-03).
//
// This section is RED today: none of the four routes or KernelHost methods
// exist (404 route_not_found), so every expectation below fails pointing at
// the missing Plan 61-10 Task 2 dispatch, never at a syntax error. The
// 61-03/61-05/61-08/61-09 tests above stay green.
// ---------------------------------------------------------------------------

const PROACTIVE_ROUTES = Object.freeze({
  state: "/v1/proactive/state",
  controls: "/v1/proactive/controls",
  dismiss: "/v1/proactive/dismiss",
  undo: "/v1/proactive/undo",
});
const PROACTIVE_PROVIDERS = Object.freeze({
  state: "proactive.state.get",
  controls: "proactive.controls.update",
  dismiss: "proactive.dismiss",
  undo: "proactive.dismiss.undo",
});
const PROACTIVE_CATEGORIES = new Set(["同步", "简报", "反思候选"]);
const PROJECT_SCOPE_PATTERN = /^project:[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,255}$/;
const QUIET_TIME_PATTERN = /^([01]?\d|2[0-3]):([0-5]\d)$/;

function proactiveStateBody(overrides = {}) {
  return {
    scope: "global",
    events: [
      { event_id: "pi_evt_proactive_001", type: "conversation.delta.committed", source: "pk-sync", occurred_at: "2026-08-09T09:00:00.000Z", category: "反思候选", scope: "global", cluster_key: "cluster-proactive-1", support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], receipt_checksum: "a".repeat(64), canonical_checksum: "b".repeat(64), watermark: "b".repeat(64), rule_version: "conversation-reflection-v1" },
      { event_id: "pi_evt_proactive_002", type: "conversation.delta.committed", source: "pk-sync", occurred_at: "2026-08-09T09:05:00.000Z", category: "反思候选", scope: "global", cluster_key: "cluster-proactive-1", support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], receipt_checksum: "c".repeat(64), canonical_checksum: "b".repeat(64), watermark: "b".repeat(64), rule_version: "conversation-reflection-v1" },
    ],
    controls: [
      { scope: "global", category: "同步", enabled: true },
      { scope: "global", category: "简报", enabled: true },
      { scope: "global", category: "反思候选", enabled: true },
    ],
    quiet_hours: { enabled: false, start: "22:00", end: "07:00" },
    now: "2026-08-09T12:00:00Z",
    manual_order: ["manual-1", "manual-2"],
    task_id: "pi_task_proactive_state_001",
    idempotency_key: "pi-idem-proactive-state-001",
    binding: "pi_kernel_proactive_state",
    ...overrides,
  };
}

function proactiveControlsBody(overrides = {}) {
  return {
    scope: "global",
    category: "同步",
    enabled: true,
    task_id: "pi_task_proactive_controls_001",
    idempotency_key: "pi-idem-proactive-controls-001",
    binding: "pi_kernel_proactive_controls",
    ...overrides,
  };
}

function proactiveDismissBody(overrides = {}) {
  return {
    cluster_key: "cluster-proactive-1",
    feedback_id: "feedback_proactive_dismiss_001",
    actor_identity_hash: "a".repeat(64),
    now: "2026-08-09T10:00:00Z",
    task_id: "pi_task_proactive_dismiss_001",
    idempotency_key: "pi-idem-proactive-dismiss-001",
    binding: "pi_kernel_proactive_dismiss",
    ...overrides,
  };
}

function proactiveUndoBody(overrides = {}) {
  return {
    dismissal_feedback_id: "feedback_proactive_dismiss_001",
    feedback_id: "feedback_proactive_undo_001",
    actor_identity_hash: "a".repeat(64),
    now: "2026-08-09T10:05:00Z",
    task_id: "pi_task_proactive_undo_001",
    idempotency_key: "pi-idem-proactive-undo-001",
    binding: "pi_kernel_proactive_undo",
    ...overrides,
  };
}

/** Gateway double: records every dispatch and mirrors the Python gateway guard. */
function createProactiveBridge(records) {
  const approvedProjects = new Set(["project:alpha"]);
  const privateField = (params) => Object.keys(params || {}).find((key) =>
    /^(?:body|content|prompt|completion|credential|secret|token|password|sql|statement|provider|operation|endpoint|path|authority|schedule|permission|value|canonical|promotion|rollback)$/i.test(key));
  return {
    async invoke(operation, params) {
      records.push({ operation, params });
      if (!Object.values(PROACTIVE_PROVIDERS).includes(operation)) {
        return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
      if (privateField(params)) {
        return { ok: false, status: "error", error: { code: "undeclared_input" } };
      }
      if (params.scope !== undefined && params.scope !== "global" && !approvedProjects.has(String(params.scope))) {
        return { ok: false, status: "error", error: { code: "unknown_scope" } };
      }
      if (operation === PROACTIVE_PROVIDERS.state) {
        for (const event of Array.isArray(params.events) ? params.events : []) {
          if (!PROACTIVE_CATEGORIES.has(event?.category)) {
            return { ok: false, status: "error", error: { code: "declared_category" } };
          }
          if (event?.type !== "conversation.delta.committed") {
            return { ok: false, status: "error", error: { code: "declared_event" } };
          }
        }
        const quietHours = params.quiet_hours;
        if (quietHours?.enabled && (!QUIET_TIME_PATTERN.test(String(quietHours.start ?? "")) || !QUIET_TIME_PATTERN.test(String(quietHours.end ?? "")))) {
          return { ok: false, status: "error", error: { code: "quiet_hours_invalid" } };
        }
        return {
          ok: true, status: "success",
          data: {
            active: true, quiet_until: null, scope: params.scope, controls: params.controls,
            cards: [{
              cluster_key: "cluster-proactive-1", category: "反思候选", scope: params.scope, merged_count: 2,
              merged_evidence: [
                { event_id: "pi_evt_proactive_001", source: "pk-sync", occurred_at: "2026-08-09T09:00:00.000Z", receipt_checksum: "a".repeat(64), support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], canonical_checksum: "b".repeat(64), watermark: "b".repeat(64) },
                { event_id: "pi_evt_proactive_002", source: "pk-sync", occurred_at: "2026-08-09T09:05:00.000Z", receipt_checksum: "c".repeat(64), support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"], canonical_checksum: "b".repeat(64), watermark: "b".repeat(64) },
              ],
              support_refs: ["evidence:proactive-1:support"], conflict_refs: ["evidence:proactive-1:conflict"],
              rule_version: "conversation-reflection-v1", anchor_before: "manual-1",
            }],
            manual_order: params.manual_order,
            feedback: { feedback_id: "feedback_proactive_state_001", feedback_count: 0 },
            metadata_only: true,
          },
        };
      }
      if (operation === PROACTIVE_PROVIDERS.controls) {
        return {
          ok: true, status: "success",
          data: {
            scope: params.scope, category: params.category, enabled: params.enabled === true,
            quiet_hours: params.quiet_hours ?? null,
            feedback: { feedback_id: "feedback_proactive_controls_001", feedback_count: 0 },
            metadata_only: true,
          },
        };
      }
      if (operation === PROACTIVE_PROVIDERS.dismiss) {
        const entry = {
          operation: "dismiss", cluster_key: params.cluster_key, feedback_id: params.feedback_id,
          actor_identity_hash: params.actor_identity_hash, idempotency_key: params.idempotency_key,
          dismissed_at: params.now, receipt_checksum: sha256Hex(`dismiss:${params.feedback_id}`),
        };
        return {
          ok: true, status: "success",
          data: {
            existing: false,
            feedback_log: [...(params.feedback_log ?? []), entry],
            receipt: { operation: "dismiss", feedback_id: params.feedback_id, cluster_key: params.cluster_key, actor_identity_hash: params.actor_identity_hash, idempotency_key: params.idempotency_key, dismissed_at: params.now, receipt_checksum: entry.receipt_checksum, feedback_count: (params.feedback_log?.length ?? 0) + 1, metadata_only: true },
            metadata_only: true,
          },
        };
      }
      if (params.dismissal_feedback_id !== "feedback_proactive_dismiss_001") {
        return { ok: false, status: "error", error: { code: "dismissal_not_found" } };
      }
      return {
        ok: true, status: "success",
        data: {
          operation: "undo_dismissal", dismissal_feedback_id: params.dismissal_feedback_id, feedback_id: params.feedback_id,
          actor_identity_hash: params.actor_identity_hash, idempotency_key: params.idempotency_key,
          undone_at: params.now, receipt_checksum: sha256Hex(`undo:${params.feedback_id}`),
          feedback_count: (params.feedback_log?.length ?? 0) + 1, metadata_only: true,
        },
      };
    },
  };
}

async function startProactiveServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-proactive-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const bridgeCalls = [];
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: createProactiveBridge(bridgeCalls),
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });
  return { port, bridgeCalls };
}

test("kernel-host declares exactly the four fixed proactive KernelHost methods (RED until 61-10 Task 2)", async () => {
  const source = await readFile(join(KERNEL_ROOT, "src/kernel-host.mjs"), "utf8");
  for (const method of ["getProactiveState", "updateProactiveControls", "dismissProactive", "undoProactiveDismissal"]) {
    assert.match(
      source,
      new RegExp(`\\basync\\s+${method}\\s*\\(|\\b${method}\\s*\\(`),
      `kernel-host.mjs must declare ${method} (RED: missing for 61-10 Task 1)`,
    );
  }
});

test("four fixed proactive routes map only to their matching Gateway providers through KernelHost->Gateway binding", async (t) => {
  const { port, bridgeCalls } = await startProactiveServer(t);
  const cases = [
    { name: "state", method: "POST", path: PROACTIVE_ROUTES.state, operation: PROACTIVE_PROVIDERS.state, body: proactiveStateBody() },
    { name: "controls", method: "POST", path: PROACTIVE_ROUTES.controls, operation: PROACTIVE_PROVIDERS.controls, body: proactiveControlsBody() },
    { name: "dismiss", method: "POST", path: PROACTIVE_ROUTES.dismiss, operation: PROACTIVE_PROVIDERS.dismiss, body: proactiveDismissBody() },
    { name: "undo", method: "POST", path: PROACTIVE_ROUTES.undo, operation: PROACTIVE_PROVIDERS.undo, body: proactiveUndoBody() },
  ];
  for (const route of cases) {
    const response = await requestJson(port, route.method, route.path, route.body);
    assert.notEqual(response.status, 404, `RED: ${route.method} ${route.path} must exist (expected for 61-10 Task 1)`);
    assert.equal(response.status, 200, `a safe proactive ${route.name} envelope must be a 200`);
    assert.equal(response.json.ok, true);
    const payload = response.json.data ?? response.json;
    assert.equal(payload.metadata_only, true, "proactive responses are metadata-only");
    assert.equal(/promot|rollback|watermark|active_pointer/.test(JSON.stringify(response.json)), false,
      `${route.name} envelope must never claim canonical/promotion/watermark/active-pointer authority`);
    assertNoPrivateLeak(response.json, `proactive ${route.name} response`);
  }
  assert.equal(bridgeCalls.length, 4, "each proactive route must dispatch exactly once to the bound Gateway bridge");
  for (const route of cases) {
    const call = bridgeCalls.find((entry) => entry.operation === route.operation);
    assert.ok(call, `${route.operation} must be dispatched through the Gateway bridge`);
    assert.equal("capability" in (call.params || {}), false, "capability is the loopback transport header, never a declared parameter");
    assert.ok(call.params.idempotency_key, `${route.operation} dispatch must carry idempotency_key`);
    assert.ok(call.params.binding, `${route.operation} dispatch must carry binding`);
  }
  for (const call of bridgeCalls) {
    assert.ok(Object.values(PROACTIVE_PROVIDERS).includes(call.operation),
      `only the named proactive providers may be dispatched (got ${call.operation})`);
  }
});

test("proactive routes are exactly four fixed paths; wrong methods and alternate paths fail closed", async (t) => {
  const { port, bridgeCalls } = await startProactiveServer(t);

  // Each fixed route is POST-only (a deterministic request body is required).
  for (const [name, path] of Object.entries(PROACTIVE_ROUTES)) {
    const get = await requestJson(port, "GET", path);
    assert.equal(get.status, 405, `RED: POST ${path} must exist and reject other methods (got 404/405)`);
    assert.equal(get.json.error.code, "method_not_allowed");
    assertNoPrivateLeak(get.json, `GET ${path} rejection`);
  }

  // Alternate paths must not exist (one fixed path per provider, no endpoint override).
  const alternatePaths = [
    "/v1/proactive/state/extra", "/v1/proactive/state/current", "/v1/proactive/controls/extra",
    "/v1/proactive/dismiss/extra", "/v1/proactive/undo/extra", "/v1/proactive/dismiss/undo",
    "/v1/proactive", "/v1/proactives", "/v1/proactive/all", "/v1/proactive/manage",
    "/v1/proactive/config", "/v1/proactive/schedule", "/v1/proactive/feedback", "/v1/proactive/quiet-hours",
  ];
  for (const path of alternatePaths) {
    const alt = await requestJson(port, "POST", path, proactiveDismissBody());
    assert.equal(alt.status, 404, `${path} must be route_not_found`);
    assert.equal(alt.json.error.code, "route_not_found");
    assertNoPrivateLeak(alt.json, `${path} rejection`);
  }
  assert.equal(bridgeCalls.length, 0, "alternate/method-mismatched routes must never reach the Gateway bridge");
});

test("proactive routes reject override, private, schedule, permission, value and canonical inputs before Gateway dispatch", async (t) => {
  const { port, bridgeCalls } = await startProactiveServer(t);
  const cases = [
    { name: "state", method: "POST", path: PROACTIVE_ROUTES.state, body: proactiveStateBody() },
    { name: "controls", method: "POST", path: PROACTIVE_ROUTES.controls, body: proactiveControlsBody() },
    { name: "dismiss", method: "POST", path: PROACTIVE_ROUTES.dismiss, body: proactiveDismissBody() },
    { name: "undo", method: "POST", path: PROACTIVE_ROUTES.undo, body: proactiveUndoBody() },
  ];
  const before = bridgeCalls.length;
  for (const route of cases) {
    for (const [label, extra] of [
      ["provider override", { provider: "model.wake" }],
      ["operation override", { operation: "canonical.promote" }],
      ["endpoint override", { endpoint: "http://127.0.0.1:9999" }],
      ["path override", { path: "/v1/canonical" }],
      ["authority override", { authority: "authority:promotion" }],
      ["schedule input", { schedule_at: "2026-08-10T09:00:00Z" }],
      ["permission input", { permission: "broadcast" }],
      ["value input", { value: "override-personal-value" }],
      ["canonical command", { canonical: "promote" }],
      ["private prompt", { prompt: SENTINELS.prompt }],
      ["private secret", { secret: SENTINELS.secret }],
    ]) {
      const rejected = await requestJson(port, route.method, route.path, { ...route.body, ...extra });
      assert.equal(rejected.status, 400, `${route.name} ${label} must be rejected (got ${rejected.status})`);
      assert.equal(rejected.json.ok, false);
      assertNoPrivateLeak(rejected.json, `${route.name} ${label} rejection`);
      assert.equal(rejected.text.includes(SENTINELS.prompt), false, `${route.name} ${label} must never leak request text`);
    }
    for (const [label, malformed] of [
      ["no idempotency key", { idempotency_key: undefined }],
      ["no binding", { binding: undefined }],
    ]) {
      const rejected = await requestJson(port, route.method, route.path, { ...route.body, ...malformed });
      assert.equal(rejected.status, 400, `${route.name} ${label} must fail closed`);
      assert.equal(rejected.json.ok, false);
      assertNoPrivateLeak(rejected.json, `${route.name} ${label} rejection`);
    }
  }
  assert.equal(bridgeCalls.length, before, "rejected proactive inputs must never reach the Gateway bridge");
});

test("proactive routes reject foreign scope, unknown category, malformed quiet hours and foreign feedback/item identity", async (t) => {
  const { port, bridgeCalls } = await startProactiveServer(t);

  // Kernel-level identity/format validation: rejected before any Gateway dispatch.
  const before = bridgeCalls.length;
  const kernelNegatives = [
    ["state foreign scope shape", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), scope: "not-a-scope" }, "scope_identity_invalid"],
    ["state missing now", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), now: undefined }, "proactive_request_invalid"],
    ["state non-array events", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), events: "not-an-array" }, "proactive_request_invalid"],
    ["state malformed quiet hours format", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), quiet_hours: { enabled: true, start: "25:00", end: "07:00" } }, "proactive_request_invalid"],
    ["controls unknown category", "POST", PROACTIVE_ROUTES.controls, { ...proactiveControlsBody(), category: "autonomous" }, "category_unknown"],
    ["controls quiet hours shape", "POST", PROACTIVE_ROUTES.controls, { ...proactiveControlsBody(), quiet_hours: { enabled: true } }, "proactive_request_invalid"],
    ["dismiss malformed feedback id", "POST", PROACTIVE_ROUTES.dismiss, { ...proactiveDismissBody(), feedback_id: "" }, "proactive_request_invalid"],
    ["undo non-string feedback id", "POST", PROACTIVE_ROUTES.undo, { ...proactiveUndoBody(), feedback_id: 42 }, "proactive_request_invalid"],
  ];
  for (const [label, method, path, body, code] of kernelNegatives) {
    const rejected = await requestJson(port, method, path, body);
    assert.equal(rejected.status, 400, `${label} must be rejected (got ${rejected.status})`);
    assert.equal(rejected.json.ok, false);
    assert.equal(rejected.json.error.code, code, `${label} must surface the Kernel rejection code`);
    assertNoPrivateLeak(rejected.json, `${label} rejection`);
  }
  assert.equal(bridgeCalls.length, before, "shape/identity-invalid proactive inputs must never reach the Gateway bridge");

  // Provider-level validation: the fixed route dispatches once, then surfaces the
  // Gateway/adapter rejection as a safe no-store 400 (never a crash or a leak).
  const providerNegatives = [
    ["state foreign project scope", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), scope: "project:not-approved" }, "unknown_scope"],
    ["state undeclared event category", "POST", PROACTIVE_ROUTES.state, { ...proactiveStateBody(), events: [{ ...proactiveStateBody().events[0], category: "autonomous" }] }, "declared_category"],
    ["undo unknown dismissal feedback", "POST", PROACTIVE_ROUTES.undo, { ...proactiveUndoBody(), dismissal_feedback_id: "feedback_never_exists" }, "dismissal_not_found"],
  ];
  for (const [label, method, path, body, code] of providerNegatives) {
    const rejected = await requestJson(port, method, path, body);
    assert.equal(rejected.status, 400, `${label} must surface a safe 400 (got ${rejected.status})`);
    assert.equal(rejected.json.ok, false);
    assert.equal(rejected.json.error.code, code, `${label} must surface the safe Gateway rejection code`);
    assertNoPrivateLeak(rejected.json, `${label} rejection`);
    assert.equal(rejected.text.includes(SENTINELS.prompt), false, `${label} must never leak request text`);
  }
});

// ---------------------------------------------------------------------------
// Phase 6a: bounded multi-turn memory (history prefix) + projection default
// injection.
//
// 6a-1 keeps the per-turn AgentSession isolation model and the privacy boundary
// (normalized user/assistant display text only; tool input/result, thinking and
// secret shapes never cross). History is OFF by default
// (PI_CONVERSATION_HISTORY_TURNS unset/0) and is a prompt-text prefix only —
// never persisted to the kernel session store.
//
// 6a-2 runs the governed projection provider on every real turn with a default
// `global` scope unless an explicit scope is supplied; unavailable/incompatible
// projections stay a silent omission.
// ---------------------------------------------------------------------------

test("6a-1 runConversationTurn injects normalized history as a prompt-text prefix on later turns", async () => {
  const { runConversationTurn } = await importTurnService();

  const double = createSessionDouble({ script: "settle" });
  const first = await runConversationTurn({
    session: double.session,
    prompt: "what is the sales total?",
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_memory_001",
    sessionId: "pi_session_memory_001",
    idempotencyKey: "pi-idem-memory-001",
    timeoutMs: 1000,
  });
  assert.equal(first.turn.state, "settled");
  assert.equal(double.calls.prompts[0].text, "what is the sales total?", "single-turn behavior is unchanged without history");
  assert.equal(first.turn.receipts.history, undefined, "no history receipt when nothing is injected");

  // Turn two: the same session's prior user/assistant turns are available as a
  // marked prompt-text prefix without any real model (fixture session double).
  const second = await runConversationTurn({
    session: double.session,
    prompt: "and what about this month?",
    activeToolNames: ["knowledge.search"],
    profile: "conversation",
    taskId: "pi_task_memory_002",
    sessionId: "pi_session_memory_001",
    idempotencyKey: "pi-idem-memory-002",
    history_turns: [
      { role: "user", content: "what is the sales total?" },
      { role: "assistant", content: "the total is 1284 units" },
    ],
    timeoutMs: 1000,
  });
  assert.equal(second.turn.state, "settled");
  const promptText = double.calls.prompts[1].text;
  assert.ok(promptText.startsWith("<conversation_history>"), "history must be marked with a clear block");
  assert.ok(promptText.includes("what is the sales total?"), "the previous user turn must be visible");
  assert.ok(promptText.includes("the total is 1284 units"), "the previous assistant turn must be visible");
  assert.ok(promptText.includes("</conversation_history>"), "history block must close");
  assert.ok(promptText.endsWith("and what about this month?"), "the new prompt follows the history block");
  assert.equal(second.turn.receipts.history.injected, 2);
  assert.ok(Number.isInteger(second.turn.receipts.history.bytes) && second.turn.receipts.history.bytes > 0);
  assert.equal(second.turn.receipts.history.truncated, false);
  assertNoPrivateLeak(second, "history-aware turn result");
});

test("6a-1 buildHistoryContext keeps only normalized user/assistant text and bounds total bytes", async () => {
  const { buildHistoryContext, MAX_HISTORY_CONTEXT_BYTES } = await importTurnService();
  const system = { role: "system", content: SENTINELS.credential };
  const toolResult = { role: "tool", content: SENTINELS.toolResult, tool_call_id: "t1" };
  const thinking = { role: "thinking", content: SENTINELS.secret };
  const user = { role: "user", content: "keep me" };
  const assistant = { role: "assistant", content: "kept too" };

  const ctx = buildHistoryContext([system, toolResult, thinking, user, assistant]);
  assert.equal(ctx.turn_count, 2, "tool/system/thinking messages must be filtered out");
  assert.ok(ctx.text.includes("keep me"));
  assert.ok(ctx.text.includes("kept too"));
  assert.ok(!ctx.text.includes(SENTINELS.credential));
  assert.ok(!ctx.text.includes(SENTINELS.toolResult));
  assert.ok(!ctx.text.includes(SENTINELS.secret));

  // The block is byte-bounded: oldest turns are dropped first, then a single
  // oversized recent turn is hard-truncated on a UTF-8 boundary.
  const huge = [];
  for (let index = 0; index < 25; index += 1) {
    huge.push({ role: "user", content: `m${index} `.repeat(20_000) });
  }
  const bounded = buildHistoryContext(huge);
  assert.ok(Buffer.byteLength(bounded.text, "utf8") <= MAX_HISTORY_CONTEXT_BYTES);
  assert.ok(bounded.turn_count > 0, "the most recent turn survives the byte budget");
  assert.equal(bounded.truncated, true);

  // Null/empty/malformed inputs are a no-history result.
  assert.equal(buildHistoryContext(null).turn_count, 0);
  assert.equal(buildHistoryContext([]).turn_count, 0);
  assert.equal(buildHistoryContext([{ role: "user", content: "" }]).turn_count, 0);
  assert.equal(buildHistoryContext([{ role: "user" }]).turn_count, 0);
});

test("6a-2 conversation turn injects projection by default and keeps explicit scope override", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-turn-projection-default-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const bridgeCalls = [];
  const projectionBridge = {
    async invoke(operation, params) {
      bridgeCalls.push({ operation, params });
      if (operation !== MODEL_PROJECTION_OPERATION) {
        return { ok: false, status: "error", error: { code: "unknown_operation" } };
      }
      return { ok: true, status: "success", data: projectionFixture(String(params.scope ?? "global")) };
    },
  };
  const double = createSessionDouble({ script: "settle" });
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: projectionBridge,
    conversationSessionFactory: async () => ({ session: double.session, resourceLoader: null, modelRuntime: { providerCalls: 0 } }),
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  // No explicit scope: the default whole-person `global` projection is injected.
  const body = {
    task_id: "pi_task_proj_default_001",
    session_id: "pi_session_proj_default_001",
    idempotency_key: "pi-idem-proj-default-001",
    skill_id: "knowledge.research",
    prompt: SENTINELS.prompt,
  };
  const response = await requestJson(port, "POST", "/v1/conversations/turn", body);
  assert.equal(response.status, 201);
  assert.equal(response.json.turn.state, "settled");
  const defaultCall = bridgeCalls.find((call) => call.operation === MODEL_PROJECTION_OPERATION);
  assert.ok(defaultCall, "the projection provider must run even without an explicit scope");
  assert.equal(defaultCall.params.scope, "global", "the default scope is the whole-person global scope");
  const promptOptions = double.calls.prompts[0].options;
  assert.ok(Array.isArray(promptOptions.projection_context) && promptOptions.projection_context.length > 0,
    "the default projection is injected before AgentSession.prompt");
  assert.equal(promptOptions.projection_context[0].scope, "global");
  assert.equal(promptOptions.projection_context[0].status, "current");
  assert.ok(response.json.turn.receipts.projection, "the receipt carries the projection summary");
  assertNoPrivateLeak(response.json, "default-projection turn response");

  // Explicit scope still overrides the default.
  const before = bridgeCalls.length;
  const scoped = await requestJson(port, "POST", "/v1/conversations/turn", {
    ...body,
    task_id: "pi_task_proj_scope_001",
    session_id: "pi_session_proj_scope_001",
    idempotency_key: "pi-idem-proj-scope-001",
    scope: "/work/alpha",
  });
  assert.equal(scoped.status, 201);
  const scopedCall = bridgeCalls.slice(before).find((call) => call.operation === MODEL_PROJECTION_OPERATION);
  assert.ok(scopedCall, "the scoped turn must run the projection provider");
  assert.equal(scopedCall.params.scope, "/work/alpha", "explicit scope overrides the default");
  assert.equal(double.calls.prompts[1].options.projection_context[0].scope, "/work/alpha");
  assertNoPrivateLeak(scoped.json, "scoped-projection turn response");
});

test("6a-1 enable_history fetches normalized canonical history and injects it as a bounded prompt prefix", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-turn-history-http-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const bridgeCalls = [];
  const threadBridge = {
    async invoke(operation, params) {
      bridgeCalls.push({ operation, params });
      if (operation === MODEL_PROJECTION_OPERATION) {
        return { ok: true, status: "success", data: projectionFixture(String(params.scope ?? "global"), { status: "unknown" }) };
      }
      if (operation === "conversation.thread.select") {
        return {
          ok: true, status: "success",
          data: {
            conversation_id: params.conversation_id,
            project_scope_id: "/work/alpha",
            messages: [
              { message_id: "m1", role: "user", display_text: "previous question", created_at: "2026-08-10T01:00:00Z", source_ref: "", evidence_ref: "" },
              { message_id: "m2", role: "assistant", display_text: "previous answer", created_at: "2026-08-10T01:00:01Z", source_ref: "", evidence_ref: "" },
              { message_id: "m3", role: "tool", display_text: SENTINELS.toolResult, created_at: "2026-08-10T01:00:02Z", source_ref: "", evidence_ref: "" },
            ],
            pagination: { limit: 8, has_more: false, cursor: null },
            truncated: false,
            state: "current",
            limitation: "fixture",
          },
        };
      }
      return { ok: false, status: "error", error: { code: "unknown_operation" } };
    },
  };
  const double = createSessionDouble({ script: "settle" });
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
    domainBridge: threadBridge,
    conversationSessionFactory: async () => ({ session: double.session, resourceLoader: null, modelRuntime: { providerCalls: 0 } }),
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  const body = {
    task_id: "pi_task_history_http_001",
    session_id: "pi_session_history_http_001",
    idempotency_key: "pi-idem-history-http-001",
    skill_id: "knowledge.research",
    prompt: "follow-up on the total",
    enable_history: true,
    history_conversation_id: "canonical_conv_001",
  };
  const response = await requestJson(port, "POST", "/v1/conversations/turn", body);
  assert.equal(response.status, 201);
  assert.equal(response.json.turn.state, "settled");
  const promptText = double.calls.prompts[0].text;
  assert.ok(promptText.startsWith("<conversation_history>"), "history block must open the prompt");
  assert.ok(promptText.includes("previous question"));
  assert.ok(promptText.includes("previous answer"));
  assert.ok(!promptText.includes(SENTINELS.toolResult), "tool messages are never injected");
  assert.equal(response.json.turn.receipts.history.injected, 2);
  assert.equal(response.json.turn.receipts.history.truncated, false);
  const fetch = bridgeCalls.find((call) => call.operation === "conversation.thread.select");
  assert.ok(fetch, "history must be fetched through conversation.thread.select");
  assert.equal(fetch.params.conversation_id, "canonical_conv_001");
  assert.equal(fetch.params.limit, 8, "the default history limit is 8 normalized turns");
  assert.equal(fetch.params.binding, "pi_kernel_conversation_turn");
  assertNoPrivateLeak(response.json, "history-aware turn response");

  // A malformed history_turns array fails closed without reaching the gateway.
  const before = bridgeCalls.length;
  const malformed = await requestJson(port, "POST", "/v1/conversations/turn", {
    ...body,
    task_id: "pi_task_history_bad_001",
    session_id: "pi_session_history_bad_001",
    idempotency_key: "pi-idem-history-bad-001",
    history_turns: [{ role: "user", content: 42 }],
  });
  assert.equal(malformed.status, 400);
  assert.equal(malformed.json.ok, false);
  assert.equal(malformed.json.error.code, "history_input_invalid");
  assertNoPrivateLeak(malformed.json, "malformed history rejection");
  assert.equal(bridgeCalls.length, before, "malformed history must never reach the Gateway bridge");
});

