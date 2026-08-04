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
    if (!value || value.schema !== "pi-provider-config-v1" || value.provider !== "dashscope") return {};
    const mode = String(value.mode || "replay").trim().toLowerCase();
    const baseUrl = String(value.base_url || "").trim();
    const model = String(value.model || "").trim();
    const costCeiling = Number(value.cost_ceiling ?? 0);
    const inputPricePerMillion = Number(value.input_price_per_million ?? 1);
    const outputPricePerMillion = Number(value.output_price_per_million ?? 2);
    const currency = String(value.currency || "CNY").trim().toUpperCase();
    if (!["replay", "aliyun", "dashscope"].includes(mode) || !model || !Number.isFinite(costCeiling) || costCeiling < 0 || !Number.isFinite(inputPricePerMillion) || inputPricePerMillion < 0 || !Number.isFinite(outputPricePerMillion) || outputPricePerMillion < 0 || !currency) return {};
    return Object.freeze({
      mode,
      provider: "dashscope",
      baseUrl,
      model,
      costCeiling,
      inputPricePerMillion,
      outputPricePerMillion,
      currency,
      secretPath: absolutePath(value.secret_path, DEFAULT_PROVIDER_SECRET_PATH),
    });
  } catch {
    return {};
  }
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
