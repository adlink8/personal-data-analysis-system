import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer, request as httpRequest } from "node:http";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import { once } from "node:events";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

import { startKernelServer } from "../src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";

const repoRoot = resolve(process.cwd(), "..", "..");

function requestJson(port, method, path, body, extraHeaders = {}) {
  return new Promise((resolveRequest, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const request = httpRequest({
      host: "127.0.0.1", port, method, path,
      headers: payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload), ...extraHeaders } : extraHeaders,
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolveRequest({ status: response.statusCode, json: text ? JSON.parse(text) : null });
      });
    });
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  await new Promise((resolveClose) => server.close(resolveClose));
  return port;
}

async function waitForHealth(port) {
  const deadline = Date.now() + 15000;
  let lastError = "not_started";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) return response.json();
      lastError = `http_${response.status}`;
    } catch (error) {
      lastError = error?.message ?? "connection_failed";
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error(`domain_test_server_unavailable:${lastError}`);
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  const exited = once(child, "exit");
  child.kill();
  await Promise.race([exited, new Promise((resolveWait) => setTimeout(resolveWait, 3000))]);
}

test("real Pi Skill -> domain tool -> isolated SQLite write -> verification", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-skill-warehouse-e2e-"));
  const decisionPath = join(dir, "decision.json");
  const ledgerPath = join(dir, "warehouse-test.sqlite");
  const domainPort = await freePort();
  const capability = "pi-e2e-domain-capability";
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");

  const python = spawn(process.env.PYTHON ?? "python", [
    resolve(repoRoot, "src/personal_knowledge/services/api_server.py"),
    "--port", String(domainPort),
  ], {
    cwd: repoRoot,
    env: {
      ...process.env,
      PYTHONPATH: `${resolve(repoRoot, "src")};${process.env.PYTHONPATH ?? ""}`,
      PI_DOMAIN_CAPABILITY: capability,
      PI_DOMAIN_TEST_LEDGER_PATH: ledgerPath,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let pythonStderr = "";
  python.stderr.on("data", (chunk) => { pythonStderr += chunk.toString(); });

  const previousEnv = {
    PI_DOMAIN_HOST: process.env.PI_DOMAIN_HOST,
    PI_DOMAIN_PORT: process.env.PI_DOMAIN_PORT,
    PI_DOMAIN_CAPABILITY: process.env.PI_DOMAIN_CAPABILITY,
  };
  Object.assign(process.env, {
    PI_DOMAIN_HOST: "127.0.0.1",
    PI_DOMAIN_PORT: String(domainPort),
    PI_DOMAIN_CAPABILITY: capability,
  });

  let runtime;
  try {
    await waitForHealth(domainPort);
    runtime = await startKernelServer({
      projectRoot: repoRoot,
      decisionPath,
      databasePath: join(dir, "events.sqlite"),
      controlDatabaseDirectory: dir,
      cwd: dir,
      agentDir: join(dir, "agent"),
      host: "127.0.0.1",
      port: 0,
      providerMode: "replay",
      internalCapability: "pi-e2e-kernel-capability",
    });
    const port = runtime.server.address().port;
    const body = {
      task_id: "pi_task_skill_warehouse_e2e_001",
      session_id: "pi_session_skill_warehouse_e2e_001",
      idempotency_key: "pi-skill-warehouse-e2e-001",
      skill_id: "warehouse.failed_batch_recovery",
      skill_input: {
        step_inputs: {
          failed: { authority_id: "knowledge", limit: 10 },
          preview: {
            authority_id: "knowledge", source_checksum: "source:pi-e2e",
            snapshot_checksum: "snapshot:pi-e2e", watermark_checksum: "watermark:pi-e2e",
            count: 1, actor: "pi_e2e", profile: "test",
          },
        },
      },
      include_response: true,
    };
    const headers = { "x-pi-internal-capability": "pi-e2e-kernel-capability" };
    const first = await requestJson(port, "POST", "/v1/tasks", body, headers);
    assert.equal(first.status, 201);
    assert.equal(first.json.ok, true);
    assert.equal(first.json.task.state, "succeeded");
    assert.equal(first.json.route, "skill");
    assert.equal(first.json.skill_id, "warehouse.failed_batch_recovery");
    assert.equal(first.json.skill_state, "completed");
    assert.equal(first.json.skill_steps.length, 5);
    assert.ok(first.json.skill_steps.every((step) => step.status === "committed"));
    assert.equal(first.json.receipt.completed_steps, 5);
    assert.equal(first.json.response.steps.length, 5);
    assert.equal(first.json.provider_calls, 0);

    const duplicate = await requestJson(port, "POST", "/v1/tasks", body, headers);
    assert.equal(duplicate.status, 200);
    assert.equal(duplicate.json.duplicate, true);
    assert.equal(duplicate.json.response.schema, "pi_skill_report_v1");
    assert.equal(duplicate.json.response.task_id, body.task_id);

    await runtime.stop(500);
    runtime = undefined;
    await stopChild(python);

    const warehouseDb = new DatabaseSync(ledgerPath);
    try {
      const operation = warehouseDb.prepare("SELECT status, count FROM pi_data_operations WHERE capability_id='ingestion.preview'").get();
      const warehouseEventCount = warehouseDb.prepare("SELECT COUNT(*) AS count FROM pi_test_warehouse_events").get().count;
      assert.equal(operation.status, "committed");
      assert.equal(Number(operation.count), 1);
      assert.equal(Number(warehouseEventCount), 1);
    } finally {
      warehouseDb.close();
    }

    const eventDb = new DatabaseSync(join(dir, "events.sqlite"));
    try {
      const toolEvents = eventDb.prepare("SELECT event_type, COUNT(*) AS count FROM pi_kernel_events WHERE event_type IN ('tool_started','tool_completed') GROUP BY event_type ORDER BY event_type").all();
      assert.deepEqual(toolEvents.map((row) => [row.event_type, Number(row.count)]), [["tool_completed", 5], ["tool_started", 5]]);
    } finally {
      eventDb.close();
    }
  } finally {
    if (runtime) await runtime.stop(500).catch(() => undefined);
    await stopChild(python).catch(() => undefined);
    for (const [key, value] of Object.entries(previousEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    await rm(dir, { recursive: true, force: true });
  }

  if (pythonStderr.trim()) t.diagnostic(`python stderr: ${pythonStderr.trim()}`);
});
