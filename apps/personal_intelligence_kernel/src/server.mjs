import { createServer as createHttpServer } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";

import { createKernelHost, DEFAULT_KERNEL_HOST, KernelHostError } from "./kernel-host.mjs";
import { JOURNAL_SCHEMA_VERSION, PiKernelJournalError } from "./events/journal.mjs";
import { PiKernelSchemaError, validatePiKernelEvent } from "./events/schema.mjs";
import { streamJournalAsSse, SseTransportError } from "./transport/sse.mjs";

export const ALLOWED_ROUTES = Object.freeze([
  "GET /health",
  "GET /ready",
  "GET /v1/tasks",
  "GET /v1/tasks/:task_id",
  "GET /v1/skills",
  "POST /v1/tasks",
  "POST /v1/tasks/:task_id/cancel",
  "POST /v1/tasks/:task_id/resume",
  "POST /internal/v1/candidates",
  "POST /v1/events",
  "GET /v1/events/stream",
]);
export const MAX_EVENT_BODY_BYTES = 64 * 1024;
export const SAFE_ERROR_CODES = Object.freeze([
  "route_not_found",
  "method_not_allowed",
  "event_invalid",
  "event_too_large",
  "event_idempotency_conflict",
  "event_checksum_conflict",
  "cursor_invalid",
  "cursor_not_found",
  "journal_unavailable",
  "task_runtime_unavailable",
  "task_identity_invalid",
  "task_prompt_invalid",
  "model_route_unknown",
  "task_enqueue_failed",
  "task_not_found",
  "task_busy",
  "task_not_cancelable",
  "task_not_resumable",
  "task_reconcile_state_required",
  "stale_version",
  "illegal_transition",
  "legacy_provider_rollback_only",
  "provider_mode_unknown",
  "provider_credential_missing",
  "provider_transport_missing",
  "provider_response_invalid",
  "provider_response_unavailable",
  "internal_capability_invalid",
  "candidate_identity_invalid",
  "candidate_metadata_invalid",
  "provider_cost_ceiling_exceeded",
  "provider_timeout",
  "provider_transport_error",
  "skill_runtime_unavailable",
  "skill_identity_invalid",
  "skill_input_invalid",
  "skill_not_found",
  "skill_response_unavailable",
  "skill_registry_unavailable",
  "skill_tool_escalation",
  "binding_required",
  "domain_unavailable",
  "timeout",
  "host_not_ready",
  "host_bind_failed",
  "non_loopback_bind",
  "invalid_port",
  "internal_error",
]);

function safeCode(error, fallback = "internal_error") {
  if (error instanceof SseTransportError) {
    if (error.code === "invalid_cursor") return "cursor_invalid";
    if (error.code === "cursor_not_found") return "cursor_not_found";
  }
  if (error instanceof PiKernelSchemaError) return "event_invalid";
  if (error instanceof PiKernelJournalError) {
    if (error.code === "idempotency_conflict") return "event_idempotency_conflict";
    if (error.code === "event_checksum_conflict") return "event_checksum_conflict";
    if (error.code === "invalid_cursor") return "cursor_invalid";
    return "journal_unavailable";
  }
  if (error instanceof KernelHostError && SAFE_ERROR_CODES.includes(error.code)) return error.code;
  return fallback;
}

function sendJson(response, statusCode, body) {
  const payload = JSON.stringify(body);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(payload),
    "Cache-Control": "no-store",
  });
  response.end(payload);
}

function sendSafeError(response, statusCode, code) {
  sendJson(response, statusCode, { ok: false, error: { code } });
}

function statusForError(code) {
  if (code === "route_not_found") return 404;
  if (code === "method_not_allowed") return 405;
  if (code === "host_not_ready" || code === "journal_unavailable") return 503;
  if (code === "cursor_not_found" || code === "event_idempotency_conflict" || code === "event_checksum_conflict") return 409;
  return 400;
}

