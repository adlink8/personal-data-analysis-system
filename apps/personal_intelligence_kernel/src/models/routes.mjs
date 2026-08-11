import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { readProviderConfig } from "./persistent-config.mjs";

export const MODEL_ROUTE_SCHEMA = "pi_model_routes_v1";

// Budget defaults fall back to the governance manifest
// (governance/manifests/ai/pi-model-routes.json) so operators tune budgets in
// files, not code. The embedded table below is only a last-resort default when
// the manifest is missing or malformed; it mirrors the manifest values today.
const EMBEDDED_ROUTE_BUDGETS = Object.freeze({
  structured_analysis: Object.freeze({ max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  guarded_generation: Object.freeze({ max_output_tokens: 2048, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  extraction_summary: Object.freeze({ max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  generic_generation: Object.freeze({ max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  conversation_summary: Object.freeze({ max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  memory_candidate_extraction: Object.freeze({ max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
  memory_repair: Object.freeze({ max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true }),
});

const DEFAULT_MODEL_ROUTES_MANIFEST = resolve(
  import.meta.dirname,
  "../../../../governance/manifests/ai/pi-model-routes.json",
);

/** Read the pi-model-routes manifest as the per-purpose budget fallback. */
export function loadModelRouteManifest({ manifestPath = process.env.PI_MODEL_ROUTES_MANIFEST } = {}) {
  const path = resolve(String(manifestPath || DEFAULT_MODEL_ROUTES_MANIFEST));
  if (!existsSync(path)) return {};
  try {
    const value = JSON.parse(readFileSync(path, "utf8"));
    if (!value || value.schema !== "pi-model-routes-v1" || !Array.isArray(value.routes)) return {};
    const result = {};
    for (const entry of value.routes) {
      if (!entry || typeof entry !== "object" || typeof entry.purpose !== "string" || !entry.purpose) continue;
      const budget = {};
      const maxOutputTokens = Number(entry.max_output_tokens);
      if (Number.isFinite(maxOutputTokens) && maxOutputTokens > 0) budget.max_output_tokens = maxOutputTokens;
      const costCeiling = Number(entry.cost_ceiling);
      if (Number.isFinite(costCeiling) && costCeiling >= 0) budget.cost_ceiling = costCeiling;
      const maxAttempts = Number(entry.max_attempts);
      if (Number.isInteger(maxAttempts) && maxAttempts >= 1 && maxAttempts <= 3) budget.max_attempts = maxAttempts;
      budget.no_fallback = Boolean(entry.no_fallback);
      result[entry.purpose] = budget;
    }
    return result;
  } catch {
    return {};
  }
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function numberAtLeast(min, ...values) {
  for (const value of values) {
    if (value === undefined || value === null || value === "") continue;
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed >= min) return parsed;
  }
  return undefined;
}

function attemptsInteger(...values) {
  for (const value of values) {
    if (value === undefined || value === null || value === "") continue;
    const parsed = Number(value);
    if (Number.isInteger(parsed) && parsed >= 1 && parsed <= 3) return parsed;
  }
  return undefined;
}

function booleanValue(...values) {
  for (const value of values) {
    if (value === undefined || value === null || value === "") continue;
    if (typeof value === "boolean") return value;
    const normalized = String(value).trim().toLowerCase();
    if (normalized === "1" || normalized === "true") return true;
    if (normalized === "0" || normalized === "false") return false;
  }
  return undefined;
}

/**
 * Build the frozen route table.
 *
 * Budget precedence (highest first): per-route env is not supported, so
 * 1. global env (PI_PROVIDER_MAX_OUTPUT_TOKENS / _MAX_ATTEMPTS / _NO_FALLBACK)
 * 2. pi-provider.json per-purpose `routes.<purpose>` override
 * 3. pi-provider.json global keys (max_output_tokens / max_attempts / no_fallback)
 * 4. governance manifest fallback (governance/manifests/ai/pi-model-routes.json)
 * 5. embedded last-resort constants
 * cost_ceiling additionally follows the existing PI_PROVIDER_COST_CEILING env
 * chain and stays 0 in replay mode.
 */
export function buildModelRoutes({ manifest = {}, config = {}, env = process.env } = {}) {
  const configuredMode = String(env.PI_PROVIDER_MODE ?? config.mode ?? "").trim().toLowerCase();
  const vertexProviderEnabled = ["vertex_google", "vertex", "gemini"].includes(configuredMode);
  const openaiCompatibleEnabled = ["openai", "openai-compatible"].includes(configuredMode);
  const realProviderEnabled = ["aliyun", "dashscope"].includes(configuredMode) || openaiCompatibleEnabled || vertexProviderEnabled;
  const realModel = String(env.PI_PROVIDER_MODEL ?? (vertexProviderEnabled ? env.PERSONAL_DATA_VERTEX_MODEL : config.model) ?? (vertexProviderEnabled ? "gemini-3.5-flash" : "deepseek-v4-flash-0731")).trim() || (vertexProviderEnabled ? "gemini-3.5-flash" : "deepseek-v4-flash-0731");
  const realCostCeiling = Number(env.PI_PROVIDER_COST_CEILING ?? config.costCeiling ?? 0);
  const globalCostCeiling = Number.isFinite(realCostCeiling) && realCostCeiling >= 0 ? realCostCeiling : 0;
  const provider = vertexProviderEnabled ? "vertex_google" : realProviderEnabled ? (openaiCompatibleEnabled ? "openai-compatible" : "dashscope") : "replay";
  const model = realProviderEnabled ? realModel : "replay-v1";
  const currency = realProviderEnabled ? (vertexProviderEnabled ? "USD" : (config.currency || "CNY")) : "CNY";
  const inputPricePerMillion = realProviderEnabled ? Number(config.inputPricePerMillion ?? 1) : 0;
  const outputPricePerMillion = realProviderEnabled ? Number(config.outputPricePerMillion ?? 2) : 0;
  const supportsStructuredOutput = !realProviderEnabled;

  const globalEnv = {
    max_output_tokens: env.PI_PROVIDER_MAX_OUTPUT_TOKENS,
    max_attempts: env.PI_PROVIDER_MAX_ATTEMPTS,
    no_fallback: env.PI_PROVIDER_NO_FALLBACK,
  };

  const routes = {};
  for (const purpose of Object.keys(EMBEDDED_ROUTE_BUDGETS)) {
    const embedded = EMBEDDED_ROUTE_BUDGETS[purpose];
    const fromManifest = manifest[purpose] ?? {};
    const fromConfig = config.routeOverrides?.[purpose] ?? {};
    routes[purpose] = Object.freeze({
      purpose,
      provider,
      model,
      timeout_ms: numberAtLeast(1000, fromConfig.timeout_ms, config.timeoutMs, fromManifest.timeout_ms, embedded.timeout_ms) ?? 30000,
      max_input_tokens: 4096,
      max_output_tokens: numberAtLeast(1, globalEnv.max_output_tokens, fromConfig.max_output_tokens, config.maxOutputTokens, fromManifest.max_output_tokens, embedded.max_output_tokens) ?? 4096,
      cost_ceiling: realProviderEnabled ? (numberAtLeast(0, fromConfig.cost_ceiling, globalCostCeiling, fromManifest.cost_ceiling, embedded.cost_ceiling) ?? 0) : 0,
      currency,
      input_price_per_million: inputPricePerMillion,
      output_price_per_million: outputPricePerMillion,
      structured_output: supportsStructuredOutput,
      max_attempts: attemptsInteger(globalEnv.max_attempts, fromConfig.max_attempts, config.maxAttempts, fromManifest.max_attempts, embedded.max_attempts) ?? 1,
      retryable_codes: [],
      no_fallback: booleanValue(globalEnv.no_fallback, fromConfig.no_fallback, config.noFallback, fromManifest.no_fallback, embedded.no_fallback) ?? true,
    });
  }
  return Object.freeze(routes);
}

const PERSISTED_CONFIG = readProviderConfig();
const MODEL_ROUTE_MANIFEST = loadModelRouteManifest();

export const MODEL_ROUTES = buildModelRoutes({
  manifest: MODEL_ROUTE_MANIFEST,
  config: PERSISTED_CONFIG,
  env: process.env,
});

export const routeChecksum = (route) => createHash("sha256").update(JSON.stringify(route, Object.keys(route).sort())).digest("hex");
export function getModelRoute(purpose, model = undefined) { const route = MODEL_ROUTES[purpose]; if (!route || (model && model !== route.model)) throw new Error("model_route_unknown"); return Object.freeze({ ...route, route_checksum: routeChecksum(route) }); }
export const resolveModelRoute = getModelRoute;
