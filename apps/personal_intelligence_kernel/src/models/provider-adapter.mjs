import { createHash } from "node:crypto";
import { getModelRoute } from "./routes.mjs";

export class ProviderAdapterError extends Error { constructor(code, message = code) { super(message); this.name = "ProviderAdapterError"; this.code = code; } }
const checksum = (value) => createHash("sha256").update(JSON.stringify(value, Object.keys(value ?? {}).sort())).digest("hex");

export class ProviderAdapter {
  constructor({ credentials, transport, replay = false } = {}) { this.credentials = credentials; this.transport = transport; this.replay = replay; this.providerCalls = 0; this.spentCost = 0; this.outcomeUnknown = new Set(); }
  async generate({ purpose, model, prompt, task_id, session_id, event_id, idempotency_key, max_output_tokens } = {}) {
    const route = getModelRoute(purpose, model);
    if (!prompt || !task_id || !session_id || !idempotency_key) throw new ProviderAdapterError("identity_required");
    if (max_output_tokens != null && max_output_tokens > route.max_output_tokens) throw new ProviderAdapterError("provider_budget_exceeded");
    if (!this.replay && !this.credentials) throw new ProviderAdapterError("provider_credential_missing");
    if (this.outcomeUnknown.has(idempotency_key)) throw new ProviderAdapterError("outcome_unknown_reconcile_required");
    const request = { purpose, model: route.model, prompt, prompt_ref: checksum({ prompt }), task_id, session_id, event_id: event_id ?? null, idempotency_key, max_output_tokens: max_output_tokens ?? route.max_output_tokens };
    let response;
    if (this.replay) response = { payload: { replay: true, purpose, request_checksum: checksum(request) }, usage: { input_tokens: 1, output_tokens: 1 }, provider: "replay", model: route.model };
    else { if (typeof this.transport !== "function") throw new ProviderAdapterError("provider_transport_missing"); this.providerCalls += 1; response = await this.transport(request, route); }
    if (!response || !response.payload || typeof response.payload !== "object") throw new ProviderAdapterError("provider_response_invalid");
    const usage = { input_tokens: Number(response.usage?.input_tokens ?? 0), output_tokens: Number(response.usage?.output_tokens ?? 0) };
    const cost = Number(response.cost ?? 0);
    if (!Number.isFinite(cost) || cost < 0) throw new ProviderAdapterError("provider_cost_invalid");
    if (route.cost_ceiling > 0 && this.spentCost + cost > route.cost_ceiling) throw new ProviderAdapterError("provider_cost_ceiling_exceeded");
    this.spentCost += cost;
    return Object.freeze({ schema_version: "pi_provider_receipt_v1", task_id, session_id, event_id: event_id ?? null, idempotency_key, route_checksum: route.route_checksum, response: response.payload, response_checksum: checksum(response.payload), usage, usage_checksum: checksum(usage), telemetry: { provider: response.provider ?? route.provider, model: response.model ?? route.model, status: "completed", cost, currency: response.currency ?? route.currency ?? "CNY" } });
  }
  markOutcomeUnknown(idempotencyKey) { this.outcomeUnknown.add(idempotencyKey); }
  reconcile(idempotencyKey) { this.outcomeUnknown.delete(idempotencyKey); return { idempotency_key: idempotencyKey, reconciled: true }; }
}
export function createReplayProviderAdapter() { return new ProviderAdapter({ replay: true }); }