async function readBoundedJson(request) {
  const length = Number(request.headers["content-length"]);
  if (Number.isFinite(length) && length > MAX_EVENT_BODY_BYTES) {
    request.resume();
    throw new KernelHostError("event_too_large");
  }
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > MAX_EVENT_BODY_BYTES) throw new KernelHostError("event_too_large");
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8") || "null");
  } catch {
    throw new KernelHostError("event_invalid");
  }
}

function resourceRegistryReady(host) {
  const loader = host?.resourceLoader;
  const exactFlags = ["noExtensions", "noSkills", "noPromptTemplates", "noThemes", "noContextFiles"];
  if (!loader || exactFlags.some((flag) => loader[flag] !== true)) return false;
  try {
    const empty = loader.getExtensions().extensions?.length === 0
      && loader.getSkills().skills?.length === 0
      && loader.getPrompts().prompts?.length === 0
      && loader.getThemes().themes?.length === 0
      && loader.getAgentsFiles().agentsFiles?.length === 0;
    const tools = host.session.getAllTools().map((tool) => tool.name).sort();
    const expected = (host.capabilityRegistry?.operations ?? []).map((operation) => operation.id).sort();
    return empty && Boolean(host.capabilityRegistry?.checksum) && tools.length === expected.length && tools.every((name, index) => name === expected[index]);
  } catch {
    return false;
  }
}

export function getReadiness(host) {
  let integrity = { ok: false, integrity_check: "failed" };
  try { integrity = host.journal.integrityCheck(); } catch { /* safe readiness failure */ }
  const checks = {
    package_decision: host?.decision?.accepted === true && host?.decision?.status === "accepted",
    resource_registry: resourceRegistryReady(host),
    schema_migration: integrity.schema_version === JOURNAL_SCHEMA_VERSION,
    sqlite_integrity: integrity.ok === true && integrity.integrity_check === "ok",
  };
  return {
    ready: host?.lifecycle === "ready" && host?.host === DEFAULT_KERNEL_HOST.host && Object.values(checks).every(Boolean),
    checks,
    provider_calls: host?.providerCalls ?? 0,
  };
}

function liveHealth(host) {
  return {
    ok: true,
    status: "ok",
    host: host.host,
    port: host.server.address()?.port ?? host.port,
    provider_calls: host.providerCalls,
  };
}

