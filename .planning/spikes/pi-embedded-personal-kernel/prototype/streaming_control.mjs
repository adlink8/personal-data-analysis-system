// Spike 005: SSE-style cursor replay and safe control projection.

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

class EventStream {
  constructor(retention = 32) { this.retention = retention; this.events = []; this.nextSeq = 1; }
  append(type, summary, taskId = "task-005") {
    if (/secret|token|provider_body|raw_input/i.test(summary)) throw new Error("unsafe summary");
    const event = { sequence: this.nextSeq++, event_id: `evt-${this.nextSeq - 1}`, task_id: taskId, type, summary };
    this.events.push(event);
    if (this.events.length > this.retention) this.events.shift();
    return event;
  }
  replay(after = 0) {
    const earliest = this.events[0]?.sequence ?? this.nextSeq;
    if (after && after < earliest - 1) return { gap: true, events: [] };
    return { gap: false, events: this.events.filter((event) => event.sequence > after) };
  }
}

class Projection {
  constructor() { this.lastSequence = 0; this.seen = new Set(); this.state = "idle"; this.events = []; }
  apply(event) {
    if (this.seen.has(event.event_id)) return "duplicate";
    if (event.sequence <= this.lastSequence) return "out_of_order";
    this.seen.add(event.event_id);
    this.lastSequence = event.sequence;
    this.events.push(event);
    if (["started", "tool_started"].includes(event.type)) this.state = "running";
    if (["cancelled", "failed", "completed"].includes(event.type)) this.state = event.type;
    return "applied";
  }
}

const stream = new EventStream();
const projection = new Projection();
for (const [type, summary] of [
  ["started", "Task accepted"],
  ["tool_started", "Inspecting synthetic Delta"],
  ["candidate_created", "Candidate staged for evaluation"],
  ["completed", "Evaluation completed"],
]) projection.apply(stream.append(type, summary));

const duplicate = projection.apply({ ...stream.events[1] });
const reconnect = stream.replay(1);
for (const event of reconnect.events) projection.apply(event);
const cancel = { task_id: "task-005", task_version: 1, command: "cancel", args_checksum: "synthetic" };
const cancelAccepted = cancel.command === "cancel" && cancel.task_version === 1;
projection.apply(stream.append("cancelled", "Cancellation acknowledged"));

const uiPath = join(dirname(fileURLToPath(import.meta.url)), "ui", "index.html");
const html = await readFile(uiPath, "utf8");
const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url?.startsWith("/events")) {
    const after = Number(new URL(req.url, "http://127.0.0.1").searchParams.get("after") || 0);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(stream.replay(after)));
    return;
  }
  if (req.method === "POST" && req.url === "/control") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ accepted: cancelAccepted, command: cancel.command }));
    return;
  }
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(html);
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const base = `http://127.0.0.1:${address.port}`;
const rootResponse = await fetch(`${base}/`);
const eventsResponse = await fetch(`${base}/events?after=1`);
const controlResponse = await fetch(`${base}/control`, { method: "POST" });
server.close();

const report = {
  transport: "SSE-style cursor replay; control over POST",
  ui_served: rootResponse.status === 200 && html.includes("Cancel task"),
  replay: { gap: reconnect.gap, count: reconnect.events.length, last_event_id: reconnect.events.at(-1)?.event_id },
  duplicate_delivery: duplicate,
  projection: { state: projection.state, last_sequence: projection.lastSequence, applied_events: projection.events.length },
  cancel: { accepted: cancelAccepted, response_status: controlResponse.status },
  safe_payload: !/secret|token|provider_body|raw_input/i.test(JSON.stringify(stream.events)),
  http_replay_status: eventsResponse.status,
  legacy_comparison: { status: "not_measured", reason: "quality/cost needs a real baseline window" },
};
console.log(JSON.stringify(report, null, 2));
if (!report.ui_served || !report.safe_payload || duplicate !== "duplicate" || !cancelAccepted || reconnect.gap) process.exitCode = 1;
