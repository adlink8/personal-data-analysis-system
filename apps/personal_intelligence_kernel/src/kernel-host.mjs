import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";

import {
  createContainedSession,
  PHASE_48_TOOL_NAMES,
  SYNTHETIC_SYSTEM_PROMPT,
} from "./runtime/resource-policy.mjs";
import { EventJournal, PI_KERNEL_EVENTS_DB } from "./events/journal.mjs";
import { createPiKernelEvent, sha256 } from "./events/schema.mjs";
import { TaskLedger, PI_KERNEL_TASKS_DB, TaskLedgerError } from "./tasks/ledger.mjs";
import { SessionStore, PI_KERNEL_SESSIONS_DB } from "./sessions/store.mjs";
import { CandidateStore, PI_KERNEL_CANDIDATES_DB } from "./candidates/store.mjs";
import { createConfiguredProviderAdapter } from "./models/runtime-provider.mjs";
import { getModelRoute } from "./models/routes.mjs";

export const DEFAULT_KERNEL_HOST = Object.freeze({ host: "127.0.0.1", port: 8790 });
export const PHASE_48_DECISION_RUN_ID = "piq_f7896e839999ed2eac87ebd4";
export const RESOURCE_POLICY_VERSION = "pi_resource_policy_v1_exact";
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,255}$/;
const MAX_PROMPT_BYTES = 48 * 1024;

export class KernelHostError extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = "KernelHostError";
    this.code = code;
  }
}

function safeError(code) {
  return new KernelHostError(code);
}

function assertIdentifier(value, code) {
  if (typeof value !== "string" || !IDENTIFIER.test(value)) throw safeError(code);
  return value;
}

function taskPayloadRef(taskId, checksum) {
  return { kind: "task", ref: taskId, checksum };
}

function artifactRef(responseChecksum) {
  return { kind: "artifact", ref: `provider:${responseChecksum.slice(0, 32)}`, checksum: responseChecksum };
}

export async function readPhase48Decision(decisionPath, now = new Date()) {
  let decision;
  try {
    decision = JSON.parse(await readFile(decisionPath, "utf8"));
  } catch {
    throw safeError("package_decision_missing");
  }
  if (!decision || decision.schema !== "pi-package-decision-v1" || decision.run_id !== PHASE_48_DECISION_RUN_ID || decision.status !== "accepted" || decision.accepted !== true) {
    throw safeError("package_decision_not_accepted");
  }
  const expiry = Date.parse(decision.expiry || "");
  if (!Number.isFinite(expiry) || expiry <= now.getTime()) throw safeError("package_decision_expired");
  return Object.freeze({ run_id: decision.run_id, status: decision.status, accepted: true, expiry: decision.expiry });
}

function assertLoopback(host) {
  if (host !== DEFAULT_KERNEL_HOST.host) throw safeError("non_loopback_bind");
}

function assertExactResourcePolicy(resourceLoader, session) {
  const exactFlags = ["noExtensions", "noSkills", "noPromptTemplates", "noThemes", "noContextFiles"];
  if (!resourceLoader || exactFlags.some((flag) => resourceLoader[flag] !== true)) throw safeError("resource_policy_mismatch");
  if (resourceLoader.getSystemPrompt() !== SYNTHETIC_SYSTEM_PROMPT) throw safeError("resource_policy_mismatch");
  if (resourceLoader.getExtensions().extensions?.length || resourceLoader.getSkills().skills?.length || resourceLoader.getPrompts().prompts?.length || resourceLoader.getThemes().themes?.length || resourceLoader.getAgentsFiles().agentsFiles?.length) {
    throw safeError("resource_policy_not_empty");
  }
  const tools = session.getAllTools().map((tool) => tool.name).sort();
  const expected = [...PHASE_48_TOOL_NAMES].sort();
  if (tools.length !== expected.length || tools.some((name, index) => name !== expected[index])) throw safeError("tool_registry_mismatch");
}

