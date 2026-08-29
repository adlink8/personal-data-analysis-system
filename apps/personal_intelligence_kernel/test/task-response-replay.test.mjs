import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { startKernelServer } from "../src/server.mjs";
import { KernelHost, PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";
import { EventJournal } from "../src/events/journal.mjs";
import { TaskLedger } from "../src/tasks/ledger.mjs";
import { SessionStore } from "../src/sessions/store.mjs";
import { SkillEngine } from "../src/skills/engine.mjs";
import { SkillRegistry, skillChecksum } from "../src/skills/registry.mjs";

function requestJson(port, method, path, body, extraHeaders = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const request = httpRequest({
      host: "127.0.0.1", port, method, path,
      headers: payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload), ...extraHeaders } : { ...extraHeaders },
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolve({ status: response.statusCode, text, json: text ? JSON.parse(text) : null });
      });
    });
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

test("task include_response replay is served from the persisted ledger across a host restart", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-replay-"));
  t.after(async () => { await rm(dir, { recursive: true, force: true }); });
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const options = () => ({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0,
    providerMode: "replay", internalCapability: "test-replay-capability",
  });

  const runtime = await startKernelServer(options());
  const port = runtime.server.address().port;
  const body = {
    task_id: "pi_task_replay_001",
    session_id: "pi_session_replay_001",
    idempotency_key: "pi-idem-replay-001",
    purpose: "structured_analysis",
    prompt: "private prompt stays memory-only: return a JSON object with ok=true",
    include_response: true,
  };
  const headers = { "x-pi-internal-capability": "test-replay-capability" };
  const first = await requestJson(port, "POST", "/v1/tasks", body, headers);
  assert.equal(first.status, 201);
  assert.equal(first.json.ok, true);
  assert.equal(first.json.task.state, "succeeded");
  assert.equal(first.json.response.replay, true);

  const duplicate = await requestJson(port, "POST", "/v1/tasks", body, headers);
  assert.equal(duplicate.status, 200);
  assert.equal(duplicate.json.duplicate, true);
  assert.deepEqual(duplicate.json.response, first.json.response);
  await runtime.stop(100);

  // Simulated restart: a fresh host reopens the same durable task ledger; the
  // duplicate include_response replay must be served from persisted state.
  const restarted = await startKernelServer(options());
  try {
    const replay = await requestJson(restarted.server.address().port, "POST", "/v1/tasks", body, headers);
    assert.equal(replay.status, 200);
    assert.equal(replay.json.duplicate, true);
    assert.equal(replay.json.task.state, "succeeded");
    assert.deepEqual(replay.json.response, first.json.response);
    assert.equal(replay.text.includes("private prompt"), false);
  } finally {
    await restarted.stop(100);
  }
});

function replaySkillManifest() {
  const base = {
    schema: "pi-project-skill-v1", id: "skill.replay", version: "1.0.0", purpose: "replay", input_schema: "workflow-v1",
    output_schema: "receipt-v1", profile: "production", privacy_ceiling: "R1", allowed_tools: ["domain_inspect"],
    instruction_checksum: "0".repeat(64),
    steps: [{ id: "inspect", tool: "domain_inspect", requires_confirmation: false, receipt_required: true }],
    max_steps: 1, max_rounds: 3, token_budget: 1000, cost_budget: 0, timeout_ms: 1000, stops: ["receipt", "checkpoint"],
    recovery: { resume_from_receipt: true, outcome_unknown: "reconcile" }, owner: "repo", expires_at: "2099-01-01T00:00:00Z", status: "active",
  };
  return { ...base, checksum: skillChecksum(base) };
}

function buildSkillReplayHost(dir) {
  const registry = new SkillRegistry({ manifests: [replaySkillManifest()], allowedTools: ["domain_inspect"] });
  registry.load();
  return new KernelHost({
    journal: new EventJournal(join(dir, "events.sqlite")),
    providerAdapter: { providerCalls: 0 },
    taskLedger: new TaskLedger(join(dir, "pi_kernel_tasks.sqlite")),
    sessionStore: new SessionStore(join(dir, "pi_kernel_sessions.sqlite")),
    candidateStore: null,
    decision: { accepted: true, status: "accepted" },
    host: "127.0.0.1", port: 0,
    skillRegistry: registry,
    skillEngine: new SkillEngine({ registry }),
    domainBridge: { invoke: async (tool) => ({ status: "success", data: { ok: true, tool } }) },
  });
}

test("skill report replay is served from the persisted ledger across a host restart", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-skill-replay-"));
  t.after(async () => { await rm(dir, { recursive: true, force: true }); });
  const request = {
    task_id: "pi_task_skill_replay_001", session_id: "pi_session_skill_replay_001",
    idempotency_key: "pi-idem-skill-replay-001", skill_id: "skill.replay", skill_input: {}, include_response: true,
  };

  const host = buildSkillReplayHost(dir);
  const first = await host.executeSkillTask(request);
  assert.equal(first.duplicate, false);
  assert.equal(first.skill_state, "completed");
  assert.equal(first.response.schema, "pi_skill_report_v1");

  const duplicate = await host.executeSkillTask(request);
  assert.equal(duplicate.duplicate, true);
  assert.deepEqual(duplicate.response, first.response);
  await host.shutdown();

  const restarted = buildSkillReplayHost(dir);
  try {
    const replay = await restarted.executeSkillTask(request);
    assert.equal(replay.duplicate, true);
    assert.equal(replay.skill_id, "skill.replay");
    assert.deepEqual(replay.response, first.response);
  } finally {
    await restarted.shutdown();
  }
});

test("task ledger persists bounded responses across reopen and skips oversized ones", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-task-responses-"));
  t.after(async () => { await rm(dir, { recursive: true, force: true }); });
  const ledger = new TaskLedger(join(dir, "tasks.sqlite"));
  ledger.enqueue({ task_id: "task-resp-1", idempotency_key: "idem-resp-1", input_ref: { kind: "artifact", ref: "artifact:1" } });
  const stored = ledger.putResponse("task-resp-1", { schema: "pi_skill_report_v1", ok: true });
  assert.equal(stored.stored, true);
  const oversized = ledger.putResponse("task-resp-1", { blob: "x".repeat(1024 * 1024 + 1) });
  assert.equal(oversized.stored, false);
  assert.equal(oversized.reason, "response_too_large");
  ledger.close();

  const reopened = new TaskLedger(join(dir, "tasks.sqlite"));
  try {
    assert.deepEqual(reopened.getResponse("task-resp-1"), { schema: "pi_skill_report_v1", ok: true });
    assert.equal(reopened.getResponse("task-missing"), null);
    assert.equal(reopened.integrityCheck().ok, true);
  } finally {
    reopened.close();
  }
});
