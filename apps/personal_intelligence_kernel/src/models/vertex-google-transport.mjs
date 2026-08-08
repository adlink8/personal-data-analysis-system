import { execFileSync } from "node:child_process";
import { ProxyAgent, request as undiciRequest } from "undici";

import { ProviderAdapterError } from "./provider-adapter.mjs";

export const DEFAULT_VERTEX_PROJECT = "project-c5cbd608-1b00-454e-80f";
export const DEFAULT_VERTEX_LOCATION = "global";
export const DEFAULT_VERTEX_MODEL = "gemini-3.5-flash";

function safeHttpCode(status) {
  return Number.isInteger(status) && status >= 400 && status <= 599 ? `provider_http_${status}` : "provider_http_error";
}

function accessToken({ executable = process.env.PERSONAL_DATA_GCLOUD ?? "gcloud" } = {}) {
  try {
    const value = String(executable);
    const isWindowsScript = /\.(?:bat|cmd)$/i.test(value);
    const command = /\s/.test(value) ? `""${value}" auth print-access-token` : `${value} auth print-access-token`;
    const stdout = isWindowsScript
      ? execFileSync(process.env.ComSpec ?? "cmd.exe", ["/d", "/s", "/c", command], { encoding: "utf8", timeout: 30000, windowsHide: true, stdio: ["ignore", "pipe", "ignore"] })
      : execFileSync(value, ["auth", "print-access-token"], { encoding: "utf8", timeout: 30000, windowsHide: true, stdio: ["ignore", "pipe", "ignore"] });
    const token = String(stdout).trim();
    if (!token) throw new Error("empty_token");
    return token;
  } catch {
    throw new ProviderAdapterError("provider_credential_unavailable");
  }
}

function endpoint({ project, location, model }) {
  const safeProject = encodeURIComponent(String(project));
  const safeLocation = encodeURIComponent(String(location));
  const safeModel = encodeURIComponent(String(model));
  return `https://aiplatform.googleapis.com/v1/projects/${safeProject}/locations/${safeLocation}/publishers/google/models/${safeModel}:generateContent`;
}

function textFromCandidates(candidates) {
  return (Array.isArray(candidates) ? candidates : [])
    .flatMap((candidate) => Array.isArray(candidate?.content?.parts) ? candidate.content.parts : [])
    .filter((part) => part?.thought !== true && typeof part?.text === "string")
    .map((part) => part.text)
    .join("");
}

async function proxyAwareRequest(url, options) {
  const proxyUrl = process.env.HTTPS_PROXY ?? process.env.HTTP_PROXY;
  const dispatcher = proxyUrl ? new ProxyAgent(proxyUrl) : undefined;
  const result = await undiciRequest(url, {
    method: options.method,
    headers: options.headers,
    body: options.body,
    signal: options.signal,
    dispatcher,
    headersTimeout: 30000,
    bodyTimeout: 30000,
  });
  const chunks = [];
  for await (const chunk of result.body) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString("utf8");
  return { ok: result.statusCode >= 200 && result.statusCode < 300, status: result.statusCode, async json() { return JSON.parse(body); } };
}

/** Vertex AI REST transport using the user's existing gcloud ADC/access-token session. */
export function createVertexGoogleTransport({
  project = process.env.PERSONAL_DATA_GCP_PROJECT ?? DEFAULT_VERTEX_PROJECT,
  location = process.env.PERSONAL_DATA_VERTEX_LOCATION ?? DEFAULT_VERTEX_LOCATION,
  model = process.env.PERSONAL_DATA_VERTEX_MODEL ?? DEFAULT_VERTEX_MODEL,
  gcloudExecutable = process.env.PERSONAL_DATA_GCLOUD ?? "gcloud",
  tokenProvider = () => accessToken({ executable: gcloudExecutable }),
  fetchImpl,
} = {}) {
  return async (request, route) => {
    if (!request?.prompt) throw new ProviderAdapterError("provider_request_invalid");
    const token = tokenProvider();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), Number(route?.timeout_ms ?? 30000));
    let response;
    try {
      response = await (fetchImpl ?? proxyAwareRequest)(endpoint({ project, location, model: request.model || model }), {
        method: "POST",
        headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: request.prompt }] }],
          generationConfig: { maxOutputTokens: request.max_output_tokens },
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
    try { raw = await response.json(); } catch { throw new ProviderAdapterError("provider_response_invalid"); }
    if (!response.ok) throw new ProviderAdapterError(safeHttpCode(response.status));
    const text = textFromCandidates(raw?.candidates);
    if (!text) throw new ProviderAdapterError("provider_response_invalid");
    const usage = raw?.usageMetadata ?? {};
    return {
      payload: {
        text,
        finish_reason: raw?.candidates?.[0]?.finishReason ?? null,
        usage_metadata: {
          prompt_token_count: Number(usage.promptTokenCount ?? 0),
          candidates_token_count: Number(usage.candidatesTokenCount ?? 0),
          total_token_count: Number(usage.totalTokenCount ?? 0),
        },
      },
      usage: { input_tokens: Number(usage.promptTokenCount ?? 0), output_tokens: Number(usage.candidatesTokenCount ?? 0) },
      provider: "vertex_google",
      model: String(raw?.modelVersion || request.model || model),
      cost: 0,
      currency: "USD",
    };
  };
}
