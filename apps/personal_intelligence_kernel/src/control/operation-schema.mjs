import { createHash } from "node:crypto";

export const PI_OPERATION_SCHEMA = "pi-kernel-operation-v1";
export const OPERATION_KINDS = Object.freeze([
  "kernel_task", "kernel_session", "kernel_skill", "domain_tool", "provider", "authority_transaction",
]);
export const OPERATION_STATES = Object.freeze([
  "queued", "running", "cancel_requested", "cancelled", "succeeded", "failed",
  "outcome_unknown", "reconciling", "resumable", "compensated", "manual_review",
]);
export const SIDE_EFFECT_CLASSES = Object.freeze(["none", "idempotent", "mutation"]);

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const FORBIDDEN = /^(?:body|content|prompt|completion|payload|input|output|result|credential|secret|token|password|path|command)$/i;
const ROOT_KEYS = Object.freeze([
  "schema", "operation_id", "operation_kind", "task_id", "session_id", "correlation_id", "causation_id",
  "idempotency_key", "authority_class", "side_effect_class", "snapshot_id", "state", "version", "attempt",
  "budget", "receipt_refs", "fingerprint_refs", "recovery_actions", "reason", "created_at", "updated_at", "checksum",
]);
const BUDGET_KEYS = Object.freeze(["token_limit", "cost_limit", "timeout_ms", "token_used", "cost_used"]);
const REF_KEYS = Object.freeze(["ref", "checksum"]);

export class PiOperationSchemaError extends TypeError {
  constructor(code, field, message = code) { super(message); this.name = "PiOperationSchemaError"; this.code = code; this.field = field; }
}

function fail(code, field) { throw new PiOperationSchemaError(code, field); }
function record(value, field) { if (value === null || typeof value !== "object" || Array.isArray(value)) fail("invalid_type", field); }
function id(value, field, { allowNull = false } = {}) { if (allowNull && value === null) return; if (typeof value !== "string" || !IDENTIFIER.test(value)) fail("invalid_type", field); }
function exactKeys(value, expected, field) {
  const actual = Object.keys(value).sort(); const keys = [...expected].sort();
  if (actual.length !== keys.length || actual.some((key, index) => key !== keys[index])) fail("unknown_key", field);
}
function noForbidden(value, field = "operation") {
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) { value.forEach((child, index) => noForbidden(child, `${field}[${index}]`)); return; }
  for (const [key, child] of Object.entries(value)) { if (FORBIDDEN.test(key)) fail("forbidden_inline_field", `${field}.${key}`); noForbidden(child, `${field}.${key}`); }
}
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}
function digest(value) { return createHash("sha256").update(canonical(value)).digest("hex"); }
function assertRefList(value, field) {
  if (!Array.isArray(value) || value.length > 20) fail("invalid_type", field);
  for (const [index, item] of value.entries()) {
    record(item, `${field}[${index}]`); exactKeys(item, REF_KEYS, `${field}[${index}]`);
    id(item.ref, `${field}[${index}].ref`); if (typeof item.checksum !== "string" || !SHA256.test(item.checksum)) fail("invalid_checksum", `${field}[${index}].checksum`);
  }
  return value.map((item) => ({ ref: item.ref, checksum: item.checksum }));
}

export function operationChecksum(operation) {
  const { checksum, ...unsigned } = operation;
  return digest(unsigned);
}

