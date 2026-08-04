import { once } from "node:events";

export const DEFAULT_SSE_POLL_INTERVAL_MS = 50;
export const DEFAULT_SSE_HEARTBEAT_INTERVAL_MS = 15000;
export const MAX_SSE_HEARTBEAT_BYTES = 256;

export class SseTransportError extends Error {
  constructor(code) {
    super(code);
    this.name = "SseTransportError";
    this.code = code;
  }
}

function safeCursorError(code) {
  return new SseTransportError(code);
}

function parseLastEventId(value, journal) {
  const cursor = String(value ?? "").trim();
  if (!cursor) return 0;
  if (/^\d+$/.test(cursor)) {
    const sequence = Number(cursor);
    if (Number.isSafeInteger(sequence) && sequence >= 0) return sequence;
    throw safeCursorError("invalid_cursor");
  }
  if (!/^pi_evt_[a-f0-9]{64}$/.test(cursor)) throw safeCursorError("invalid_cursor");
  const row = journal.getByEventId(cursor);
  if (!row) throw safeCursorError("cursor_not_found");
  return row.sequence;
}

function sseWrite(response, value) {
  if (response.destroyed || response.writableEnded) return false;
  try {
    response.write(value);
    return true;
  } catch {
    return false;
  }
}

export function writeSseRecord(response, row) {
  const data = JSON.stringify({
    sequence: row.sequence,
    event: row.event,
    event_id: row.event_id,
    occurred_at: row.occurred_at,
  });
  return sseWrite(response, `id: ${row.event_id}\nevent: kernel-event\ndata: ${data}\n\n`);
}

export function writeSseHeartbeat(response, latestSequence) {
  const data = JSON.stringify({
    status: "alive",
    latest_sequence: Number.isSafeInteger(latestSequence) ? latestSequence : 0,
  });
  if (Buffer.byteLength(data) > MAX_SSE_HEARTBEAT_BYTES) return false;
  return sseWrite(response, `event: heartbeat\ndata: ${data}\n\n`);
}

async function flushReplay(response, journal, state) {
  let replay;
  do {
    replay = journal.replay(state.sequence, 100);
    for (const row of replay.events) {
      if (!writeSseRecord(response, row)) return false;
      state.sequence = row.sequence;
    }
  } while (replay.has_more);
  return true;
}

function boundedInterval(value, fallback, minimum, maximum) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(maximum, Math.max(minimum, Math.floor(number)));
}

/**
 * Serve one durable journal cursor as an SSE stream. The stream is deliberately
 * polling-based: SQLite sequence is the source of truth across process restarts.
 */
export async function streamJournalAsSse({ request, response, journal, pollIntervalMs, heartbeatIntervalMs }) {
  const sequence = parseLastEventId(request.headers["last-event-id"], journal);
  const state = { sequence };
  const pollMs = boundedInterval(pollIntervalMs, DEFAULT_SSE_POLL_INTERVAL_MS, 10, 1000);
  const heartbeatMs = boundedInterval(heartbeatIntervalMs, DEFAULT_SSE_HEARTBEAT_INTERVAL_MS, 1000, 60000);

  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });
  response.flushHeaders?.();
  if (!writeSseHeartbeat(response, journal.latestSequence())) return;
  if (!(await flushReplay(response, journal, state))) return;

  let stopped = false;
  let polling = false;
  let lastHeartbeatAt = Date.now();
  const stop = () => {
    stopped = true;
    clearInterval(pollTimer);
    clearInterval(heartbeatTimer);
  };
  request.once("aborted", stop);
  request.once("close", stop);
  response.once("close", stop);

  const pollTimer = setInterval(async () => {
    if (stopped || polling || response.destroyed || response.writableEnded) return;
    polling = true;
    try {
      if (!(await flushReplay(response, journal, state))) stop();
    } catch {
      stop();
      try { response.destroy(); } catch { /* bounded stream cleanup */ }
    } finally {
      polling = false;
    }
  }, pollMs);
  const heartbeatTimer = setInterval(() => {
    if (stopped || response.destroyed || response.writableEnded) return;
    const now = Date.now();
    if (now - lastHeartbeatAt < heartbeatMs) return;
    lastHeartbeatAt = now;
    if (!writeSseHeartbeat(response, journal.latestSequence())) stop();
  }, heartbeatMs);
  pollTimer.unref?.();
  heartbeatTimer.unref?.();

  // Keep the request handler alive while the timers own the stream. This also
  // gives tests and graceful shutdown a single promise to await when desired.
  await once(request, "close").catch(() => undefined);
  stop();
}

export const serveJournalSse = streamJournalAsSse;
