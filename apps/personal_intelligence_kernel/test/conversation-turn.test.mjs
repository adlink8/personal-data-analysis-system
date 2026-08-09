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
