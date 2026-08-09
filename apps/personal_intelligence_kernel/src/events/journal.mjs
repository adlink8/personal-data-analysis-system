import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  canonicalEventJson,
  CONVERSATION_DELTA_TYPE,
  deriveIdempotencyIdentity,
  eventChecksum,
  PiKernelSchemaError,
  sha256,
  validatePiKernelEvent,
} from "./schema.mjs";

export const PI_KERNEL_EVENTS_DB = "var/db/pi_kernel_events.sqlite";
export const JOURNAL_SCHEMA_VERSION = "pi_kernel_events_v1";
const MIGRATION_ID = "001_pi_kernel_events_v1";

// Plan 61-06: append-only named consumer-checkpoint history. Kept as a second
// migration so existing v1 journals stay valid while gaining the replay cursor.
export const CONSUMER_CHECKPOINTS_TABLE = "pi_kernel_consumer_checkpoints";
const CONSUMER_CHECKPOINTS_MIGRATION_ID = "002_pi_kernel_consumer_checkpoints_v1";
const CONSUMER_CHECKPOINTS_SCHEMA_VERSION = "pi_kernel_consumer_checkpoints_v1";

const MIGRATION_SQL = `
CREATE TABLE IF NOT EXISTS pi_kernel_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  idempotency_identity TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  event_json TEXT NOT NULL,
  canonical_checksum TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pi_kernel_events_occurred_at
  ON pi_kernel_events (occurred_at, sequence);

CREATE TRIGGER IF NOT EXISTS pi_kernel_events_no_update
BEFORE UPDATE ON pi_kernel_events
BEGIN
  SELECT RAISE(ABORT, 'pi_kernel_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS pi_kernel_events_no_delete
BEFORE DELETE ON pi_kernel_events
BEGIN
  SELECT RAISE(ABORT, 'pi_kernel_events is append-only');
END;
`;

const MIGRATION_CHECKSUM = sha256(MIGRATION_SQL);

const CONSUMER_CHECKPOINTS_SQL = `
CREATE TABLE IF NOT EXISTS pi_kernel_consumer_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  consumer_name TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  checksum TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pi_kernel_consumer_checkpoints_name
  ON pi_kernel_consumer_checkpoints (consumer_name, sequence);

CREATE TRIGGER IF NOT EXISTS pi_kernel_consumer_checkpoints_no_update
BEFORE UPDATE ON pi_kernel_consumer_checkpoints
BEGIN
  SELECT RAISE(ABORT, 'pi_kernel_consumer_checkpoints is append-only');
END;

CREATE TRIGGER IF NOT EXISTS pi_kernel_consumer_checkpoints_no_delete
BEFORE DELETE ON pi_kernel_consumer_checkpoints
BEGIN
  SELECT RAISE(ABORT, 'pi_kernel_consumer_checkpoints is append-only');
END;
`;

const CONSUMER_CHECKPOINTS_CHECKSUM = sha256(CONSUMER_CHECKPOINTS_SQL);

const SHA256_HEX = /^[a-f0-9]{64}$/;
const CONSUMER_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,255}$/;

export class PiKernelJournalError extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = "PiKernelJournalError";
    this.code = code;
  }
}

function nowIso() {
  return new Date().toISOString();
}

function rowToEvent(row) {
  try {
    const event = JSON.parse(row.event_json);
    validatePiKernelEvent(event);
    return event;
  } catch (error) {
    if (error instanceof PiKernelSchemaError) throw error;
    throw new PiKernelJournalError("corrupt_event_json");
  }
}

function publicRow(row) {
  const event = rowToEvent(row);
  return {
    sequence: Number(row.sequence),
    event,
    event_id: row.event_id,
    idempotency_identity: row.idempotency_identity,
    canonical_checksum: row.canonical_checksum,
    occurred_at: row.occurred_at,
    created_at: row.created_at,
  };
}

export class EventJournal {
  constructor(databasePath = PI_KERNEL_EVENTS_DB) {
    this.databasePath = resolve(databasePath);
    mkdirSync(dirname(this.databasePath), { recursive: true });
    this.db = new DatabaseSync(this.databasePath);
    this.closed = false;
    this.#configure();
    this.#migrate();
  }

