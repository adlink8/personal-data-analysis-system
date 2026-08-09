// Plan 61-06 Task 1 RED contract: committed-only delta publishing + durable replay.
//
// This file is the RED test for Task 1. It is intentionally written against the
// Plan 61-06 Task 2 contract that does not exist yet:
//   - events/schema.mjs         -> registers event type "conversation.delta.committed"
//   - events/journal.mjs        -> append-only named consumer-checkpoint API
//                                  (consumerCheckpoint / checkpointAppend / checkpointHistory)
//   - src/reflection/conversation-delta-dispatcher.mjs
//                              -> createConversationDeltaDispatcher() with guarded
//                                 staging callback and persisted cursor (consumer
//                                 "conversation-reflection-v1")
//   - server.mjs                -> fixed internal producer route
//                                  POST /internal/v1/conversation-deltas (gated by the
//                                  internal capability header, never the public events route)
//   - src/personal_knowledge/application/sync.py -> post-commit publisher (Python test)
//
// Running this against the current kernel MUST FAIL: the delta type is not
// registered, the internal producer route returns 404, the dispatcher module is
// missing and the journal has no consumer-checkpoint API. Every failure points
// at the missing publisher/dispatcher/schema/journal implementation, never at a
// syntax error. The producer entry is the real post-commit sync/close seam
// (kernel-side fixed internal endpoint); no `harness_reflection` or Candidate
// helper is ever used as the producer or dispatcher entry point.

import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { request as httpRequest } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { startKernelServer } from "../src/server.mjs";
import { PHASE_48_DECISION_RUN_ID } from "../src/kernel-host.mjs";
import { EventJournal, PiKernelJournalError } from "../src/events/journal.mjs";
import { PI_KERNEL_EVENT_TYPES, PI_KERNEL_PRIVACY_CLASSES, validatePiKernelEvent } from "../src/events/schema.mjs";

const TEST_ROOT = dirname(fileURLToPath(import.meta.url));

const DELTA_TYPE = "conversation.delta.committed";
const CONSUMER_NAME = "conversation-reflection-v1";
const RULE_VERSION = "conversation-reflection-v1";
const INTERNAL_ROUTE = "/internal/v1/conversation-deltas";
const INTERNAL_CAPABILITY = "test-conversation-delta-capability";
const CHECKPOINT_TABLE = "pi_kernel_consumer_checkpoints";

// Sentinel private values. If any reaches an event, response, checkpoint or
// callback payload the test fails closed, exactly like the freshness test.
const SENTINELS = Object.freeze({
  body: "PRIVATE_CONVERSATION_BODY_SENTINEL_4a1f2b",
  prompt: "PRIVATE_PROMPT_SENTINEL_9f3a1c",
  credential: "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
  secret: "PRIVATE_SECRET_SENTINEL_1b5e7c",
  sql: "SELECT * FROM messages WHERE body LIKE '%PRIVATE_SQL_SENTINEL_2c6d8e%'",
});
// Mirrors schema.mjs FORBIDDEN_KEY plus the SQL statement guard.
const FORBIDDEN_KEY = /^(?:body|content|prompt|completion|payload|inline_payload|input|output|result|credential|secret|token|password|path|sql|query)$/i;

function sha256Hex(value) {
  return createHash("sha256").update(value).digest("hex");
}

function assertNoPrivateLeak(value, label) {
  const text = JSON.stringify(value);
  for (const [kind, sentinel] of Object.entries(SENTINELS)) {
    assert.equal(text.includes(sentinel), false, `${label} leaked ${kind} sentinel`);
  }
  const walk = (node, path) => {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach((item, index) => walk(item, `${path}[${index}]`));
      return;
    }
    for (const [key, child] of Object.entries(node)) {
      assert.equal(FORBIDDEN_KEY.test(key), false, `${label} persisted forbidden key "${key}" at ${path}`);
      walk(child, `${path}.${key}`);
    }
  };
  walk(value, label);
}

function requestJson(port, method, path, body, extraHeaders = {}) {
  return new Promise((resolveRequest, reject) => {
    const payload = body === undefined ? null : JSON.stringify(body);
    const request = httpRequest({
      host: "127.0.0.1", port, method, path,
      headers: payload ? { "content-type": "application/json", "content-length": Buffer.byteLength(payload), ...extraHeaders } : { ...extraHeaders },
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        resolveRequest({ status: response.statusCode, text, json: text ? JSON.parse(text) : null });
      });
    });
    request.on("error", reject);
    if (payload) request.write(payload);
    request.end();
  });
}

