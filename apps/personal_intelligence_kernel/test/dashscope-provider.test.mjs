import assert from "node:assert/strict";
import test from "node:test";

import { createDashScopeTransport } from "../src/models/dashscope-transport.mjs";
import { ProviderAdapter, ProviderAdapterError } from "../src/models/provider-adapter.mjs";
import { createConfiguredProviderAdapter } from "../src/models/runtime-provider.mjs";

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
  assert.equal(JSON.parse(observed.init.body).model, "replay-v1");
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
