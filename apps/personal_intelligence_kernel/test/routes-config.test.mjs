import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildModelRoutes, loadModelRouteManifest } from "../src/models/routes.mjs";

const MANIFEST = {
  schema: "pi-model-routes-v1",
  version: "54.02.2",
  routes: [
    { purpose: "structured_analysis", max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "guarded_generation", max_output_tokens: 2048, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "extraction_summary", max_output_tokens: 1024, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "generic_generation", max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "conversation_summary", max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "memory_candidate_extraction", max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
    { purpose: "memory_repair", max_output_tokens: 4096, cost_ceiling: 0, max_attempts: 1, no_fallback: true },
  ],
};

test("route budgets fall back to the manifest and stay zero-cost in replay mode", () => {
  const routes = buildModelRoutes({ manifest: MANIFEST, config: {}, env: { PI_PROVIDER_MODE: "replay" } });
  assert.equal(routes.structured_analysis.max_output_tokens, 1024);
  assert.equal(routes.generic_generation.max_output_tokens, 4096);
  assert.equal(routes.structured_analysis.max_attempts, 1);
  assert.equal(routes.structured_analysis.no_fallback, true);
  assert.equal(routes.structured_analysis.cost_ceiling, 0);
  assert.equal(routes.structured_analysis.model, "replay-v1");
});

test("missing or malformed manifest falls back to embedded defaults", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "pi-routes-"));
  const missing = path.join(root, "missing.json");
  assert.deepEqual(loadModelRouteManifest({ manifestPath: missing }), {});
  const routes = buildModelRoutes({ manifest: {}, config: {}, env: {} });
  assert.equal(routes.structured_analysis.max_output_tokens, 1024);
  assert.equal(routes.memory_repair.max_output_tokens, 4096);
  assert.equal(routes.structured_analysis.max_attempts, 1);
  assert.equal(routes.structured_analysis.no_fallback, true);

  const malformed = path.join(root, "malformed.json");
  await writeFile(malformed, "{not json", "utf8");
  assert.deepEqual(loadModelRouteManifest({ manifestPath: malformed }), {});
  const wrongSchema = path.join(root, "wrong.json");
  await writeFile(wrongSchema, JSON.stringify({ schema: "other", routes: [] }), "utf8");
  assert.deepEqual(loadModelRouteManifest({ manifestPath: wrongSchema }), {});
});

test("pi-provider.json per-purpose overrides beat manifest defaults", () => {
  const routes = buildModelRoutes({
    manifest: MANIFEST,
    config: {
      routeOverrides: {
        structured_analysis: { max_output_tokens: 2048, max_attempts: 2, no_fallback: false, cost_ceiling: 5 },
      },
      costCeiling: 30,
    },
    env: { PI_PROVIDER_MODE: "aliyun", PI_PROVIDER_COST_CEILING: "30" },
  });
  assert.equal(routes.structured_analysis.max_output_tokens, 2048);
  assert.equal(routes.structured_analysis.max_attempts, 2);
  assert.equal(routes.structured_analysis.no_fallback, false);
  assert.equal(routes.structured_analysis.cost_ceiling, 5);
  // Other purposes keep manifest values with the global cost ceiling.
  assert.equal(routes.guarded_generation.max_output_tokens, 2048);
  assert.equal(routes.guarded_generation.cost_ceiling, 30);
  assert.equal(routes.structured_analysis.model, "deepseek-v4-flash-0731");
});

test("global config budget keys override manifest defaults when no per-purpose override", () => {
  const routes = buildModelRoutes({
    manifest: MANIFEST,
    config: { maxOutputTokens: 8192, maxAttempts: 3, noFallback: false, costCeiling: 30 },
    env: { PI_PROVIDER_MODE: "aliyun" },
  });
  assert.equal(routes.structured_analysis.max_output_tokens, 8192);
  assert.equal(routes.generic_generation.max_output_tokens, 8192);
  assert.equal(routes.structured_analysis.max_attempts, 3);
  assert.equal(routes.structured_analysis.no_fallback, false);
  assert.equal(routes.structured_analysis.cost_ceiling, 30);
});

test("global env vars override both config and manifest budget defaults", () => {
  const routes = buildModelRoutes({
    manifest: MANIFEST,
    config: { maxOutputTokens: 8192, maxAttempts: 3, routeOverrides: { structured_analysis: { max_output_tokens: 4096 } } },
    env: { PI_PROVIDER_MODE: "aliyun", PI_PROVIDER_MAX_OUTPUT_TOKENS: "16384", PI_PROVIDER_MAX_ATTEMPTS: "2", PI_PROVIDER_NO_FALLBACK: "true" },
  });
  assert.equal(routes.structured_analysis.max_output_tokens, 16384);
  assert.equal(routes.generic_generation.max_output_tokens, 16384);
  assert.equal(routes.structured_analysis.max_attempts, 2);
  assert.equal(routes.structured_analysis.no_fallback, true);
  // The env global still wins over a per-purpose config override (env first).
  const perPurpose = buildModelRoutes({
    manifest: MANIFEST,
    config: { routeOverrides: { structured_analysis: { max_output_tokens: 4096 } } },
    env: { PI_PROVIDER_MODE: "aliyun", PI_PROVIDER_MAX_OUTPUT_TOKENS: "16384" },
  });
  assert.equal(perPurpose.structured_analysis.max_output_tokens, 16384);
  assert.equal(perPurpose.guarded_generation.max_output_tokens, 16384);
});

test("invalid configured budget values fall back to the previous layer", () => {
  const routes = buildModelRoutes({
    manifest: MANIFEST,
    config: { maxOutputTokens: -5, maxAttempts: 99, routeOverrides: { structured_analysis: { max_output_tokens: "abc", max_attempts: -1 } } },
    env: { PI_PROVIDER_MODE: "aliyun", PI_PROVIDER_MAX_ATTEMPTS: "not-a-number" },
  });
  assert.equal(routes.structured_analysis.max_output_tokens, 1024);
  assert.equal(routes.generic_generation.max_output_tokens, 4096);
  assert.equal(routes.structured_analysis.max_attempts, 1);
});
