import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, resolve } from "node:path";

import {
  createContainedSession,
  deriveConversationLease,
} from "./runtime/resource-policy.mjs";
import { conversationSessionFactory } from "./runtime/conversation-session.mjs";
import { runConversationTurn } from "./conversation/turn-service.mjs";
import { createConversationSession, SessionServiceError } from "./conversation/session-service.mjs";
import { EventJournal, PI_KERNEL_EVENTS_DB } from "./events/journal.mjs";
import { createPiKernelEvent, sha256 } from "./events/schema.mjs";
import { TaskLedger, PI_KERNEL_TASKS_DB, TaskLedgerError } from "./tasks/ledger.mjs";
import { SessionStore, PI_KERNEL_SESSIONS_DB } from "./sessions/store.mjs";
import { CandidateStore, PI_KERNEL_CANDIDATES_DB } from "./candidates/store.mjs";
import { createConfiguredProviderAdapter } from "./models/runtime-provider.mjs";
import { getModelRoute } from "./models/routes.mjs";
import { createRuntimeControl } from "./control/runtime-control.mjs";
import { createProjectDomainBridge } from "./tools/domain-bridge.mjs";
import { SkillEngine } from "./skills/engine.mjs";
import { SkillRegistry } from "./skills/registry.mjs";

export const DEFAULT_KERNEL_HOST = Object.freeze({ host: "127.0.0.1", port: 8790 });
export const PHASE_48_DECISION_RUN_ID = "piq_f7896e839999ed2eac87ebd4";
export const RESOURCE_POLICY_VERSION = "pi_resource_policy_v1_exact";
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,255}$/;
const MAX_PROMPT_BYTES = 48 * 1024;

// Plan 61-08: the fixed candidate.review route accepts exactly the review
// request shape (capability is the loopback transport header). Private payload
// fields, provider/operation/authority overrides, batch inputs and alternate
// paths fail before Gateway dispatch so no endpoint/path/provider bypass is
// possible (T-61-REVIEW-02).
const CANDIDATE_REVIEW_ACTIONS = new Set(["accept", "edit", "ignore", "undo"]);
const CANDIDATE_REVIEW_ALLOWED_FIELDS = new Set([
  "candidate_id", "action", "expected_version", "edited_payload",
  "edited_payload_checksum", "explicit_confirmation", "confirmation_token",
  "conflict_disposition", "feedback_id", "task_id", "binding", "idempotency_key",
]);

// Plan 61-09: the fixed personal-model projection read route (HARNESS-07)
// accepts exactly {scope, task_id, idempotency_key, binding}; capability is the
// loopback transport header and never a field. Private/override fields,
// provider/operation/endpoint/path/authority overrides and alternate paths fail
// before Gateway dispatch so no endpoint/path/provider bypass is possible
// (T-61-PROJ-02).
const MODEL_PROJECTION_OPERATION = "personal.model_projection.get";
const MODEL_PROJECTION_ALLOWED_FIELDS = new Set(["scope", "task_id", "idempotency_key", "binding"]);

// Plan 61-10: four fixed deterministic proactive presentation bindings
// (D-23-D-25, HARNESS-05). Each route accepts exactly the declared request
// vocabulary (capability is the loopback transport header and never a field);
// state is a read and controls/dismiss/undo are guarded_writes. Private/
// override fields, provider/operation/endpoint/path/authority overrides,
// learned-scheduling/permission/value/canonical commands, alternate paths and
// method mismatches fail before Gateway dispatch so no endpoint/path/provider
// bypass is possible (T-61-PROACTIVE-02/-03). Feedback stays append-only and
// the envelopes never claim a canonical/promotion/rollback/watermark/
// active-pointer authority mutation.
const PROACTIVE_STATE_OPERATION = "proactive.state.get";
const PROACTIVE_CONTROLS_OPERATION = "proactive.controls.update";
const PROACTIVE_DISMISS_OPERATION = "proactive.dismiss";
const PROACTIVE_UNDO_OPERATION = "proactive.dismiss.undo";
const PROACTIVE_CATEGORIES = new Set(["同步", "简报", "反思候选"]);
const PROACTIVE_PROJECT_SCOPE = /^project:[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,255}$/;
const PROACTIVE_QUIET_TIME = /^([01]?\d|2[0-3]):([0-5]\d)$/;
const PROACTIVE_ALLOWED_FIELDS = Object.freeze({
  [PROACTIVE_STATE_OPERATION]: new Set(["scope", "events", "controls", "quiet_hours", "now", "manual_order", "task_id", "idempotency_key", "binding"]),
  [PROACTIVE_CONTROLS_OPERATION]: new Set(["scope", "category", "enabled", "quiet_hours", "task_id", "idempotency_key", "binding"]),
  [PROACTIVE_DISMISS_OPERATION]: new Set(["cluster_key", "feedback_id", "actor_identity_hash", "now", "feedback_log", "task_id", "idempotency_key", "binding"]),
  [PROACTIVE_UNDO_OPERATION]: new Set(["dismissal_feedback_id", "feedback_id", "actor_identity_hash", "now", "feedback_log", "task_id", "idempotency_key", "binding"]),
});

function assertProactivePayloadShape(payload) {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) throw safeError("proactive_request_invalid");
}

function assertProactiveBinding(payload) {
  if (typeof payload.idempotency_key !== "string" || !payload.idempotency_key) throw safeError("idempotency_key_required");
  if (payload.binding === null || payload.binding === undefined || (typeof payload.binding !== "string" && typeof payload.binding !== "object")) throw safeError("binding_required");
}

function assertProactiveScope(value) {
  if (typeof value !== "string" || (value !== "global" && !PROACTIVE_PROJECT_SCOPE.test(value))) throw safeError("scope_identity_invalid");
  return value;
}

