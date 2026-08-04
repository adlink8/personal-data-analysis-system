import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

import {
  canonicalEventJson,
  deriveIdempotencyIdentity,
  eventChecksum,
  PiKernelSchemaError,
  sha256,
  validatePiKernelEvent,
} from "./schema.mjs";

export const PI_KERNEL_EVENTS_DB = "var/db/pi_kernel_events.sqlite";
export const JOURNAL_SCHEMA_VERSION = "pi_kernel_events_v1";
const MIGRATION_ID = "001_pi_kernel_events_v1";

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
    const existing = this.db.prepare("SELECT schema_version, migration_checksum FROM pi_kernel_migrations WHERE id = ?").get(MIGRATION_ID);
    if (existing) {
      if (existing.schema_version !== JOURNAL_SCHEMA_VERSION || existing.migration_checksum !== MIGRATION_CHECKSUM) {
        throw new PiKernelJournalError("migration_checksum_mismatch");
      }
      return;
    }
    this.db.exec("BEGIN IMMEDIATE");
    try {
      this.db.exec(MIGRATION_SQL);
      this.db.prepare("INSERT INTO pi_kernel_migrations (id, schema_version, migration_checksum, applied_at) VALUES (?, ?, ?, ?)").run(
        MIGRATION_ID, JOURNAL_SCHEMA_VERSION, MIGRATION_CHECKSUM, nowIso(),
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
    const checksum = eventChecksum(event);
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
        if (Number(row.sequence) <= previous || row.canonical_checksum !== sha256(row.event_json)) return { ok: false, integrity_check: sqliteCheck, error: "event_checksum_mismatch" };
        validatePiKernelEvent(JSON.parse(row.event_json));
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
