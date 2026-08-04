import { ProviderAdapter, createReplayProviderAdapter } from "./provider-adapter.mjs";
import { createDashScopeTransport } from "./dashscope-transport.mjs";
import { readPersistedDashScopeApiKey, readProviderConfig } from "./persistent-config.mjs";

/** Build the explicitly selected provider; replay remains the safe default. */
export function createConfiguredProviderAdapter({
  mode,
  apiKey,
  baseUrl,
  fetchImpl = globalThis.fetch,
} = {}) {
  const config = readProviderConfig();
  const normalizedMode = String(mode ?? process.env.PI_PROVIDER_MODE ?? config.mode ?? "replay").trim().toLowerCase();
  if (normalizedMode === "replay") return createReplayProviderAdapter();
  if (!["aliyun", "dashscope"].includes(normalizedMode)) throw new Error("provider_mode_unknown");
  const configuredKey = apiKey ?? process.env.DASHSCOPE_API_KEY ?? readPersistedDashScopeApiKey({ secretPath: config.secretPath });
  return new ProviderAdapter({
    credentials: configuredKey,
    transport: createDashScopeTransport({ apiKey: configuredKey, baseUrl: baseUrl ?? process.env.PI_PROVIDER_BASE_URL ?? config.baseUrl, fetchImpl }),
  });
}