export class KernelHost {
  constructor({ journal, session, resourceLoader, modelRuntime, providerAdapter, taskLedger, sessionStore, candidateStore, decision, host, port, shutdownTimeoutMs }) {
    this.journal = journal;
    this.session = session;
    this.resourceLoader = resourceLoader;
    this.modelRuntime = modelRuntime;
    this.providerAdapter = providerAdapter;
    this.taskLedger = taskLedger;
    this.sessionStore = sessionStore;
    this.candidateStore = candidateStore;
    this.decision = decision;
    this.host = host;
    this.port = port;
    this.shutdownTimeoutMs = shutdownTimeoutMs;
    // Provider bodies are kept only for the lifetime of this process so a
    // trusted Python adapter can finish its existing parser contract. They
    // are never written to Task/Session/Event/Candidate stores.
    this.ephemeralResponses = new Map();
    this.server = createServer((_request, response) => {
      response.statusCode = 404;
      response.end();
    });
    this.lifecycle = "ready";
  }

  get providerCalls() { return this.providerAdapter?.providerCalls ?? this.modelRuntime.providerCalls; }

  readiness() {
    if (this.lifecycle !== "ready") return { ready: false, reason: "host_not_running" };
    const integrity = this.journal.integrityCheck();
    const policy = this.resourceLoader && this.resourceLoader.noExtensions === true && this.resourceLoader.noSkills === true && this.resourceLoader.noPromptTemplates === true && this.resourceLoader.noThemes === true && this.resourceLoader.noContextFiles === true;
    return {
      ready: Boolean(this.decision.accepted && policy && integrity.ok && this.host === DEFAULT_KERNEL_HOST.host),
      decision: "accepted",
      resource_policy: RESOURCE_POLICY_VERSION,
      journal: integrity.ok ? "ok" : "failed",
      provider_calls: this.providerCalls,
    };
  }

  isReady() { return this.readiness().ready; }

  status() {
    return { lifecycle: this.lifecycle, host: this.host, port: this.port, provider_calls: this.providerCalls, ready: this.isReady() };
  }

