import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  ALLOWED_ROUTES,
  startKernelServer,
} from "../src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";
import { createPiKernelEvent } from "../src/events/schema.mjs";

const EVENT_BASE = {
  type: "task_started",
  source: "pi_kernel",
  authority: "authority:server-test",
  snapshot: "snapshot:server-test",
  correlation_id: "corr:server-test",
  causation_id: null,
  idempotency_key: "idem:server-test:1",
  occurred_at: "2026-08-04T09:00:00.000Z",
  payload_ref: { kind: "none", ref: null, checksum: null },
  privacy_class: "R1",
};

function event(overrides = {}) {
  return createPiKernelEvent({ ...EVENT_BASE, ...overrides });
}

function requestJson(port, method, path, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const request = httpRequest({
      host: "127.0.0.1",
      port,
      method,
      path,
      headers: {
        ...(payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload) } : {}),
        ...headers,
      },
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let json;
        try { json = text ? JSON.parse(text) : null; } catch { json = null; }
        resolve({ status: response.statusCode, headers: response.headers, text, json });
      });
    });
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

async function decisionFixture(dir) {
  const path = join(dir, "decision.json");
  await writeFile(path, JSON.stringify({
    schema: "pi-package-decision-v1",
    run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted",
    accepted: true,
    expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  return path;
}

async function runningServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-server-"));
  const runtime = await startKernelServer({
    projectRoot: process.cwd(),
    decisionPath: await decisionFixture(dir),
    databasePath: join(dir, "events.sqlite"),
    cwd: dir,
    agentDir: join(dir, "agent"),
    host: "127.0.0.1",
    port: 0,
    heartbeatIntervalMs: 1000,
  });
  t.after(async () => {
    await runtime.stop(100);
    await rm(dir, { recursive: true, force: true });
  });
  return { runtime, port: runtime.server.address().port };
}

test("server exposes only loopback health/readiness and the allowlisted routes", async (t) => {
  const { port } = await runningServer(t);
  const health = await requestJson(port, "GET", "/health");
  assert.equal(health.status, 200);
  assert.equal(health.json.ok, true);
  const ready = await requestJson(port, "GET", "/ready");
  assert.equal(ready.status, 200);
  assert.equal(ready.json.ready, true);
  assert.deepEqual(ready.json.checks, {
    package_decision: true,
    resource_registry: true,
    schema_migration: true,
    sqlite_integrity: true,
  });
  const unknown = await requestJson(port, "GET", "/private-body-value");
  assert.equal(unknown.status, 404);
  assert.deepEqual(unknown.json, { ok: false, error: { code: "route_not_found" } });
  const wrongMethod = await requestJson(port, "PUT", "/health", { secret: "private-body-value" });
  assert.equal(wrongMethod.status, 405);
  assert.deepEqual(wrongMethod.json, { ok: false, error: { code: "method_not_allowed" } });
  assert.equal(wrongMethod.text.includes("private-body-value"), false);
});

test("operations control routes serve the runtime control plane with safe error codes", async (t) => {
  const { runtime, port } = await runningServer(t);
  const operation = runtime.host.runtimeControl.register({
    operation_kind: "kernel_task", task_id: "task:ops-routes", session_id: "session:ops-routes",
    correlation_id: "corr:ops-routes", idempotency_key: "idem:ops-routes",
    authority_class: "authority:kernel", snapshot_id: "snapshot:ops-routes", side_effect_class: "mutation",
  });
  const list = await requestJson(port, "GET", "/v1/operations");
  assert.equal(list.status, 200);
  assert.equal(list.json.ok, true);
  assert.equal(list.json.operations.some((item) => item.operation_id === operation.operation_id), true);

  const got = await requestJson(port, "GET", `/v1/operations/${operation.operation_id}`);
  assert.equal(got.status, 200);
  assert.equal(got.json.ok, true);
  assert.equal(got.json.operation.operation_id, operation.operation_id);

  const missing = await requestJson(port, "GET", "/v1/operations/op_missing");
  assert.equal(missing.status, 404);
  assert.deepEqual(missing.json, { ok: false, error: { code: "operation_not_found" } });

  const cancelled = await requestJson(port, "POST", `/v1/operations/${operation.operation_id}/cancel`, {
    expected_version: 0, idempotency_key: "idem:ops-cancel:1",
  });
  assert.equal(cancelled.status, 200);
  assert.equal(cancelled.json.ok, true);
  assert.equal(cancelled.json.operation.state, "cancel_requested");

  const stale = await requestJson(port, "POST", `/v1/operations/${operation.operation_id}/resume`, {
    expected_version: 0, idempotency_key: "idem:ops-resume:stale",
  });
  assert.equal(stale.status, 400);
  assert.equal(stale.json.error.code, "stale_expected_version");

  const resumed = await requestJson(port, "POST", `/v1/operations/${operation.operation_id}/resume`, {
    expected_version: 1, idempotency_key: "idem:ops-resume:1",
  });
  assert.equal(resumed.status, 200);
  assert.equal(resumed.json.ok, true);
  assert.equal(resumed.json.operation.state, "running");

  const unreconcilable = await requestJson(port, "POST", `/v1/operations/${operation.operation_id}/reconcile`, {
    expected_version: 2, idempotency_key: "idem:ops-reconcile:early",
  });
  assert.equal(unreconcilable.status, 400);
  assert.equal(unreconcilable.json.error.code, "reconcile_state_required");

  runtime.host.runtimeControl._transition({
    operationId: operation.operation_id, expectedVersion: 2, idempotencyKey: "idem:ops-unknown:1",
    nextState: "outcome_unknown", reason: "provider_timeout",
  });
  const reconciled = await requestJson(port, "POST", `/v1/operations/${operation.operation_id}/reconcile`, {
    expected_version: 3, idempotency_key: "idem:ops-reconcile:1",
    receipt_refs: [{ ref: "receipt:ops-1", checksum: "a".repeat(64) }],
    fingerprint_refs: [{ ref: "fingerprint:ops-1", checksum: "b".repeat(64) }],
    receipt_status: "succeeded",
  });
  assert.equal(reconciled.status, 200);
  assert.equal(reconciled.json.ok, true);
  assert.equal(reconciled.json.operation.state, "succeeded");
  assert.equal(reconciled.json.reconciled_before_retry, true);
});

test("ALLOWED_ROUTES declares the operations control-plane routes it dispatches", () => {
  // Contract guard: these five dispatch branches existed before the whitelist
  // declared them, which silently drifted the published route contract. Any
  // future dispatch branch must be registered here in the same change.
  const operationsRoutes = [
    "GET /v1/operations",
    "GET /v1/operations/:operation_id",
    "POST /v1/operations/:operation_id/cancel",
    "POST /v1/operations/:operation_id/resume",
    "POST /v1/operations/:operation_id/reconcile",
  ];
  for (const route of operationsRoutes) {
    assert.equal(ALLOWED_ROUTES.includes(route), true, `ALLOWED_ROUTES missing dispatched route: ${route}`);
  }
});

test("event ingress validates metadata, preserves exact duplicate replay, and never leaks errors", async (t) => {
  const { port } = await runningServer(t);
  const firstEvent = event();
  const first = await requestJson(port, "POST", "/v1/events", firstEvent);
  assert.equal(first.status, 201);
  assert.equal(first.json.status, "appended");
  const duplicate = await requestJson(port, "POST", "/v1/events", firstEvent);
  assert.equal(duplicate.status, 200);
  assert.deepEqual(duplicate.json, { ...first.json, status: "duplicate", replay: true, duplicate: true });
  const malformed = await requestJson(port, "POST", "/v1/events", {
    type: "unknown-event",
    body: "private-body-value",
    path: "C:/private/credential.txt",
  });
  assert.equal(malformed.status, 400);
  assert.deepEqual(malformed.json, { ok: false, error: { code: "event_invalid" } });
  assert.equal(malformed.text.includes("private-body-value"), false);
  assert.equal(malformed.text.includes("credential.txt"), false);
});

test("SSE reconnect maps Last-Event-ID to durable sequence without gaps or duplicates", async (t) => {
  const { port } = await runningServer(t);
  const first = event();
  const second = event({ type: "tool_started", idempotency_key: "idem:server-test:2" });
  const firstResponse = await requestJson(port, "POST", "/v1/events", first);
  const secondResponse = await requestJson(port, "POST", "/v1/events", second);
  assert.equal(firstResponse.status, 201);
  assert.equal(secondResponse.status, 201);

  const stream = await new Promise((resolve, reject) => {
    const request = httpRequest({ host: "127.0.0.1", port, path: "/v1/events/stream", headers: { "Last-Event-ID": first.event_id } }, (response) => {
      let text = "";
      response.on("data", (chunk) => {
        text += chunk;
        if (text.includes(second.event_id)) {
          request.destroy();
          resolve({ status: response.statusCode, text });
        }
      });
      response.on("error", () => undefined);
    });
    request.on("error", (error) => { if (error.code !== "ECONNRESET") reject(error); });
    request.end();
  });
  assert.equal(stream.status, 200);
  assert.equal((stream.text.match(new RegExp(`^id: ${second.event_id}$`, "gm")) || []).length, 1);
  assert.equal(stream.text.includes(first.event_id), false);
  assert.equal(stream.text.includes("private-body"), false);
});

test("transport stop force-closes an active connection within the bound", async (t) => {
  const { runtime, port } = await runningServer(t);
  const socket = await new Promise((resolve, reject) => {
    const request = httpRequest({ host: "127.0.0.1", port, path: "/v1/events/stream" }, (response) => resolve(response.socket));
    request.on("error", reject);
    request.end();
  });
  assert.ok(socket && !socket.destroyed);
  const started = Date.now();
  const result = await runtime.stop(50);
  assert.equal(result.lifecycle, "disposed");
  assert.ok(Date.now() - started < 1000);
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.equal(socket.destroyed, true);
});
