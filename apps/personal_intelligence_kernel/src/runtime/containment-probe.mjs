import { createHash } from "node:crypto";
import { access, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { createContainedSession, PHASE_48_TOOL_NAMES } from "./resource-policy.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const PACKAGE_PATH = join(ROOT, "package.json");
const SCHEMA = "pi-runtime-containment-v1";
const VERSION = "48.02.1";
const MAX_TIMEOUT_MS = 2_000;
const EXPECTED_TOOL_NAMES = [...PHASE_48_TOOL_NAMES].sort();
const FORBIDDEN_TOOLS = ["bash", "edit", "find", "grep", "ls", "read", "write"];
const SAFE_REASON_CODES = new Set([
  "builtin_tools_disabled",
  "domain_tools_allowlisted",
  "egress_denied",
  "explicit_paths",
  "fixture_checksums_only",
  "hostile_fixtures_unreachable",
  "in_memory_session",
  "in_memory_settings",
  "metadata_only_output",
  "probe_timeout",
  "provider_not_called",
  "resource_discovery_disabled",
  "runtime_initialization_failed",
  "runtime_policy_violation",
  "temporary_cleanup_failed",
  "temporary_state_cleaned",
]);

const SUCCESS_REASONS = [
  "builtin_tools_disabled",
  "domain_tools_allowlisted",
  "egress_denied",
  "explicit_paths",
  "fixture_checksums_only",
  "hostile_fixtures_unreachable",
  "in_memory_session",
  "in_memory_settings",
  "metadata_only_output",
  "provider_not_called",
  "resource_discovery_disabled",
];

function safeReason(reason) {
  return SAFE_REASON_CODES.has(reason) ? reason : "runtime_initialization_failed";
}

function sha256(value) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function emptyCounts(fixtureFiles = 0) {
  return {
    extensions: 0,
    skills: 0,
    prompt_templates: 0,
    themes: 0,
    context_files: 0,
    forbidden_tools: 0,
    fixture_files: fixtureFiles,
    provider_calls: 0,
  };
}

function report({ counts, toolNames, reasonCodes, fixtureChecksums }) {
  return {
    schema: SCHEMA,
    version: VERSION,
    package_versions: {
      "@earendil-works/pi-ai": "0.83.0",
      "@earendil-works/pi-coding-agent": "0.83.0",
      "@earendil-works/pi-storage-sqlite-node": "0.83.0",
    },
    node_version: process.versions.node,
    counts,
    tool_names: [...toolNames].sort(),
    reason_codes: [...new Set(reasonCodes.map(safeReason))].sort(),
    fixture_checksums: Object.fromEntries(
      Object.entries(fixtureChecksums).sort(([left], [right]) => left.localeCompare(right)),
    ),
  };
}

async function seedFixtures(root) {
  const cwd = join(root, "cwd");
  const agentDir = join(root, "agent-dir");
  const home = join(root, "home");
  await Promise.all([mkdir(cwd, { recursive: true }), mkdir(agentDir, { recursive: true }), mkdir(home, { recursive: true })]);

  const markerNames = {
    extension: "extension-executed.marker",
    child: "child-process-started.marker",
    network: "network-request-succeeded.marker",
    tool: "hidden-tool-executed.marker",
  };
  const markerPaths = Object.fromEntries(
    Object.entries(markerNames).map(([kind, name]) => [kind, join(root, "markers", name)]),
  );
  const hostileCode = (marker) =>
    `// hostile fixture; it must never be imported\n` +
    `import { writeFileSync } from "node:fs";\n` +
    `writeFileSync("${marker}", "should-not-exist");\n`;
  const records = [
    ["local_extension", join(cwd, ".pi", "extensions", "local.mjs"), hostileCode(markerPaths.extension)],
    ["global_extension", join(agentDir, "extensions", "global.mjs"), hostileCode(markerPaths.extension)],
    ["local_skill", join(cwd, ".pi", "skills", "local", "SKILL.md"), "---\nname: local-decoy\n---\nlocal skill\n"],
    ["global_skill", join(agentDir, "skills", "global", "SKILL.md"), "---\nname: global-decoy\n---\nglobal skill\n"],
    ["local_prompt", join(cwd, ".pi", "prompts", "local.md"), "local prompt decoy\n"],
    ["global_prompt", join(agentDir, "prompts", "global.md"), "global prompt decoy\n"],
    ["local_theme", join(cwd, ".pi", "themes", "local.json"), '{"name":"local-decoy"}\n'],
    ["global_theme", join(agentDir, "themes", "global.json"), '{"name":"global-decoy"}\n'],
    ["local_context", join(cwd, "AGENTS.md"), "local context decoy\n"],
    ["global_context", join(agentDir, "AGENTS.md"), "global context decoy\n"],
    ["parent_context", join(root, "AGENTS.md"), "parent context decoy\n"],
    ["settings", join(agentDir, "settings.json"), '{"defaultProvider":"evil","extensions":["evil"]}\n'],
    ["auth", join(agentDir, "auth.json"), '{"evil":{"type":"api_key","key":"PI-CONTAINMENT-SECRET"}}\n'],
    ["hidden_tool", join(cwd, ".pi", "extensions", "hidden-tool.mjs"), hostileCode(markerPaths.tool)],
    ["child_process_marker", join(cwd, ".pi", "extensions", "child-process.mjs"), hostileCode(markerPaths.child)],
    ["unknown_network_host", join(cwd, ".pi", "extensions", "network.mjs"), "https://unknown.invalid/phase-48\n"],
    ["oversized_result", join(cwd, ".pi", "skills", "oversized", "result.txt"), "oversized-result-".repeat(100_000)],
    ["credential_like_env", join(home, ".pi", "agent", "credential-fixture.txt"), "CREDENTIAL_LIKE_ENV=PI-CONTAINMENT-SECRET\n"],
  ];

  await Promise.all(records.map(async ([, path, content]) => {
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, content, "utf8");
  }));

  const fixtureChecksums = Object.fromEntries(records.map(([name, , content]) => [name, sha256(`${name}\0${content}`)]));
  return { cwd, agentDir, home, markerPaths, fixtureChecksums, fixtureFiles: records.length };
}

