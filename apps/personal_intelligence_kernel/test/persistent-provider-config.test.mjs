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
