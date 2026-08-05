import assert from "node:assert/strict";
import test from "node:test";
import { loadCapabilityRegistry, capabilityByName } from "../src/tools/capability-registry.mjs";

test("production capability registry loads the approved project surface", () => {
  const registry = loadCapabilityRegistry({ profile: "production" });
  assert.equal(registry.profile, "production");
  assert.equal(registry.operations.length, 44);
  assert.ok(registry.checksum.match(/^[0-9a-f]{64}$/));
  assert.equal(capabilityByName(registry, "search").id, "knowledge.search");
});

test("capability aliases resolve only to canonical operations", () => {
  const registry = loadCapabilityRegistry({ profile: "production" });
  assert.equal(capabilityByName(registry, "external_context_list").id, "external.list");
  assert.throws(() => capabilityByName(registry, "operator.delete"), { code: "capability_unknown" });
});

test("generated production descriptor bundle has one source checksum for representative domains", async () => {
  const { readFile } = await import("node:fs/promises");
  const path = new URL("../../../governance/manifests/capabilities/generated/project-capability-descriptors.production.json", import.meta.url);
  const bundle = JSON.parse(await readFile(path, "utf8"));
  const names = ["knowledge.search", "retrieval.status", "state.current", "external.list", "decision.get", "action_outcome.list", "evidence.resolve", "wiki.page", "data_quality.report", "system.health"];
  for (const name of names) {
    const operation = bundle.pi.operations.find((candidate) => candidate.name === name);
    assert.equal(operation?.source_checksum?.length, 64, name);
    assert.equal(operation?.name, name);
  }
});