function assertProactiveQuietHours(quietHours) {
  if (quietHours === undefined || quietHours === null) return;
  if (typeof quietHours !== "object" || Array.isArray(quietHours)) throw safeError("proactive_request_invalid");
  if (quietHours.enabled !== true) return;
  if (typeof quietHours.start !== "string" || !PROACTIVE_QUIET_TIME.test(quietHours.start)
    || typeof quietHours.end !== "string" || !PROACTIVE_QUIET_TIME.test(quietHours.end)) {
    throw safeError("proactive_request_invalid");
  }
}

/** Shared field allowlist + sender/binding gate for a fixed proactive route. */
function assertProactiveRequest(operation, payload) {
  assertProactivePayloadShape(payload);
  for (const key of Object.keys(payload)) {
    if (!PROACTIVE_ALLOWED_FIELDS[operation].has(key)) throw safeError("undeclared_input");
  }
  assertProactiveBinding(payload);
}

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

/**
 * Plan 61-09 (T-61-CANON-02): bound the served projection envelope so it never
 * exposes canonical/promotion authority state. Watermark/active-pointer keys
 * and evidence references that name canonical/promotion authority are stripped;
 * support/conflict counts are recomputed against the sanitized refs. The
 * projection route is a bounded no-store read and never claims an authority
 * mutation.
 */