function attachRequestHandler(host, options) {
  const server = host.server;
  const connections = new Set();
  server.on("connection", (socket) => {
    connections.add(socket);
    socket.once("close", () => connections.delete(socket));
  });
  server.removeAllListeners("request");
  server.on("request", async (request, response) => {
    const url = new URL(request.url || "/", "http://127.0.0.1");
    const route = `${request.method || ""} ${url.pathname}`;
    try {
      if (route === "GET /health") {
        sendJson(response, 200, liveHealth(host));
        return;
      }
      if (route === "GET /ready") {
        const readiness = getReadiness(host);
        sendJson(response, readiness.ready ? 200 : 503, { ok: readiness.ready, ...readiness });
        return;
      }
      if (route === "GET /v1/tasks") {
        sendJson(response, 200, { ok: true, tasks: host.taskLedger.list().map((task) => ({ ...task, input_ref: task.input_ref, output_ref: task.output_ref })) });
        return;
      }
      if (route === "GET /v1/skills") {
        sendJson(response, 200, { ok: true, skills: host.skillList() });
        return;
      }
      if (route === "GET /v1/operations") {
        sendJson(response, 200, { ok: true, operations: host.operationList() });
        return;
      }
      if (request.method === "GET" && url.pathname.startsWith("/v1/operations/")) {
        const operationId = url.pathname.slice("/v1/operations/".length);
        const operation = host.operationGet(operationId);
        if (!operation) throw new KernelHostError("operation_not_found");
        sendJson(response, 200, { ok: true, operation });
        return;
      }
      if (route === "POST /v1/tasks") {
        const body = await readBoundedJson(request);
        const includeResponse = body?.include_response === true;
        if (includeResponse && !isInternalRequest(request, options)) throw new KernelHostError("internal_capability_invalid");
        const result = await host.executeTask(body);
        sendJson(response, result.duplicate ? 200 : 201, { ok: true, ...result });
        return;
      }
      if (route === "POST /internal/v1/candidates") {
        if (!isInternalRequest(request, options)) throw new KernelHostError("internal_capability_invalid");
        const body = await readBoundedJson(request);
        const result = host.stageCandidate(body);
        sendJson(response, result.duplicate ? 200 : 201, { ok: true, ...result });
        return;
      }
      if (request.method === "POST" && url.pathname.match(/^\/v1\/tasks\/[^/]+\/(cancel|resume)$/)) {
        const match = url.pathname.match(/^\/v1\/tasks\/([^/]+)\/(cancel|resume)$/);
        const body = await readBoundedJson(request);
        const taskId = match[1];
        if (body.task_id !== undefined && body.task_id !== taskId) throw new KernelHostError("task_identity_invalid");
        const payload = { ...body, task_id: taskId };
        const result = match[2] === "cancel" ? host.cancelTask(payload) : host.reconcileTask(payload);
        sendJson(response, 200, { ok: true, ...result });
        return;
      }
      if (request.method === "POST" && url.pathname.match(/^\/v1\/operations\/[^/]+\/(cancel|resume|reconcile)$/)) {
        const match = url.pathname.match(/^\/v1\/operations\/([^/]+)\/(cancel|resume|reconcile)$/);
        const body = await readBoundedJson(request);
        if (body.operation_id !== undefined && body.operation_id !== match[1]) throw new KernelHostError("operation_identity_invalid");
        const payload = { ...body, operation_id: match[1] };
        const result = match[2] === "cancel" ? host.operationCancel(payload) : match[2] === "resume" ? host.operationResume(payload) : host.operationReconcile(payload);
        sendJson(response, 200, result);
        return;
      }
      if (request.method === "GET" && url.pathname.startsWith("/v1/tasks/")) {
        const taskId = url.pathname.slice("/v1/tasks/".length);
        const task = host.taskLedger.get(taskId);
        if (!task) throw new KernelHostError("task_not_found");
        sendJson(response, 200, { ok: true, task });
        return;
      }
      if (route === "POST /v1/events") {
        const event = await readBoundedJson(request);
        const row = host.journal.append(validatePiKernelEvent(event));
        sendJson(response, row.duplicate ? 200 : 201, {
          ok: true,
          status: row.status,
          replay: row.replay,
          duplicate: row.duplicate,
          sequence: row.sequence,
          event_id: row.event_id,
          idempotency_identity: row.idempotency_identity,
        });
        return;
      }
      if (route === "GET /v1/events/stream") {
        await streamJournalAsSse({
          request,
          response,
          journal: host.journal,
          pollIntervalMs: options.pollIntervalMs,
          heartbeatIntervalMs: options.heartbeatIntervalMs,
        });
        return;
      }
      const samePath = ["/health", "/ready", "/v1/tasks", "/v1/skills", "/v1/operations", "/v1/events", "/v1/events/stream", "/internal/v1/candidates"].includes(url.pathname) || url.pathname.startsWith("/v1/tasks/") || url.pathname.startsWith("/v1/operations/");
      sendSafeError(response, samePath ? 405 : 404, samePath ? "method_not_allowed" : "route_not_found");
    } catch (error) {
      const code = safeCode(error);
      if (!response.headersSent) sendSafeError(response, statusForError(code), code);
      else {
        try { response.destroy(); } catch { /* client already closed */ }
      }
    }
  });
  return connections;
}