async function startFixtureServer(t) {
  const dir = await mkdtemp(join(tmpdir(), "pi-conversation-delta-"));
  const decisionPath = join(dir, "decision.json");
  await writeFile(decisionPath, JSON.stringify({
    schema: "pi-package-decision-v1", run_id: PHASE_48_DECISION_RUN_ID,
    status: "accepted", accepted: true, expiry: "2099-01-01T00:00:00.000Z",
  }), "utf8");
  const runtime = await startKernelServer({
    projectRoot: process.cwd(), decisionPath, databasePath: join(dir, "events.sqlite"), controlDatabaseDirectory: dir,
    cwd: dir, agentDir: join(dir, "agent"), host: "127.0.0.1", port: 0,
    providerMode: "replay", internalCapability: INTERNAL_CAPABILITY,
  });
  const port = runtime.server.address().port;
  t.after(async () => { await runtime.stop(100); await rm(dir, { recursive: true, force: true }); });
  return { runtime, dir, port, journalPath: join(dir, "events.sqlite") };
}

// Canonical checksum / watermark fixture. In the real flow `_record_conversation_versions`
// records watermark_value == file_checksum(canonical DB); "committed" means the observed
// canonical checksum equals the committed watermark.
const CANONICAL_CHECKSUM = sha256Hex("canonical:agent.conversation:fixture-v1");
const SOURCE_CHECKSUM = sha256Hex("agentsview:sessions.db:fixture-v1");

function committedDeltaBody(overrides = {}) {
  return {
    producer: "pk-sync",
    scope: "agent.conversation",
    source_checksum: SOURCE_CHECKSUM,
    canonical_checksum: CANONICAL_CHECKSUM,
    watermark: CANONICAL_CHECKSUM,
    publication_version: "2026-08-09T09:00:00.000Z#1",
    occurred_at: "2026-08-09T09:00:00.000Z",
    idempotency_key: "pi-idem-conversation-delta-001",
    committed: true,
    ...overrides,
  };
}

async function importDispatcher() {
  try {
    return await import("../src/reflection/conversation-delta-dispatcher.mjs");
  } catch (error) {
    assert.fail(`RED: src/reflection/conversation-delta-dispatcher.mjs not implemented (expected for 61-06 Task 1): ${error.code ?? error.message}`);
  }
}

function consumerCheckpoint(journal, name) {
  if (typeof journal.consumerCheckpoint !== "function") {
    assert.fail("RED: EventJournal must expose consumerCheckpoint(name) append-only API (expected for 61-06 Task 1)");
  }
  return journal.consumerCheckpoint(name);
}

function requireCheckpointAppend(journal) {
  if (typeof journal.checkpointAppend !== "function") {
    assert.fail("RED: EventJournal must expose checkpointAppend(name, sequence, { checksum }) append-only API (expected for 61-06 Task 1)");
  }
  return journal.checkpointAppend.bind(journal);
}

