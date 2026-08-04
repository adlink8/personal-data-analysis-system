import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { createHash } from "node:crypto";

export const PI_KERNEL_SESSIONS_DB = "var/db/pi_kernel_sessions.sqlite";
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const nowIso = () => new Date().toISOString();
const json = (value) => JSON.stringify(value ?? null);
const parse = (value) => value == null ? null : JSON.parse(value);
export class SessionStoreError extends Error { constructor(code, message = code) { super(message); this.name = "SessionStoreError"; this.code = code; } }
function row(row) { return row ? { session_id: row.session_id, parent_session_id: row.parent_session_id, parent_checksum: row.parent_checksum, schema_version: row.schema_version, privacy_class: row.privacy_class, retention_until: row.retention_until, redaction_status: row.redaction_status, trajectory: parse(row.trajectory), created_at: row.created_at, updated_at: row.updated_at } : null; }
export class SessionStore {
  constructor(databasePath = PI_KERNEL_SESSIONS_DB) { this.databasePath = resolve(databasePath); mkdirSync(dirname(this.databasePath), { recursive: true }); this.db = new DatabaseSync(this.databasePath); this.db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS pi_kernel_sessions (session_id TEXT PRIMARY KEY,parent_session_id TEXT,parent_checksum TEXT,schema_version TEXT NOT NULL,privacy_class TEXT NOT NULL CHECK(privacy_class IN ('R1','R2')),retention_until TEXT,redaction_status TEXT NOT NULL DEFAULT 'none',trajectory TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pi_kernel_session_receipts (receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT NOT NULL REFERENCES pi_kernel_sessions(session_id),kind TEXT NOT NULL,receipt_json TEXT NOT NULL,created_at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS idx_pi_kernel_sessions_retention ON pi_kernel_sessions(retention_until);"); }
  #validateInput(input) { if (!input || typeof input !== "object" || Object.keys(input).some((key) => /body|content|prompt|completion|credential|secret/i.test(key))) throw new SessionStoreError("private_body_rejected"); }
  create({ session_id, trajectory = [], privacy_class = "R1", retention_until = null, parent_session_id = null, parent_checksum = null, schema_version = "pi_kernel_session_v1", now = nowIso() } = {}) { this.#validateInput({ trajectory }); if (!session_id) throw new SessionStoreError("missing_session_id"); if (!Array.isArray(trajectory)) throw new SessionStoreError("invalid_trajectory"); this.db.prepare("INSERT INTO pi_kernel_sessions VALUES (?,?,?,?,?,?,?,?,?,?)").run(session_id,parent_session_id,parent_checksum,schema_version,privacy_class,retention_until,"none",json(trajectory),now,now); return this.get(session_id); }
  get(sessionId) { return row(this.db.prepare("SELECT * FROM pi_kernel_sessions WHERE session_id=?").get(sessionId)); }
  append(sessionId, item, { now = nowIso(), receipt = null } = {}) { this.#validateInput(item); const current = this.get(sessionId); if (!current) throw new SessionStoreError("session_not_found"); const trajectory = [...current.trajectory, { ...item, metadata_only: true, recorded_at: now }]; this.db.prepare("UPDATE pi_kernel_sessions SET trajectory=?,updated_at=? WHERE session_id=?").run(json(trajectory),now,sessionId); if (receipt) this.db.prepare("INSERT INTO pi_kernel_session_receipts(session_id,kind,receipt_json,created_at) VALUES(?,?,?,?)").run(sessionId,receipt.kind ?? "tool",json(receipt),now); return this.get(sessionId); }
  resume(sessionId, { parent_checksum } = {}) { const current = this.get(sessionId); if (!current) throw new SessionStoreError("session_not_found"); if (parent_checksum && parent_checksum !== sha256(JSON.stringify(current.trajectory))) throw new SessionStoreError("parent_checksum_mismatch"); return current; }
  fork(sessionId, { new_session_id, now = nowIso() } = {}) { const parent = this.get(sessionId); if (!parent) throw new SessionStoreError("session_not_found"); return this.create({ session_id: new_session_id, parent_session_id: parent.session_id, parent_checksum: sha256(JSON.stringify(parent.trajectory)), privacy_class: parent.privacy_class, retention_until: parent.retention_until, trajectory: [], now }); }
  retain({ now = nowIso() } = {}) { const result = this.db.prepare("UPDATE pi_kernel_sessions SET trajectory='[]',redaction_status='redacted',updated_at=? WHERE retention_until IS NOT NULL AND retention_until <= ? AND redaction_status='none'").run(now,now); return { redacted: result.changes }; }
  integrityCheck() { const result = this.db.prepare("PRAGMA integrity_check").get(); return { ok: result?.integrity_check === "ok", integrity_check: result?.integrity_check, session_count: Number(this.db.prepare("SELECT COUNT(*) AS count FROM pi_kernel_sessions").get().count) }; }
  tableColumns() { return this.db.prepare("SELECT name FROM pragma_table_info('pi_kernel_sessions') ORDER BY cid").all().map((item) => item.name); }
  close() { this.db.close(); }
  dispose() { this.close(); }
}
export const SessionTrajectoryStore = SessionStore;
export function createSessionStore(path) { return new SessionStore(path); }
