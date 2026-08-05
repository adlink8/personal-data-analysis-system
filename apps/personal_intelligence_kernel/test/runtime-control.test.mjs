import test from "node:test";
import assert from "node:assert/strict";
import { KernelRuntimeControl, RuntimeControlError } from "../src/control/runtime-control.mjs";
import { OPERATION_KINDS, createOperationEnvelope, operationChecksum, validateOperationEnvelope } from "../src/control/operation-schema.mjs";

const REF = (ref, fill) => ({ ref, checksum: fill.repeat(64) });
function input(overrides = {}) {
  return {
    operation_kind: "domain_tool", task_id: "task:59", session_id: "session:59", correlation_id: "corr:59", idempotency_key: "idem:59",
    authority_class: "authority:python", snapshot_id: "snapshot:59", side_effect_class: "mutation", ...overrides,
  };
}

test("strict operation envelope covers every coordinator plane and is metadata-only", () => {
  for (const operation_kind of OPERATION_KINDS) {
    const operation = createOperationEnvelope(input({ operation_kind }));
    assert.equal(validateOperationEnvelope(operation).checksum, operation.checksum);
    assert.equal(operationChecksum(operation), operation.checksum);
  }
  assert.throws(() => createOperationEnvelope(input({ prompt: "secret" })), /forbidden_inline_field/);
});

test("reducer rejects stale and illegal transitions while duplicate commands replay", () => {
  const control = new KernelRuntimeControl(); const operation = control.register(input());
  const started = control.resume({ operation_id: operation.operation_id, expected_version: 0, idempotency_key: "resume:1" });
  assert.equal(started.operation.state, "running");
  assert.deepEqual(control.resume({ operation_id: operation.operation_id, expected_version: 0, idempotency_key: "resume:1" }), started);
  assert.throws(() => control.cancel({ operation_id: operation.operation_id, expected_version: 0, idempotency_key: "cancel:stale" }), /stale_expected_version/);
  assert.equal(control.resume({ operation_id: operation.operation_id, expected_version: 1, idempotency_key: "resume:2" }).action, "resume_noop");
  const cancelled = control.cancel({ operation_id: operation.operation_id, expected_version: 1, idempotency_key: "cancel:1" });
  assert.equal(cancelled.operation.state, "cancel_requested");
  assert.equal(control.journal().filter((event) => event.type.startsWith("operation_")).length, 3);
});

test("outcome_unknown reconciles receipt and fingerprint before retry", () => {
  const control = new KernelRuntimeControl(); const operation = control.register(input({ idempotency_key: "idem:unknown" }));
  control.resume({ operation_id: operation.operation_id, expected_version: 0, idempotency_key: "resume:unknown" });
  const unknown = control._transition({ operationId: operation.operation_id, expectedVersion: 1, idempotencyKey: "unknown:1", nextState: "outcome_unknown", reason: "provider_timeout" });
  assert.equal(unknown.operation.state, "outcome_unknown");
  assert.throws(() => control.resume({ operation_id: operation.operation_id, expected_version: 2, idempotency_key: "resume:blind" }), /reconcile_before_resume/);
  const reconciled = control.reconcile({ operation_id: operation.operation_id, expected_version: 2, idempotency_key: "reconcile:1", receipt_refs: [REF("receipt:1", "a")], fingerprint_refs: [REF("fingerprint:1", "b")], receipt_status: "succeeded" });
  assert.equal(reconciled.operation.state, "succeeded"); assert.equal(reconciled.retry_allowed, false); assert.equal(reconciled.reconciled_before_retry, true);
});

test("missing reconciliation evidence resolves to manual_review without side effect retry", () => {
  const control = new KernelRuntimeControl(); const operation = control.register(input({ idempotency_key: "idem:manual" }));
  control.resume({ operation_id: operation.operation_id, expected_version: 0, idempotency_key: "resume:manual" });
  control._transition({ operationId: operation.operation_id, expectedVersion: 1, idempotencyKey: "unknown:manual", nextState: "outcome_unknown", reason: "authority_timeout" });
  const result = control.reconcile({ operation_id: operation.operation_id, expected_version: 2, idempotency_key: "reconcile:manual" });
  assert.equal(result.operation.state, "manual_review"); assert.equal(result.retry_allowed, false);
});