  /** Request cancellation without exposing prompt/output data. */
  cancelTask({ task_id: taskId, expected_version: expectedVersion, idempotency_key: idempotencyKey } = {}) {
    if (!this.taskLedger) throw safeError("task_runtime_unavailable");
    assertIdentifier(taskId, "task_identity_invalid");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    const current = this.taskLedger.get(taskId);
    if (!current) throw safeError("task_not_found");
    if (Number(expectedVersion) !== Number(current.version)) throw safeError("stale_version");
    if (!["queued", "claimed", "running"].includes(current.state)) throw safeError("task_not_cancelable");
    try {
      const event = this.#appendLifecycle("task_cancel_requested", {
        taskId,
        idempotencyKey,
        checksum: current.input_ref?.checksum ?? sha256(taskId),
      });
      const task = this.taskLedger.cancel(taskId, { expectedVersion: current.version, event_ref: event.event.event_id });
      return { task, provider_calls: this.providerCalls };
    } catch (error) {
      if (error instanceof TaskLedgerError) throw safeError(error.code);
      throw safeError("task_execution_failed");
    }
    return { task, provider_calls: this.providerCalls };
  }

  /** Reconcile outcome_unknown only with an explicit terminal state; never retries implicitly. */
  reconcileTask({ task_id: taskId, expected_version: expectedVersion, idempotency_key: idempotencyKey, state, output_checksum: outputChecksum, error_code: errorCode } = {}) {
    if (!this.taskLedger) throw safeError("task_runtime_unavailable");
    assertIdentifier(taskId, "task_identity_invalid");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    if (!["succeeded", "failed"].includes(state)) throw safeError("task_reconcile_state_required");
    const current = this.taskLedger.get(taskId);
    if (!current) throw safeError("task_not_found");
    if (Number(expectedVersion) !== Number(current.version)) throw safeError("stale_version");
    if (current.state !== "outcome_unknown") throw safeError("task_not_resumable");
    try {
      const event = this.#appendLifecycle(state === "succeeded" ? "task_completed" : "task_failed", {
        taskId,
        idempotencyKey,
        checksum: outputChecksum ?? current.input_ref?.checksum ?? sha256(taskId),
      });
      const task = this.taskLedger.transition(taskId, state, {
        expectedVersion: current.version,
        output_ref: outputChecksum ? artifactRef(outputChecksum) : undefined,
        error_code: errorCode,
        event_ref: event.event.event_id,
      });
      return { task, provider_calls: this.providerCalls };
    } catch (error) {
      if (error instanceof TaskLedgerError) throw safeError(error.code);
      throw safeError("task_execution_failed");
    }
  }

  #appendLifecycle(type, { taskId, idempotencyKey, checksum, causationId = null } = {}) {
    const event = createPiKernelEvent({
      type,
      source: "pi_kernel",
      authority: "authority:pi-kernel",
      snapshot: "snapshot:pi-kernel",
      correlation_id: taskId,
      causation_id: causationId,
      idempotency_key: `${idempotencyKey}:${type}`,
      occurred_at: new Date().toISOString(),
      payload_ref: taskPayloadRef(taskId, checksum),
      privacy_class: "R1",
    });
    return { event, row: this.journal.append(event) };
  }

  /** Execute one task through the Pi-owned adapter. The raw prompt remains in memory. */
  async executeTask({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, purpose = "structured_analysis", model, prompt, include_response = false } = {}) {
    if (!this.taskLedger || !this.sessionStore || !this.providerAdapter) throw safeError("task_runtime_unavailable");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    if (taskId !== undefined) assertIdentifier(taskId, "task_identity_invalid");
    if (sessionId !== undefined) assertIdentifier(sessionId, "task_identity_invalid");
    if (typeof prompt !== "string" || !prompt.trim() || Buffer.byteLength(prompt, "utf8") > MAX_PROMPT_BYTES) throw safeError("task_prompt_invalid");
    let route;
    try { route = getModelRoute(purpose, model); } catch { throw safeError("model_route_unknown"); }

    const actualTaskId = taskId ?? `pi_task_${sha256(idempotencyKey).slice(0, 24)}`;
    const actualSessionId = sessionId ?? `pi_session_${sha256(`${idempotencyKey}:session`).slice(0, 24)}`;
    const promptChecksum = sha256(prompt);
    const inputRef = { kind: "artifact", ref: `prompt:${promptChecksum.slice(0, 32)}`, checksum: promptChecksum };
    let accepted;
    try {
      accepted = this.taskLedger.enqueue({ task_id: actualTaskId, idempotency_key: idempotencyKey, input_ref: inputRef });
    } catch (error) {
      if (error instanceof TaskLedgerError) throw safeError(error.code);
      throw safeError("task_enqueue_failed");
    }
    if (accepted.duplicate) {
      const result = { duplicate: true, task: accepted.task, session_id: actualSessionId, route: route.purpose, provider_calls: this.providerCalls };
      if (include_response) {
        const cached = this.ephemeralResponses.get(actualTaskId);
        if (!cached) throw safeError("provider_response_unavailable");
        result.response = cached;
      }
      return result;
    }

    try {
      if (!this.sessionStore.get(actualSessionId)) this.sessionStore.create({ session_id: actualSessionId, trajectory: [] });
      const acceptedEvent = this.#appendLifecycle("task_accepted", { taskId: actualTaskId, idempotencyKey, checksum: promptChecksum });
      let task = this.taskLedger.claim(actualTaskId, { owner: "pi_kernel", leaseMs: route.timeout_ms + 5000 });
      task = this.taskLedger.transition(actualTaskId, "running", { expectedVersion: task.version, owner: "pi_kernel", event_ref: acceptedEvent.event.event_id });
      const startedEvent = this.#appendLifecycle("task_started", { taskId: actualTaskId, idempotencyKey, checksum: promptChecksum, causationId: acceptedEvent.event.event_id });
      const receipt = await this.providerAdapter.generate({ purpose, model: route.model, prompt, task_id: actualTaskId, session_id: actualSessionId, event_id: startedEvent.event.event_id, idempotency_key: idempotencyKey, max_output_tokens: route.max_output_tokens });
      const responseChecksum = receipt.response_checksum;
      this.ephemeralResponses.set(actualTaskId, receipt.response);
      this.sessionStore.append(actualSessionId, { kind: "model_receipt", task_id: actualTaskId, route_checksum: receipt.route_checksum, response_checksum: responseChecksum, usage_checksum: receipt.usage_checksum, status: receipt.telemetry.status }, { receipt: { kind: "model", task_id: actualTaskId, response_checksum: responseChecksum, route_checksum: receipt.route_checksum, usage_checksum: receipt.usage_checksum } });
      const completedEvent = this.#appendLifecycle("task_completed", { taskId: actualTaskId, idempotencyKey, checksum: responseChecksum, causationId: startedEvent.event.event_id });
      task = this.taskLedger.transition(actualTaskId, "succeeded", { expectedVersion: task.version, owner: "pi_kernel", output_ref: artifactRef(responseChecksum), event_ref: completedEvent.event.event_id });
      const result = { duplicate: false, task, session_id: actualSessionId, route: route.purpose, receipt: { response_checksum: responseChecksum, usage_checksum: receipt.usage_checksum, input_tokens: receipt.usage.input_tokens, output_tokens: receipt.usage.output_tokens, provider: receipt.telemetry.provider, model: receipt.telemetry.model, cost: receipt.telemetry.cost, currency: receipt.telemetry.currency }, provider_calls: this.providerCalls };
      if (include_response) result.response = receipt.response;
      return result;
    } catch (error) {
      const code = error?.code || "task_execution_failed";
      const task = this.taskLedger.get(actualTaskId);
      if (task && !["succeeded", "failed", "outcome_unknown"].includes(task.state)) {
        const unknown = ["provider_timeout", "provider_transport_error"].includes(code);
        const next = unknown ? "outcome_unknown" : "failed";
        try { this.taskLedger.transition(actualTaskId, next, { expectedVersion: task.version, owner: "pi_kernel", error_code: code }); } catch { /* retain safe terminal evidence */ }
        try { this.#appendLifecycle(unknown ? "error" : "task_failed", { taskId: actualTaskId, idempotencyKey, checksum: promptChecksum }); } catch { /* preserve safe error */ }
      }
      if (error instanceof KernelHostError) throw error;
      throw safeError(code);
    }
  }

  /** Stage only candidate metadata; serving lifecycle remains Python-owned. */
  stageCandidate({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, candidate_id: candidateId, proposal, evidence_refs: evidenceRefs, model_receipt: modelReceipt } = {}) {
    assertIdentifier(taskId, "task_identity_invalid");
    assertIdentifier(sessionId, "task_identity_invalid");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    assertIdentifier(candidateId, "candidate_identity_invalid");
    if (!proposal || typeof proposal !== "object" || !Array.isArray(evidenceRefs) || !modelReceipt || typeof modelReceipt !== "object") throw safeError("candidate_metadata_invalid");
    const existing = this.candidateStore.get(candidateId);
    if (existing) return { duplicate: true, candidate: existing };
    const candidate = this.candidateStore.add({ candidate_id: candidateId, proposal, evidence_refs: evidenceRefs, model_receipt: modelReceipt, schema_version: "pi_kernel_candidate_v1" });
    const candidateChecksum = sha256({ candidate_id: candidateId, proposal, evidence_refs: evidenceRefs, model_receipt: modelReceipt });
    const event = this.#appendLifecycle("candidate_staged", { taskId, idempotencyKey, checksum: candidateChecksum });
    this.sessionStore.append(sessionId, { kind: "candidate_receipt", task_id: taskId, candidate_id: candidateId, candidate_checksum: candidateChecksum }, { receipt: { kind: "candidate", task_id: taskId, candidate_id: candidateId, candidate_checksum: candidateChecksum } });
    return { duplicate: false, candidate, event: { event_id: event.event.event_id, canonical_checksum: event.row.canonical_checksum } };
  }

  async listen() {
    if (this.server.listening) return;
    await new Promise((resolveListen, rejectListen) => {
      const onError = () => {
        this.server.removeListener("listening", onListening);
        rejectListen(safeError("host_bind_failed"));
      };
      const onListening = () => {
        this.server.removeListener("error", onError);
        resolveListen();
      };
      this.server.once("error", onError);
      this.server.once("listening", onListening);
      this.server.listen(this.port, this.host);
    });
  }

  async closeServer(timeoutMs) {
    if (!this.server.listening) return false;
    let timedOut = false;
    await Promise.race([
      new Promise((resolveClose) => this.server.close(() => resolveClose())),
      new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
    ]);
    return timedOut;
  }

  async shutdown(timeoutMs = this.shutdownTimeoutMs) {
    if (this.lifecycle === "disposed") return { lifecycle: "disposed", timed_out: false };
    this.lifecycle = "stopping";
    let timedOut = false;
    const abort = Promise.resolve().then(() => this.session?.abort?.()).catch(() => undefined);
    await Promise.race([
      abort,
      new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
    ]);
    try {
      await Promise.race([
        Promise.resolve().then(() => this.session?.dispose?.()),
        new Promise((resolveTimeout) => setTimeout(() => { timedOut = true; resolveTimeout(); }, timeoutMs)),
      ]);
    } catch { /* bounded disposal must continue */ }
    timedOut = (await this.closeServer(timeoutMs)) || timedOut;
    try { this.taskLedger?.close(); } catch { /* bounded disposal continues */ }
    try { this.sessionStore?.close(); } catch { /* bounded disposal continues */ }
    try { this.candidateStore?.close(); } catch { /* bounded disposal continues */ }
    this.ephemeralResponses.clear();
    this.journal.close();
    this.lifecycle = "disposed";
    return { lifecycle: this.lifecycle, timed_out: timedOut };
  }

  async dispose(timeoutMs = this.shutdownTimeoutMs) { return this.shutdown(timeoutMs); }
}

