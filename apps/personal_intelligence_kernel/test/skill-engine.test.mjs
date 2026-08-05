import test from "node:test";
import assert from "node:assert/strict";
import { SkillEngine } from "../src/skills/engine.mjs";
import { SkillRegistry, skillChecksum } from "../src/skills/registry.mjs";

function manifest(overrides = {}) {
  const base = {
    schema: "pi-project-skill-v1", id: "skill.workflow", version: "1.0.0", purpose: "workflow", input_schema: "workflow-v1", output_schema: "receipt-v1", profile: "production", privacy_ceiling: "R1", allowed_tools: ["domain_inspect", "snapshot.activate"], instruction_checksum: "0".repeat(64), steps: [{ id: "inspect", tool: "domain_inspect", requires_confirmation: false, receipt_required: true }, { id: "activate", tool: "snapshot.activate", requires_confirmation: true, receipt_required: true }], max_steps: 2, max_rounds: 3, token_budget: 1000, cost_budget: 0, timeout_ms: 1000, stops: ["receipt", "checkpoint"], recovery: { resume_from_receipt: true, outcome_unknown: "reconcile" }, owner: "repo", expires_at: "2099-01-01T00:00:00Z", status: "active", ...overrides,
  };
  return { ...base, checksum: skillChecksum(base) };
}

function setup(skill = manifest()) { const registry = new SkillRegistry({ manifests: [skill], allowedTools: ["domain_inspect", "snapshot.activate"] }); registry.load(); return { registry, skill: registry.manifests[0] }; }

test("engine runs declared steps and pauses at the L3 checkpoint", async () => {
  const { registry, skill } = setup(); const engine = new SkillEngine({ registry }); const calls = [];
  const first = await engine.run({ skill, task_id: "task-1", session_id: "session-1", idempotency_key: "run-1", executor: async ({ step, idempotency_key }) => { calls.push({ tool: step.tool, idempotency_key }); return { receipt: { receipt_id: `receipt:${step.id}` } }; } });
  assert.equal(first.state, "waiting_confirmation"); assert.equal(first.steps.length, 1); assert.equal(calls.length, 1);
  const done = await engine.run({ skill, task_id: "task-1", session_id: "session-1", idempotency_key: "run-1", confirmed: true, executor: async ({ step, idempotency_key }) => { calls.push({ tool: step.tool, idempotency_key }); return { receipt: { receipt_id: `receipt:${step.id}` } }; } });
  assert.equal(done.state, "waiting_confirmation"); assert.deepEqual(calls.map((item) => item.tool), ["domain_inspect", "snapshot.activate"]); assert.equal(new Set(calls.map((item) => item.idempotency_key)).size, 2);
  const completed = await engine.run({ skill, task_id: "task-1", session_id: "session-1", idempotency_key: "run-1", confirmed: true, executor: async ({ step, idempotency_key }) => { calls.push({ tool: step.tool, idempotency_key }); return { receipt: { receipt_id: `receipt:${step.id}` } }; } });
  assert.equal(completed.state, "completed");
});

test("outcome unknown resumes from the committed receipt without repeating the side effect", async () => {
  const skill = manifest({ id: "skill.recovery", allowed_tools: ["domain_inspect"], steps: [{ id: "write", tool: "domain_inspect", requires_confirmation: false, receipt_required: true }, { id: "verify", tool: "domain_inspect", requires_confirmation: false, receipt_required: true }] });
  const { registry } = setup(skill); const engine = new SkillEngine({ registry }); let calls = 0;
  const first = await engine.run({ skill: registry.manifests[0], task_id: "task-2", session_id: "session-2", idempotency_key: "run-2", executor: async ({ step }) => { calls += 1; if (step.id === "write") { const error = new Error("unknown"); error.code = "outcome_unknown"; throw error; } return { receipt: { receipt_id: "verify" } }; } });
  assert.equal(first.state, "outcome_unknown");
  const done = await engine.run({ skill: registry.manifests[0], task_id: "task-2", session_id: "session-2", idempotency_key: "run-2", executor: async ({ step }) => { calls += 1; return { receipt: { receipt_id: step.id } }; }, reconcile: async () => ({ receipt_id: "write-reconciled" }) });
  assert.equal(done.state, "completed"); assert.equal(calls, 2); assert.equal(done.steps[0].receipt.receipt_id, "write-reconciled");
});

test("engine refuses undeclared tools and cancellation is terminal", async () => {
  const invalid = manifest({ id: "skill.invalid", allowed_tools: ["domain_inspect"], steps: [{ id: "bad", tool: "snapshot.activate", requires_confirmation: true, receipt_required: true }] });
  const registry = new SkillRegistry({ manifests: [invalid], allowedTools: ["domain_inspect"] }); assert.equal(registry.load().length, 0);
  const { registry: validRegistry, skill } = setup(); const engine = new SkillEngine({ registry: validRegistry });
  const state = engine.cancel({ skill, task_id: "missing", session_id: "missing" }); assert.equal(state, null);
  const run = await engine.run({ skill, task_id: "task-3", session_id: "session-3", idempotency_key: "run-3", executor: async () => ({ receipt: { receipt_id: "ok" } }) });
  assert.equal(run.state, "waiting_confirmation"); assert.equal(engine.cancel({ skill, task_id: "task-3", session_id: "session-3" }).state, "cancelled");
});
