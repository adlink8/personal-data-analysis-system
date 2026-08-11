import { ProviderAdapterError } from "./provider-adapter.mjs";
import { readProviderConfig } from "./persistent-config.mjs";

export const DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";

function completionUrl(baseUrl) {
  let parsed;
  try {
    parsed = new URL(String(baseUrl || DEFAULT_DASHSCOPE_BASE_URL));
  } catch {
    throw new ProviderAdapterError("provider_endpoint_invalid");
  }
  if (parsed.protocol !== "https:") throw new ProviderAdapterError("provider_endpoint_invalid");
  const path = parsed.pathname.replace(/\/+$/, "");
  parsed.pathname = path.endsWith("/chat/completions") ? path : `${path}/chat/completions`;
  return parsed.toString();
}

function safeHttpCode(status) {
  return Number.isInteger(status) && status >= 400 && status <= 599 ? `provider_http_${status}` : "provider_http_error";
}

/**
 * DashScope OpenAI-compatible Chat Completions transport.
 * The key is read at construction time and is never included in receipts or errors.
 */
export function createDashScopeTransport({
  apiKey = process.env.DASHSCOPE_API_KEY,
  baseUrl = process.env.PI_PROVIDER_BASE_URL || readProviderConfig().baseUrl || DEFAULT_DASHSCOPE_BASE_URL,
  fetchImpl = globalThis.fetch,
} = {}) {
  const endpoint = completionUrl(baseUrl);
  return async (request, route) => {
    if (!apiKey) throw new ProviderAdapterError("provider_credential_missing");
    if (typeof fetchImpl !== "function") throw new ProviderAdapterError("provider_transport_missing");
    if (!request?.prompt) throw new ProviderAdapterError("provider_request_invalid");

    const controller = new AbortController();
    const persisted = readProviderConfig();
    const timeoutMs = Number(route?.timeout_ms ?? 30000);
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    let response;
    try {
      response = await fetchImpl(endpoint, {
        method: "POST",
        headers: {
          authorization: `Bearer ${apiKey}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          model: request.model,
          messages: [
            ...(route?.structured_output === false ? [{ role: "system", content: "Return exactly one valid JSON object. Do not use Markdown fences or add commentary." }] : []),
            { role: "user", content: request.prompt },
          ],
          temperature: 0.2,
          max_tokens: request.max_output_tokens,
          enable_thinking: false,
          // Thinking models (deepseek-v4-flash) honor Anthropic-style
          // thinking.disabled; both flags are sent so fast direct responses
          // are possible instead of reasoning-token-heavy output.
          thinking: { type: "disabled" },
          ...(route?.structured_output === true ? { response_format: { type: "json_object" } } : {}),
        }),
        signal: controller.signal,
      });
    } catch (error) {
      if (error?.name === "AbortError") throw new ProviderAdapterError("provider_timeout");
      throw new ProviderAdapterError("provider_transport_error");
    } finally {
      clearTimeout(timeout);
    }

    let raw;
    try {
      raw = await response.json();
    } catch {
      throw new ProviderAdapterError("provider_response_invalid");
    }
    if (!response.ok) throw new ProviderAdapterError(safeHttpCode(response.status));

    try {
      const content = raw.choices[0].message.content;
      // Thinking models (deepseek-v4-flash etc.) return natural-language text,
      // not JSON. Prefer JSON when the model emits it; otherwise wrap the text
      // so the payload stays an object (provider-adapter requires object).
      let payload;
      if (typeof content === "string") {
        try {
          payload = JSON.parse(content);
        } catch {
          payload = { content };
        }
      } else {
        payload = content;
      }
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("payload");
      const inputTokens = Number(raw.usage?.prompt_tokens ?? 0);
      const outputTokens = Number(raw.usage?.completion_tokens ?? 0);
      const inputPrice = Number(route?.input_price_per_million ?? persisted.inputPricePerMillion ?? 0);
      const outputPrice = Number(route?.output_price_per_million ?? persisted.outputPricePerMillion ?? 0);
      const cost = raw.cost_amount == null
        ? (inputTokens * inputPrice + outputTokens * outputPrice) / 1_000_000
        : Number(raw.cost_amount);
      return {
        payload,
        usage: {
          input_tokens: inputTokens,
          output_tokens: outputTokens,
        },
        provider: "dashscope",
        model: String(raw.model || request.model),
        cost,
        currency: String(raw.cost_currency || route?.currency || persisted.currency || "CNY"),
      };
    } catch {
      throw new ProviderAdapterError("provider_response_invalid");
    }
  };
}