/** Construct the sole Phase 49 host after all package and resource gates pass. */
export async function createKernelHost(options = {}) {
  const host = options.host ?? DEFAULT_KERNEL_HOST.host;
  const port = options.port ?? DEFAULT_KERNEL_HOST.port;
  assertLoopback(host);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw safeError("invalid_port");
  const projectRoot = resolve(options.projectRoot ?? process.cwd());
  const decisionPath = resolve(options.decisionPath ?? resolve(projectRoot, "governance/manifests/ai/pi-package-decision.json"));
  const decision = await readPhase48Decision(decisionPath, options.now ?? new Date());
  const eventDatabasePath = options.databasePath ?? resolve(projectRoot, PI_KERNEL_EVENTS_DB);
  const journal = new EventJournal(eventDatabasePath);
  const dbRoot = resolve(options.controlDatabaseDirectory ?? dirname(resolve(eventDatabasePath)));
  const taskLedger = new TaskLedger(options.tasksDatabasePath ?? resolve(dbRoot, PI_KERNEL_TASKS_DB.replace("var/db/", "")));
  const sessionStore = new SessionStore(options.sessionsDatabasePath ?? resolve(dbRoot, PI_KERNEL_SESSIONS_DB.replace("var/db/", "")));
  const candidateStore = new CandidateStore(options.candidatesDatabasePath ?? resolve(dbRoot, PI_KERNEL_CANDIDATES_DB.replace("var/db/", "")));
  const providerAdapter = createConfiguredProviderAdapter({
    mode: options.providerMode ?? process.env.PI_KERNEL_PROVIDER_MODE ?? "replay",
    fetchImpl: options.fetchImpl,
  });
  let hostInstance;
  try {
    const cwd = resolve(options.cwd ?? projectRoot);
    const agentDir = resolve(options.agentDir ?? resolve(projectRoot, ".pi-agent-disabled"));
    const contained = await createContainedSession({ cwd, agentDir });
    assertExactResourcePolicy(contained.resourceLoader, contained.session);
    if (contained.modelRuntime.providerCalls !== 0) throw safeError("provider_call_detected");
    hostInstance = new KernelHost({
      journal,
      session: contained.session,
      resourceLoader: contained.resourceLoader,
      modelRuntime: contained.modelRuntime,
      providerAdapter,
      taskLedger,
      sessionStore,
      candidateStore,
      decision,
      host,
      port,
      shutdownTimeoutMs: options.shutdownTimeoutMs ?? 1000,
    });
    if (!hostInstance.isReady()) throw safeError("host_not_ready");
    await hostInstance.listen();
    return hostInstance;
  } catch (error) {
    try { await hostInstance?.shutdown(options.shutdownTimeoutMs ?? 1000); } catch { /* preserve bootstrap error */ }
    try { journal.close(); } catch { /* preserve bootstrap error */ }
    try { taskLedger.close(); } catch { /* preserve bootstrap error */ }
    try { sessionStore.close(); } catch { /* preserve bootstrap error */ }
    try { candidateStore.close(); } catch { /* preserve bootstrap error */ }
    if (error instanceof KernelHostError) throw error;
    throw safeError("resource_policy_mismatch");
  }
}

export const createKernelHostFactory = createKernelHost;
