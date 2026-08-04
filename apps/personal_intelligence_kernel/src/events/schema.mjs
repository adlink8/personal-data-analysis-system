import { createHash } from "node:crypto";

export const PI_KERNEL_EVENT_SCHEMA = "pi_kernel_event_v1";

export const EVENT_KEYS = Object.freeze([
  "event_id",
  "type",
  "source",
  "authority",
  "snapshot",
  "correlation_id",
  "causation_id",
  "idempotency_key",
  "occurred_at",
  "payload_ref",
  "privacy_class",
]);

const IDENTITY_KEYS = Object.freeze(EVENT_KEYS.slice(1));
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const EVENT_ID = /^pi_evt_[a-f0-9]{64}$/;
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

export const PI_KERNEL_EVENT_TYPES = Object.freeze([
  "kernel_bootstrap",
  "kernel_ready",
  "kernel_shutdown",
  "kernel_disposed",
  "task_accepted",
  "task_started",
  "task_completed",
  "task_failed",
  "task_cancel_requested",
  "task_cancelled",
  "session_started",
  "session_resumed",
  "session_forked",
  "tool_requested",
  "tool_started",
  "tool_completed",
  "tool_failed",
  "candidate_staged",
  "error",
  // Prototype-compatible lifecycle names are intentionally project-owned.
  "started",
  "completed",
  "cancelled",
  "failed",
  "candidate_created",
]);

export const PI_KERNEL_PRIVACY_CLASSES = Object.freeze(["R1", "R2"]);

const PAYLOAD_REF_KEYS = Object.freeze(["kind", "ref", "checksum"]);
const PAYLOAD_REF_KINDS = new Set([
  "none",
  "artifact",
  "candidate",
  "event",
  "session",
  "task",
  "tool",
]);

const FORBIDDEN_KEY = /^(?:body|content|prompt|completion|payload|inline_payload|input|output|result|credential|secret|token|password|path)$/i;

export class PiKernelSchemaError extends TypeError {
  constructor(code, field, message = code) {
    super(message);
    this.name = "PiKernelSchemaError";
    this.code = code;
    this.field = field;
  }
}

function fail(code, field, message = code) {
  throw new PiKernelSchemaError(code, field, message);
}

function assertRecord(value, field) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail("invalid_type", field);
  }
}

function assertIdentifier(value, field, { allowNull = false } = {}) {
  if (allowNull && value === null) return;
  if (typeof value !== "string" || !IDENTIFIER.test(value)) {
    fail("invalid_type", field);
  }
}

function assertNoForbiddenKeys(value, field = "event") {
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoForbiddenKeys(item, `${field}[${index}]`));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (FORBIDDEN_KEY.test(key)) fail("forbidden_inline_field", `${field}.${key}`);
    assertNoForbiddenKeys(child, `${field}.${key}`);
  }
}

function assertCanonicalValue(value, field = "value") {
  if (value === undefined || typeof value === "function" || typeof value === "symbol") {
    fail("invalid_type", field);
  }
  if (typeof value === "number" && !Number.isFinite(value)) fail("invalid_type", field);
  if (value && typeof value === "object") {
    if (Array.isArray(value)) value.forEach((item, index) => assertCanonicalValue(item, `${field}[${index}]`));
    else for (const [key, child] of Object.entries(value)) assertCanonicalValue(child, `${field}.${key}`);
  }
}

