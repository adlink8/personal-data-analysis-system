import { createHash } from "node:crypto";

export const MODEL_ROUTE_SCHEMA = "pi_model_routes_v1";
export const MODEL_ROUTES = Object.freeze({
  structured_analysis: Object.freeze({ purpose: "structured_analysis", provider: "replay", model: "replay-v1", timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
  guarded_generation: Object.freeze({ purpose: "guarded_generation", provider: "replay", model: "replay-v1", timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 2048, cost_ceiling: 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
  extraction_summary: Object.freeze({ purpose: "extraction_summary", provider: "replay", model: "replay-v1", timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
});
export const routeChecksum = (route) => createHash("sha256").update(JSON.stringify(route, Object.keys(route).sort())).digest("hex");
export function getModelRoute(purpose, model = undefined) { const route = MODEL_ROUTES[purpose]; if (!route || (model && model !== route.model)) throw new Error("model_route_unknown"); return Object.freeze({ ...route, route_checksum: routeChecksum(route) }); }
export const resolveModelRoute = getModelRoute;
