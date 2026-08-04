import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { readFile } from "node:fs/promises";

import { createContainedSession } from "../src/runtime/resource-policy.mjs";
import { runContainmentProbe } from "../src/runtime/containment-probe.mjs";

const root = resolve(import.meta.dirname, "../../..");
const registryPath = resolve(root, "governance/manifests/ai/pi-tool-registry.json");
const networkPath = resolve(root, "governance/manifests/ai/pi-network-allowlist.json");

test("containment probe exposes only the exact synthetic runtime", async () => {
  const result = await runContainmentProbe();
  assert.equal(result.exitCode, 0);
  assert.deepEqual(Object.keys(result.report).sort(), [
    "counts",
    "fixture_checksums",
    "node_version",
    "package_versions",
    "reason_codes",
    "schema",
    "tool_names",
    "version",
  ]);
  assert.equal(result.report.schema, "pi-runtime-containment-v1");
  assert.deepEqual(result.report.tool_names, ["domain_candidate", "domain_inspect"]);
  assert.deepEqual(
    {
      extensions: result.report.counts.extensions,
      skills: result.report.counts.skills,
      prompt_templates: result.report.counts.prompt_templates,
      themes: result.report.counts.themes,
      context_files: result.report.counts.context_files,
      forbidden_tools: result.report.counts.forbidden_tools,
      provider_calls: result.report.counts.provider_calls,
    },
    { extensions: 0, skills: 0, prompt_templates: 0, themes: 0, context_files: 0, forbidden_tools: 0, provider_calls: 0 },
  );
  assert.ok(Object.keys(result.report.fixture_checksums).length >= 12);
  assert.ok(result.report.reason_codes.includes("temporary_state_cleaned"));
});

test("hostile fixtures remain unreachable and the probe output is privacy-safe", async () => {
  let temporaryRoot;
  const result = await runContainmentProbe({ onTemporaryRoot: (value) => { temporaryRoot = value; } });
  const serialized = JSON.stringify(result.report);
  assert.equal(result.exitCode, 0);
  assert.equal(temporaryRoot && !serialized.includes(temporaryRoot), true);
  assert.equal(serialized.includes("PI-CONTAINMENT-SECRET"), false);
  assert.equal(serialized.includes("unknown.invalid"), false);
  assert.equal(temporaryRoot && !existsSync(temporaryRoot), true);
});

for (const fixtureMode of ["failure", "timeout"]) {
  test(`probe cleans temporary state after ${fixtureMode}`, async () => {
    let temporaryRoot;
    const result = await runContainmentProbe({
      fixtureMode,
      timeoutMs: 10,
      onTemporaryRoot: (value) => { temporaryRoot = value; },
    });
    assert.notEqual(result.exitCode, 0);
    assert.ok(result.report.reason_codes.includes("temporary_state_cleaned"));
    assert.equal(existsSync(temporaryRoot), false);
  });
}

test("factory requires explicit isolated paths and disables all ambient resources", async () => {
  await assert.rejects(() => createContainedSession(), /cwd must be explicitly supplied/);
  const fixtureRoot = await mkdtemp(join(tmpdir(), "pi-policy-test-"));
  const cwd = join(fixtureRoot, "cwd");
  const agentDir = join(fixtureRoot, "agent");
  await mkdir(join(cwd, ".pi", "extensions"), { recursive: true });
  await writeFile(join(cwd, ".pi", "extensions", "decoy.mjs"), "throw new Error('decoy');\n");
  let runtime;
  try {
    runtime = await createContainedSession({ cwd, agentDir });
    assert.deepEqual(runtime.session.agent.state.tools.map((tool) => tool.name).sort(), ["domain_candidate", "domain_inspect"]);
    assert.equal(runtime.resourceLoader.getExtensions().extensions.length, 0);
    assert.equal(runtime.resourceLoader.getSkills().skills.length, 0);
    assert.equal(runtime.resourceLoader.getPrompts().prompts.length, 0);
    assert.equal(runtime.resourceLoader.getThemes().themes.length, 0);
    assert.equal(runtime.resourceLoader.getAgentsFiles().agentsFiles.length, 0);
    assert.equal(runtime.resourceLoader.getSystemPrompt(), "Phase 48 synthetic containment session. Use only the registered domain tools.");
    assert.equal(runtime.modelRuntime.providerCalls, 0);
  } finally {
    await runtime?.session?.dispose();
    await rm(fixtureRoot, { recursive: true, force: true });
  }
});

test("governance manifests are exact and offline", async () => {
  const registry = JSON.parse(await readFile(registryPath, "utf8"));
  const network = JSON.parse(await readFile(networkPath, "utf8"));
  assert.deepEqual(registry.tools.map((tool) => tool.name).sort(), ["domain_candidate", "domain_inspect"]);
  assert.equal(new Set(registry.tools.map((tool) => tool.name)).size, registry.tools.length);
  const events = registry.tools.flatMap((tool) => tool.event_ids);
  assert.equal(new Set(events).size, events.length);
  assert.deepEqual(network.hosts, []);
  assert.deepEqual(network.ports, []);
  assert.deepEqual(network.methods, []);
});
