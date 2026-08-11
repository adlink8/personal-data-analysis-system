import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { readProviderConfig } from "../src/models/persistent-config.mjs";

test("persistent provider config reads non-secret DashScope settings and rejects malformed config", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pi-provider-config-"));
  await mkdir(path.join(root, "var", "config"), { recursive: true });
  const configPath = path.join(root, "var", "config", "pi-provider.json");
  await writeFile(configPath, JSON.stringify({
    schema: "pi-provider-config-v1",
    provider: "dashscope",
    mode: "aliyun",
    base_url: "https://ws-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    model: "deepseek-v4-flash-0731",
    cost_ceiling: 0.1,
    secret_path: "var/secrets/dashscope.api.dpapi.txt",
  }));
  const config = readProviderConfig({ configPath });
  assert.equal(config.mode, "aliyun");
  assert.equal(config.model, "deepseek-v4-flash-0731");
  assert.equal(config.costCeiling, 0.1);
  assert.ok(config.secretPath.endsWith(path.join("var", "secrets", "dashscope.api.dpapi.txt")));

  await writeFile(configPath, JSON.stringify({ schema: "wrong", provider: "dashscope" }));
  assert.deepEqual(readProviderConfig({ configPath }), {});
});

test("persistent provider config reads optional route budget overrides and rejects malformed entries", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pi-budget-config-"));
  await mkdir(path.join(root, "var", "config"), { recursive: true });
  const configPath = path.join(root, "var", "config", "pi-provider.json");
  await writeFile(configPath, JSON.stringify({
    schema: "pi-provider-config-v1",
    provider: "dashscope",
    mode: "aliyun",
    model: "deepseek-v4-flash-0731",
    cost_ceiling: 30,
    max_output_tokens: 8192,
    max_attempts: 3,
    no_fallback: false,
    routes: {
      structured_analysis: { max_output_tokens: 2048, max_attempts: 2, no_fallback: true, cost_ceiling: 5 },
      guarded_generation: { max_output_tokens: "not-a-number" },
      memory_repair: { max_attempts: 99, cost_ceiling: -1 },
      not_a_purpose: { max_output_tokens: 128 },
    },
  }));
  const config = readProviderConfig({ configPath });
  assert.equal(config.maxOutputTokens, 8192);
  assert.equal(config.maxAttempts, 3);
  assert.equal(config.noFallback, false);
  assert.deepEqual(config.routeOverrides.structured_analysis, { max_output_tokens: 2048, max_attempts: 2, no_fallback: true, cost_ceiling: 5 });
  // Invalid per-route entries are dropped individually (fail-safe): a purpose
  // with no valid override key is absent from routeOverrides.
  assert.equal(config.routeOverrides.guarded_generation, undefined);
  assert.equal(config.routeOverrides.memory_repair, undefined);
  assert.deepEqual(config.routeOverrides.not_a_purpose, { max_output_tokens: 128 });
});
