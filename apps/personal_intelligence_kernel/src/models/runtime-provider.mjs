import { ProviderAdapter, createReplayProviderAdapter } from "./provider-adapter.mjs";
import { createDashScopeTransport } from "./dashscope-transport.mjs";

/** Build the explicitly selected provider; replay remains the safe default. */
export function createConfiguredProviderAdapter({
  mode = process.env.PI_PROVIDER_MODE || "replay",
  apiKey = process.env.DASHSCOPE_API_KEY,
  baseUrl = process.env.PI_PROVIDER_BASE_URL,
  fetchImpl = globalThis.fetch,
} = {}) {
  const normalizedMode = String(mode).trim().toLowerCase();
  if (normalizedMode === "replay") return createReplayProviderAdapter();
  if (!["aliyun", "dashscope"].includes(normalizedMode)) throw new Error("provider_mode_unknown");
  return new ProviderAdapter({
    credentials: apiKey,
    transport: createDashScopeTransport({ apiKey, baseUrl, fetchImpl }),
  });
}