export function validateOperationEnvelope(input) {
  record(input, "operation"); noForbidden(input); exactKeys(input, ROOT_KEYS, "operation");
  if (input.schema !== PI_OPERATION_SCHEMA) fail("schema_mismatch", "schema");
  id(input.operation_id, "operation_id");
  if (!OPERATION_KINDS.includes(input.operation_kind)) fail("operation_kind_forbidden", "operation_kind");
  id(input.task_id, "task_id"); id(input.session_id, "session_id"); id(input.correlation_id, "correlation_id"); id(input.causation_id, "causation_id", { allowNull: true });
  id(input.idempotency_key, "idempotency_key"); id(input.authority_class, "authority_class"); id(input.snapshot_id, "snapshot_id");
  if (!SIDE_EFFECT_CLASSES.includes(input.side_effect_class)) fail("side_effect_class_forbidden", "side_effect_class");
  if (!OPERATION_STATES.includes(input.state)) fail("state_forbidden", "state");
  for (const field of ["version", "attempt"]) if (!Number.isInteger(input[field]) || input[field] < 0) fail("invalid_number", field);
  record(input.budget, "budget"); exactKeys(input.budget, BUDGET_KEYS, "budget");
  for (const field of BUDGET_KEYS) if (!Number.isInteger(input.budget[field]) || input.budget[field] < 0) fail("invalid_number", `budget.${field}`);
  const receiptRefs = assertRefList(input.receipt_refs, "receipt_refs");
  const fingerprintRefs = assertRefList(input.fingerprint_refs, "fingerprint_refs");
  if (!Array.isArray(input.recovery_actions) || input.recovery_actions.some((item) => typeof item !== "string" || !IDENTIFIER.test(item))) fail("invalid_type", "recovery_actions");
  if (typeof input.reason !== "string" || input.reason.length > 256) fail("invalid_type", "reason");
  for (const field of ["created_at", "updated_at"]) if (typeof input[field] !== "string" || !UTC_INSTANT.test(input[field])) fail("invalid_timestamp", field);
  if (typeof input.checksum !== "string" || !SHA256.test(input.checksum) || input.checksum !== operationChecksum(input)) fail("checksum_mismatch", "checksum");
  return { ...input, budget: { ...input.budget }, receipt_refs: receiptRefs, fingerprint_refs: fingerprintRefs, recovery_actions: [...input.recovery_actions] };
}

export function createOperationEnvelope(input = {}, now = new Date()) {
  noForbidden(input, "input");
  const timestamp = now.toISOString();
  const unsigned = {
    schema: PI_OPERATION_SCHEMA,
    operation_id: input.operation_id ?? `op_${digest({ operation_kind: input.operation_kind, task_id: input.task_id, session_id: input.session_id, correlation_id: input.correlation_id, idempotency_key: input.idempotency_key }).slice(0, 48)}`,
    operation_kind: input.operation_kind,
    task_id: input.task_id,
    session_id: input.session_id,
    correlation_id: input.correlation_id,
    causation_id: input.causation_id ?? null,
    idempotency_key: input.idempotency_key,
    authority_class: input.authority_class,
    side_effect_class: input.side_effect_class ?? "none",
    snapshot_id: input.snapshot_id,
    state: input.state ?? "queued",
    version: input.version ?? 0,
    attempt: input.attempt ?? 0,
    budget: { token_limit: 0, cost_limit: 0, timeout_ms: 0, token_used: 0, cost_used: 0, ...(input.budget ?? {}) },
    receipt_refs: input.receipt_refs ?? [],
    fingerprint_refs: input.fingerprint_refs ?? [],
    recovery_actions: input.recovery_actions ?? ["cancel", "resume", "reconcile"],
    reason: input.reason ?? "",
    created_at: input.created_at ?? timestamp,
    updated_at: input.updated_at ?? timestamp,
  };
  return validateOperationEnvelope({ ...unsigned, checksum: operationChecksum(unsigned) });
}

export const OPERATION_TRANSITIONS = Object.freeze({
  queued: ["running", "cancel_requested", "cancelled"],
  running: ["succeeded", "failed", "outcome_unknown", "cancel_requested", "cancelled"],
  cancel_requested: ["cancelled", "running", "outcome_unknown"],
  failed: ["resumable", "manual_review", "cancelled"],
  outcome_unknown: ["reconciling", "succeeded", "resumable", "manual_review"],
  reconciling: ["succeeded", "resumable", "compensated", "manual_review"],
  resumable: ["running", "cancelled"],
  manual_review: ["reconciling", "resumable", "cancelled"],
  succeeded: [], cancelled: [], compensated: [],
});

export function canTransition(from, to) { return OPERATION_TRANSITIONS[from]?.includes(to) === true; }
export function isTerminalState(state) { return ["succeeded", "cancelled", "compensated"].includes(state); }
