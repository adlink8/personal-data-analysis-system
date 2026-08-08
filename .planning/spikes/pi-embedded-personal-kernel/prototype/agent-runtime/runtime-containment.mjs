import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createAgentSession, DefaultResourceLoader, defineTool, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "tmp");
const cwd = join(root, "project");
const agentDir = join(root, "agent");
const decoys = [
  join(cwd, ".pi", "extensions", "evil-extension.ts"),
  join(cwd, ".pi", "skills", "evil-skill", "SKILL.md"),
  join(agentDir, "extensions", "evil-global.ts"),
  join(agentDir, "skills", "evil-global", "SKILL.md"),
];

await rm(root, { recursive: true, force: true });
await Promise.all(decoys.map(async (path) => {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, "export default () => { throw new Error('must not load'); };\n", "utf8");
}));

const tool = (name, label) => defineTool({
  name,
  label,
  description: `${label} synthetic domain tool`,
  parameters: Type.Object({}),
  execute: async () => ({ content: [{ type: "text", text: "synthetic" }], details: {} }),
});

const loader = new DefaultResourceLoader({
  cwd,
  agentDir,
  settingsManager: SettingsManager.inMemory(),
  noExtensions: true,
  noSkills: true,
  noPromptTemplates: true,
  noThemes: true,
  noContextFiles: true,
  systemPrompt: "Synthetic containment test.",
});
await loader.reload();

const { session, extensionsResult } = await createAgentSession({
  cwd,
  agentDir,
  resourceLoader: loader,
  settingsManager: SettingsManager.inMemory(),
  sessionManager: SessionManager.inMemory(cwd),
  noTools: "builtin",
  tools: ["domain_inspect", "domain_candidate"],
  customTools: [tool("domain_inspect", "Inspect"), tool("domain_candidate", "Candidate")],
});

const toolNames = session.agent.state.tools.map((item) => item.name);
const forbidden = ["read", "bash", "edit", "write", "grep", "find", "ls"];
const result = {
  packageVersion: "0.83.0",
  node: process.version,
  tools: toolNames,
  extensions: extensionsResult.extensions.map((item) => item.path ?? item.name ?? "unknown"),
  extensionErrors: extensionsResult.errors,
  skills: loader.getSkills().skills.map((item) => item.name),
  prompts: loader.getPrompts().prompts.length,
  contextFiles: loader.getAgentsFiles().agentsFiles.length,
  forbiddenLoaded: forbidden.filter((name) => toolNames.includes(name)),
  decoyCount: decoys.length,
};

session.dispose();
console.log(JSON.stringify(result, null, 2));

if (JSON.stringify(toolNames.sort()) !== JSON.stringify(["domain_candidate", "domain_inspect"])) {
  process.exitCode = 1;
}
if (result.extensions.length !== 0 || result.skills.length !== 0 || result.prompts !== 0 || result.contextFiles !== 0) {
  process.exitCode = 1;
}
if (result.forbiddenLoaded.length !== 0) process.exitCode = 1;
await rm(root, { recursive: true, force: true });
