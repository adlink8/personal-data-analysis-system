import { createPiKernelEvent } from "../events/schema.mjs";
import {
  OPERATION_STATES, canTransition, createOperationEnvelope, isTerminalState, operationChecksum, validateOperationEnvelope,
} from "./operation-schema.mjs";

const nowIso = () => new Date().toISOString();

export class RuntimeControlError extends Error { constructor(code, message = code) { super(message); this.name = "RuntimeControlError"; this.code = code; } }

function sameJson(left, right) { return JSON.stringify(left) === JSON.stringify(right); }

export class KernelRuntimeControl {
  constructor({ now = new Date(), operations = [] } = {}) {
    this.now = now;
    this.operations = new Map();
    this.commands = new Map();
    this.events = [];
    for (const operation of operations) this.register(operation);
  }

  register(input) {
    const operation = validateOperationEnvelope(input.checksum ? input : createOperationEnvelope(input, this.now));
    const existing = this.operations.get(operation.operation_id);
    if (existing) {
      if (!sameJson(existing, operation)) throw new RuntimeControlError("operation_identity_conflict");
      return this.snapshot(existing);
    }
    this.operations.set(operation.operation_id, operation);
    this._event("operation_created", operation, `create:${operation.idempotency_key}`);
    return this.snapshot(operation);
  }

  get(operationId) { const operation = this.operations.get(operationId); return operation ? this.snapshot(operation) : null; }
  list() { return [...this.operations.values()].map((operation) => this.snapshot(operation)); }
  journal() { return this.events.map((event) => ({ ...event })); }
  snapshot(operation) { return JSON.parse(JSON.stringify(operation)); }

  _operation(operationId) { const operation = this.operations.get(operationId); if (!operation) throw new RuntimeControlError("operation_not_found"); return operation; }
  _commandKey(operationId, idempotencyKey) { return `${operationId}:${idempotencyKey}`; }
  _event(type, operation, idempotencyKey) {
    const event = createPiKernelEvent({
      type, source: "pi_kernel_control", authority: "authority:kernel", snapshot: operation.snapshot_id,
      correlation_id: operation.correlation_id, causation_id: operation.operation_id, idempotency_key: idempotencyKey,
      occurred_at: nowIso(), payload_ref: { kind: "event", ref: operation.operation_id, checksum: operationChecksum(operation) }, privacy_class: "R1",
    });
    this.events.push(event); return event;
  }

  _replayOrClaim(operation, idempotencyKey, expectedVersion) {
    if (!idempotencyKey) throw new RuntimeControlError("idempotency_key_required");
    const key = this._commandKey(operation.operation_id, idempotencyKey); const prior = this.commands.get(key);
    if (prior) return { prior };
    if (!Number.isInteger(expectedVersion) || expectedVersion !== operation.version) throw new RuntimeControlError("stale_expected_version");
    return { key };
  }

  _transition({ operationId, expectedVersion, idempotencyKey, nextState, reason = "", receiptRefs, fingerprintRefs, recoveryActions }) {
    const current = this._operation(operationId); const claim = this._replayOrClaim(current, idempotencyKey, expectedVersion);
    if (claim.prior) return claim.prior;
    if (!OPERATION_STATES.includes(nextState) || !canTransition(current.state, nextState)) throw new RuntimeControlError("illegal_transition");
    const updated = createOperationEnvelope({ ...current, state: nextState, version: current.version + 1, attempt: current.attempt + (nextState === "running" ? 1 : 0), reason, receipt_refs: receiptRefs ?? current.receipt_refs, fingerprint_refs: fingerprintRefs ?? current.fingerprint_refs, recovery_actions: recoveryActions ?? current.recovery_actions, updated_at: nowIso() }, this.now);
    this.operations.set(operationId, updated);
    const result = { ok: true, operation: this.snapshot(updated), action: nextState, retry_allowed: nextState === "resumable" };
    this.commands.set(claim.key, result); this._event(`operation_${nextState}`, updated, idempotencyKey);
    return result;
  }

  cancel({ operation_id: operationId, expected_version: expectedVersion, idempotency_key: idempotencyKey } = {}) {
    const current = this._operation(operationId); const prior = this.commands.get(this._commandKey(operationId, idempotencyKey)); if (prior) return prior;
    if (isTerminalState(current.state) || current.state === "cancel_requested") return { ok: true, operation: this.snapshot(current), action: "cancel_noop", retry_allowed: false };
    return this._transition({ operationId, expectedVersion, idempotencyKey, nextState: "cancel_requested", reason: "cancel_requested" });
  }

  resume({ operation_id: operationId, expected_version: expectedVersion, idempotency_key: idempotencyKey } = {}) {
    const current = this._operation(operationId);
    const prior = this.commands.get(this._commandKey(operationId, idempotencyKey));
    if (prior) return prior;
    if (current.state === "outcome_unknown") throw new RuntimeControlError("reconcile_before_resume");
    if (current.state === "running") return { ok: true, operation: this.snapshot(current), action: "resume_noop", retry_allowed: false };
    if (current.state === "succeeded" || current.state === "cancelled" || current.state === "compensated") return { ok: true, operation: this.snapshot(current), action: "resume_noop", retry_allowed: false };
    return this._transition({ operationId, expectedVersion, idempotencyKey, nextState: "running", reason: "resume_requested" });
  }

  reconcile({ operation_id: operationId, expected_version: expectedVersion, idempotency_key: idempotencyKey, receipt_refs: receiptRefs = [], fingerprint_refs: fingerprintRefs = [], receipt_status = "unknown" } = {}) {
    const current = this._operation(operationId);
    if (current.state !== "outcome_unknown") throw new RuntimeControlError("reconcile_state_required");
    if (!Array.isArray(receiptRefs) || !Array.isArray(fingerprintRefs) || receiptRefs.length === 0 || fingerprintRefs.length === 0) {
      return this._transition({ operationId, expectedVersion, idempotencyKey, nextState: "manual_review", reason: "reconciliation_evidence_required", recoveryActions: ["inspect", "compensate"] });
    }
    const nextState = receipt_status === "succeeded" ? "succeeded" : receipt_status === "retryable" ? "resumable" : "manual_review";
    const result = this._transition({ operationId, expectedVersion, idempotencyKey, nextState, reason: `reconciled:${receipt_status}`, receiptRefs, fingerprintRefs, recoveryActions: nextState === "resumable" ? ["resume", "compensate"] : ["inspect"] });
    return { ...result, retry_allowed: false, reconciled_before_retry: true };
  }
}

export const createRuntimeControl = (options) => new KernelRuntimeControl(options);
