import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

export const DEFAULT_PROVIDER_CONFIG_PATH = "var/config/pi-provider.json";
export const DEFAULT_PROVIDER_SECRET_PATH = "var/secrets/dashscope.api.dpapi.txt";

function absolutePath(value, fallback) {
  return resolve(String(value || fallback));
}

/** Read non-secret Pi provider settings. Invalid/missing local config fails closed. */
export function readProviderConfig({ configPath = process.env.PI_PROVIDER_CONFIG } = {}) {
  const path = absolutePath(configPath, DEFAULT_PROVIDER_CONFIG_PATH);
  if (!existsSync(path)) return {};
  try {
    const value = JSON.parse(readFileSync(path, "utf8"));
    if (!value || value.schema !== "pi-provider-config-v1") return {};
    // provider identity: dashscope (legacy) or a generic OpenAI-compatible
    // endpoint. Anything else is rejected (no authority to guess).
    const provider = String(value.provider ?? "dashscope").trim().toLowerCase();
    if (!["dashscope", "openai-compatible"].includes(provider)) return {};
    const mode = String(value.mode || "replay").trim().toLowerCase();
    const baseUrl = String(value.base_url || "").trim();
    const model = String(value.model || "").trim();
    // Plaintext API key support (2026-08-11): the key is stored directly in the
    // config file instead of DPAPI-encrypted secret_path. Read at construction;
    // never included in receipts or errors.
    const apiKey = typeof value.api_key === "string" && value.api_key.trim() ? value.api_key.trim() : undefined;
    const costCeiling = Number(value.cost_ceiling ?? 0);
    const inputPricePerMillion = Number(value.input_price_per_million ?? 1);
    const outputPricePerMillion = Number(value.output_price_per_million ?? 2);
    const currency = String(value.currency || "CNY").trim().toUpperCase();
    if (!["replay", "aliyun", "dashscope", "openai", "openai-compatible"].includes(mode) || !model || !Number.isFinite(costCeiling) || costCeiling < 0 || !Number.isFinite(inputPricePerMillion) || inputPricePerMillion < 0 || !Number.isFinite(outputPricePerMillion) || outputPricePerMillion < 0 || !currency) return {};
    // Optional route budget overrides. Each field is validated independently so
    // a single malformed entry falls back to the manifest/embedded default
    // instead of invalidating the whole provider config.
    const maxOutputTokens = positiveNumber(value.max_output_tokens);
    const maxAttempts = attemptsInteger(value.max_attempts);
    const noFallback = value.no_fallback == null ? undefined : Boolean(value.no_fallback);
    const timeoutMs = positiveNumber(value.timeout_ms);
    const routeOverrides = {};
    if (value.routes && typeof value.routes === "object" && !Array.isArray(value.routes)) {
      for (const [purpose, entry] of Object.entries(value.routes)) {
        if (!entry || typeof entry !== "object") continue;
        const override = {};
        if (entry.max_output_tokens != null) { const parsed = positiveNumber(entry.max_output_tokens); if (parsed !== undefined) override.max_output_tokens = parsed; }
        if (entry.max_attempts != null) { const parsed = attemptsInteger(entry.max_attempts); if (parsed !== undefined) override.max_attempts = parsed; }
        if (entry.no_fallback != null) override.no_fallback = Boolean(entry.no_fallback);
        if (entry.cost_ceiling != null) { const parsed = nonNegativeNumber(entry.cost_ceiling); if (parsed !== undefined) override.cost_ceiling = parsed; }
        if (entry.timeout_ms != null) { const parsed = positiveNumber(entry.timeout_ms); if (parsed !== undefined) override.timeout_ms = parsed; }
        if (Object.keys(override).length > 0) routeOverrides[purpose] = Object.freeze(override);
      }
    }
    return Object.freeze({
      mode,
      provider,
      baseUrl,
      model,
      costCeiling,
      inputPricePerMillion,
      outputPricePerMillion,
      currency,
      apiKey,
      secretPath: absolutePath(value.secret_path, DEFAULT_PROVIDER_SECRET_PATH),
      maxOutputTokens,
      maxAttempts,
      noFallback,
      timeoutMs,
      routeOverrides,
    });
  } catch {
    return {};
  }
}

/** Optional positive finite number; undefined when absent or invalid. */
function positiveNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

/** Optional integer within the safe retry window; undefined when invalid. */
function attemptsInteger(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 3 ? parsed : undefined;
}

/** Optional non-negative finite number; undefined when invalid. */
function nonNegativeNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

/** Decrypt a Windows DPAPI SecureString file only in memory; never logs the plaintext. */
export function readPersistedDashScopeApiKey({ secretPath } = {}) {
  const config = readProviderConfig();
  const path = absolutePath(secretPath, config.secretPath || DEFAULT_PROVIDER_SECRET_PATH);
  if (!existsSync(path)) return undefined;
  const encrypted = readFileSync(path, "utf8").trim();
  if (!encrypted) return undefined;
  const script = [
    "$encrypted = [Console]::In.ReadToEnd().Trim()",
    "$secure = ConvertTo-SecureString -String $encrypted",
    "$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)",
    "try { [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }",
  ].join("; ");
  try {
    const value = execFileSync("pwsh", ["-NoProfile", "-NonInteractive", "-Command", script], {
      input: `${encrypted}\n`,
      encoding: "utf8",
      timeout: 5000,
      windowsHide: true,
      stdio: ["pipe", "pipe", "ignore"],
    }).trim();
    return value || undefined;
  } catch {
    return undefined;
  }
}
