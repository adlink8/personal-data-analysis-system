import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { startKernelServer } from "../src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";
import { EventJournal } from "../src/events/journal.mjs";
import { TaskLedger } from "../src/tasks/ledger.mjs";
import { SessionStore } from "../src/sessions/store.mjs";
import { CandidateStore } from "../src/candidates/store.mjs";

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

test("Kernel task route persists metadata-only task/session receipts and replays idempotently", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-workflow-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0,
    providerMode: "replay", internalCapability: "test-kernel-capability",
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  const body = {
    task_id: "pi_task_kernel_workflow_001",
    session_id: "pi_session_kernel_workflow_001",
    idempotency_key: "pi-idem-kernel-workflow-001",
    purpose: "structured_analysis",
    prompt: "private prompt must never be returned or persisted: return a JSON object with ok=true",
    include_response: true,
  };
  const first = await requestJson(port, "POST", "/v1/tasks", body, { "x-pi-internal-capability": "test-kernel-capability" });
  assert.equal(first.status, 201);
  assert.equal(first.json.ok, true);
  assert.equal(first.json.task.state, "succeeded");
  assert.equal(first.json.receipt.provider, "replay");
  assert.equal(first.json.response.replay, true);
  assert.equal(first.json.provider_calls, 0);
  assert.equal(first.text.includes("private prompt"), false);

  const duplicate = await requestJson(port, "POST", "/v1/tasks", body, { "x-pi-internal-capability": "test-kernel-capability" });
  assert.equal(duplicate.status, 200);
  assert.equal(duplicate.json.duplicate, true);
  assert.equal(duplicate.json.provider_calls, 0);

  const candidate = await requestJson(port, "POST", "/internal/v1/candidates", {
    task_id: body.task_id, session_id: body.session_id, idempotency_key: "pi-idem-kernel-workflow-001:candidate",
    candidate_id: "pi_candidate_kernel_workflow_001",
    proposal: { kind: "analysis_candidate", status: "pending", candidate_checksum: "c".repeat(64) },
    evidence_refs: [{ ref: "artifact:evidence-1", checksum: "a".repeat(64) }],
    model_receipt: { task_id: body.task_id, session_id: body.session_id, response_checksum: first.json.receipt.response_checksum, model: "replay-v1" },
  }, { "x-pi-internal-capability": "test-kernel-capability" });
  assert.equal(candidate.status, 201);
  assert.equal(candidate.json.candidate.candidate_id, "pi_candidate_kernel_workflow_001");

  const task = await requestJson(port, "GET", "/v1/tasks/pi_task_kernel_workflow_001");
  assert.equal(task.status, 200);
  assert.equal(task.json.task.state, "succeeded");
  assert.equal(task.text.includes("private prompt"), false);

  await runtime.stop(100);
  const events = new EventJournal(join(dir, "events.sqlite"));
  const tasks = new TaskLedger(join(dir, "pi_kernel_tasks.sqlite"));
  const sessions = new SessionStore(join(dir, "pi_kernel_sessions.sqlite"));
  const candidates = new CandidateStore(join(dir, "pi_kernel_candidates.sqlite"));
  try {
    assert.equal(events.integrityCheck().ok, true);
    assert.equal(events.replay(0, 10).events.length, 4);
    assert.equal(tasks.integrityCheck().ok, true);
    assert.equal(sessions.integrityCheck().ok, true);
    assert.equal(candidates.integrityCheck().ok, true);
    assert.equal(candidates.list().length, 1);
    assert.equal(JSON.stringify(sessions.get("pi_session_kernel_workflow_001")).includes("private prompt"), false);
  } finally {
    events.close(); tasks.close(); sessions.close(); candidates.close();
  }
});

test("Kernel cancel and resume routes enforce versioned metadata-only recovery", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-recovery-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "replay",
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });

  runtime.host.taskLedger.enqueue({
    task_id: "pi_task_cancel_route_001", idempotency_key: "pi-cancel-seed-001",
    input_ref: { kind: "artifact", ref: "prompt:seed", checksum: "a".repeat(64) },
  });
  const cancelled = await requestJson(port, "POST", "/v1/tasks/pi_task_cancel_route_001/cancel", {
    expected_version: 1, idempotency_key: "pi-cancel-route-001",
  });
  assert.equal(cancelled.status, 200);
  assert.equal(cancelled.json.task.state, "cancel_requested");
  assert.equal(cancelled.text.includes('"prompt"'), false);

  runtime.host.taskLedger.enqueue({
    task_id: "pi_task_resume_route_001", idempotency_key: "pi-resume-seed-001",
    input_ref: { kind: "artifact", ref: "prompt:seed2", checksum: "b".repeat(64) },
  });
  let task = runtime.host.taskLedger.claim("pi_task_resume_route_001", { owner: "pi_kernel" });
  task = runtime.host.taskLedger.transition("pi_task_resume_route_001", "running", { expectedVersion: task.version, owner: "pi_kernel" });
  runtime.host.taskLedger.markOutcomeUnknown("pi_task_resume_route_001", { expectedVersion: task.version, owner: "pi_kernel", error_code: "provider_timeout" });
  const resumed = await requestJson(port, "POST", "/v1/tasks/pi_task_resume_route_001/resume", {
    expected_version: 4, idempotency_key: "pi-resume-route-001", state: "failed", error_code: "operator_reconciled",
  });
  assert.equal(resumed.status, 200);
  assert.equal(resumed.json.task.state, "failed");
  assert.equal(resumed.text.includes("operator_reconciled"), true);
});
