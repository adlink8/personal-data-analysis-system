import { resolve } from "node:path";

import {
  createAgentSession,
  DefaultResourceLoader,
  defineTool,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { capabilityToolNames, loadCapabilityRegistry } from "../tools/capability-registry.mjs";
import { skillChecksum } from "../skills/registry.mjs";

export const SYNTHETIC_SYSTEM_PROMPT =
  "Phase 48 synthetic containment session. Use only the registered domain tools.";

export const PHASE_48_TOOL_NAMES = Object.freeze([
  "domain_candidate",
  "domain_inspect",
]);
export const PRODUCTION_SYSTEM_PROMPT = "Pi production Capability Registry tools only; use the declared domain operation and never access ambient resources.";

/**
 * The one Pi runtime resolves exactly three explicit policy profiles. Resolution
 * is deny-by-default: unknown profiles return null and cross-profile tool names
 * are never unioned. Allowlists are derived from the governed production
 * Capability Registry by side-effect class, so an ordinary Conversation lease
 * can never see or mutate Reflection/Operator authority.
 */
const PRODUCTION_REGISTRY = loadCapabilityRegistry({ profile: "production" });

function operationsBySideEffectClass(registry, predicate) {
  return registry.operations.filter((operation) => predicate(operation.side_effect_class)).map((operation) => operation.id);
}

export const PROFILE_DEFINITIONS = Object.freeze({
  conversation: Object.freeze({
    id: "conversation",
    allowlist: Object.freeze(operationsBySideEffectClass(PRODUCTION_REGISTRY, (side) => side === "none")),
    side_effect_class: "read_only",
  }),
  reflection: Object.freeze({
    id: "reflection",
    allowlist: Object.freeze(operationsBySideEffectClass(PRODUCTION_REGISTRY, (side) => side === "candidate")),
    side_effect_class: "candidate",
  }),
  operator: Object.freeze({
    id: "operator",
    allowlist: Object.freeze(operationsBySideEffectClass(PRODUCTION_REGISTRY, (side) => side === "promotion" || side === "rollback" || side === "derived" || side === "canonical")),
    side_effect_class: "mutation",
  }),
});

/** Resolve a named profile definition; unknown profiles fail closed. */
export function resolveProfile(profileId) {
  return PROFILE_DEFINITIONS[profileId] ?? null;
}

/** Tool-name allowlist for a profile; unknown profiles return null. */
export function profileToolNames(profileId) {
  const definition = resolveProfile(profileId);
  return definition ? [...definition.allowlist] : null;
}

/** Exact per-operation profile membership; unknown profiles fail closed. */
export function isProfileOperation(profileId, operation) {
  const definition = resolveProfile(profileId);
  return definition ? definition.allowlist.includes(operation) : false;
}

/**
 * Derive the exact active Conversation tool lease from zero/one primary Skill
 * plus at most one bounded supporting Skill. Every selected tool must be in the
 * read-only Conversation base and every Skill must reproduce its manifest
 * checksum; drift, mutation or out-of-lease operations fail closed.
 */
export function deriveConversationLease({ primarySkill = null, supportSkill = null } = {}) {
  const base = PROFILE_DEFINITIONS.conversation.allowlist;
  const baseSet = new Set(base);
  const primary = Array.isArray(primarySkill) ? primarySkill : primarySkill == null ? [] : [primarySkill];
  const support = Array.isArray(supportSkill) ? supportSkill : supportSkill == null ? [] : [supportSkill];
  if (primary.length > 1) return { ok: false, reason: "at_most_one_primary" };
  if (support.length > 1) return { ok: false, reason: "at_most_one_support" };
  const selected = [];
  for (const skill of [...primary, ...support]) {
    if (!skill || typeof skill !== "object" || Array.isArray(skill)) return { ok: false, reason: "skill_invalid" };
    if (typeof skill.checksum !== "string" || skillChecksum(skill) !== skill.checksum) return { ok: false, reason: "checksum_drift" };
    if (!Array.isArray(skill.allowed_tools) || skill.allowed_tools.length === 0) return { ok: false, reason: "skill_invalid" };
    for (const tool of skill.allowed_tools) {
      if (!baseSet.has(tool)) return { ok: false, reason: "not_read_only" };
    }
    selected.push(...skill.allowed_tools);
  }
  return { ok: true, active_tool_names: [...new Set([...base, ...selected])].sort() };
}

export const SYNTHETIC_MODEL = Object.freeze({
  api: "synthetic-containment",
  provider: "synthetic-containment",
  id: "phase-48-containment",
  name: "Phase 48 containment model",
  reasoning: false,
  input: ["text"],
  contextWindow: 4096,
  maxTokens: 256,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
});

function requireExplicitDirectory(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${name} must be explicitly supplied`);
  }
  return resolve(value);
}

function syntheticTool(name, label) {
  return defineTool({
    name,
    label,
    description: `${label} synthetic Phase 48 Domain Tool`,
    parameters: Type.Object({}),
    execute: async () => ({
      content: [{ type: "text", text: "synthetic" }],
      details: {},
    }),
  });
}

export function productionTool(operation, invokeTool) {
  return defineTool({
    name: operation.id,
    label: operation.title,
    description: operation.description,
    parameters: Type.Record(Type.String(), Type.Unknown()),
    execute: async (_toolCallId, params) => {
      if (typeof invokeTool !== "function") return {
        content: [{ type: "text", text: `${operation.id} requires a bound Kernel task invocation.` }],
        details: { ok: false, error: { code: "capability_binding_required" }, capability: operation.id },
      };
      try {
        const result = await invokeTool(operation.id, params);
        return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
      } catch (error) {
        return { content: [{ type: "text", text: `${operation.id} failed.` }], details: { ok: false, error: { code: error?.code ?? "domain_unavailable" }, capability: operation.id } };
      }
    },
  });
}

export function providerFreeRuntime() {
  let providerCalls = 0;
  const unavailable = () => undefined;
  return {
    get providerCalls() {
      return providerCalls;
    },
    getModels: () => [],
    getAvailableSnapshot: () => [],
    getModel: unavailable,
    getProvider: unavailable,
    getError: unavailable,
    getRegisteredProviderConfig: unavailable,
    getRegisteredNativeProvider: unavailable,
    getRegisteredProviderIds: () => [],
    hasConfiguredAuth: () => false,
    isUsingOAuth: () => false,
    getProviderAuthStatus: () => ({ configured: false }),
    getAuth: async () => undefined,
    checkAuth: async () => undefined,
    getAvailable: async () => [],
    listCredentials: async () => [],
    getCompatibilityRequestConfig: () => ({}),
    refresh: async () => {
      providerCalls += 1;
      return { aborted: false, errors: new Map() };
    },
    registerProvider: () => {
      providerCalls += 1;
    },
    registerNativeProvider: () => {
      providerCalls += 1;
    },
    unregisterProvider: () => {
      providerCalls += 1;
    },
    stream: () => {
      providerCalls += 1;
      throw new Error("provider disabled");
    },
    streamSimple: () => {
      providerCalls += 1;
      throw new Error("provider disabled");
    },
    complete: async () => {
      providerCalls += 1;
      throw new Error("provider disabled");
    },
    completeSimple: async () => {
      providerCalls += 1;
      throw new Error("provider disabled");
    },
  };
}

/**
 * Build the only supported Phase 48 Pi session. Paths, resource discovery,
 * settings, session persistence, built-in tools and provider access are all
 * explicit here so SDK defaults cannot widen the capability boundary.
 */
export async function createContainedSession({ cwd, agentDir, profile = "synthetic", invokeTool } = {}) {
  const explicitCwd = requireExplicitDirectory(cwd, "cwd");
  const explicitAgentDir = requireExplicitDirectory(agentDir, "agentDir");
  const settingsManager = SettingsManager.inMemory();
  const sessionManager = SessionManager.inMemory(explicitCwd);
  const registry = profile === "production" ? loadCapabilityRegistry({ profile }) : null;
  const toolNames = registry ? capabilityToolNames(registry) : [...PHASE_48_TOOL_NAMES];
  const resourceLoader = new DefaultResourceLoader({
    cwd: explicitCwd,
    agentDir: explicitAgentDir,
    settingsManager,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: registry ? PRODUCTION_SYSTEM_PROMPT : SYNTHETIC_SYSTEM_PROMPT,
  });
  await resourceLoader.reload();

  const customTools = registry
    ? registry.operations.map((operation) => productionTool(operation, invokeTool))
    : [syntheticTool("domain_inspect", "Domain inspect"), syntheticTool("domain_candidate", "Domain candidate")];
  const modelRuntime = providerFreeRuntime();
  const { session, extensionsResult } = await createAgentSession({
    cwd: explicitCwd,
    agentDir: explicitAgentDir,
    model: SYNTHETIC_MODEL,
    modelRuntime,
    resourceLoader,
    settingsManager,
    sessionManager,
    noTools: "builtin",
    tools: toolNames,
    customTools,
    thinkingLevel: "off",
  });

  return {
    session,
    resourceLoader,
    settingsManager,
    sessionManager,
    extensionsResult,
    modelRuntime,
    profile,
    registry,
    toolNames,
  };
}
