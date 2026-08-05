import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../");
export const DEFAULT_CAPABILITY_REGISTRY_PATH = resolve(ROOT, "governance/manifests/capabilities/project-capabilities.json");
export const CAPABILITY_REGISTRY_SCHEMA = "project-capability-registry-v1";
const PROFILES = new Set(["production", "operator", "test"]);
function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  return value;
}
const digest = (value) => createHash("sha256").update(JSON.stringify(canonicalize(value))).digest("hex");

export class CapabilityRegistryError extends Error {
  constructor(code, message = code) { super(message); this.name = "CapabilityRegistryError"; this.code = code; }
}

function operationChecksum(operation) {
  const { checksum: ignored, ...payload } = operation;
  return digest(payload);
}

function registryChecksum(registry) {
  const { checksum: ignored, ...payload } = registry;
  return digest(payload);
}

function fail(code) { throw new CapabilityRegistryError(code); }

export function loadCapabilityRegistry({ path = DEFAULT_CAPABILITY_REGISTRY_PATH, profile = "production" } = {}) {
  if (!PROFILES.has(profile)) fail("profile_unknown");
  let registry;
  try { registry = JSON.parse(readFileSync(path, "utf8")); } catch { fail("registry_unavailable"); }
  if (!registry || registry.schema !== CAPABILITY_REGISTRY_SCHEMA) fail("registry_schema");
  if (registry.checksum !== registryChecksum(registry)) fail("registry_checksum_drift");
  const ids = new Set();
  const aliases = new Set();
  for (const operation of registry.operations ?? []) {
    if (!operation?.id || ids.has(operation.id)) fail("duplicate_operation_id");
    if (operation.checksum !== operationChecksum(operation)) fail("operation_checksum_drift");
    ids.add(operation.id);
    for (const alias of operation.aliases ?? []) {
      if (aliases.has(alias.name) || ids.has(alias.name)) fail("duplicate_alias");
      aliases.add(alias.name);
    }
  }
  const operations = (registry.operations ?? []).filter((operation) => operation.status === "active" && operation.profiles.includes(profile)).sort((a, b) => a.id.localeCompare(b.id));
  return Object.freeze({
    schema: registry.schema,
    version: registry.version,
    checksum: registry.checksum,
    profile,
    operations: Object.freeze(operations.map((operation) => Object.freeze({ ...operation }))),
  });
}

export function capabilityToolNames(registry) { return registry.operations.map((operation) => operation.id); }
export function capabilityByName(registry, name) {
  const operation = registry.operations.find((candidate) => candidate.id === name || (candidate.aliases ?? []).some((alias) => alias.name === name));
  if (!operation) fail("capability_unknown");
  return operation;
}

export { operationChecksum, registryChecksum };
