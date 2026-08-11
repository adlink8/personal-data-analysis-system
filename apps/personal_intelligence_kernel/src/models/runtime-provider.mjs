import { ProviderAdapter, createReplayProviderAdapter } from "./provider-adapter.mjs";
import { createDashScopeTransport } from "./dashscope-transport.mjs";
import { createVertexGoogleTransport } from "./vertex-google-transport.mjs";
import { readPersistedDashScopeApiKey, readProviderConfig } from "./persistent-config.mjs";

/** Build the explicitly selected provider; replay remains the safe default. */
export function createConfiguredProviderAdapter({
  mode,
  apiKey,
  baseUrl,
  fetchImpl,
} = {}) {
  const config = readProviderConfig();
  const normalizedMode = String(mode ?? process.env.PI_PROVIDER_MODE ?? config.mode ?? "replay").trim().toLowerCase();
  if (normalizedMode === "replay") return createReplayProviderAdapter();
  if (["vertex_google", "vertex", "gemini"].includes(normalizedMode)) {
    return new ProviderAdapter({
      credentials: "gcloud",
      transport: createVertexGoogleTransport({
        project: process.env.PERSONAL_DATA_GCP_PROJECT,
        location: process.env.PERSONAL_DATA_VERTEX_LOCATION,
        model: process.env.PERSONAL_DATA_VERTEX_MODEL ?? process.env.PI_PROVIDER_MODEL,
        gcloudExecutable: process.env.PERSONAL_DATA_GCLOUD,
        fetchImpl,
      }),
    });
  }
  if (!["aliyun", "dashscope", "openai", "openai-compatible"].includes(normalizedMode)) throw new Error("provider_mode_unknown");
  const configuredKey = apiKey ?? process.env.DASHSCOPE_API_KEY ?? config.apiKey ?? readPersistedDashScopeApiKey({ secretPath: config.secretPath });
  return new ProviderAdapter({
    credentials: configuredKey,
    // dashscope/aliyun and any generic OpenAI-compatible endpoint share the
    // Chat Completions transport; baseUrl comes from the argument, env or the
    // persisted config (dashscope's default endpoint stays the fallback).
    transport: createDashScopeTransport({ apiKey: configuredKey, baseUrl: baseUrl ?? process.env.PI_PROVIDER_BASE_URL ?? config.baseUrl, fetchImpl: fetchImpl ?? globalThis.fetch }),
  });
}