  #assertOpen() {
    if (this.closed) throw new PiKernelJournalError("journal_closed");
  }

  #configure() {
    this.db.exec("PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;");
  }

  #migrate() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS pi_kernel_migrations (
        id TEXT PRIMARY KEY,
        schema_version TEXT NOT NULL,
        migration_checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL
      );
      CREATE TRIGGER IF NOT EXISTS pi_kernel_migrations_no_update
      BEFORE UPDATE ON pi_kernel_migrations
      BEGIN SELECT RAISE(ABORT, 'pi_kernel_migrations is append-only'); END;
      CREATE TRIGGER IF NOT EXISTS pi_kernel_migrations_no_delete
      BEFORE DELETE ON pi_kernel_migrations
      BEGIN SELECT RAISE(ABORT, 'pi_kernel_migrations is append-only'); END;
    `);
    this.#applyMigration(MIGRATION_ID, JOURNAL_SCHEMA_VERSION, MIGRATION_SQL, MIGRATION_CHECKSUM);
    this.#applyMigration(CONSUMER_CHECKPOINTS_MIGRATION_ID, CONSUMER_CHECKPOINTS_SCHEMA_VERSION, CONSUMER_CHECKPOINTS_SQL, CONSUMER_CHECKPOINTS_CHECKSUM);
  }

  #applyMigration(id, schemaVersion, sql, checksum) {
    const existing = this.db.prepare("SELECT schema_version, migration_checksum FROM pi_kernel_migrations WHERE id = ?").get(id);
    if (existing) {
      if (existing.schema_version !== schemaVersion || existing.migration_checksum !== checksum) {
        throw new PiKernelJournalError("migration_checksum_mismatch");
      }
      return;
    }
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.db.exec(sql);
      this.db.prepare("INSERT INTO pi_kernel_migrations (id, schema_version, migration_checksum, applied_at) VALUES (?, ?, ?, ?)").run(
        id, schemaVersion, checksum, nowIso(),
      );
      this.db.exec("COMMIT");
    } catch (error) {
      try { this.db.exec("ROLLBACK"); } catch { /* preserve original error */ }
      throw error;
    }
  }

  append(input, { created_at: createdAt = nowIso() } = {}) {
    this.#assertOpen();
    const event = validatePiKernelEvent(input);
    const eventJson = canonicalEventJson(event);
    // `conversation.delta.committed` carries the committed canonical artifact
    // checksum (watermark) in the canonical_checksum column; every other event
    // keeps the envelope's own canonical JSON checksum.
    const isDelta = event.type === CONVERSATION_DELTA_TYPE;
    const checksum = isDelta ? event.payload_ref.checksum : eventChecksum(event);
    const idempotencyIdentity = deriveIdempotencyIdentity(event);
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const byEventId = this.db.prepare("SELECT * FROM pi_kernel_events WHERE event_id = ?").get(event.event_id);
      const byIdempotency = this.db.prepare("SELECT * FROM pi_kernel_events WHERE idempotency_identity = ?").get(idempotencyIdentity);
      const existing = byEventId || byIdempotency;
      if (existing) {
        const existingEvent = publicRow(existing);
        if (existing.event_id !== event.event_id) {
          throw new PiKernelJournalError("idempotency_conflict");
        }
        if (existing.canonical_checksum !== checksum || existing.event_json !== eventJson) {
          throw new PiKernelJournalError("event_checksum_conflict");
        }
        this.db.exec("COMMIT");
        return { status: "duplicate", duplicate: true, replay: true, ...existingEvent };
      }
      const result = this.db.prepare(`
        INSERT INTO pi_kernel_events
          (event_id, idempotency_identity, event_type, event_json, canonical_checksum, occurred_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(event.event_id, idempotencyIdentity, event.type, eventJson, checksum, event.occurred_at, createdAt);
      this.db.exec("COMMIT");
      return {
        status: "appended",
        duplicate: false,
        replay: false,
        sequence: Number(result.lastInsertRowid),
        event,
        event_id: event.event_id,
        idempotency_identity: idempotencyIdentity,
        canonical_checksum: checksum,
        occurred_at: event.occurred_at,
        created_at: createdAt,
      };
    } catch (error) {
      try { this.db.exec("ROLLBACK"); } catch { /* preserve original error */ }
      if (error instanceof PiKernelJournalError || error instanceof PiKernelSchemaError) throw error;
      throw new PiKernelJournalError("append_failed");
    }
  }

  getByEventId(eventId) {
    this.#assertOpen();
    const row = this.db.prepare("SELECT * FROM pi_kernel_events WHERE event_id = ?").get(eventId);
    return row ? publicRow(row) : null;
  }

  replay(afterSequence = 0, limit = 100) {
    this.#assertOpen();
    if (typeof afterSequence === "object" && afterSequence !== null) {
      limit = afterSequence.limit ?? 100;
      afterSequence = afterSequence.after ?? afterSequence.afterSequence ?? afterSequence.cursor ?? 0;
    }
    if (!Number.isSafeInteger(afterSequence) || afterSequence < 0) throw new PiKernelJournalError("invalid_cursor");
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 1000) throw new PiKernelJournalError("invalid_limit");
    const rows = this.db.prepare("SELECT * FROM pi_kernel_events WHERE sequence > ? ORDER BY sequence ASC LIMIT ?").all(afterSequence, limit + 1);
    const hasMore = rows.length > limit;
    const events = rows.slice(0, limit).map(publicRow);
    const latest = this.latestSequence();
    const earliestRow = this.db.prepare("SELECT sequence FROM pi_kernel_events ORDER BY sequence ASC LIMIT 1").get();
    const earliest = earliestRow ? Number(earliestRow.sequence) : latest + 1;
    return {
      gap: false,
      events,
      next_cursor: events.at(-1)?.sequence ?? afterSequence,
      has_more: hasMore,
      earliest_sequence: earliest,
      latest_sequence: latest,
    };
  }

  readAfter(afterSequence = 0, limit = 100) { return this.replay(afterSequence, limit); }
  cursor(afterSequence = 0, limit = 100) { return this.replay(afterSequence, limit); }

  latestSequence() {
    this.#assertOpen();
    const row = this.db.prepare("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM pi_kernel_events").get();
    return Number(row.sequence);
  }

  /** Latest persisted checkpoint for a named consumer, or null when fresh. */
  consumerCheckpoint(name) {
    this.#assertOpen();
    if (typeof name !== "string" || !CONSUMER_NAME_PATTERN.test(name)) throw new PiKernelJournalError("invalid_consumer_name");
    const row = this.db.prepare("SELECT * FROM pi_kernel_consumer_checkpoints WHERE consumer_name = ? ORDER BY sequence DESC, id DESC LIMIT 1").get(name);
    if (!row) return null;
    return { id: Number(row.id), consumer_name: row.consumer_name, sequence: Number(row.sequence), checksum: row.checksum, created_at: row.created_at };
  }

  /** Append one durable checkpoint row; history is strictly append-only. */
  checkpointAppend(name, sequence, { checksum } = {}) {
    this.#assertOpen();
    if (typeof name !== "string" || !CONSUMER_NAME_PATTERN.test(name)) throw new PiKernelJournalError("invalid_consumer_name");
    if (!Number.isSafeInteger(sequence) || sequence < 1) throw new PiKernelJournalError("invalid_cursor");
    if (typeof checksum !== "string" || !SHA256_HEX.test(checksum)) throw new PiKernelJournalError("invalid_checksum");
    const latest = this.consumerCheckpoint(name);
    if (latest && sequence <= latest.sequence) throw new PiKernelJournalError("checkpoint_stale");
    this.db.exec("BEGIN IMMEDIATE");
    try {
      const result = this.db.prepare("INSERT INTO pi_kernel_consumer_checkpoints (consumer_name, sequence, checksum, created_at) VALUES (?, ?, ?, ?)").run(name, sequence, checksum, nowIso());
      this.db.exec("COMMIT");
      return { id: Number(result.lastInsertRowid), consumer_name: name, sequence, checksum, created_at: nowIso() };
    } catch (error) {
      try { this.db.exec("ROLLBACK"); } catch { /* preserve original error */ }
      if (error instanceof PiKernelJournalError) throw error;
      throw new PiKernelJournalError("checkpoint_append_failed");
    }
  }

  /** Append-only ordered checkpoint history for a named consumer. */
  checkpointHistory(name) {
    this.#assertOpen();
    if (typeof name !== "string" || !CONSUMER_NAME_PATTERN.test(name)) throw new PiKernelJournalError("invalid_consumer_name");
    const rows = this.db.prepare("SELECT * FROM pi_kernel_consumer_checkpoints WHERE consumer_name = ? ORDER BY sequence ASC, id ASC").all(name);
    return rows.map((row) => ({ id: Number(row.id), consumer_name: row.consumer_name, sequence: Number(row.sequence), checksum: row.checksum, created_at: row.created_at }));
  }

  integrityCheck() {
    this.#assertOpen();
    try {
      const sqliteResult = this.db.prepare("PRAGMA integrity_check").get();
      const sqliteCheck = String(sqliteResult?.integrity_check ?? "");
      const migration = this.db.prepare("SELECT schema_version, migration_checksum FROM pi_kernel_migrations WHERE id = ?").get(MIGRATION_ID);
      if (!migration || migration.schema_version !== JOURNAL_SCHEMA_VERSION || migration.migration_checksum !== MIGRATION_CHECKSUM) {
        return { ok: false, integrity_check: sqliteCheck, error: "migration_mismatch" };
      }
      let previous = 0;
      for (const row of this.db.prepare("SELECT * FROM pi_kernel_events ORDER BY sequence ASC").all()) {
        const event = validatePiKernelEvent(JSON.parse(row.event_json));
        // Delta events bind the committed canonical artifact checksum; all other
        // events bind the canonical JSON checksum of their stored envelope.
        const expectedChecksum = event.type === CONVERSATION_DELTA_TYPE
          ? event.payload_ref.checksum
          : sha256(row.event_json);
        if (Number(row.sequence) <= previous || row.canonical_checksum !== expectedChecksum) return { ok: false, integrity_check: sqliteCheck, error: "event_checksum_mismatch" };
        previous = Number(row.sequence);
      }
      return { ok: sqliteCheck === "ok", integrity_check: sqliteCheck, schema_version: JOURNAL_SCHEMA_VERSION, event_count: previous === 0 ? 0 : this.latestSequence() };
    } catch (error) {
      return { ok: false, integrity_check: "failed", error: error instanceof PiKernelJournalError ? error.code : "integrity_failed" };
    }
  }

  preflight() { return this.integrityCheck(); }

  tableColumns(tableName = "pi_kernel_events") {
    this.#assertOpen();
    return this.db.prepare("SELECT name, type FROM pragma_table_info(?) ORDER BY cid").all(tableName);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.db.close();
  }

  dispose() { this.close(); }
}

export const PiKernelEventJournal = EventJournal;

export function createEventJournal(options = {}) {
  return new EventJournal(typeof options === "string" ? options : options.databasePath);
}
