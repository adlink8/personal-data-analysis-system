import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TaskLedger, TaskLedgerError } from "../src/tasks/ledger.mjs";

test("task ledger claims atomically and enforces transitions/idempotency", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-task-ledger-")); t.after(() => rm(dir, { recursive: true, force: true }));
  const ledger = new TaskLedger(join(dir, "tasks.sqlite"));
  const created = ledger.enqueue({ task_id: "task-1", idempotency_key: "idem-1", input_ref: { ref: "artifact:1" } });
  assert.equal(created.task.state, "queued");
  assert.equal(ledger.enqueue({ task_id: "task-1", idempotency_key: "idem-1", input_ref: { ref: "artifact:1" } }).duplicate, true);
  const claimed = ledger.claim("task-1", { owner: "worker-a", leaseMs: 1000 });
  assert.equal(claimed.state, "claimed");
  assert.throws(() => ledger.claim("task-1", { owner: "worker-b" }), (error) => error instanceof TaskLedgerError && error.code === "task_busy");
  const running = ledger.transition("task-1", "running", { expectedVersion: claimed.version, owner: "worker-a" });
  const unknown = ledger.markOutcomeUnknown("task-1", { expectedVersion: running.version, owner: "worker-a" });
  assert.equal(unknown.state, "outcome_unknown");
  assert.throws(() => ledger.transition("task-1", "running", { expectedVersion: unknown.version }), /illegal_transition/);
  const reconciled = ledger.reconcile("task-1", { state: "succeeded", output_ref: { ref: "result:1" } });
  assert.equal(reconciled.state, "succeeded");
  assert.equal(ledger.integrityCheck().ok, true); ledger.close();
  const restarted = new TaskLedger(join(dir, "tasks.sqlite"));
  assert.equal(restarted.get("task-1").state, "succeeded"); restarted.close();
});
