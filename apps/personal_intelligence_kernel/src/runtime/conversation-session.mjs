import { resolve } from "node:path";

import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

import {
  PRODUCTION_SYSTEM_PROMPT,
  productionTool,
  providerFreeRuntime,
  SYNTHETIC_MODEL,
} from "./resource-policy.mjs";

function requireExplicitDirectory(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new TypeError(`${name} must be explicitly supplied`);
  }
  return resolve(value);
}

/**
 * Per-turn Conversation session factory (Plan 61-03 route seam).
 *
 * Each conversation turn gets its own real `AgentSession` with the same explicit
 * containment flags as the Phase 48 session: no extensions/skills/prompt
 * templates/themes/context files, no built-in tools, and an explicit provider-free
 * model runtime unless the caller supplies one. A live provider is never silently
 * selected; the deterministic fixture/replay provider is used for tests/UAT while
 * the real `AgentSession.prompt(... source: "rpc")` lifecycle still runs.
 */
export async function conversationSessionFactory({
  cwd,
  agentDir,
  model = SYNTHETIC_MODEL,
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
  const runtime = modelRuntime ?? providerFreeRuntime();
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
    model,
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