function withBoundedTimeout(operation, timeoutMs) {
  const bounded = Math.min(Math.max(Number(timeoutMs) || 250, 1), MAX_TIMEOUT_MS);
  let workTimer;
  let timeoutTimer;
  const work = new Promise((resolveWork) => {
    workTimer = setTimeout(resolveWork, bounded * 4);
  });
  const timeout = new Promise((_, reject) => {
    timeoutTimer = setTimeout(() => reject(new Error("probe_timeout")), bounded);
  });
  return Promise.race([operation(), work, timeout]).finally(() => {
    clearTimeout(workTimer);
    clearTimeout(timeoutTimer);
  });
}

function resourceCounts(resourceLoader, toolNames, fixtureFiles, providerCalls) {
  const extensions = resourceLoader.getExtensions();
  const skills = resourceLoader.getSkills();
  const prompts = resourceLoader.getPrompts();
  const themes = resourceLoader.getThemes();
  const contextFiles = resourceLoader.getAgentsFiles();
  const forbiddenTools = toolNames.filter((name) => FORBIDDEN_TOOLS.includes(name));
  return {
    extensions: extensions.extensions.length,
    skills: skills.skills.length,
    prompt_templates: prompts.prompts.length,
    themes: themes.themes.length,
    context_files: contextFiles.agentsFiles.length,
    forbidden_tools: forbiddenTools.length,
    fixture_files: fixtureFiles,
    provider_calls: providerCalls,
  };
}

function assertContained(counts, toolNames) {
  if (JSON.stringify([...toolNames].sort()) !== JSON.stringify(EXPECTED_TOOL_NAMES)) {
    throw new Error("runtime_policy_violation");
  }
  if (["extensions", "skills", "prompt_templates", "themes", "context_files", "forbidden_tools", "provider_calls"].some((key) => counts[key] !== 0)) {
    throw new Error("runtime_policy_violation");
  }
}

async function packageVersions() {
  try {
    const packageJson = JSON.parse(await readFile(PACKAGE_PATH, "utf8"));
    if (packageJson.dependencies?.["@earendil-works/pi-ai"] !== "0.83.0") throw new Error("version");
    if (packageJson.dependencies?.["@earendil-works/pi-coding-agent"] !== "0.83.0") throw new Error("version");
    if (packageJson.dependencies?.["@earendil-works/pi-storage-sqlite-node"] !== "0.83.0") throw new Error("version");
  } catch {
    throw new Error("runtime_initialization_failed");
  }
}

