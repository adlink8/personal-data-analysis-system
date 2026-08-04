import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionStore, SessionStoreError } from "../src/sessions/store.mjs";
import { CandidateStore, CandidateStoreError } from "../src/candidates/store.mjs";

test("Session and Candidate stores are isolated, resumable and non-serving", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-artifacts-")); t.after(() => rm(dir, { recursive: true, force: true }));
  const sessions = new SessionStore(join(dir, "sessions.sqlite"));
  const candidates = new CandidateStore(join(dir, "candidates.sqlite"));
  sessions.create({ session_id: "s1", trajectory: [{ type: "tool_started", ref: "artifact:1" }] });
  const fork = sessions.fork("s1", { new_session_id: "s2" });
  assert.equal(fork.parent_session_id, "s1");
  assert.throws(() => sessions.append("s1", { prompt: "private" }), (error) => error instanceof SessionStoreError && error.code === "private_body_rejected");
  const candidate = candidates.add({ candidate_id: "c1", proposal: { kind: "draft" }, evidence_refs: [{ ref: "artifact:1", checksum: "a".repeat(64) }], model_receipt: { model: "synthetic", checksum: "b".repeat(64) } });
  assert.equal(candidate.candidate_id, "c1");
  assert.throws(() => candidates.add({ candidate_id: "c2", proposal: { active: true }, evidence_refs: [], model_receipt: {} }), (error) => error instanceof CandidateStoreError);
  assert.deepEqual(new Set(sessions.tableColumns()), new Set(["session_id","parent_session_id","parent_checksum","schema_version","privacy_class","retention_until","redaction_status","trajectory","created_at","updated_at"]));
  assert.ok(!candidates.tableColumns().some((column) => /active|promoted|watermark|authority/i.test(column)));
  assert.notEqual(sessions.databasePath, candidates.databasePath);
  assert.equal(sessions.integrityCheck().ok, true); assert.equal(candidates.integrityCheck().ok, true);
  sessions.close(); candidates.close();
});
