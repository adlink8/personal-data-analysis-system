import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer, request as httpRequest } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { DatabaseSync } from "node:sqlite";
import { once } from "node:events";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

process.env.PI_PROVIDER_MODE = "vertex_google";
process.env.PI_KERNEL_PROVIDER_MODE = "vertex_google";
process.env.PI_PROVIDER_MODEL = "gemini-3.5-flash-lite";
process.env.PERSONAL_DATA_GCLOUD = "C:\\Users\\li\\google-cloud-sdk\\gcloud.bat";
process.env.PERSONAL_DATA_GCP_PROJECT = "project-c5cbd608-1b00-454e-80f";
process.env.PERSONAL_DATA_VERTEX_LOCATION = "global";

const { startKernelServer } = await import("../../src/server.mjs");
const { PHASE_48_DECISION_RUN_ID } = await import("../../src/kernel-host.mjs");

const repoRoot = resolve(process.cwd(), "..", "..");
const kernelCapability = "pi-gemini-all-skills-kernel";
const domainCapability = "pi-gemini-all-skills-domain";

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
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`);
      if (response.ok) return response.json();
    } catch { /* child is still booting */ }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error("domain_test_server_unavailable");
}

async function stopChild(child) {
  if (!child || child.exitCode !== null) return;
  const exited = once(child, "exit");
  child.kill();
  await Promise.race([exited, new Promise((resolveWait) => setTimeout(resolveWait, 3000))]);
}

function semanticInput(suffix) {
  const evidence = [{ ref: `evidence:gemini:${suffix}`, checksum: `checksum:gemini:${suffix}` }];
  return {
    source_scope: "knowledge", snapshot_checksum: `snapshot:gemini:${suffix}`, watermark_checksum: `watermark:gemini:${suffix}`,
    batch_limit: 1, extractor: "gemini-35-flash-lite", model_receipt: `model:gemini:${suffix}`, schema_version: "pi_semantic_candidate_v1",
    evidence_refs: evidence,
    records: [{ candidate_id: `candidate:gemini:${suffix}`, claim_checksum: `claim:gemini:${suffix}`, unit_type: "fact", evidence_refs: evidence, extractor: "gemini-35-flash-lite", model_receipt: `model:gemini:${suffix}`, schema_version: "pi_semantic_candidate_v1" }],
    actor: "pi_gemini_e2e", profile: "test",
  };
}

function skillInputs(skillId, seedOperationId) {
  const empty = {};
  if (skillId === "knowledge.maintenance") {
    const input = semanticInput("maintenance");
    return { inspect: { authority_id: "knowledge", limit: 10 }, extract: input, repair: input, conflicts: input, backfill: input, verify: { operation_id: seedOperationId } };
  }
  if (skillId === "warehouse.failed_batch_recovery") {
    return {
      failed: { authority_id: "knowledge", limit: 10 },
      preview: { authority_id: "knowledge", source_checksum: "source:gemini", snapshot_checksum: "snapshot:gemini", watermark_checksum: "watermark:gemini", count: 1, actor: "pi_gemini_e2e", profile: "test" },
    };
  }
  if (skillId === "retrieval.rebuild") {
    return {
      inspect: { authority_id: "retrieval", limit: 10 },
      build: { semantic_snapshot_checksum: "semantic:gemini", source_ids: ["source:gemini"], embedding_receipt: "embedding:gemini", index_schema_version: "index-v1", actor: "pi_gemini_e2e", profile: "test" },
      reconcile: { expected_ids: [], indexed_ids: [] },
      evaluate: { policy_id: "policy:gemini", policy_checksum: "policy:gemini", reconcile: { missing: 0, orphan: 0, duplicate: 0 } },
      prepare: { action: "activate", snapshot_id: "snapshot:gemini-rebuild", manifest: { schema: "manifest-v1" }, reconcile: { missing: 0, orphan: 0, duplicate: 0 }, eval_passed: true, eval_checksum: "eval:gemini", current_pointer: "pointer:active", target_pointer: "pointer:gemini-rebuild", protected_fingerprint: "fingerprint:gemini", actor: "pi_gemini_e2e", profile: "test" },
    };
  }
  if (skillId === "snapshot.release") {
    const base = { generation_id: "generation:gemini-release" };
    return {
      inspect: { authority_id: "retrieval", limit: 10 },
      reconcile: { ...base, expected_ids: [], indexed_ids: [] },
      evaluate: { ...base, policy_id: "policy:gemini", policy_checksum: "policy:gemini", reconcile: { missing: 0, orphan: 0, duplicate: 0 } },
      prepare: { ...base, action: "activate", snapshot_id: "snapshot:gemini-release", manifest: { schema: "manifest-v1" }, reconcile: { missing: 0, orphan: 0, duplicate: 0 }, eval_passed: true, eval_checksum: "eval:gemini", current_pointer: "pointer:active", target_pointer: "pointer:gemini-release", protected_fingerprint: "fingerprint:gemini", actor: "pi_gemini_e2e", profile: "test" },
      activate: { confirmed: true },
    };
  }
  const result = {};
  for (const [stepId, tool] of [
    ["inspect", "warehouse.inspect"], ["runtime", "warehouse.inspect"], ["quality", "warehouse.quality"], ["integrity", "warehouse.integrity"],
    ["lineage", "warehouse.lineage"], ["freshness", "warehouse.freshness"], ["failed", "warehouse.failed_batches"],
  ]) {
    if (tool && skillId === "system.diagnosis" && ["inspect", "quality", "integrity"].includes(stepId)) result[stepId] = { authority_id: "system", limit: 10 };
    else if (tool && skillId === "warehouse.health") result[stepId] = { authority_id: "knowledge", limit: 10 };
  }
  return result || empty;
}

function directToolInput(operation, index) {
  const base = { task_id: `pi_direct_${index}`, idempotency_key: `pi-direct-${index}`, binding: "pi_gemini_direct" };
  if (operation.startsWith("warehouse.")) return { ...base, authority_id: "knowledge", limit: 10 };
  if (operation === "ingestion.discover") return { ...base, authority_id: "knowledge", source_checksum: "source:direct", snapshot_checksum: "snapshot:direct", watermark_checksum: "watermark:direct", count: 0, actor: "pi_gemini_e2e", profile: "test" };
  if (operation === "knowledge.extract_l2") return { ...base, ...semanticInput("direct-l2") };
  if (operation === "retrieval.search") return { ...base, query: "gemini", limit: 10 };
  if (["decision.get", "external.get"].includes(operation)) return { ...base, record_id: "record:gemini" };
  return base;
}

test("real Gemini -> all registered Skills -> declared tools -> isolated test DB", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-gemini-all-skills-"));
  const decisionPath = join(dir, "decision.json");
  const ledgerPath = join(dir, "warehouse-test.sqlite");
  const domainPort = await freePort();
  await writeFile(decisionPath, JSON.stringify({ schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID, status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z" }), "utf8");
  const python = spawn(process.env.PYTHON ?? "python", [resolve(repoRoot, "src/personal_knowledge/services/api_server.py"), "--port", String(domainPort)], {
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: `${resolve(repoRoot, "src")};${process.env.PYTHONPATH ?? ""}`, PI_DOMAIN_CAPABILITY: domainCapability, PI_DOMAIN_TEST_LEDGER_PATH: ledgerPath },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let pythonStderr = "";
  python.stderr.on("data", (chunk) => { pythonStderr += chunk.toString(); });
  const previousEnv = { PI_DOMAIN_HOST: process.env.PI_DOMAIN_HOST, PI_DOMAIN_PORT: process.env.PI_DOMAIN_PORT, PI_DOMAIN_CAPABILITY: process.env.PI_DOMAIN_CAPABILITY };
  Object.assign(process.env, { PI_DOMAIN_HOST: "127.0.0.1", PI_DOMAIN_PORT: String(domainPort), PI_DOMAIN_CAPABILITY: domainCapability });
  let runtime;
  try {
    await waitForHealth(domainPort);
    const seed = await requestJson(domainPort, "POST", "/internal/pi-domain/dispatch", {
      operation: "ingestion.preview", params: { task_id: "seed", idempotency_key: "seed-preview", binding: "pi_gemini_direct", authority_id: "knowledge", source_checksum: "source:seed", snapshot_checksum: "snapshot:seed", watermark_checksum: "watermark:seed", count: 1, actor: "pi_gemini_e2e", profile: "test" },
    }, { "x-pi-domain-capability": domainCapability });
    assert.equal(seed.json.ok, true);
    const { capability_checksum: _seedCapabilityChecksum, ...seedPreview } = seed.json.data;
    const committed = await requestJson(domainPort, "POST", "/internal/pi-domain/dispatch", { operation: "ingestion.commit", params: { task_id: "seed-commit", idempotency_key: seedPreview.idempotency_key, binding: "pi_gemini_direct", preview: seedPreview } }, { "x-pi-domain-capability": domainCapability });
    assert.equal(committed.json.ok, true);
    const seedOperationId = committed.json.data.operation_id;

    runtime = await startKernelServer({ projectRoot: repoRoot, decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir, cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0, providerMode: "vertex_google", internalCapability: kernelCapability });
    const port = runtime.server.address().port;
    const skills = runtime.host.skillList();
    assert.equal(skills.length, 11);
    const headers = { "x-pi-internal-capability": kernelCapability };
    const skillResults = [];
    for (const [index, skill] of skills.entries()) {
      const body = {
        task_id: `pi_gemini_skill_${index + 1}`,
        session_id: `pi_gemini_session_${index + 1}`,
        idempotency_key: `pi-gemini-skill-${index + 1}`,
        skill_id: skill.id,
        model: "gemini-3.5-flash-lite",
        model_prompt: `Validate the declared ${skill.id} workflow. Return one compact JSON object with ready=true. Do not call tools; the Kernel executes the declared tools.`,
        skill_input: { step_inputs: skillInputs(skill.id, seedOperationId) },
        confirmed: skill.id === "snapshot.release",
        include_response: true,
      };
      const result = await requestJson(port, "POST", "/v1/tasks", body, headers);
      assert.equal(result.status, 201, `${skill.id}:${JSON.stringify(result.json?.error ?? {})}`);
      assert.equal(result.json.ok, true);
      assert.equal(result.json.response.model_receipt.provider, "vertex_google");
      assert.equal(result.json.response.model_receipt.model, "gemini-3.5-flash-lite");
      if (skill.id === "snapshot.release") {
        assert.equal(result.json.skill_state, "waiting_confirmation");
        assert.equal(result.json.response.checkpoint, "activate");
      } else {
        assert.equal(result.json.task.state, "succeeded", `${skill.id}:${JSON.stringify(result.json)}`);
        assert.equal(result.json.skill_state, "completed");
        assert.ok(result.json.skill_steps.every((step) => step.status === "committed"));
      }
      skillResults.push({ skill_id: skill.id, state: result.json.skill_state, steps: result.json.skill_steps.length, provider_calls: result.json.provider_calls });
    }

    const registry = JSON.parse(await readFile(resolve(repoRoot, "governance/manifests/capabilities/project-capabilities.json"), "utf8"));
    const allOperations = registry.operations.map((operation) => operation.id);
    const covered = new Set(skills.flatMap((skill) => skill.steps.map((step) => step.tool)));
    const uncovered = allOperations.filter((operation) => !covered.has(operation));
    const directResults = [];
    for (const [index, operation] of uncovered.entries()) {
      const result = await requestJson(domainPort, "POST", "/internal/pi-domain/dispatch", { operation, params: directToolInput(operation, index + 100) }, { "x-pi-domain-capability": domainCapability });
      const code = result.json?.error?.code ?? null;
      if (operation.startsWith("canonical.")) assert.equal(code, "preview_required", `${operation}:${JSON.stringify(result.json)}`);
      else assert.equal(result.json?.ok, true, `${operation}:${JSON.stringify(result.json)}`);
      directResults.push({ operation, status: result.json?.status ?? "error", error_code: code });
    }

    await runtime.stop(500);
    runtime = undefined;
    await stopChild(python);
    const warehouseDb = new DatabaseSync(ledgerPath);
    const eventDb = new DatabaseSync(join(dir, "events.sqlite"));
    try {
      const eventCounts = eventDb.prepare("SELECT event_type, COUNT(*) AS count FROM pi_kernel_events WHERE event_type IN ('tool_started','tool_completed') GROUP BY event_type ORDER BY event_type").all();
      const warehouseRows = Number(warehouseDb.prepare("SELECT COUNT(*) AS count FROM pi_data_operations").get().count);
      assert.ok(warehouseRows >= 1);
      assert.ok(eventCounts.some((row) => row.event_type === "tool_started" && Number(row.count) >= 30));
      assert.ok(eventCounts.some((row) => row.event_type === "tool_completed" && Number(row.count) >= 30));
      t.diagnostic(JSON.stringify({ model: "gemini-3.5-flash-lite", skills: skillResults, skill_count: skills.length, registry_operation_count: allOperations.length, covered_tool_count: covered.size, uncovered_tool_count: uncovered.length, direct_tools: directResults, warehouse_operation_rows: warehouseRows, tool_event_counts: eventCounts }));
    } finally {
      eventDb.close();
      warehouseDb.close();
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