/** Run the offline containment probe and return a safe report plus typed exitCode. */
export async function runContainmentProbe({ fixtureMode = "success", timeoutMs = 250, onTemporaryRoot } = {}) {
  let root;
  let seeded;
  let runtime;
  let output;
  let exitCode = 0;
  let cleanupFailed = false;
  const originalSecret = process.env.PI_CONTAINMENT_FIXTURE_SECRET;
  process.env.PI_CONTAINMENT_FIXTURE_SECRET = "PI-CONTAINMENT-SECRET";

  try {
    await packageVersions();
    root = await mkdtemp(join(tmpdir(), "pi-runtime-containment-"));
    onTemporaryRoot?.(root);
    seeded = await seedFixtures(root);
    const initial = report({
      counts: emptyCounts(seeded.fixtureFiles),
      toolNames: [],
      reasonCodes: [],
      fixtureChecksums: seeded.fixtureChecksums,
    });

    try {
      runtime = await createContainedSession({ cwd: seeded.cwd, agentDir: seeded.agentDir });
      if (fixtureMode === "failure") throw new Error("runtime_initialization_failed");
      if (fixtureMode === "timeout") {
        await withBoundedTimeout(
          () => new Promise((resolveWork) => setTimeout(resolveWork, Math.max(timeoutMs, 1) * 4)),
          timeoutMs,
        );
      }
      const toolNames = runtime.session.agent.state.tools.map((tool) => tool.name).sort();
      const counts = resourceCounts(runtime.resourceLoader, toolNames, seeded.fixtureFiles, runtime.modelRuntime.providerCalls);
      assertContained(counts, toolNames);
      for (const marker of Object.values(seeded.markerPaths)) {
        try {
          await access(marker);
          throw new Error("runtime_policy_violation");
        } catch (error) {
          if (error?.message === "runtime_policy_violation") throw error;
        }
      }
      output = report({ counts, toolNames, reasonCodes: SUCCESS_REASONS, fixtureChecksums: seeded.fixtureChecksums });
    } catch (error) {
      const reasonCode = error?.message === "probe_timeout" ? "probe_timeout" : safeReason(error?.message);
      exitCode = reasonCode === "probe_timeout" ? 22 : 21;
      output = report({
        counts: emptyCounts(seeded.fixtureFiles),
        toolNames: [],
        reasonCodes: [reasonCode, "metadata_only_output"],
        fixtureChecksums: seeded.fixtureChecksums,
      });
    } finally {
      if (runtime?.session) {
        const session = runtime.session;
        runtime = undefined;
        try {
          await Promise.resolve(session.dispose());
        } catch {
          exitCode = exitCode || 21;
          output = report({
            counts: emptyCounts(seeded.fixtureFiles),
            toolNames: [],
            reasonCodes: ["runtime_initialization_failed", "metadata_only_output"],
            fixtureChecksums: seeded.fixtureChecksums,
          });
        }
      }
    }
  } catch (error) {
    exitCode = exitCode || 21;
    output = report({
      counts: emptyCounts(seeded?.fixtureFiles ?? 0),
      toolNames: [],
      reasonCodes: [safeReason(error?.message), "metadata_only_output"],
      fixtureChecksums: seeded?.fixtureChecksums ?? {},
    });
  } finally {
    if (runtime?.session) {
      try {
        await Promise.resolve(runtime.session.dispose());
      } catch {
        exitCode = exitCode || 21;
      }
    }
    if (root) {
      try {
        await rm(root, { recursive: true, force: true });
      } catch {
        cleanupFailed = true;
      }
    }
    if (originalSecret === undefined) delete process.env.PI_CONTAINMENT_FIXTURE_SECRET;
    else process.env.PI_CONTAINMENT_FIXTURE_SECRET = originalSecret;
    if (cleanupFailed) {
      exitCode = 23;
      if (output) {
        output = report({
          counts: output.counts,
          toolNames: output.tool_names,
          reasonCodes: [...output.reason_codes, "temporary_cleanup_failed"],
          fixtureChecksums: output.fixture_checksums,
        });
      }
    } else if (output) {
      output = report({
        counts: output.counts,
        toolNames: output.tool_names,
        reasonCodes: [...output.reason_codes, "temporary_state_cleaned"],
        fixtureChecksums: output.fixture_checksums,
      });
    }
  }
  return {
    report: output ?? report({ counts: emptyCounts(), toolNames: [], reasonCodes: ["runtime_initialization_failed"], fixtureChecksums: {} }),
    exitCode,
  };
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  const result = await runContainmentProbe();
  process.stdout.write(`${JSON.stringify(result.report)}\n`);
  process.exitCode = result.exitCode;
}
