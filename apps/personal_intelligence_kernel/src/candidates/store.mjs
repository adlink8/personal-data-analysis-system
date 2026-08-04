import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
export const PI_KERNEL_CANDIDATES_DB = "var/db/pi_kernel_candidates.sqlite";
export class CandidateStoreError extends Error { constructor(code, message = code) { super(message); this.name = "CandidateStoreError"; this.code = code; } }
const json = (value) => JSON.stringify(value ?? null);
function row(value) { return value ? { candidate_id: value.candidate_id, proposal: JSON.parse(value.proposal), evidence_refs: JSON.parse(value.evidence_refs), model_receipt: JSON.parse(value.model_receipt), schema_version: value.schema_version, created_at: value.created_at } : null; }
export class CandidateStore {
  constructor(databasePath = PI_KERNEL_CANDIDATES_DB) { this.databasePath = resolve(databasePath); mkdirSync(dirname(this.databasePath), { recursive: true }); this.db = new DatabaseSync(this.databasePath); this.db.exec("PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS pi_kernel_candidates (candidate_id TEXT PRIMARY KEY,proposal TEXT NOT NULL,evidence_refs TEXT NOT NULL,model_receipt TEXT NOT NULL,schema_version TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS pi_kernel_candidate_receipts (candidate_id TEXT PRIMARY KEY REFERENCES pi_kernel_candidates(candidate_id),receipt_json TEXT NOT NULL);"); }
  #validate(input) { const forbidden = ["canonical_fact","active","promoted","watermark","authority_pointer","promotion","serving"]; const seen = []; const walk = (value) => { if (!value || typeof value !== "object") return; for (const [key, nested] of Object.entries(value)) { seen.push(key.toLowerCase()); walk(nested); } }; walk(input); if (seen.some((key) => forbidden.some((item) => key.includes(item)))) throw new CandidateStoreError("serving_lifecycle_forbidden"); if (!input?.candidate_id || !input?.proposal || !Array.isArray(input?.evidence_refs) || !input?.model_receipt) throw new CandidateStoreError("evidence_and_receipt_required"); if (seen.some((key) => /path|credential|secret|body|content|prompt|completion/.test(key))) throw new CandidateStoreError("private_body_rejected"); }
  add(input = {}) { this.#validate(input); const now = input.created_at ?? new Date().toISOString(); this.db.prepare("INSERT INTO pi_kernel_candidates VALUES(?,?,?,?,?,?)").run(input.candidate_id,json(input.proposal),json(input.evidence_refs),json(input.model_receipt),input.schema_version ?? "pi_kernel_candidate_v1",now); return this.get(input.candidate_id); }
  get(candidateId) { return row(this.db.prepare("SELECT * FROM pi_kernel_candidates WHERE candidate_id=?").get(candidateId)); }
  list() { return this.db.prepare("SELECT * FROM pi_kernel_candidates ORDER BY created_at,candidate_id").all().map(row); }
  integrityCheck() { const result = this.db.prepare("PRAGMA integrity_check").get(); return { ok: result?.integrity_check === "ok", integrity_check: result?.integrity_check, candidate_count: Number(this.db.prepare("SELECT COUNT(*) AS count FROM pi_kernel_candidates").get().count) }; }
  tableColumns() { return this.db.prepare("SELECT name FROM pragma_table_info('pi_kernel_candidates') ORDER BY cid").all().map((item) => item.name); }
  close() { this.db.close(); }
  dispose() { this.close(); }
}
export const CandidateStagingStore = CandidateStore;
export function createCandidateStore(path) { return new CandidateStore(path); }