function sortedJson(value) {
  if (Array.isArray(value)) return `[${value.map(sortedJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${sortedJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

/** Return deterministic JSON with lexicographically ordered object keys. */
export function canonicalizeJson(value) {
  assertCanonicalValue(value);
  return sortedJson(value);
}

export function sha256(value) {
  return createHash("sha256").update(typeof value === "string" ? value : canonicalizeJson(value)).digest("hex");
}

function validatePayloadRef(value) {
  assertRecord(value, "payload_ref");
  const actual = Object.keys(value).sort();
  const expected = [...PAYLOAD_REF_KEYS].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail("unknown_key", "payload_ref");
  }
  if (typeof value.kind !== "string" || !PAYLOAD_REF_KINDS.has(value.kind)) fail("invalid_type", "payload_ref.kind");
  const isNone = value.kind === "none";
  if (isNone) {
    if (value.ref !== null || value.checksum !== null) fail("invalid_payload_ref", "payload_ref");
    return { kind: "none", ref: null, checksum: null };
  }
  assertIdentifier(value.ref, "payload_ref.ref");
  if (typeof value.checksum !== "string" || !SHA256.test(value.checksum)) fail("invalid_payload_ref", "payload_ref.checksum");
  return { kind: value.kind, ref: value.ref, checksum: value.checksum };
}

function identityObject(event) {
  return Object.fromEntries(IDENTITY_KEYS.map((key) => [key, event[key]]));
}

export function eventIdentity(event) {
  return `${PI_KERNEL_EVENT_SCHEMA}:${canonicalizeJson(identityObject(event))}`;
}

export function eventIdentityHash(event) {
  return sha256(eventIdentity(event));
}

export function deriveEventId(event) {
  return `pi_evt_${eventIdentityHash(event)}`;
}

export function deriveIdempotencyIdentity(event) {
  return sha256(`${PI_KERNEL_EVENT_SCHEMA}:idempotency:${canonicalizeJson({
    source: event.source,
    authority: event.authority,
    snapshot: event.snapshot,
    idempotency_key: event.idempotency_key,
  })}`);
}

function validateRootKeys(input) {
  assertRecord(input, "event");
  const actual = Object.keys(input).sort();
  const expected = [...EVENT_KEYS].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    const unknown = actual.find((key) => !expected.includes(key));
    fail(unknown ? "unknown_key" : "missing_field", unknown || EVENT_KEYS.find((key) => !(key in input)));
  }
}

/** Validate and return a plain project-owned event envelope. */
export function validatePiKernelEvent(input) {
  validateRootKeys(input);
  assertNoForbiddenKeys(input);

  if (typeof input.event_id !== "string" || !EVENT_ID.test(input.event_id)) fail("invalid_event_id", "event_id");
  if (typeof input.type !== "string" || !PI_KERNEL_EVENT_TYPES.includes(input.type)) fail("unknown_event_type", "type");
  assertIdentifier(input.source, "source");
  assertIdentifier(input.authority, "authority");
  assertIdentifier(input.snapshot, "snapshot");
  assertIdentifier(input.correlation_id, "correlation_id");
  assertIdentifier(input.causation_id, "causation_id", { allowNull: true });
  assertIdentifier(input.idempotency_key, "idempotency_key");
  if (typeof input.occurred_at !== "string" || !UTC_INSTANT.test(input.occurred_at) || Number.isNaN(Date.parse(input.occurred_at))) {
    fail("invalid_type", "occurred_at");
  }
  const payloadRef = validatePayloadRef(input.payload_ref);
  if (typeof input.privacy_class !== "string" || !PI_KERNEL_PRIVACY_CLASSES.includes(input.privacy_class)) {
    fail("privacy_class_forbidden", "privacy_class");
  }

  const event = {
    event_id: input.event_id,
    type: input.type,
    source: input.source,
    authority: input.authority,
    snapshot: input.snapshot,
    correlation_id: input.correlation_id,
    causation_id: input.causation_id,
    idempotency_key: input.idempotency_key,
    occurred_at: input.occurred_at,
    payload_ref: payloadRef,
    privacy_class: input.privacy_class,
  };
  const expectedEventId = deriveEventId(event);
  if (event.event_id !== expectedEventId) fail("event_id_mismatch", "event_id");
  return event;
}

/** Build a valid event from identity fields, deriving its event_id. */
export function createPiKernelEvent(input) {
  assertRecord(input, "event");
  const { event_id: suppliedEventId, ...identity } = input;
  const event = { event_id: "", ...identity };
  event.event_id = deriveEventId(event);
  if (suppliedEventId !== undefined && suppliedEventId !== event.event_id) fail("event_id_mismatch", "event_id");
  return validatePiKernelEvent(event);
}

export function canonicalEventJson(event) {
  return canonicalizeJson(validatePiKernelEvent(event));
}

export function eventChecksum(event) {
  return sha256(canonicalEventJson(event));
}

const SDK_TYPE_MAP = Object.freeze({
  agent_start: "kernel_bootstrap",
  agent_end: "kernel_shutdown",
  agent_settled: "task_completed",
  turn_start: "task_started",
  turn_end: "task_completed",
  tool_execution_start: "tool_started",
  tool_execution_end: "tool_completed",
  message_end: "session_started",
  error: "error",
});

/** Normalize only known SDK lifecycle metadata; SDK-private objects never escape. */
export function normalizePiSdkEvent(sdkEvent, context = {}) {
  assertRecord(sdkEvent, "sdk_event");
  const type = SDK_TYPE_MAP[sdkEvent.type];
  if (!type) fail("unknown_sdk_event", "sdk_event.type");
  const { authority, snapshot, correlation_id: correlationId, causation_id: causationId = null, idempotency_key: idempotencyKey, payload_ref: payloadRef = { kind: "none", ref: null, checksum: null }, occurred_at: occurredAt = new Date().toISOString(), source = "pi_kernel" } = context;
  return createPiKernelEvent({
    type,
    source,
    authority,
    snapshot,
    correlation_id: correlationId,
    causation_id: causationId,
    idempotency_key: idempotencyKey,
    occurred_at: occurredAt,
    payload_ref: payloadRef,
    privacy_class: context.privacy_class || "R1",
  });
}

export const normalizePiEvent = normalizePiSdkEvent;
