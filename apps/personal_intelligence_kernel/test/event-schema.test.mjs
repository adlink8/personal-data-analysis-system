import test from "node:test";
import assert from "node:assert/strict";

import {
  PI_KERNEL_EVENT_TYPES,
  PiKernelSchemaError,
  canonicalEventJson,
  canonicalizeJson,
  createPiKernelEvent,
  deriveEventId,
  eventChecksum,
  normalizePiSdkEvent,
  validatePiKernelEvent,
} from "../src/events/schema.mjs";

const base = Object.freeze({
  type: "task_started",
  source: "pi_kernel",
  authority: "authority:test",
  snapshot: "snapshot:test",
  correlation_id: "corr:test",
  causation_id: null,
  idempotency_key: "idem:test:1",
  occurred_at: "2026-08-04T09:00:00.000Z",
  payload_ref: { kind: "none", ref: null, checksum: null },
  privacy_class: "R1",
});

function valid(overrides = {}) {
  return createPiKernelEvent({ ...base, ...overrides });
}

function expectCode(fn, code) {
  assert.throws(fn, (error) => error instanceof PiKernelSchemaError && error.code === code);
}

test("valid event has the exact v1 envelope and deterministic identity", () => {
  const first = valid();
  const second = valid();
  assert.deepEqual(Object.keys(first), [
    "event_id", "type", "source", "authority", "snapshot", "correlation_id",
    "causation_id", "idempotency_key", "occurred_at", "payload_ref", "privacy_class",
  ]);
  assert.equal(first.event_id, second.event_id);
  assert.equal(first.event_id, deriveEventId(first));
  assert.equal(eventChecksum(first), eventChecksum(second));
});

test("canonical JSON orders keys regardless of insertion order", () => {
  assert.equal(canonicalizeJson({ z: 1, a: { y: 2, x: 1 } }), '{"a":{"x":1,"y":2},"z":1}');
  assert.equal(canonicalEventJson(valid()), canonicalEventJson({ ...valid(), event_id: valid().event_id }));
});

test("each binding change changes event identity", () => {
  const event = valid();
  for (const field of ["type", "source", "authority", "snapshot", "correlation_id", "idempotency_key", "occurred_at", "privacy_class"]) {
    const changed = valid({ [field]: field === "type" ? "task_completed" : field === "privacy_class" ? "R2" : field === "occurred_at" ? "2026-08-04T09:00:01.000Z" : `${field}:changed` });
    assert.notEqual(changed.event_id, event.event_id, field);
  }
  assert.notEqual(valid({ causation_id: "cause:1" }).event_id, event.event_id);
  assert.notEqual(valid({ payload_ref: { kind: "artifact", ref: "artifact:1", checksum: "a".repeat(64) } }).event_id, event.event_id);
});

test("missing root field is rejected", () => {
  const event = valid();
  for (const field of ["event_id", "type", "source", "authority", "snapshot", "correlation_id", "causation_id", "idempotency_key", "occurred_at", "payload_ref", "privacy_class"]) {
    const copy = { ...event };
    delete copy[field];
    expectCode(() => validatePiKernelEvent(copy), "missing_field");
  }
});

test("unknown root key is rejected", () => {
  expectCode(() => validatePiKernelEvent({ ...valid(), unexpected: true }), "unknown_key");
});

test("inline body/content/prompt/completion keys are rejected", () => {
  for (const field of ["body", "content", "prompt", "completion", "payload", "inline_payload"]) {
    expectCode(() => validatePiKernelEvent({ ...valid(), [field]: "private" }), "unknown_key");
    expectCode(() => validatePiKernelEvent({ ...valid(), payload_ref: { kind: "artifact", ref: "x", checksum: "a".repeat(64), [field]: "private" } }), "forbidden_inline_field");
  }
});

test("invalid types and bindings are rejected", () => {
  expectCode(() => validatePiKernelEvent({ ...valid(), authority: {} }), "invalid_type");
  expectCode(() => validatePiKernelEvent({ ...valid(), snapshot: "" }), "invalid_type");
  expectCode(() => validatePiKernelEvent({ ...valid(), correlation_id: 1 }), "invalid_type");
  expectCode(() => validatePiKernelEvent({ ...valid(), occurred_at: "2026-08-04T09:00:00Z" }), "invalid_type");
  expectCode(() => validatePiKernelEvent({ ...valid(), event_id: "pi_evt_" + "0".repeat(64) }), "event_id_mismatch");
});

test("unknown event type and unsupported privacy fail closed", () => {
  assert.ok(PI_KERNEL_EVENT_TYPES.includes("tool_started"));
  expectCode(() => createPiKernelEvent({ ...base, type: "provider_private_event" }), "unknown_event_type");
  expectCode(() => createPiKernelEvent({ ...base, privacy_class: "R3" }), "privacy_class_forbidden");
  expectCode(() => createPiKernelEvent({ ...base, privacy_class: "private" }), "privacy_class_forbidden");
});

test("payload refs require metadata-only typed checksum", () => {
  expectCode(() => createPiKernelEvent({ ...base, payload_ref: { kind: "artifact", ref: "artifact:1", checksum: "short" } }), "invalid_payload_ref");
  expectCode(() => createPiKernelEvent({ ...base, payload_ref: { kind: "artifact", ref: "artifact:1", checksum: "a".repeat(64), body: "private" } }), "forbidden_inline_field");
  expectCode(() => createPiKernelEvent({ ...base, payload_ref: { kind: "none", ref: "private", checksum: null } }), "invalid_payload_ref");
});

test("SDK events normalize to project-owned metadata only", () => {
  const event = normalizePiSdkEvent({ type: "tool_execution_start", toolCallId: "sdk-private" }, {
    authority: "authority:test",
    snapshot: "snapshot:test",
    correlation_id: "corr:test",
    idempotency_key: "idem:sdk:1",
    occurred_at: base.occurred_at,
  });
  assert.equal(event.type, "tool_started");
  assert.equal(event.payload_ref.kind, "none");
  assert.deepEqual(Object.keys(event), Object.keys(base).concat("event_id").sort((a, b) => ["event_id", ...Object.keys(base)].indexOf(a) - ["event_id", ...Object.keys(base)].indexOf(b)));
  expectCode(() => normalizePiSdkEvent({ type: "message_update", content: "private" }, { ...base }), "unknown_sdk_event");
});
