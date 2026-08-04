import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { createEventJournal, EventJournal, PiKernelJournalError } from "../src/events/journal.mjs";
import { createPiKernelEvent } from "../src/events/schema.mjs";
import { createKernelHost, KernelHostError, PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";

const base = {
  type: "task_started",
  source: "pi_kernel",
  authority: "authority:test",
  snapshot: "snapshot:test",
  correlation_id: "corr:test",
  causation_id: null,
  idempotency_key: "idem:journal:1",
  occurred_at: "2026-08-04T09:00:00.000Z",
  payload_ref: { kind: "none", ref: null, checksum: null },
  privacy_class: "R1",
};

function event(overrides = {}) { return createPiKernelEvent({ ...base, ...overrides }); }

async function tempDb() {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-journal-"));
  return { dir, path: join(dir, "events.sqlite") };
}

test("journal migrates append-only metadata schema with no private body columns", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(path);
  const columns = journal.tableColumns().map((column) => column.name);
  assert.deepEqual(columns, ["sequence", "event_id", "idempotency_identity", "event_type", "event_json", "canonical_checksum", "occurred_at", "created_at"]);
  assert.ok(!columns.some((name) => /body|content|prompt|completion|credential|path/i.test(name)));
  assert.equal(journal.integrityCheck().ok, true);
  journal.close();
});

test("append is monotonic and duplicate replay does not create a row", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = createEventJournal(path);
  const first = journal.append(event());
  const duplicate = journal.append(event());
  const second = journal.append(event({ idempotency_key: "idem:journal:2", type: "tool_started" }));
  assert.equal(first.status, "appended");
  assert.equal(duplicate.status, "duplicate");
  assert.equal(duplicate.sequence, first.sequence);
  assert.equal(second.sequence, first.sequence + 1);
  assert.deepEqual(journal.replay(0).events.map((row) => row.sequence), [1, 2]);
  assert.equal(journal.latestSequence(), 2);
  journal.close();
});

test("idempotency identity conflicts fail without a new row", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(path);
  journal.append(event());
  assert.throws(() => journal.append(event({ type: "tool_started", payload_ref: { kind: "artifact", ref: "artifact:changed", checksum: "b".repeat(64) } })), (error) => error instanceof PiKernelJournalError && error.code === "idempotency_conflict");
  assert.equal(journal.latestSequence(), 1);
  journal.close();
});

test("restart preserves cursor replay and integrity", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(path);
  journal.append(event());
  journal.append(event({ idempotency_key: "idem:journal:2", type: "tool_started" }));
  journal.close();
  const restarted = new EventJournal(path);
  const replay = restarted.cursor({ after: 1, limit: 10 });
  assert.equal(replay.gap, false);
  assert.deepEqual(replay.events.map((row) => row.sequence), [2]);
  assert.equal(replay.events[0].event.type, "tool_started");
  assert.equal(restarted.integrityCheck().integrity_check, "ok");
  restarted.close();
});

test("append-only triggers reject update and delete", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(path);
  journal.append(event());
  assert.throws(() => journal.db.prepare("UPDATE pi_kernel_events SET event_type = 'tampered' WHERE sequence = 1").run());
  assert.throws(() => journal.db.prepare("DELETE FROM pi_kernel_events WHERE sequence = 1").run());
  assert.equal(journal.integrityCheck().ok, true);
  journal.close();
});

async function decisionFixture(dir, overrides = {}) {
  const path = join(dir, "decision.json");
  const decision = {
    schema: "pi-package-decision-v1",
    run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted",
    accepted: true,
    expiry: "2099-01-01T00:00:00.000Z",
    ...overrides,
  };
  await writeFile(path, JSON.stringify(decision), "utf8");
  return path;
}

test("Host factory requires accepted non-expired decision and exact loopback policy", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-kernel-host-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const decisionPath = await decisionFixture(dir);
  const host = await createKernelHost({ projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), cwd: dir, agentDir: join(dir, "agent") });
  assert.equal(host.isReady(), true);
  assert.equal(host.server.listening, true);
  assert.deepEqual(host.status(), { lifecycle: "ready", host: "127.0.0.1", port: 8790, provider_calls: 0, ready: true });
  assert.equal((await host.dispose()).lifecycle, "disposed");
  await assert.rejects(() => createKernelHost({ decisionPath: join(dir, "missing.json"), databasePath: join(dir, "missing.sqlite"), cwd: dir, agentDir: join(dir, "agent") }), (error) => error instanceof KernelHostError && error.code === "package_decision_missing");
  const expiredPath = await decisionFixture(dir, { expiry: "2020-01-01T00:00:00.000Z" });
  await assert.rejects(() => createKernelHost({ decisionPath: expiredPath, databasePath: join(dir, "expired.sqlite"), cwd: dir, agentDir: join(dir, "agent") }), (error) => error.code === "package_decision_expired");
  await assert.rejects(() => createKernelHost({ decisionPath, host: "0.0.0.0", databasePath: join(dir, "remote.sqlite"), cwd: dir, agentDir: join(dir, "agent") }), (error) => error.code === "non_loopback_bind");
});

test("journal API does not serialize private bodies", async (t) => {
  const { dir, path } = await tempDb();
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(path);
  const row = journal.append(event({ payload_ref: { kind: "artifact", ref: "artifact:opaque", checksum: "c".repeat(64) } }));
  const raw = await readFile(path, null);
  assert.equal(raw.includes(Buffer.from("private body")), false);
  assert.equal(row.event.payload_ref.ref, "artifact:opaque");
  journal.close();
});
