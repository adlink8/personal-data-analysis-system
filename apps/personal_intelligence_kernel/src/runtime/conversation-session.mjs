import { resolve } from "node:path";

import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

import {
  PRODUCTION_SYSTEM_PROMPT,
  productionTool,
  providerFreeRuntime,
  SYNTHETIC_MODEL,
} from "./resource-policy.mjs";
import { readProviderConfig } from "../models/persistent-config.mjs";

function requireExplicitDirectory(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${name} must be explicitly supplied`);
  }
  return resolve(value);
}

/**
 * Real pi ModelRuntime (opencode-go built-in provider) so a conversation turn
 * drives the actual iterative model loop. Key comes from OPENCODE_API_KEY or
 * the persisted provider config; model id matches the opencode-go catalog.
 * Falls back to the provider-free runtime only when no real key is present.
 */
async function defaultRealModelRuntime() {
  const providerConfig = readProviderConfig();
  const apiKey = process.env.OPENCODE_API_KEY || providerConfig.apiKey;
  if (!apiKey) return providerFreeRuntime();
  if (!process.env.OPENCODE_API_KEY) process.env.OPENCODE_API_KEY = apiKey;
  const modelId = process.env.PI_PROVIDER_MODEL || providerConfig.model || "deepseek-v4-flash";
  try {
    const runtime = await ModelRuntime.create({ allowModelNetwork: false });
    const model = runtime.getModel("opencode-go", modelId) ?? runtime.getModels("opencode-go")[0];
    if (!model) return providerFreeRuntime();
    return { runtime, model };
  } catch {
    return providerFreeRuntime();
  }
}

/**
 * Per-turn Conversation session factory (Plan 61-03 route seam).
 *
 * Each conversation turn gets its own real `AgentSession` with the same explicit
 * containment flags as the Phase 48 session: no extensions/skills/prompt
 * templates/themes/context files, no built-in tools. The model runtime defaults
 * to a real pi `ModelRuntime` (opencode-go built-in provider; key from
 * `OPENCODE_API_KEY` or the persisted provider config) so a conversation turn
 * can drive the actual iterative model loop against the real provider. Callers
 * may still pass an explicit `modelRuntime` (fixture/replay) for tests/UAT.
 */
export async function conversationSessionFactory({
  cwd,
  agentDir,
  model,
  modelRuntime,
  settingsManager,
  sessionManager,
  resourceLoader,
  operations = [],
  invokeTool,
  tools,
} = {}) {
  const explicitCwd = requireExplicitDirectory(cwd, "cwd");
  const explicitAgentDir = requireExplicitDirectory(agentDir, "agentDir");
  const realRuntime = modelRuntime ?? await defaultRealModelRuntime();
  const runtime = realRuntime?.runtime ?? providerFreeRuntime();
  const resolvedModel = model ?? realRuntime?.model ?? SYNTHETIC_MODEL;
  const effectiveSettingsManager = settingsManager ?? SettingsManager.inMemory();
  const effectiveSessionManager = sessionManager ?? SessionManager.inMemory(explicitCwd);
  const toolNames = tools ?? operations.map((operation) => operation.id);
  const customTools = operations.map((operation) => productionTool(operation, invokeTool));
  const loader = resourceLoader ?? new DefaultResourceLoader({
    cwd: explicitCwd,
    agentDir: explicitAgentDir,
    settingsManager: effectiveSettingsManager,
    noExtensions: true,
    noSkills: true,
    noPromptTemplates: true,
    noThemes: true,
    noContextFiles: true,
    systemPrompt: PRODUCTION_SYSTEM_PROMPT,
  });
  if (!resourceLoader) await loader.reload();

  const { session, extensionsResult } = await createAgentSession({
    cwd: explicitCwd,
    agentDir: explicitAgentDir,
    model: resolvedModel,
    modelRuntime: runtime,
    resourceLoader: loader,
    settingsManager: effectiveSettingsManager,
    sessionManager: effectiveSessionManager,
    noTools: "builtin",
    tools: toolNames,
    customTools,
    thinkingLevel: "off",
  });

  return {
    session,
    resourceLoader: loader,
    modelRuntime: runtime,
    settingsManager: effectiveSettingsManager,
    sessionManager: effectiveSessionManager,
    extensionsResult,
  };
}

export const createConversationSession = conversationSessionFactory;