function isInternalRequest(request, options) {
  const expected = String(options?.internalCapability ?? process.env.PI_KERNEL_INTERNAL_CAPABILITY ?? "").trim();
  const supplied = String(request.headers["x-pi-internal-capability"] ?? "").trim();
  return Boolean(expected) && supplied === expected;
}

export function createKernelHttpServer(host, options = {}) {
  if (!host?.server || !host.journal) throw new TypeError("host is required");
  const connections = attachRequestHandler(host, options);
  let stopping;
  const stop = async (timeoutMs = options.shutdownTimeoutMs ?? 1000) => {
    if (stopping) return stopping;
    stopping = (async () => {
      // KernelHost 49-01 bounds server.close but cannot force active sockets.
      // Transport owns these sockets, so destroy them before delegating disposal.
      for (const socket of connections) socket.destroy();
      host.server.closeAllConnections?.();
      const result = await host.shutdown(timeoutMs);
      for (const socket of connections) socket.destroy();
      return result;
    })();
    return stopping;
  };
  return Object.freeze({ host, server: host.server, connections, stop });
}

async function reserveRandomLoopbackPort() {
  const probe = createHttpServer();
  probe.listen(0, DEFAULT_KERNEL_HOST.host);
  await once(probe, "listening");
  const port = probe.address().port;
  await new Promise((resolveClose) => probe.close(resolveClose));
  return port;
}

function parseCli(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) continue;
    const key = arg.slice(2).replaceAll("-", "_");
    values[key] = argv[index + 1]?.startsWith("--") ? true : (argv[index + 1] ?? true);
    if (values[key] !== true) index += 1;
  }
  return values;
}

function numberOption(value, fallback) {
  if (value === undefined) return fallback;
  const result = Number(value);
  return Number.isInteger(result) ? result : value;
}

export async function startKernelServer(options = {}) {
  const env = options.env ?? process.env;
  const cli = options.cli ?? {};
  const host = options.host ?? cli.host ?? env.PI_KERNEL_HOST ?? DEFAULT_KERNEL_HOST.host;
  const requestedPort = options.port ?? numberOption(cli.port ?? env.PI_KERNEL_PORT, DEFAULT_KERNEL_HOST.port);
  if (requestedPort === 0) options = { ...options, port: await reserveRandomLoopbackPort() };
  else options = { ...options, port: requestedPort };
  const kernelHost = await createKernelHost({ ...options, host });
  return createKernelHttpServer(kernelHost, options);
}

export async function runKernelServerCli(argv = process.argv.slice(2), env = process.env) {
  const cli = parseCli(argv);
  const runtime = await startKernelServer({
    cli,
    env,
    projectRoot: cli.project_root,
    databasePath: cli.database_path,
    decisionPath: cli.decision_path,
    cwd: cli.cwd,
    agentDir: cli.agent_dir,
    providerMode: cli.provider_mode ?? env.PI_KERNEL_PROVIDER_MODE,
    shutdownTimeoutMs: numberOption(cli.shutdown_timeout_ms ?? env.PI_KERNEL_SHUTDOWN_TIMEOUT_MS, 1000),
  });
  const address = runtime.server.address();
  process.stdout.write(`${JSON.stringify({ event: "listening", host: DEFAULT_KERNEL_HOST.host, port: address.port })}\n`);
  let stopping = false;
  const onSignal = async () => {
    if (stopping) return;
    stopping = true;
    const result = await runtime.stop();
    process.stdout.write(`${JSON.stringify({ event: "stopped", timed_out: result.timed_out === true })}\n`);
    process.exitCode = 0;
  };
  process.once("SIGINT", onSignal);
  process.once("SIGTERM", onSignal);
  return runtime;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  runKernelServerCli().catch((error) => {
    process.stderr.write(`${JSON.stringify({ ok: false, error: { code: safeCode(error) } })}\n`);
    process.exitCode = 1;
  });
}

export const createServer = createKernelHttpServer;
