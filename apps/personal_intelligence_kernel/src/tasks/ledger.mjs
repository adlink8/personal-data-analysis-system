import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";

export const PI_KERNEL_TASKS_DB = "var/db/pi_kernel_tasks.sqlite";
export const TASK_STATES = Object.freeze(["queued", "claimed", "running", "cancel_requested", "succeeded", "failed", "outcome_unknown"]);
export const TERMINAL_TASK_STATES = Object.freeze(["succeeded", "failed", "outcome_unknown"]);
const MIGRATION_ID = "001_pi_kernel_tasks_v1";
const MIGRATION_SQL = `
CREATE TABLE IF NOT EXISTS pi_kernel_tasks (
  task_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('queued','claimed','running','cancel_requested','succeeded','failed','outcome_unknown')),
  version INTEGER NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  idempotency_key TEXT NOT NULL UNIQUE,
  input_ref TEXT NOT NULL,
  output_ref TEXT,
  event_ref TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pi_kernel_tasks_lease ON pi_kernel_tasks(state, lease_expires_at);
CREATE TABLE IF NOT EXISTS pi_kernel_task_outbox (
  outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id TEXT NOT NULL REFERENCES pi_kernel_tasks(task_id),
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS pi_kernel_migrations (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, migration_checksum TEXT NOT NULL, applied_at TEXT NOT NULL
);`;

// Bounded response reports backing include_response replay. Kept as a second
// migration (mirroring events/journal.mjs) so existing v1 task ledgers stay
// valid while gaining the persistent response store.
const RESPONSES_MIGRATION_ID = "002_pi_kernel_task_responses_v1";
const RESPONSES_SCHEMA_VERSION = "pi_kernel_task_responses_v1";
const RESPONSES_MIGRATION_SQL = `
CREATE TABLE IF NOT EXISTS pi_kernel_task_responses (
  task_id TEXT PRIMARY KEY REFERENCES pi_kernel_tasks(task_id),
  response_json TEXT NOT NULL,
  response_checksum TEXT NOT NULL,
  created_at TEXT NOT NULL
);`;
// Responses are small JSON reports; oversized payloads are never persisted so
// replay fails closed with the unchanged provider/skill_response_unavailable
// contract instead of growing the ledger without bound.
const MAX_RESPONSE_BYTES = 1024 * 1024;

const checksum = (value) => createHash("sha256").update(value).digest("hex");
const nowIso = () => new Date().toISOString();
const json = (value) => JSON.stringify(value ?? null);
const parseJson = (value) => value == null ? null : JSON.parse(value);

export class TaskLedgerError extends Error {
  constructor(code, message = code) { super(message); this.name = "TaskLedgerError"; this.code = code; }
}

const allowedTransitions = Object.freeze({
  queued: new Set(["claimed", "cancel_requested"]),
  claimed: new Set(["running", "queued", "cancel_requested", "outcome_unknown"]),
  running: new Set(["succeeded", "failed", "cancel_requested", "outcome_unknown"]),
  cancel_requested: new Set(["failed", "outcome_unknown"]),
  succeeded: new Set(), failed: new Set(), outcome_unknown: new Set(["succeeded", "failed"]),
});

function rowToTask(row) {
  if (!row) return null;
  return {
    task_id: row.task_id, state: row.state, version: Number(row.version),
    lease_owner: row.lease_owner, lease_expires_at: row.lease_expires_at,
    idempotency_key: row.idempotency_key, input_ref: parseJson(row.input_ref),
    output_ref: parseJson(row.output_ref), event_ref: row.event_ref,
    error_code: row.error_code, created_at: row.created_at, updated_at: row.updated_at,
  };
}