function sanitizeProjectionEnvelope(data) {
  if (Array.isArray(data)) {
    const cleaned = [];
    for (const item of data) {
      if (typeof item === "string" && /promot|rollback|canonical\./i.test(item)) continue;
      cleaned.push(sanitizeProjectionEnvelope(item));
    }
    return cleaned;
  }
  if (data && typeof data === "object") {
    const out = {};
    for (const [key, value] of Object.entries(data)) {
      if (/^(watermark|active_pointer)$/i.test(key)) continue;
      out[key] = sanitizeProjectionEnvelope(value);
    }
    if (Array.isArray(out.support_refs)) out.support_count = out.support_refs.length;
    if (Array.isArray(out.conflict_refs)) out.conflict_count = out.conflict_refs.length;
    return out;
  }
  return data;
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

function assertExactResourcePolicy(resourceLoader, session, { profile, registry, toolNames }) {
  const exactFlags = ["noExtensions", "noSkills", "noPromptTemplates", "noThemes", "noContextFiles"];
  if (!resourceLoader || exactFlags.some((flag) => resourceLoader[flag] !== true)) throw safeError("resource_policy_mismatch");
  if (profile !== "production" || !registry?.checksum || resourceLoader.getSystemPrompt() !== "Pi production Capability Registry tools only; use the declared domain operation and never access ambient resources.") throw safeError("resource_policy_mismatch");
  if (resourceLoader.getExtensions().extensions?.length || resourceLoader.getSkills().skills?.length || resourceLoader.getPrompts().prompts?.length || resourceLoader.getThemes().themes?.length || resourceLoader.getAgentsFiles().agentsFiles?.length) {
    throw safeError("resource_policy_not_empty");
  }
  const tools = session.getAllTools().map((tool) => tool.name).sort();
  const expected = [...toolNames].sort();
  if (tools.length !== expected.length || tools.some((name, index) => name !== expected[index])) throw safeError("tool_registry_mismatch");
}

export class KernelHost {
  constructor({ journal, session, resourceLoader, modelRuntime, providerAdapter, taskLedger, sessionStore, candidateStore, decision, host, port, shutdownTimeoutMs, capabilityRegistry, runtimeControl, skillRegistry, skillEngine, domainBridge, domainBridgeOptions, conversationSessionFactory, cwd, agentDir }) {
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
    this.capabilityRegistry = capabilityRegistry;
    this.runtimeControl = runtimeControl ?? createRuntimeControl();
    this.skillRegistry = skillRegistry;
    this.skillEngine = skillEngine ?? (skillRegistry ? new SkillEngine({ registry: skillRegistry }) : null);
    this.domainBridge = domainBridge;
    this.domainBridgeOptions = domainBridgeOptions;
    this.conversationSessionFactory = conversationSessionFactory;
    this.cwd = cwd;
    this.agentDir = agentDir;
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
      capability_registry: { checksum: this.capabilityRegistry?.checksum ?? null, profile: this.capabilityRegistry?.profile ?? null, tool_count: this.capabilityRegistry?.operations?.length ?? 0 },
    };
  }

  isReady() { return this.readiness().ready; }

  status() {
    return { lifecycle: this.lifecycle, host: this.host, port: this.port, provider_calls: this.providerCalls, ready: this.isReady() };
  }

  operationList() { return this.runtimeControl.list(); }
  operationGet(operationId) { return this.runtimeControl.get(operationId); }
  operationCancel(payload) { return this.runtimeControl.cancel(payload); }
  operationResume(payload) { return this.runtimeControl.resume(payload); }
  operationReconcile(payload) { return this.runtimeControl.reconcile(payload); }
  skillList() {
    return (this.skillRegistry?.manifests ?? []).map((skill) => ({
      id: skill.id, version: skill.version, purpose: skill.purpose, checksum: skill.checksum,
      steps: skill.steps.map((step) => ({ id: step.id, tool: step.tool, requires_confirmation: step.requires_confirmation })),
      max_steps: skill.max_steps, max_rounds: skill.max_rounds, status: skill.status,
    }));
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

  /** Execute a declared Skill through the bound Python domain authority. */
  async executeSkillTask({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, skill_id: skillId, skill_input: skillInput = {}, confirmed = false, include_response = false, model_prompt: modelPrompt, model } = {}) {
    if (!this.taskLedger || !this.sessionStore || !this.skillRegistry || !this.skillEngine || !this.domainBridge) throw safeError("skill_runtime_unavailable");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    if (taskId !== undefined) assertIdentifier(taskId, "task_identity_invalid");
    if (sessionId !== undefined) assertIdentifier(sessionId, "task_identity_invalid");
    assertIdentifier(skillId, "skill_identity_invalid");
    if (!skillInput || typeof skillInput !== "object" || Array.isArray(skillInput)) throw safeError("skill_input_invalid");
    if (modelPrompt !== undefined && (typeof modelPrompt !== "string" || !modelPrompt.trim() || Buffer.byteLength(modelPrompt, "utf8") > MAX_PROMPT_BYTES)) throw safeError("task_prompt_invalid");
    const skill = this.skillRegistry.manifests.find((item) => item.id === skillId);
    if (!skill) throw safeError("skill_not_found");

    const actualTaskId = taskId ?? `pi_task_${sha256(idempotencyKey).slice(0, 24)}`;
    const actualSessionId = sessionId ?? `pi_session_${sha256(`${idempotencyKey}:session`).slice(0, 24)}`;
    const inputChecksum = sha256({ skill_id: skill.id, skill_input: skillInput });
    const inputRef = { kind: "artifact", ref: `skill-input:${inputChecksum.slice(0, 32)}`, checksum: inputChecksum };
    let accepted;
    try {
      accepted = this.taskLedger.enqueue({ task_id: actualTaskId, idempotency_key: idempotencyKey, input_ref: inputRef });
    } catch (error) {
      if (error instanceof TaskLedgerError) throw safeError(error.code);
      throw safeError("task_enqueue_failed");
    }
    if (accepted.duplicate) {
      const result = { duplicate: true, task: accepted.task, session_id: actualSessionId, route: "skill", skill_id: skill.id, provider_calls: this.providerCalls };
      if (include_response) {
        const cached = this.ephemeralResponses.get(actualTaskId);
        if (!cached) throw safeError("skill_response_unavailable");
        result.response = cached;
      }
      return result;
    }

    this.runtimeControl.register({
      operation_id: `op:task:${actualTaskId}`, operation_kind: "kernel_skill", task_id: actualTaskId, session_id: actualSessionId,
      correlation_id: actualTaskId, idempotency_key: idempotencyKey, authority_class: "authority:kernel", side_effect_class: "mutation",
      snapshot_id: "snapshot:kernel", budget: { timeout_ms: skill.timeout_ms }, reason: "skill_accepted",
    });

    try {
      if (!this.sessionStore.get(actualSessionId)) this.sessionStore.create({ session_id: actualSessionId, trajectory: [] });
      const acceptedEvent = this.#appendLifecycle("task_accepted", { taskId: actualTaskId, idempotencyKey, checksum: inputChecksum });
      let task = this.taskLedger.claim(actualTaskId, { owner: "pi_kernel", leaseMs: skill.timeout_ms + 5000 });
      task = this.taskLedger.transition(actualTaskId, "running", { expectedVersion: task.version, owner: "pi_kernel", event_ref: acceptedEvent.event.event_id });
      this.runtimeControl.resume({ operation_id: `op:task:${actualTaskId}`, expected_version: 0, idempotency_key: `${idempotencyKey}:running` });
      const startedEvent = this.#appendLifecycle("task_started", { taskId: actualTaskId, idempotencyKey, checksum: inputChecksum, causationId: acceptedEvent.event.event_id });
      let modelReceipt;
      if (modelPrompt !== undefined) {
        const receipt = await this.providerAdapter.generate({
          purpose: "generic_generation", model, prompt: modelPrompt, task_id: actualTaskId, session_id: actualSessionId,
          event_id: startedEvent.event.event_id, idempotency_key: `${idempotencyKey}:planner`, max_output_tokens: 256,
        });
        modelReceipt = {
          response_checksum: receipt.response_checksum, usage_checksum: receipt.usage_checksum,
          provider: receipt.telemetry.provider, model: receipt.telemetry.model,
          input_tokens: receipt.usage.input_tokens, output_tokens: receipt.usage.output_tokens,
        };
      }
      const executionContext = { preview: null, operation_id: null };
      const stepInputs = skillInput.step_inputs && typeof skillInput.step_inputs === "object" && !Array.isArray(skillInput.step_inputs)
        ? skillInput.step_inputs : {};
      const skillResult = await this.skillEngine.run({
        skill, task_id: actualTaskId, session_id: actualSessionId, idempotency_key: idempotencyKey,
        input: skillInput, confirmed: confirmed === true,
        executor: async ({ step, correlation_id: correlationId, idempotency_key: stepIdempotencyKey }) => {
          const configured = stepInputs[step.id];
          const params = configured && typeof configured === "object" && !Array.isArray(configured) ? { ...configured } : {};
          params.task_id = actualTaskId;
          params.idempotency_key = stepIdempotencyKey;
          params.binding = "pi_kernel_skill";
          if (executionContext.preview && ["ingestion.quarantine", "ingestion.commit", "snapshot.activate", "snapshot.rollback"].includes(step.tool)) {
            params.preview = executionContext.preview;
            params.idempotency_key = executionContext.preview.idempotency_key;
          }
          if (executionContext.operation_id && step.tool === "canonical.verify") params.operation_id = executionContext.operation_id;
          if (executionContext.generation_id && ["index.reconcile", "index.evaluate", "snapshot.prepare"].includes(step.tool) && params.generation_id === undefined) params.generation_id = executionContext.generation_id;
          const toolInputChecksum = sha256({ operation: step.tool, task_id: actualTaskId, correlation_id: correlationId });
          this.#appendLifecycle("tool_started", { taskId: actualTaskId, idempotencyKey: stepIdempotencyKey, checksum: toolInputChecksum, causationId: startedEvent.event.event_id });
          try {
            const result = await this.domainBridge.invoke(step.tool, params);
            const data = result?.data ?? result;
            const candidatePreview = data?.preview_checksum ? data : data?.preview;
            if (candidatePreview?.preview_checksum) {
              const { capability_checksum: _capabilityChecksum, ...preview } = candidatePreview;
              executionContext.preview = preview;
            }
          if (data?.operation_id) executionContext.operation_id = data.operation_id;
            if (data?.generation_id) executionContext.generation_id = data.generation_id;
            const resultChecksum = sha256(data);
            this.#appendLifecycle("tool_completed", { taskId: actualTaskId, idempotencyKey: stepIdempotencyKey, checksum: resultChecksum, causationId: startedEvent.event.event_id });
            return { receipt: { tool: step.tool, status: result.status ?? "success", data } };
          } catch (error) {
            this.#appendLifecycle("tool_failed", { taskId: actualTaskId, idempotencyKey: stepIdempotencyKey, checksum: sha256(error?.code ?? "domain_unavailable"), causationId: startedEvent.event.event_id });
            throw error;
          }
        },
      });
      const report = {
        schema: "pi_skill_report_v1", skill_id: skill.id, skill_checksum: skill.checksum, state: skillResult.state,
        task_id: actualTaskId, session_id: actualSessionId,
        steps: skillResult.steps.map((step) => ({ step_id: step.step_id, tool: step.tool, status: step.status, receipt: step.receipt ?? null, error_code: step.error_code ?? null })),
        checkpoint: skillResult.checkpoint ?? null, error_code: skillResult.error_code ?? null,
        ...(modelReceipt ? { model_receipt: modelReceipt } : {}),
      };
      const reportChecksum = sha256(report);
      this.ephemeralResponses.set(actualTaskId, report);
      this.sessionStore.append(actualSessionId, { kind: "skill_receipt", task_id: actualTaskId, skill_id: skill.id, report_checksum: reportChecksum, state: skillResult.state }, { receipt: { kind: "skill", task_id: actualTaskId, skill_id: skill.id, report_checksum: reportChecksum } });
      if (skillResult.state === "completed") {
        const completedEvent = this.#appendLifecycle("task_completed", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "succeeded", { expectedVersion: task.version, owner: "pi_kernel", output_ref: artifactRef(reportChecksum), event_ref: completedEvent.event.event_id });
        this.runtimeControl._transition({ operationId: `op:task:${actualTaskId}`, expectedVersion: 1, idempotencyKey: `${idempotencyKey}:succeeded`, nextState: "succeeded", reason: "skill_completed", receiptRefs: [{ ref: `skill:${reportChecksum.slice(0, 32)}`, checksum: reportChecksum }] });
      } else if (skillResult.state === "outcome_unknown") {
        const errorEvent = this.#appendLifecycle("error", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "outcome_unknown", { expectedVersion: task.version, owner: "pi_kernel", error_code: "outcome_unknown", event_ref: errorEvent.event.event_id });
      } else if (skillResult.state === "failed") {
        const failedEvent = this.#appendLifecycle("task_failed", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "failed", { expectedVersion: task.version, owner: "pi_kernel", error_code: skillResult.error_code ?? "skill_failed", event_ref: failedEvent.event.event_id });
      }
      const result = {
        duplicate: false, task, session_id: actualSessionId, route: "skill", skill_id: skill.id,
        skill_state: skillResult.state, skill_steps: report.steps.map(({ step_id, tool, status, error_code }) => ({ step_id, tool, status, error_code })),
        receipt: { report_checksum: reportChecksum, completed_steps: report.steps.filter((step) => step.status === "committed").length, total_steps: report.steps.length },
        provider_calls: this.providerCalls,
      };
      if (include_response) result.response = report;
      return result;
    } catch (error) {
      const code = error?.code || "skill_execution_failed";
      const task = this.taskLedger.get(actualTaskId);
      if (task && !["succeeded", "failed", "outcome_unknown"].includes(task.state)) {
        const next = code === "outcome_unknown" ? "outcome_unknown" : "failed";
        try { this.taskLedger.transition(actualTaskId, next, { expectedVersion: task.version, owner: "pi_kernel", error_code: code }); } catch { /* preserve terminal evidence when possible */ }
      }
      if (error instanceof KernelHostError) throw error;
      throw safeError(code);
    }
  }

  /** Execute one task through the Pi-owned adapter. The raw prompt remains in memory. */
  async executeTask({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, purpose = "structured_analysis", model, prompt, model_prompt: modelPrompt, skill_id: skillId, skill_input: skillInput, confirmed = false, include_response = false } = {}) {
    if (skillId) return this.executeSkillTask({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, skill_id: skillId, skill_input: skillInput, confirmed, include_response, model_prompt: modelPrompt, model });
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

    this.runtimeControl.register({
      operation_id: `op:task:${actualTaskId}`, operation_kind: "kernel_task", task_id: actualTaskId, session_id: actualSessionId,
      correlation_id: actualTaskId, idempotency_key: idempotencyKey, authority_class: "authority:kernel", side_effect_class: "mutation",
      snapshot_id: "snapshot:kernel", budget: { timeout_ms: route.timeout_ms }, reason: "task_accepted",
    });

    try {
      if (!this.sessionStore.get(actualSessionId)) this.sessionStore.create({ session_id: actualSessionId, trajectory: [] });
      const acceptedEvent = this.#appendLifecycle("task_accepted", { taskId: actualTaskId, idempotencyKey, checksum: promptChecksum });
      let task = this.taskLedger.claim(actualTaskId, { owner: "pi_kernel", leaseMs: route.timeout_ms + 5000 });
      task = this.taskLedger.transition(actualTaskId, "running", { expectedVersion: task.version, owner: "pi_kernel", event_ref: acceptedEvent.event.event_id });
      this.runtimeControl.resume({ operation_id: `op:task:${actualTaskId}`, expected_version: 0, idempotency_key: `${idempotencyKey}:running` });
      const startedEvent = this.#appendLifecycle("task_started", { taskId: actualTaskId, idempotencyKey, checksum: promptChecksum, causationId: acceptedEvent.event.event_id });
      const receipt = await this.providerAdapter.generate({ purpose, model: route.model, prompt, task_id: actualTaskId, session_id: actualSessionId, event_id: startedEvent.event.event_id, idempotency_key: idempotencyKey, max_output_tokens: route.max_output_tokens });
      const responseChecksum = receipt.response_checksum;
      this.ephemeralResponses.set(actualTaskId, receipt.response);
      this.sessionStore.append(actualSessionId, { kind: "model_receipt", task_id: actualTaskId, route_checksum: receipt.route_checksum, response_checksum: responseChecksum, usage_checksum: receipt.usage_checksum, status: receipt.telemetry.status }, { receipt: { kind: "model", task_id: actualTaskId, response_checksum: responseChecksum, route_checksum: receipt.route_checksum, usage_checksum: receipt.usage_checksum } });
      const completedEvent = this.#appendLifecycle("task_completed", { taskId: actualTaskId, idempotencyKey, checksum: responseChecksum, causationId: startedEvent.event.event_id });
      task = this.taskLedger.transition(actualTaskId, "succeeded", { expectedVersion: task.version, owner: "pi_kernel", output_ref: artifactRef(responseChecksum), event_ref: completedEvent.event.event_id });
      this.runtimeControl._transition({ operationId: `op:task:${actualTaskId}`, expectedVersion: 1, idempotencyKey: `${idempotencyKey}:succeeded`, nextState: "succeeded", reason: "task_completed", receiptRefs: [{ ref: `provider:${responseChecksum.slice(0, 32)}`, checksum: responseChecksum }] });
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
        try { this.runtimeControl._transition({ operationId: `op:task:${actualTaskId}`, expectedVersion: 1, idempotencyKey: `${idempotencyKey}:${next}`, nextState: unknown ? "outcome_unknown" : "failed", reason: code }); } catch { /* retain task truth if operation journal is unavailable */ }
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

  /**
   * Execute one real Pi-owned conversation turn. The per-turn session owns the
   * iterative tool loop via `runConversationTurn`; this host binds durable
   * Task/Session/Event ledger semantics, the exact checksum-bound Conversation
   * lease, and the lease-scoped domain bridge. This path never invokes
   * `providerAdapter.generate()` or `SkillEngine.run()` as a second outer agent
   * loop.
   */
  async executeConversationTurn({ task_id: taskId, session_id: sessionId, idempotency_key: idempotencyKey, skill_id: skillId, prompt, scope = null, binding = null } = {}) {
    if (!this.taskLedger || !this.sessionStore || !this.skillRegistry || !this.conversationSessionFactory || !this.domainBridge) throw safeError("skill_runtime_unavailable");
    assertIdentifier(idempotencyKey, "task_identity_invalid");
    if (taskId !== undefined) assertIdentifier(taskId, "task_identity_invalid");
    if (sessionId !== undefined) assertIdentifier(sessionId, "task_identity_invalid");
    assertIdentifier(skillId, "skill_identity_invalid");
    if (typeof prompt !== "string" || !prompt.trim() || Buffer.byteLength(prompt, "utf8") > MAX_PROMPT_BYTES) throw safeError("task_prompt_invalid");
    const skill = this.skillRegistry.manifests.find((item) => item.id === skillId);
    if (!skill) throw safeError("skill_not_found");

    const lease = deriveConversationLease({ primarySkill: skill });
    if (!lease.ok) throw safeError("conversation_lease_denied");

    const actualTaskId = taskId ?? `pi_task_${sha256(idempotencyKey).slice(0, 24)}`;
    const actualSessionId = sessionId ?? `pi_session_${sha256(`${idempotencyKey}:session`).slice(0, 24)}`;
    const inputChecksum = sha256({ skill_id: skill.id, prompt });
    const inputRef = { kind: "artifact", ref: `conversation-turn:${inputChecksum.slice(0, 32)}`, checksum: inputChecksum };
    let accepted;
    try {
      accepted = this.taskLedger.enqueue({ task_id: actualTaskId, idempotency_key: idempotencyKey, input_ref: inputRef });
    } catch (error) {
      if (error instanceof TaskLedgerError) throw safeError(error.code);
      throw safeError("task_enqueue_failed");
    }
    if (accepted.duplicate) {
      return { duplicate: true, ok: true, task: accepted.task, session_id: actualSessionId, route: "conversation", turn: null, provider_calls: this.providerCalls };
    }

    const leaseBridge = this.domainBridgeOptions
      ? createProjectDomainBridge({ ...this.domainBridgeOptions, operations: lease.active_tool_names })
      : this.domainBridge;
    const leaseOperations = (this.capabilityRegistry?.operations ?? [])
      .filter((operation) => lease.active_tool_names.includes(operation.id))
      .map((operation) => ({ ...operation }));

    this.runtimeControl.register({
      operation_id: `op:task:${actualTaskId}`, operation_kind: "kernel_session", task_id: actualTaskId, session_id: actualSessionId,
      correlation_id: actualTaskId, idempotency_key: idempotencyKey, authority_class: "authority:kernel", side_effect_class: "none",
      snapshot_id: "snapshot:kernel", budget: { timeout_ms: skill.timeout_ms }, reason: "conversation_turn_accepted",
    });

    let turnContext = null;
    try {
      if (!this.sessionStore.get(actualSessionId)) this.sessionStore.create({ session_id: actualSessionId, trajectory: [] });
      const acceptedEvent = this.#appendLifecycle("task_accepted", { taskId: actualTaskId, idempotencyKey, checksum: inputChecksum });
      let task = this.taskLedger.claim(actualTaskId, { owner: "pi_kernel", leaseMs: skill.timeout_ms + 5000 });
      task = this.taskLedger.transition(actualTaskId, "running", { expectedVersion: task.version, owner: "pi_kernel", event_ref: acceptedEvent.event.event_id });
      this.runtimeControl.resume({ operation_id: `op:task:${actualTaskId}`, expected_version: 0, idempotency_key: `${idempotencyKey}:running` });
      const startedEvent = this.#appendLifecycle("task_started", { taskId: actualTaskId, idempotencyKey, checksum: inputChecksum, causationId: acceptedEvent.event.event_id });

      turnContext = await this.conversationSessionFactory({
        cwd: this.cwd,
        agentDir: this.agentDir,
        operations: leaseOperations,
        bridge: leaseBridge,
        invokeTool: (operation, params) => leaseBridge.invoke(operation, params),
      });
      if (!turnContext?.session) throw safeError("conversation_session_unavailable");
      // Plan 61-09: a real turn with an approved scope/binding asks the fixed
      // read-only projection provider before prompt; an unavailable or
      // incompatible projection is omitted (never blocks the turn).
      const turnScope = typeof scope === "string" && scope ? scope : null;
      const turnBinding = typeof binding === "string" && binding ? binding : "pi_kernel_conversation_turn";
      const projectionProvider = turnScope
        ? (opts) => this.domainBridge.invoke(MODEL_PROJECTION_OPERATION, {
            scope: opts.scope,
            binding: opts.binding,
            task_id: actualTaskId,
            idempotency_key: `${idempotencyKey}:projection`,
          })
        : null;
      const result = await runConversationTurn({
        session: turnContext.session,
        prompt,
        activeToolNames: lease.active_tool_names,
        profile: "conversation",
        taskId: actualTaskId,
        sessionId: actualSessionId,
        idempotencyKey,
        skillId: skill.id,
        skillChecksum: skill.checksum,
        scope: turnScope,
        binding: turnBinding,
        modelProjectionProvider: projectionProvider,
        timeoutMs: skill.timeout_ms,
      });
      const turn = result.turn;
      const report = {
        schema: "pi_conversation_turn_v1",
        task_id: actualTaskId,
        session_id: actualSessionId,
        skill_id: skill.id,
        skill_checksum: skill.checksum,
        profile: turn.profile,
        state: turn.state,
        success: turn.success,
        tool_count: turn.receipts.tool_count,
      };
      const reportChecksum = sha256(report);
      this.sessionStore.append(actualSessionId, { kind: "conversation_receipt", task_id: actualTaskId, skill_id: skill.id, report_checksum: reportChecksum, state: turn.state }, { receipt: { kind: "conversation", task_id: actualTaskId, skill_id: skill.id, report_checksum: reportChecksum, state: turn.state } });

      if (turn.state === "settled") {
        const completedEvent = this.#appendLifecycle("task_completed", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "succeeded", { expectedVersion: task.version, owner: "pi_kernel", output_ref: artifactRef(reportChecksum), event_ref: completedEvent.event.event_id });
        this.runtimeControl._transition({ operationId: `op:task:${actualTaskId}`, expectedVersion: 1, idempotencyKey: `${idempotencyKey}:succeeded`, nextState: "succeeded", reason: "conversation_settled", receiptRefs: [{ ref: `conversation:${reportChecksum.slice(0, 32)}`, checksum: reportChecksum }] });
      } else if (turn.state === "cancelled") {
        const cancelEvent = this.#appendLifecycle("task_cancel_requested", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "cancel_requested", { expectedVersion: task.version, owner: "pi_kernel", event_ref: cancelEvent.event.event_id });
        this.runtimeControl.cancel({ operation_id: `op:task:${actualTaskId}`, expected_version: 1, idempotency_key: `${idempotencyKey}:cancelled` });
      } else if (turn.state === "outcome_unknown") {
        const errorEvent = this.#appendLifecycle("error", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "outcome_unknown", { expectedVersion: task.version, owner: "pi_kernel", error_code: "outcome_unknown", event_ref: errorEvent.event.event_id });
        this.runtimeControl._transition({ operationId: `op:task:${actualTaskId}`, expectedVersion: 1, idempotencyKey: `${idempotencyKey}:outcome_unknown`, nextState: "outcome_unknown", reason: "conversation_outcome_unknown" });
      } else {
        const failedEvent = this.#appendLifecycle("task_failed", { taskId: actualTaskId, idempotencyKey, checksum: reportChecksum, causationId: startedEvent.event.event_id });
        task = this.taskLedger.transition(actualTaskId, "failed", { expectedVersion: task.version, owner: "pi_kernel", error_code: "conversation_failed", event_ref: failedEvent.event.event_id });
      }

      return {
        duplicate: false,
        ok: true,
        task,
        session_id: actualSessionId,
        route: "conversation",
        turn: { ...turn, task_id: actualTaskId, session_id: actualSessionId },
        provider_calls: this.providerCalls,
      };
    } catch (error) {
      if (turnContext?.session) {
        try { turnContext.session.dispose(); } catch { /* bounded disposal continues */ }
      }
      const code = error?.code || "conversation_turn_failed";
      const task = this.taskLedger.get(actualTaskId);
      if (task && !["succeeded", "failed", "outcome_unknown"].includes(task.state)) {
        try { this.taskLedger.transition(actualTaskId, "failed", { expectedVersion: task.version, owner: "pi_kernel", error_code: code }); } catch { /* preserve terminal evidence when possible */ }
      }
      if (error instanceof KernelHostError) throw error;
      throw safeError(code);
    }
  }

  /**
   * Named `conversation.session.create`: validate sender/schema, request an
   * approved project scope through the Python canonical
   * `conversation.project_scope.select` provider, then persist only governed
   * empty Session metadata plus an empty safe ConversationThreadView. This path
   * never writes canonical conversation bodies, Candidate, promotion, active
   * pointer or desktop persistence, and never invokes providerAdapter.generate()
   * or SkillEngine.run() as a conversation authority.
   */
  async createConversationSession(payload = {}) {
    if (!this.sessionStore || !this.domainBridge) throw safeError("session_runtime_unavailable");
    try {
      return await createConversationSession({
        sessionStore: this.sessionStore,
        domainBridge: this.domainBridge,
        session_id: payload.session_id,
        project_scope_id: payload.project_scope_id,
        idempotency_key: payload.idempotency_key,
        binding: payload.binding,
      });
    } catch (error) {
      if (error instanceof SessionServiceError) throw safeError(error.code);
      throw error;
    }
  }

  /**
   * Fixed `candidate.review` binding (Plan 61-08 / HARNESS-06): field-level
   * validate the exact review request shape, then dispatch ONLY
   * `candidate.review` to the bound Gateway bridge. Private/override/batch
   * fields are rejected before dispatch so the bridge is never reached with
   * an endpoint/path/provider override; the returned envelope is metadata-only
   * and never journals a canonical/promotion/rollback claim.
   */
  async reviewCandidate(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) throw safeError("review_request_invalid");
    for (const key of Object.keys(payload)) {
      if (!CANDIDATE_REVIEW_ALLOWED_FIELDS.has(key)) throw safeError("undeclared_input");
    }
    if (typeof payload.candidate_id !== "string" || !payload.candidate_id) throw safeError("review_request_invalid");
    if (!CANDIDATE_REVIEW_ACTIONS.has(payload.action)) throw safeError("action_unknown");
    if (!Number.isInteger(payload.expected_version) || payload.expected_version < 1) throw safeError("review_request_invalid");
    if (typeof payload.idempotency_key !== "string" || !payload.idempotency_key) throw safeError("idempotency_key_required");
    if (payload.binding === null || payload.binding === undefined || (typeof payload.binding !== "string" && typeof payload.binding !== "object")) throw safeError("binding_required");
    const result = await this.domainBridge.invoke("candidate.review", payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...(result.data ?? result) };
  }

  /**
   * Fixed `personal.model_projection.get` binding (Plan 61-09 / HARNESS-07):
   * field-level validate the exact projection request shape, then dispatch ONLY
   * `personal.model_projection.get` to the bound Gateway bridge. Private/
   * override fields are rejected before dispatch so the bridge is never reached
   * with an endpoint/path/provider override; the returned envelope is
   * metadata-only and never claims a canonical/promotion/rollback/watermark/
   * active-pointer authority change.
   */
  async getModelProjection(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    if (payload === null || typeof payload !== "object" || Array.isArray(payload)) throw safeError("projection_request_invalid");
    for (const key of Object.keys(payload)) {
      if (!MODEL_PROJECTION_ALLOWED_FIELDS.has(key)) throw safeError("undeclared_input");
    }
    if (typeof payload.scope !== "string" || !payload.scope) throw safeError("scope_identity_invalid");
    if (typeof payload.idempotency_key !== "string" || !payload.idempotency_key) throw safeError("idempotency_key_required");
    if (payload.binding === null || payload.binding === undefined || (typeof payload.binding !== "string" && typeof payload.binding !== "object")) throw safeError("binding_required");
    const result = await this.domainBridge.invoke(MODEL_PROJECTION_OPERATION, payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...sanitizeProjectionEnvelope(result.data ?? result) };
  }

  /**
   * Fixed `proactive.state.get` binding (Plan 61-10 / HARNESS-05): field-level
   * validate the exact deterministic state request shape (scope, events,
   * controls, quiet_hours, now, manual_order, binding, idempotency), then
   * dispatch ONLY `proactive.state.get` to the bound Gateway bridge. Private/
   * override fields, schedule/permission/value/canonical commands and malformed
   * scope/now/events/quiet-hours are rejected before dispatch; the returned
   * envelope is no-store metadata-only and never claims an authority mutation.
   */
  async getProactiveState(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    assertProactiveRequest(PROACTIVE_STATE_OPERATION, payload);
    assertProactiveScope(payload.scope);
    if (typeof payload.now !== "string" || !payload.now) throw safeError("proactive_request_invalid");
    if (!Array.isArray(payload.events)) throw safeError("proactive_request_invalid");
    assertProactiveQuietHours(payload.quiet_hours);
    const result = await this.domainBridge.invoke(PROACTIVE_STATE_OPERATION, payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...sanitizeProjectionEnvelope(result.data ?? result) };
  }

  /**
   * Fixed `proactive.controls.update` binding (Plan 61-10 / HARNESS-05):
   * validate the exact controls request shape and the exact category
   * (同步/简报/反思候选), then dispatch ONLY `proactive.controls.update` to the
   * bound Gateway bridge. Controls updates never schedule, change permissions/
   * values or write canonical/promotion/rollback/watermark/active-pointer state.
   */
  async updateProactiveControls(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    assertProactiveRequest(PROACTIVE_CONTROLS_OPERATION, payload);
    assertProactiveScope(payload.scope);
    if (!PROACTIVE_CATEGORIES.has(payload.category)) throw safeError("category_unknown");
    assertProactiveQuietHours(payload.quiet_hours);
    const result = await this.domainBridge.invoke(PROACTIVE_CONTROLS_OPERATION, payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...(result.data ?? result) };
  }

  /**
   * Fixed `proactive.dismiss` binding (Plan 61-10 / HARNESS-05): validate the
   * exact dismissal request shape (cluster_key, feedback_id, actor_identity_hash,
   * now, binding, idempotency), then dispatch ONLY `proactive.dismiss` to the
   * bound Gateway bridge. Dismissal is append-only and idempotent; it never
   * schedules or mutates authority state.
   */
  async dismissProactive(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    assertProactiveRequest(PROACTIVE_DISMISS_OPERATION, payload);
    if (typeof payload.cluster_key !== "string" || !payload.cluster_key) throw safeError("proactive_request_invalid");
    if (typeof payload.feedback_id !== "string" || !payload.feedback_id) throw safeError("proactive_request_invalid");
    if (typeof payload.now !== "string" || !payload.now) throw safeError("proactive_request_invalid");
    const result = await this.domainBridge.invoke(PROACTIVE_DISMISS_OPERATION, payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...(result.data ?? result) };
  }

  /**
   * Fixed `proactive.dismiss.undo` binding (Plan 61-10 / HARNESS-05): validate
   * the exact undo request shape (dismissal_feedback_id, feedback_id,
   * actor_identity_hash, now, binding, idempotency), then dispatch ONLY
   * `proactive.dismiss.undo` to the bound Gateway bridge. Undo appends a new
   * entry and never mutates the original dismissal.
   */
  async undoProactiveDismissal(payload = {}) {
    if (!this.domainBridge) throw safeError("domain_unavailable");
    assertProactiveRequest(PROACTIVE_UNDO_OPERATION, payload);
    if (typeof payload.dismissal_feedback_id !== "string" || !payload.dismissal_feedback_id) throw safeError("proactive_request_invalid");
    if (typeof payload.feedback_id !== "string" || !payload.feedback_id) throw safeError("proactive_request_invalid");
    if (typeof payload.now !== "string" || !payload.now) throw safeError("proactive_request_invalid");
    const result = await this.domainBridge.invoke(PROACTIVE_UNDO_OPERATION, payload);
    if (result?.ok !== true) throw safeError(result?.error?.code ?? "domain_unavailable");
    return { ok: true, ...(result.data ?? result) };
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
    mode: options.providerMode ?? process.env.PI_KERNEL_PROVIDER_MODE,
    fetchImpl: options.fetchImpl,
  });
  let domainBridge = options.domainBridge;
  let hostInstance;
  try {
    const cwd = resolve(options.cwd ?? projectRoot);
    const agentDir = resolve(options.agentDir ?? resolve(projectRoot, ".pi-agent-disabled"));
    const contained = await createContainedSession({
      cwd, agentDir, profile: "production",
      invokeTool: (operation, params) => domainBridge?.invoke(operation, params),
    });
    assertExactResourcePolicy(contained.resourceLoader, contained.session, contained);
    if (contained.modelRuntime.providerCalls !== 0) throw safeError("provider_call_detected");
    const skillManifestPath = options.skillManifestPath
      ?? (existsSync(resolve(projectRoot, "governance/manifests/ai/pi-skills.json"))
        ? resolve(projectRoot, "governance/manifests/ai/pi-skills.json")
        : resolve(projectRoot, "..", "..", "governance/manifests/ai/pi-skills.json"));
    const skillRegistry = await SkillRegistry.fromFile(
      skillManifestPath,
      { allowedTools: contained.registry.operations.map((operation) => operation.id), profile: "production" },
    );
    if (skillRegistry.load().length === 0) throw safeError("skill_registry_unavailable");
    domainBridge ??= createProjectDomainBridge({
      host: process.env.PI_DOMAIN_HOST ?? "127.0.0.1",
      port: Number(process.env.PI_DOMAIN_PORT ?? 8000),
      capability: process.env.PI_DOMAIN_CAPABILITY,
      // The Phase 61 fixed Kernel routes (candidate.review, personal model
      // projection, four proactive routes) dispatch through the same bridge;
      // their named providers live in the Python PiDomainGateway registry but
      // are not Pi-tool capability operations, so union them into the default
      // allowlist or the fixed routes fail with skill_tool_escalation.
      operations: [
        ...new Set([
          ...contained.registry.operations.map((operation) => operation.id),
          "candidate.review",
          MODEL_PROJECTION_OPERATION,
          PROACTIVE_STATE_OPERATION,
          PROACTIVE_CONTROLS_OPERATION,
          PROACTIVE_DISMISS_OPERATION,
          PROACTIVE_UNDO_OPERATION,
        ]),
      ],
    });
    const domainBridgeOptions = {
      host: process.env.PI_DOMAIN_HOST ?? "127.0.0.1",
      port: Number(process.env.PI_DOMAIN_PORT ?? 8000),
      capability: process.env.PI_DOMAIN_CAPABILITY,
    };
    const defaultConversationSessionFactory = async (turnOptions = {}) => {
      const leaseOperations = turnOptions.operations ?? contained.registry.operations;
      const bridge = turnOptions.bridge ?? domainBridge;
      return conversationSessionFactory({
        cwd,
        agentDir,
        settingsManager: contained.settingsManager,
        sessionManager: contained.sessionManager,
        operations: leaseOperations,
        invokeTool: (operation, params) => bridge.invoke(operation, params),
      });
    };
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
      capabilityRegistry: contained.registry,
      runtimeControl: options.runtimeControl,
      skillRegistry,
      skillEngine: new SkillEngine({ registry: skillRegistry }),
      domainBridge,
      domainBridgeOptions,
      conversationSessionFactory: options.conversationSessionFactory ?? defaultConversationSessionFactory,
      cwd,
      agentDir,
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
