import { request } from "node:http";

export const PI_DOMAIN_TOOL_REGISTRY = Object.freeze({
  domain_inspect: Object.freeze({ operation: "domain.inspect", method: "GET" }),
  domain_candidate: Object.freeze({ operation: "domain.candidate", method: "GET" }),
  session_preview: Object.freeze({ operation: "session.preview", method: "POST" }),
  session_confirm: Object.freeze({ operation: "session.confirm", method: "POST" }),
});

export class DomainBridgeError extends Error { constructor(code, message = code) { super(message); this.name = "DomainBridgeError"; this.code = code; } }

function validateInput(toolName, input) {
  const spec = PI_DOMAIN_TOOL_REGISTRY[toolName];
  if (!spec) throw new DomainBridgeError("unknown_tool");
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new DomainBridgeError("invalid_input");
  const allowed = new Set(["task_id", "idempotency_key", "binding", "evidence_refs", "proposal", "session_id", "transition", "payload", "actor_identity_hash", "expected_sequence", "now", "preview", "confirmation_token", "confirmed"]);
  if (Object.keys(input).some((key) => !allowed.has(key))) throw new DomainBridgeError("undeclared_input");
  if (!input.task_id || !input.idempotency_key || !input.binding) throw new DomainBridgeError("binding_required");
  if (spec.operation === "session.preview" && (!input.session_id || !input.transition)) throw new DomainBridgeError("session_binding_required");
  if (spec.operation === "session.confirm" && (!input.preview || input.confirmed !== true)) throw new DomainBridgeError("confirmation_required");
  return spec;
}

export function createDomainBridge({ host = "127.0.0.1", port = 8000, capability, timeoutMs = 3000, transport } = {}) {
  const call = transport ?? (({ path, body }) => new Promise((resolve, reject) => {
    const req = request({ host, port, method: "POST", path, headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body), "X-PI-Domain-Capability": capability ?? "" } }, (res) => { const chunks = []; res.on("data", (chunk) => chunks.push(chunk)); res.on("end", () => { try { resolve({ status: res.statusCode, body: JSON.parse(Buffer.concat(chunks).toString("utf8")) }); } catch { reject(new DomainBridgeError("invalid_response")); } }); });
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new DomainBridgeError("timeout")); }); req.on("error", reject); req.end(body);
  }));
  return Object.freeze({
    async invoke(toolName, input = {}) {
      const spec = validateInput(toolName, input);
      const result = await call({ path: "/internal/pi-domain/dispatch", body: JSON.stringify({ operation: spec.operation, params: input }) });
      if (!result?.body || result.body.ok !== true) throw new DomainBridgeError(result?.body?.error?.code ?? "domain_unavailable");
      return result.body;
    },
    tools() { return Object.keys(PI_DOMAIN_TOOL_REGISTRY); },
  });
}

export const createPiDomainBridge = createDomainBridge;
