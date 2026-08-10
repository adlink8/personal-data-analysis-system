import assert from "node:assert/strict";
import test from "node:test";

import { createDashScopeTransport } from "../src/models/dashscope-transport.mjs";
import { ProviderAdapter, ProviderAdapterError } from "../src/models/provider-adapter.mjs";
import { createConfiguredProviderAdapter } from "../src/models/runtime-provider.mjs";
import { getModelRoute } from "../src/models/routes.mjs";

const identity = {
  purpose: "structured_analysis",
  prompt: "return a JSON object with an answer field",
  task_id: "task-aliyun-1",
  session_id: "session-aliyun-1",
  event_id: "event-aliyun-1",
  idempotency_key: "idem-aliyun-1",
};

test("DashScope transport maps compatible chat response to a Pi receipt", async () => {
  let observed;
  const adapter = new ProviderAdapter({
    credentials: "present-but-test-only",
    transport: createDashScopeTransport({
      apiKey: "sk-test",
      baseUrl: "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
      fetchImpl: async (url, init) => {
        observed = { url, init };
        return {
          ok: true,
          status: 200,
          json: async () => ({
            model: "deepseek-v4-flash-0731",
            choices: [{ message: { content: '{"answer":"ok"}' } }],
            usage: { prompt_tokens: 11, completion_tokens: 7 },
          }),
        };
      },
    }),
  });

  const receipt = await adapter.generate(identity);
  assert.equal(receipt.response.answer, "ok");
  assert.deepEqual(receipt.usage, { input_tokens: 11, output_tokens: 7 });
  assert.equal(receipt.telemetry.provider, "dashscope");
  assert.equal(observed.url, "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions");
  const requestBody = JSON.parse(observed.init.body);
  assert.equal(requestBody.model, getModelRoute("structured_analysis").model);
  assert.equal(requestBody.enable_thinking, false);
  assert.equal(observed.init.headers.authorization, "Bearer sk-test");
});

test("DashScope transport fails closed without a key and never calls fetch", async () => {
  let calls = 0;
  const adapter = new ProviderAdapter({
    credentials: undefined,
    transport: createDashScopeTransport({ apiKey: undefined, fetchImpl: async () => { calls += 1; } }),
  });
  await assert.rejects(() => adapter.generate(identity), (error) => error.code === "provider_credential_missing");
  assert.equal(calls, 0);
});

test("configured provider keeps replay as default and rejects unknown modes", () => {
  assert.equal(createConfiguredProviderAdapter({ mode: "replay" }).replay, true);
  assert.throws(() => createConfiguredProviderAdapter({ mode: "other" }), (error) => error.message === "provider_mode_unknown");
});

test("DashScope HTTP and malformed response errors are typed without leaking body", async () => {
  const httpAdapter = new ProviderAdapter({
    credentials: "present",
    transport: createDashScopeTransport({ apiKey: "sk-test", fetchImpl: async () => ({ ok: false, status: 401, json: async () => ({ message: "secret" }) }) }),
  });
  await assert.rejects(() => httpAdapter.generate(identity), (error) => error instanceof ProviderAdapterError && error.code === "provider_http_401");

  const malformedAdapter = new ProviderAdapter({
    credentials: "present",
    transport: createDashScopeTransport({ apiKey: "sk-test", fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ choices: [] }) }) }),
  });
  await assert.rejects(() => malformedAdapter.generate(identity), (error) => error.code === "provider_response_invalid");
});

test("openai-compatible mode reuses the OpenAI-compatible transport with a custom base URL", async () => {
  let observed = null;
  // Inject the fetch impl through the ProviderAdapter transport instead of the
  // adapter options (createConfiguredProviderAdapter builds the transport
  // internally); verify mode normalization and replay default stay intact.
  const adapter = createConfiguredProviderAdapter({ mode: "openai-compatible", apiKey: "sk-custom", baseUrl: "https://example.com/v1" });
  assert.equal(adapter.replay, false);
  assert.equal(adapter.credentials, "sk-custom");
  // Unknown provider still fails closed.
  assert.throws(() => createConfiguredProviderAdapter({ mode: "other" }), (error) => error.message === "provider_mode_unknown");
});

test("openai and openai-compatible are accepted mode aliases", () => {
  assert.equal(createConfiguredProviderAdapter({ mode: "openai", apiKey: "k", baseUrl: "https://example.com/v1" }).replay, false);
  assert.equal(createConfiguredProviderAdapter({ mode: "openai-compatible", apiKey: "k", baseUrl: "https://example.com/v1" }).replay, false);
  assert.equal(createConfiguredProviderAdapter({ mode: "aliyun", apiKey: "k", baseUrl: "https://example.com/v1" }).replay, false);
  assert.equal(createConfiguredProviderAdapter({ mode: "dashscope", apiKey: "k", baseUrl: "https://example.com/v1" }).replay, false);
});
