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

export const SYNTHETIC_SYSTEM_PROMPT =
  "Phase 48 synthetic containment session. Use only the registered domain tools.";

export const PHASE_48_TOOL_NAMES = Object.freeze([
  "domain_candidate",
  "domain_inspect",
]);
export const PRODUCTION_SYSTEM_PROMPT = "Pi production Capability Registry tools only; use the declared domain operation and never access ambient resources.";

const SYNTHETIC_MODEL = Object.freeze({
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

function productionTool(operation) {
  return defineTool({
    name: operation.id,
    label: operation.title,
    description: operation.description,
    parameters: Type.Object({}),
    execute: async () => ({
      content: [{ type: "text", text: `${operation.id} requires a bound Kernel task invocation.` }],
      details: { ok: false, error: { code: "capability_binding_required" }, capability: operation.id },
    }),
  });
}

function providerFreeRuntime() {
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
export async function createContainedSession({ cwd, agentDir, profile = "synthetic" } = {}) {
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
    ? registry.operations.map((operation) => productionTool(operation))
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