export class TaskLedger {
  constructor(databasePath = PI_KERNEL_TASKS_DB) {
    this.databasePath = resolve(databasePath);
    mkdirSync(dirname(this.databasePath), { recursive: true });
    this.db = new DatabaseSync(this.databasePath);
    this.closed = false;
    this.db.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;");
    this.#migrate();
  }
  #open() { if (this.closed) throw new TaskLedgerError("ledger_closed"); }
  #migrate() {
    const migrationChecksum = checksum(MIGRATION_SQL);
    this.db.exec(MIGRATION_SQL);
    const row = this.db.prepare("SELECT * FROM pi_kernel_migrations WHERE id=?").get(MIGRATION_ID);
    if (row && (row.schema_version !== "pi_kernel_tasks_v1" || row.migration_checksum !== migrationChecksum)) throw new TaskLedgerError("migration_checksum_mismatch");
    if (!row) this.db.prepare("INSERT INTO pi_kernel_migrations VALUES (?, ?, ?, ?)").run(MIGRATION_ID, "pi_kernel_tasks_v1", migrationChecksum, nowIso());
    const responsesChecksum = checksum(RESPONSES_MIGRATION_SQL);
    this.db.exec(RESPONSES_MIGRATION_SQL);
    const responsesRow = this.db.prepare("SELECT * FROM pi_kernel_migrations WHERE id=?").get(RESPONSES_MIGRATION_ID);
    if (responsesRow && (responsesRow.schema_version !== RESPONSES_SCHEMA_VERSION || responsesRow.migration_checksum !== responsesChecksum)) throw new TaskLedgerError("migration_checksum_mismatch");
    if (!responsesRow) this.db.prepare("INSERT INTO pi_kernel_migrations VALUES (?, ?, ?, ?)").run(RESPONSES_MIGRATION_ID, RESPONSES_SCHEMA_VERSION, responsesChecksum, nowIso());
  }
  enqueue({ task_id, idempotency_key, input_ref = {}, now = nowIso(), event_ref = null } = {}) {
    this.#open();
    if (!task_id || !idempotency_key) throw new TaskLedgerError("missing_identity");
    const existing = this.db.prepare("SELECT * FROM pi_kernel_tasks WHERE idempotency_key=?").get(idempotency_key);
    if (existing) {
      if (existing.task_id !== task_id || existing.input_ref !== json(input_ref)) throw new TaskLedgerError("idempotency_conflict");
      return { duplicate: true, task: rowToTask(existing) };
    }
    this.db.prepare("INSERT INTO pi_kernel_tasks(task_id,state,version,idempotency_key,input_ref,event_ref,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)").run(task_id, "queued", 1, idempotency_key, json(input_ref), event_ref, now, now);
    return { duplicate: false, task: this.get(task_id) };
  }
  create(input) { return this.enqueue(input); }
  get(taskId) { this.#open(); return rowToTask(this.db.prepare("SELECT * FROM pi_kernel_tasks WHERE task_id=?").get(taskId)); }
  list({ state } = {}) { this.#open(); const rows = state ? this.db.prepare("SELECT * FROM pi_kernel_tasks WHERE state=? ORDER BY created_at,task_id").all(state) : this.db.prepare("SELECT * FROM pi_kernel_tasks ORDER BY created_at,task_id").all(); return rows.map(rowToTask); }
  claim(taskId, { owner, leaseMs = 30000, now = nowIso() } = {}) {
    this.#open(); if (!owner) throw new TaskLedgerError("missing_lease_owner");
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const row = this.db.prepare("SELECT * FROM pi_kernel_tasks WHERE task_id=?").get(taskId);
      if (!row) throw new TaskLedgerError("task_not_found");
      const expired = !row.lease_expires_at || Date.parse(row.lease_expires_at) <= Date.parse(now);
      if (row.state !== "queued" && !(row.state === "claimed" && expired)) throw new TaskLedgerError("task_busy");
      const lease = new Date(Date.parse(now) + leaseMs).toISOString();
      this.db.prepare("UPDATE pi_kernel_tasks SET state='claimed',version=version+1,lease_owner=?,lease_expires_at=?,updated_at=? WHERE task_id=? AND version=?").run(owner, lease, now, taskId, row.version);
      this.db.exec("COMMIT"); return this.get(taskId);
    } catch (error) { try { this.db.exec("ROLLBACK"); } catch {} if (error instanceof TaskLedgerError) throw error; throw new TaskLedgerError("claim_failed"); }
  }
  transition(taskId, nextState, { expectedVersion, owner, output_ref, error_code, now = nowIso(), event_ref } = {}) {
    this.#open(); if (!TASK_STATES.includes(nextState)) throw new TaskLedgerError("invalid_state");
    const row = this.db.prepare("SELECT * FROM pi_kernel_tasks WHERE task_id=?").get(taskId);
    if (!row) throw new TaskLedgerError("task_not_found");
    if (expectedVersion != null && Number(expectedVersion) !== Number(row.version)) throw new TaskLedgerError("stale_version");
    if (!allowedTransitions[row.state].has(nextState)) throw new TaskLedgerError("illegal_transition");
    if (owner && row.lease_owner && owner !== row.lease_owner) throw new TaskLedgerError("lease_owner_mismatch");
    const lease = nextState === "claimed" || nextState === "running" ? row.lease_expires_at : null;
    const result = this.db.prepare("UPDATE pi_kernel_tasks SET state=?,version=version+1,lease_expires_at=?,output_ref=?,error_code=?,event_ref=COALESCE(?,event_ref),updated_at=? WHERE task_id=? AND version=?").run(nextState, lease, output_ref === undefined ? row.output_ref : json(output_ref), error_code ?? row.error_code, event_ref ?? null, now, taskId, row.version);
    if (result.changes !== 1) throw new TaskLedgerError("stale_version");
    return this.get(taskId);
  }
  cancel(taskId, options = {}) { return this.transition(taskId, "cancel_requested", options); }
  markOutcomeUnknown(taskId, options = {}) { return this.transition(taskId, "outcome_unknown", options); }
  reconcile(taskId, { state, output_ref, error_code, now = nowIso() } = {}) {
    if (!TERMINAL_TASK_STATES.includes(state)) throw new TaskLedgerError("reconcile_requires_terminal_state");
    const task = this.get(taskId); if (!task) throw new TaskLedgerError("task_not_found");
    if (task.state !== "outcome_unknown") throw new TaskLedgerError("reconcile_not_required");
    return this.transition(taskId, state, { expectedVersion: task.version, output_ref, error_code, now });
  }
  integrityCheck() {
    this.#open(); const result = this.db.prepare("PRAGMA integrity_check").get();
    const migration = this.db.prepare("SELECT * FROM pi_kernel_migrations WHERE id=?").get(MIGRATION_ID);
    return { ok: result?.integrity_check === "ok" && Boolean(migration), integrity_check: result?.integrity_check, schema_version: migration?.schema_version ?? null, task_count: Number(this.db.prepare("SELECT COUNT(*) AS count FROM pi_kernel_tasks").get().count) };
  }
  /** Persist one bounded response report so duplicate include_response replay survives restart. */
  putResponse(taskId, response, { now = nowIso() } = {}) {
    this.#open();
    if (!taskId) throw new TaskLedgerError("missing_identity");
    const serialized = JSON.stringify(response ?? null);
    if (Buffer.byteLength(serialized, "utf8") > MAX_RESPONSE_BYTES) return { stored: false, reason: "response_too_large" };
    const responseChecksum = checksum(serialized);
    this.db.prepare("INSERT INTO pi_kernel_task_responses(task_id,response_json,response_checksum,created_at) VALUES(?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET response_json=excluded.response_json,response_checksum=excluded.response_checksum,created_at=excluded.created_at").run(taskId, serialized, responseChecksum, now);
    return { stored: true, response_checksum: responseChecksum };
  }
  /** Read back a persisted response report; null when absent (replay fails closed). */
  getResponse(taskId) {
    this.#open();
    const row = this.db.prepare("SELECT response_json FROM pi_kernel_task_responses WHERE task_id=?").get(taskId);
    return row ? JSON.parse(row.response_json) : null;
  }
  /** Drop a response-less terminal row so a replay can execute fresh (2026-08-30). */
  forget(taskId) {
    this.#open();
    this.db.prepare("DELETE FROM pi_kernel_task_outbox WHERE task_id=?").run(taskId);
    this.db.prepare("DELETE FROM pi_kernel_task_responses WHERE task_id=?").run(taskId);
    this.db.prepare("DELETE FROM pi_kernel_tasks WHERE task_id=?").run(taskId);
  }
  close() { if (!this.closed) { this.closed = true; this.db.close(); } }
  dispose() { this.close(); }
}
export const DurableTaskLedger = TaskLedger;
export function createTaskLedger(path) { return new TaskLedger(path); }
