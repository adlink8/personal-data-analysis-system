import { createHash } from "node:crypto";
import { readProviderConfig } from "./persistent-config.mjs";

export const MODEL_ROUTE_SCHEMA = "pi_model_routes_v1";
const PERSISTED_CONFIG = readProviderConfig();
const CONFIGURED_MODE = String(process.env.PI_PROVIDER_MODE ?? PERSISTED_CONFIG.mode ?? "").trim().toLowerCase();
const REAL_PROVIDER_ENABLED = ["aliyun", "dashscope"].includes(CONFIGURED_MODE);
const REAL_MODEL = String(process.env.PI_PROVIDER_MODEL ?? PERSISTED_CONFIG.model ?? "deepseek-v4-flash-0731").trim() || "deepseek-v4-flash-0731";
const REAL_COST_CEILING = Number(process.env.PI_PROVIDER_COST_CEILING ?? PERSISTED_CONFIG.costCeiling ?? 0);
const costCeiling = Number.isFinite(REAL_COST_CEILING) && REAL_COST_CEILING >= 0 ? REAL_COST_CEILING : 0;
const provider = REAL_PROVIDER_ENABLED ? "dashscope" : "replay";
const model = REAL_PROVIDER_ENABLED ? REAL_MODEL : "replay-v1";

export const MODEL_ROUTES = Object.freeze({
  structured_analysis: Object.freeze({ purpose: "structured_analysis", provider, model, timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 1024, cost_ceiling: REAL_PROVIDER_ENABLED ? costCeiling : 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
  guarded_generation: Object.freeze({ purpose: "guarded_generation", provider, model, timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 2048, cost_ceiling: REAL_PROVIDER_ENABLED ? costCeiling : 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
  extraction_summary: Object.freeze({ purpose: "extraction_summary", provider, model, timeout_ms: 30000, max_input_tokens: 4096, max_output_tokens: 1024, cost_ceiling: REAL_PROVIDER_ENABLED ? costCeiling : 0, max_attempts: 1, retryable_codes: [], no_fallback: true }),
});
export const routeChecksum = (route) => createHash("sha256").update(JSON.stringify(route, Object.keys(route).sort())).digest("hex");
export function getModelRoute(purpose, model = undefined) { const route = MODEL_ROUTES[purpose]; if (!route || (model && model !== route.model)) throw new Error("model_route_unknown"); return Object.freeze({ ...route, route_checksum: routeChecksum(route) }); }
export const resolveModelRoute = getModelRoute;