function requireCheckpointHistory(journal) {
  if (typeof journal.checkpointHistory !== "function") {
    assert.fail("RED: EventJournal must expose checkpointHistory(name) append-only API (expected for 61-06 Task 1)");
  }
  return journal.checkpointHistory.bind(journal);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test("schema registers conversation.delta.committed with a metadata-only artifact payload", () => {
  assert.ok(
    PI_KERNEL_EVENT_TYPES.includes(DELTA_TYPE),
    "RED: events/schema.mjs must register conversation.delta.committed (expected for 61-06 Task 1)",
  );
  const body = committedDeltaBody();
  const event = validatePiKernelEvent({
    event_id: "",
    type: DELTA_TYPE,
    source: body.producer,
    authority: "canonical.sync",
    snapshot: `agentsview@${body.source_checksum}`,
    correlation_id: `scope:${body.scope}`,
    causation_id: null,
    idempotency_key: body.idempotency_key,
    occurred_at: body.occurred_at,
    payload_ref: {
      kind: "artifact",
      ref: `canonical.conversation@${body.watermark}#${body.publication_version}`,
      checksum: body.canonical_checksum,
    },
    privacy_class: "R2",
  });
  assert.equal(event.type, DELTA_TYPE);
  assert.ok(PI_KERNEL_PRIVACY_CLASSES.includes(event.privacy_class));
  assert.equal(event.payload_ref.checksum, CANONICAL_CHECKSUM);
  assertNoPrivateLeak(event, "delta event envelope");
});

test("fixed internal producer route emits exactly one committed metadata-only delta (pk-sync post-commit)", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const body = committedDeltaBody();
  const response = await requestJson(port, "POST", INTERNAL_ROUTE, body, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(response.status, 201, `RED: ${INTERNAL_ROUTE} must exist and append one committed delta (got ${response.status})`);
  assert.equal(response.json.ok, true);
  assert.equal(response.json.status, "appended");
  assert.equal(response.json.duplicate, false);
  assert.ok(response.json.event_id, "server must derive the event id server-side");
  assert.equal(typeof response.json.sequence, "number");
  assertNoPrivateLeak(response.json, "producer response");

  const journal = new EventJournal(journalPath);
  const rows = journal.replay(0).events;
  assert.equal(rows.length, 1, "one committed sync emits exactly one delta event");
  const event = rows[0].event;
  assert.equal(event.type, DELTA_TYPE);
  assert.equal(event.source, body.producer);
  assert.equal(event.correlation_id, `scope:${body.scope}`);
  assert.ok(event.snapshot.includes(body.source_checksum), "snapshot must bind the source->AgentView checksum");
  assert.equal(event.payload_ref.checksum, body.canonical_checksum, "AgentView->canonical binding must carry the canonical checksum");
  assert.ok(event.payload_ref.ref.includes(body.watermark), "payload ref must bind the committed watermark");
  assert.ok(event.payload_ref.ref.includes(body.publication_version), "payload ref must bind the publication version");
  assertNoPrivateLeak(event, "journal delta event");
  assert.equal(journal.integrityCheck().ok, true);
  journal.close();
});

test("matching committed conversation-close producer emits one delta and exact replay deduplicates", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const closeBody = committedDeltaBody({ producer: "conversation.close", idempotency_key: "pi-idem-conversation-close-001" });
  const first = await requestJson(port, "POST", INTERNAL_ROUTE, closeBody, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(first.status, 201, `RED: committed close trigger must emit a delta (got ${first.status})`);
  const retry = await requestJson(port, "POST", INTERNAL_ROUTE, closeBody, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(retry.status, 200);
  assert.equal(retry.json.replay, true);
  assert.equal(retry.json.event_id, first.json.event_id, "exact retry returns the same event id");
  assert.equal(retry.json.sequence, first.json.sequence, "exact retry returns the same sequence");

  const journal = new EventJournal(journalPath);
  assert.equal(journal.latestSequence(), 1, "exact retry must not append a second delta");
  journal.close();
});

test("fixed internal route gate: unauthenticated and public/renderer/model triggers publish no delta", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const body = committedDeltaBody();

  // 1. The internal producer route without the internal capability header is rejected.
  const noCapability = await requestJson(port, "POST", INTERNAL_ROUTE, body);
  assert.notEqual(noCapability.status, 201, "internal producer route must require the internal capability header");

  // 2. The public generic events endpoint must never accept a delta (fixed producer endpoint only).
  const viaPublic = await requestJson(port, "POST", "/v1/events", {
    event_id: "",
    type: DELTA_TYPE,
    source: "renderer",
    authority: "renderer",
    snapshot: "snapshot:renderer",
    correlation_id: "corr:renderer",
    causation_id: null,
    idempotency_key: "pi-idem-renderer-001",
    occurred_at: body.occurred_at,
    payload_ref: { kind: "artifact", ref: "canonical.conversation@x", checksum: body.canonical_checksum },
    privacy_class: "R2",
  });
  assert.notEqual(viaPublic.status, 201, "public generic events route must reject conversation.delta.committed");

  const journal = new EventJournal(journalPath);
  assert.equal(journal.latestSequence(), 0, "no delta may be produced outside the fixed internal route");
  journal.close();
});

test("dry-run, uncommitted, missing, and mismatched checksum/watermark publish no event", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const cases = [
    { label: "uncommitted/dry-run", body: committedDeltaBody({ committed: false }) },
    { label: "missing canonical checksum", body: committedDeltaBody({ canonical_checksum: "" }) },
    { label: "missing watermark", body: committedDeltaBody({ watermark: "" }) },
    { label: "mismatched watermark", body: committedDeltaBody({ watermark: sha256Hex("different:watermark") }) },
  ];
  for (const { label, body } of cases) {
    const response = await requestJson(port, "POST", INTERNAL_ROUTE, body, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
    assert.equal(response.status, 400, `${label} trigger must be rejected by the fixed internal producer (got ${response.status})`);
    assertNoPrivateLeak(response.json, `${label} response`);
  }
  const journal = new EventJournal(journalPath);
  assert.equal(journal.latestSequence(), 0, "no uncommitted/mismatched/missing trigger may append a delta");
  journal.close();
});

test("exact retry returns the same EventJournal event/sequence and divergent identity fails closed", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const body = committedDeltaBody();
  const first = await requestJson(port, "POST", INTERNAL_ROUTE, body, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(first.status, 201, `RED: producer must append the committed delta (got ${first.status})`);
  const retry = await requestJson(port, "POST", INTERNAL_ROUTE, body, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(retry.status, 200);
  assert.equal(retry.json.duplicate, true);
  assert.equal(retry.json.event_id, first.json.event_id);
  assert.equal(retry.json.sequence, first.json.sequence);

  // Divergent identity: same idempotency key, different canonical checksum/watermark.
  const divergent = await requestJson(port, "POST", INTERNAL_ROUTE, committedDeltaBody({
    canonical_checksum: sha256Hex("different:canonical"),
    watermark: sha256Hex("different:canonical"),
  }), { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(divergent.status, 409, "divergent identity must fail closed (idempotency conflict)");

  const journal = new EventJournal(journalPath);
  assert.equal(journal.latestSequence(), 1, "neither retry nor divergence may append a second delta");
  journal.close();
});

test("delta event identity is append-only and committed ordering is preserved", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const first = committedDeltaBody({ idempotency_key: "pi-idem-committed-order-001", occurred_at: "2026-08-09T09:00:00.000Z" });
  const second = committedDeltaBody({ idempotency_key: "pi-idem-committed-order-002", occurred_at: "2026-08-09T09:05:00.000Z" });
  const a = await requestJson(port, "POST", INTERNAL_ROUTE, first, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  const b = await requestJson(port, "POST", INTERNAL_ROUTE, second, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(a.status, 201, `RED: committed sync must append (got ${a.status})`);
  assert.equal(b.status, 201);
  assert.ok(b.json.sequence > a.json.sequence, "committed deltas must receive monotonic sequences");

  const journal = new EventJournal(journalPath);
  const events = journal.replay(0).events.map((row) => row.event);
  assert.equal(events.length, 2);
  assert.equal(events[0].event_id, a.json.event_id);
  assert.equal(events[1].event_id, b.json.event_id);
  assert.equal(events[0].occurred_at < events[1].occurred_at, true);

  // Append-only identity: neither UPDATE nor DELETE may mutate a persisted event.
  const sequence = a.json.sequence;
  assert.throws(() => journal.db.prepare("UPDATE pi_kernel_events SET event_type = 'tampered' WHERE sequence = ?").run(sequence));
  assert.throws(() => journal.db.prepare("DELETE FROM pi_kernel_events WHERE sequence = ?").run(sequence));
  assert.equal(journal.integrityCheck().ok, true);
  journal.close();
});

test("journal keeps an append-only named consumer-checkpoint history and rejects mutation", async (t) => {
  const dir = await mkdtemp(join(tmpdir(), "pi-consumer-checkpoint-"));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const journal = new EventJournal(join(dir, "events.sqlite"));

  assert.equal(consumerCheckpoint(journal, CONSUMER_NAME), null, "a fresh consumer has no checkpoint");
  const checkpointAppend = requireCheckpointAppend(journal);
  const checkpointHistory = requireCheckpointHistory(journal);

  checkpointAppend(CONSUMER_NAME, 1, { checksum: sha256Hex("event:1") });
  checkpointAppend(CONSUMER_NAME, 2, { checksum: sha256Hex("event:2") });
  assert.equal(consumerCheckpoint(journal, CONSUMER_NAME).sequence, 2, "consumer cursor reads the latest checkpoint");

  const history = checkpointHistory(CONSUMER_NAME);
  assert.deepEqual(history.map((row) => row.sequence), [1, 2], "checkpoint history is append-only and ordered");
  assert.ok(history.every((row) => typeof row.checksum === "string"), "each checkpoint binds the dispatched event checksum");

  // A replayed exact dispatch must not add a second checkpoint entry for the same sequence.
  assert.throws(() => journal.db.prepare(`UPDATE ${CHECKPOINT_TABLE} SET sequence = 99`).run(), /append-only/i, "checkpoint rows are append-only");
  assert.throws(() => journal.db.prepare(`DELETE FROM ${CHECKPOINT_TABLE} WHERE sequence = 1`).run(), /append-only/i, "checkpoint rows are append-only");
  assert.equal(consumerCheckpoint(journal, CONSUMER_NAME).sequence, 2, "replay/failure must retain the last successful checkpoint");
  journal.close();
});

test("dispatcher replays from a persisted cursor and only advances after guarded callback success", async (t) => {
  const { port, journalPath } = await startFixtureServer(t);
  const { createConversationDeltaDispatcher } = await importDispatcher();

  // Produce committed deltas through the real post-commit producer seam.
  const one = committedDeltaBody({ idempotency_key: "pi-idem-dispatch-001" });
  const two = committedDeltaBody({ idempotency_key: "pi-idem-dispatch-002" });
  const first = await requestJson(port, "POST", INTERNAL_ROUTE, one, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  const second = await requestJson(port, "POST", INTERNAL_ROUTE, two, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(first.status, 201, `RED: producer must append committed deltas (got ${first.status})`);
  assert.equal(second.status, 201);

  const journal = new EventJournal(journalPath);
  const seen = [];
  const stage = async (metadata) => {
    seen.push(metadata);
    assertNoPrivateLeak(metadata, "staging callback metadata");
    assert.equal(metadata.rule_version, RULE_VERSION, "callback metadata must carry the binding rule version");
    assert.ok(metadata.event_id && metadata.canonical_checksum && metadata.watermark, "callback gets event/checksum/watermark metadata only");
  };
  const dispatcher = createConversationDeltaDispatcher({
    journal, consumerName: CONSUMER_NAME, ruleVersion: RULE_VERSION, stage,
  });
  const run = await dispatcher.run({ limit: 10 });
  assert.equal(run.dispatched, 2);
  assert.equal(run.failures, 0);
  assert.equal(run.cursor, second.json.sequence, "cursor advances to the last dispatched event");
  assert.equal(seen.length, 2);
  for (const metadata of seen) {
    assert.ok(metadata.event_id === first.json.event_id || metadata.event_id === second.json.event_id);
  }

  const rerun = await dispatcher.run({ limit: 10 });
  assert.equal(rerun.dispatched, 0, "replaying the same events dispatches nothing new");
  assert.equal(rerun.cursor, second.json.sequence);

  // A failing staging callback must NOT advance the persisted cursor.
  const failing = createConversationDeltaDispatcher({
    journal, consumerName: CONSUMER_NAME, ruleVersion: RULE_VERSION,
    stage: async () => { throw new Error("staging failure"); },
  });
  const three = committedDeltaBody({ idempotency_key: "pi-idem-dispatch-003" });
  const third = await requestJson(port, "POST", INTERNAL_ROUTE, three, { "x-pi-internal-capability": INTERNAL_CAPABILITY });
  assert.equal(third.status, 201);
  const failedRun = await failing.run({ limit: 10 });
  assert.ok(failedRun.failures >= 1, "staging failure must be reported");
  assert.equal(failedRun.cursor, second.json.sequence, "cursor must not advance past a failed guarded dispatch");
  assert.equal(consumerCheckpoint(journal, CONSUMER_NAME).sequence, second.json.sequence, "failure checkpoint retention keeps the last successful cursor");

  // Restart: a fresh dispatcher (same journal) resumes from the persisted cursor.
  const restarted = createConversationDeltaDispatcher({
    journal, consumerName: CONSUMER_NAME, ruleVersion: RULE_VERSION,
    stage: async (metadata) => { seen.push(metadata); },
  });
  const restartRun = await restarted.run({ limit: 10 });
  assert.equal(restartRun.dispatched, 1, "restart resumes replay from the persisted cursor");
  assert.equal(restartRun.cursor, third.json.sequence);
  assert.equal(seen.at(-1).event_id, third.json.event_id, "the third event is delivered exactly once after restart");
  journal.close();
});
