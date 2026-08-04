#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname, join, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const REGISTRY = "https://registry.npmjs.org";
const SCHEMA = "pi-package-qualification-v1";
const DECISION_SCHEMA = "pi-package-decision-v1";
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(SCRIPT_DIR, "../../..");
const DEFAULT_PACKAGE_DIR = resolve(SCRIPT_DIR, "..");
const DEFAULT_BASELINE = resolve(PROJECT_ROOT, "governance/manifests/ai/pi-package-baseline.json");
const DEFAULT_TOOL_REGISTRY = resolve(PROJECT_ROOT, "governance/manifests/ai/pi-tool-registry.json");
const DEFAULT_NETWORK_ALLOWLIST = resolve(PROJECT_ROOT, "governance/manifests/ai/pi-network-allowlist.json");
const DEFAULT_RUNTIME_EVIDENCE = resolve(PROJECT_ROOT, "ops/reports/audits/pi-runtime-containment.json");
const DEFAULT_REPORT = resolve(PROJECT_ROOT, "ops/reports/audits/pi-package-qualification.json");
const DEFAULT_DECISION = resolve(PROJECT_ROOT, "governance/manifests/ai/pi-package-decision.json");
const DEFAULT_MARKDOWN = resolve(PROJECT_ROOT, "ops/reports/audits/pi-package-qualification.md");
const SAFE_RUNTIME_STATUSES = new Set(["pass", "passed", "accepted"]);
const SAFE_REASON_CODES = new Set([
  "baseline_schema_mismatch", "baseline_status_not_allowed", "candidate_identity_mismatch", "esm_required",
  "engine_mismatch", "unapproved_install_script", "dependency_set_mismatch", "non_exact_dependency",
  "lockfile_direct_version_drift", "override_outside_manifest", "override_missing", "transitive_version_drift",
  "missing_integrity", "unapproved_registry_host", "package_missing_from_lockfile", "version_drift",
  "integrity_mismatch", "metadata_unavailable", "metadata_version_or_integrity_mismatch", "metadata_registry_mismatch",
  "license_mismatch", "repository_mismatch", "audit_high_or_critical", "audit_not_clean", "audit_unavailable",
  "tool_registry_invalid", "network_allowlist_invalid",
  "runtime_evidence_missing", "runtime_evidence_invalid", "runtime_evidence_unknown_status", "runtime_evidence_missing_run_id",
  "runtime_evidence_mixed_run", "runtime_evidence_stale", "runtime_containment_failed", "runtime_privacy_failed",
  "runtime_fingerprint_changed", "runtime_test_failure", "qualification_input_invalid"
]);

function args(argv) {
  const out = { check: false };
  const valueArgs = new Set([
    "--json", "--package-dir", "--baseline", "--audit-file", "--metadata-file", "--runtime-evidence",
    "--tool-registry", "--network-allowlist", "--decision-json", "--markdown", "--owner", "--reviewed-at", "--expiry"
  ]);
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--check") out.check = true;
    else if (valueArgs.has(arg)) out[arg.slice(2).replaceAll("-", "_")] = argv[++i];
    else if (arg === "--help") out.help = true;
  }
  return out;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function readJsonMaybe(path) {
  try { return { present: true, value: readJson(path), bytes: readFileSync(path) }; }
  catch { return { present: false, value: null, bytes: null }; }
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sha256File(path) {
  return sha256(readFileSync(path));
}

function hashObject(value) {
  return sha256(Buffer.from(JSON.stringify(value), "utf8"));
}

function packageName(lockKey) {
  const marker = "node_modules/";
  return lockKey.slice(lockKey.lastIndexOf(marker) + marker.length);
}

function lockEntries(lock) {
  return Object.entries(lock.packages ?? {}).filter(([key]) => key.startsWith("node_modules/") && !lock.packages[key].link);
}

function matchingEntries(lock, name) {
  return lockEntries(lock).filter(([key]) => packageName(key) === name);
}

function safeRegistryUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === "registry.npmjs.org";
  } catch {
    return false;
  }
}

function normalizedRepository(value) {
  const raw = typeof value === "string" ? value : value?.url;
  if (!raw) return "";
  return raw.replace(/^git\+/, "").replace(/\.git$/, "").replace(/\/$/, "");
}

function commandJson(command, commandArgs, cwd) {
  const result = spawnSync(command, commandArgs, {
    cwd,
    encoding: "utf8",
    windowsHide: true,
    shell: process.platform === "win32"
  });
  if (result.error) return { ok: false, exit: null };
  try {
    return { ok: true, value: JSON.parse(result.stdout || result.stderr || "{}"), exit: result.status };
  } catch {
    return { ok: false, exit: result.status };
  }
}

function metadataFor(name, version, fixture, cwd) {
  const key = `${name}@${version}`;
  if (fixture?.[key]) return { ok: true, value: fixture[key], exit: 0 };
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  return commandJson(npm, ["view", key, "--json", `--registry=${REGISTRY}`], cwd);
}

function auditFor(packageDir, auditFile) {
  if (auditFile) {
    const result = readJsonMaybe(resolve(auditFile));
    return result.present ? { ok: true, value: result.value, exit: 0 } : { ok: false, exit: 1 };
  }
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  return commandJson(npm, ["audit", "--omit=dev", "--json", `--registry=${REGISTRY}`], packageDir);
}

function advisoryCounts(audit) {
  const counts = audit?.metadata?.vulnerabilities ?? {};
  if (Object.keys(counts).length) {
    return Object.fromEntries(["info", "low", "moderate", "high", "critical", "total"].map((key) => [key, Number(counts[key] ?? 0)]));
  }
  const result = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 };
  for (const advisory of Object.values(audit?.vulnerabilities ?? {})) {
    const severity = String(advisory.severity ?? "unknown").toLowerCase();
    if (severity in result) result[severity] += 1;
    result.total += 1;
  }
  return result;
}

function isAuditReport(value) {
  const vulnerabilities = value?.metadata?.vulnerabilities;
  const requiredCounts = ["info", "low", "moderate", "high", "critical", "total"];
  return Boolean(
    value && typeof value === "object" && (value.auditReportVersion === 1 || value.auditReportVersion === 2) &&
    vulnerabilities && typeof vulnerabilities === "object" &&
    requiredCounts.every((key) => Number.isFinite(vulnerabilities[key]) && vulnerabilities[key] >= 0)
  );
}

function addReason(checks, code) {
  if (SAFE_REASON_CODES.has(code)) checks.push(code);
}

function uniqueSorted(values) {
  return [...new Set(values)].sort();
}

function isSha(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function safeIntegrity(value) {
  return typeof value === "string" && /^sha512-[A-Za-z0-9+/=]+$/.test(value) ? value : "invalid";
}

function safeRepository(value) {
  return typeof value === "string" && /^https:\/\/github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/.test(value) ? value : "unapproved";
}

function safeEngine(value) {
  return typeof value === "string" && /^>=\d+\.\d+\.\d+$/.test(value) ? value : "unknown";
}

function safeIdentifier(value, fallback = "unknown") {
  return typeof value === "string" && /^[A-Za-z0-9@._+/-]+$/.test(value) ? value : fallback;
}

function validToolRegistry(value) {
  const tools = value?.tools;
  if (value?.schema !== "pi-tool-registry-v1" || value?.version !== "48.02.1" || value?.phase !== 48) return false;
  if (!Array.isArray(tools) || tools.length !== 2) return false;
  const names = tools.map((tool) => tool?.name).sort();
  if (names.join("\0") !== ["domain_candidate", "domain_inspect"].join("\0")) return false;
  if (!tools.every((tool) => tool.kind === "synthetic_domain" && Array.isArray(tool.event_ids) && tool.event_ids.length === 1)) return false;
  const eventIds = tools.flatMap((tool) => tool.event_ids);
  if (new Set(eventIds).size !== eventIds.length) return false;
  const capabilities = ["filesystem", "process", "network", "credentials", "authority_writes"];
  if (!tools.every((tool) => capabilities.every((key) => Array.isArray(tool.capabilities?.[key]) && tool.capabilities[key].length === 0))) return false;
  if (JSON.stringify(value.forbidden_builtin_tools) !== JSON.stringify(["bash", "edit", "find", "grep", "ls", "read", "write"])) return false;
  return value.policy?.default === "deny" && value.policy?.provider_calls === 0 && Array.isArray(value.policy?.side_effects) && value.policy.side_effects.length === 0;
}

function validNetworkAllowlist(value) {
  return value?.schema === "pi-network-allowlist-v1" &&
    value?.version === "48.02.1" &&
    value?.phase === 48 &&
    value?.default === "deny" &&
    Array.isArray(value.hosts) && value.hosts.length === 0 &&
    Array.isArray(value.ports) && value.ports.length === 0 &&
    Array.isArray(value.methods) && value.methods.length === 0 &&
    value.policy?.provider_calls === 0 &&
    value.policy?.unknown_hosts === "deny" &&
    value.policy?.network === "offline";
}

function dateOrDefault(value, fallback) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) ? value : fallback;
}

function addDaysIso(date, days) {
  return new Date(new Date(date).getTime() + days * 86400000).toISOString();
}

function defaultRuntimeEvidence(path) {
  return {
    path,
    present: false,
    value: null,
    checksum: null
  };
}

function loadRuntimeEvidence(path) {
  const result = readJsonMaybe(path);
  if (!result.present) return defaultRuntimeEvidence(path);
  return { path, present: true, value: result.value, checksum: sha256(result.bytes) };
}

function runtimeAssessment(runtime, checksums, runId, now) {
  if (!runtime.present) return { pass: false, conditional: ["runtime_evidence_missing"], hard: [], details: { present: false } };
  const value = runtime.value;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { pass: false, conditional: [], hard: ["runtime_evidence_invalid"], details: { present: true } };
  }
  const hard = [];
  if (!SAFE_RUNTIME_STATUSES.has(value.status)) addReason(hard, "runtime_evidence_unknown_status");
  if (!value.run_id) addReason(hard, "runtime_evidence_missing_run_id");
  if (value.run_id && value.run_id !== runId) addReason(hard, "runtime_evidence_mixed_run");
  const expected = { ...checksums };
  const supplied = value.evidence_checksums ?? value.package_checksums;
  for (const key of Object.keys(checksums).filter((key) => key !== "runtime_evidence")) {
    if (!isSha(supplied?.[key]) || supplied[key] !== expected[key]) addReason(hard, "runtime_evidence_mixed_run");
  }
  const runtimeChecksumValue = { ...value };
  delete runtimeChecksumValue.runtime_evidence_checksum;
  if (!isSha(value.runtime_evidence_checksum) || value.runtime_evidence_checksum !== hashObject(runtimeChecksumValue)) {
    addReason(hard, "runtime_evidence_mixed_run");
  }
  const expiry = value.expiry ?? value.expires_at;
  if (expiry && (!Number.isFinite(Date.parse(expiry)) || Date.parse(expiry) <= now.getTime())) addReason(hard, "runtime_evidence_stale");
  if (value.containment_pass !== true && value.pass !== true) addReason(hard, "runtime_containment_failed");
  if (value.privacy_pass !== true) addReason(hard, "runtime_privacy_failed");
  if (value.protected_fingerprints_unchanged !== true) addReason(hard, "runtime_fingerprint_changed");
  if (value.tests_passed !== true) addReason(hard, "runtime_test_failure");
  const details = {
    present: true,
    schema: safeIdentifier(value.schema, "unknown"),
    status: safeIdentifier(value.status, "unknown"),
    run_id_match: value.run_id === runId,
    evidence_checksums_match: hard.every((code) => code !== "runtime_evidence_mixed_run"),
    checks_pass: hard.length === 0
  };
  return { pass: hard.length === 0, conditional: [], hard: uniqueSorted(hard), details };
}

function qualify(options) {
  const packageDir = resolve(options.package_dir ?? DEFAULT_PACKAGE_DIR);
  const baselinePath = resolve(options.baseline ?? DEFAULT_BASELINE);
  const toolRegistryPath = resolve(options.tool_registry ?? DEFAULT_TOOL_REGISTRY);
  const networkAllowlistPath = resolve(options.network_allowlist ?? DEFAULT_NETWORK_ALLOWLIST);
  const runtimePath = resolve(options.runtime_evidence ?? DEFAULT_RUNTIME_EVIDENCE);
  const baseline = readJson(baselinePath);
  const manifestPath = join(packageDir, "package.json");
  const lockPath = join(packageDir, "package-lock.json");
  const manifest = readJson(manifestPath);
  const lock = readJson(lockPath);
  const toolRegistry = readJson(toolRegistryPath);
  const networkAllowlist = readJson(networkAllowlistPath);
  const checks = [];
  const manifestReasons = [];
  const lockReasons = [];
  const metadataReasons = [];
  const scriptReasons = [];
  const auditReasons = [];
  const boundaryReasons = [];

  if (!validToolRegistry(toolRegistry)) addReason(boundaryReasons, "tool_registry_invalid");
  if (!validNetworkAllowlist(networkAllowlist)) addReason(boundaryReasons, "network_allowlist_invalid");

  if (baseline.schema !== "pi-package-baseline-v1") addReason(checks, "baseline_schema_mismatch");
  const allowedStatuses = new Set(baseline.allowed_statuses ?? []);
  if (!allowedStatuses.has(baseline.candidate?.status)) addReason(checks, "baseline_status_not_allowed");
  if (manifest.name !== baseline.candidate?.name || manifest.version !== baseline.candidate?.version) addReason(manifestReasons, "candidate_identity_mismatch");
  if (manifest.type !== "module") addReason(manifestReasons, "esm_required");
  if (manifest.engines?.node !== baseline.node?.engine) addReason(manifestReasons, "engine_mismatch");
  const lifecycle = new Set(["preinstall", "install", "postinstall", "prepare"]);
  if (Object.keys(manifest.scripts ?? {}).some((key) => lifecycle.has(key))) addReason(scriptReasons, "unapproved_install_script");

  const direct = new Map((baseline.packages ?? []).map((entry) => [entry.name, entry]));
  const directDeps = manifest.dependencies ?? {};
  if (Object.keys(directDeps).sort().join("\0") !== [...direct.keys()].sort().join("\0")) addReason(manifestReasons, "dependency_set_mismatch");
  for (const entry of baseline.packages ?? []) {
    if (directDeps[entry.name] !== entry.version || !/^\d+\.\d+\.\d+$/.test(directDeps[entry.name] ?? "")) addReason(manifestReasons, "non_exact_dependency");
    if (lock.packages?.[""]?.dependencies?.[entry.name] !== entry.version) addReason(lockReasons, "lockfile_direct_version_drift");
  }

  const baselineOverrides = baseline.overrides ?? {};
  if (JSON.stringify(manifest.overrides ?? {}) !== JSON.stringify(baselineOverrides)) addReason(manifestReasons, "override_outside_manifest");
  for (const [name, version] of Object.entries(baselineOverrides)) {
    const entries = matchingEntries(lock, name);
    if (!entries.length) addReason(lockReasons, "override_missing");
    for (const [, value] of entries) {
      if (value.version !== version) addReason(lockReasons, "transitive_version_drift");
      if (!value.resolved || !value.integrity) addReason(lockReasons, "missing_integrity");
      if (value.resolved && !safeRegistryUrl(value.resolved)) addReason(lockReasons, "unapproved_registry_host");
    }
  }
  for (const [name, expected] of Object.entries(baseline.transitive_pi_packages ?? {})) {
    for (const [, value] of matchingEntries(lock, name)) if (value.version !== expected) addReason(lockReasons, "transitive_version_drift");
  }
  for (const entry of baseline.packages ?? []) {
    const matches = matchingEntries(lock, entry.name);
    if (!matches.length) addReason(lockReasons, "package_missing_from_lockfile");
    for (const [, value] of matches) {
      if (value.version !== entry.version) addReason(lockReasons, "version_drift");
      if (value.integrity !== entry.integrity) addReason(lockReasons, value.integrity ? "integrity_mismatch" : "missing_integrity");
      if (!value.resolved || !safeRegistryUrl(value.resolved)) addReason(lockReasons, "unapproved_registry_host");
    }
  }
  for (const [key, value] of lockEntries(lock)) {
    const name = packageName(key);
    if (value.hasInstallScript) {
      const known = (baseline.install_scripts?.known_ignored_packages ?? []).some((item) => item.name === name && item.version === value.version);
      if (!known) addReason(scriptReasons, "unapproved_install_script");
    }
  }

  const metadataFixture = options.metadata_file ? readJson(resolve(options.metadata_file)) : undefined;
  for (const entry of baseline.packages ?? []) {
    const result = metadataFor(entry.name, entry.version, metadataFixture, packageDir);
    const metadata = result.value;
    const dist = metadata?.dist ?? {};
    const repository = normalizedRepository(metadata?.repository);
    if (!result.ok) addReason(metadataReasons, "metadata_unavailable");
    if (metadata?.version !== entry.version || dist.integrity !== entry.integrity) addReason(metadataReasons, "metadata_version_or_integrity_mismatch");
    if (!safeRegistryUrl(dist.tarball) || dist.tarball !== entry.resolved) addReason(metadataReasons, "metadata_registry_mismatch");
    if (metadata?.license !== entry.license) addReason(metadataReasons, "license_mismatch");
    if (repository !== entry.repository) addReason(metadataReasons, "repository_mismatch");
    if (metadata?.engines?.node !== entry.engine) addReason(metadataReasons, "engine_mismatch");
  }

  const auditResult = auditFor(packageDir, options.audit_file);
  const audit = auditResult.value;
  const counts = advisoryCounts(audit);
  if (counts.high > 0 || counts.critical > 0) addReason(auditReasons, "audit_high_or_critical");
  if (counts.total > 0) addReason(auditReasons, "audit_not_clean");
  if (!auditResult.ok || !isAuditReport(audit)) addReason(auditReasons, "audit_unavailable");

  const checksums = {
    package_json: sha256File(manifestPath),
    package_lock: sha256File(lockPath),
    package_baseline: sha256File(baselinePath),
    tool_registry: sha256File(toolRegistryPath),
    network_allowlist: sha256File(networkAllowlistPath),
    runtime_evidence: null
  };
  const runBasis = {
    package_json: checksums.package_json,
    package_lock: checksums.package_lock,
    package_baseline: checksums.package_baseline,
    tool_registry: checksums.tool_registry,
    network_allowlist: checksums.network_allowlist
  };
  const runId = `piq_${hashObject(runBasis).slice(0, 24)}`;
  const runtime = loadRuntimeEvidence(runtimePath);
  checksums.runtime_evidence = runtime.checksum;
  const runtimeResult = runtimeAssessment(runtime, checksums, runId, new Date());
  const packageReasonCodes = uniqueSorted([...checks, ...manifestReasons, ...lockReasons, ...metadataReasons, ...scriptReasons, ...auditReasons, ...boundaryReasons]);
  const packageSecurityPass = packageReasonCodes.length === 0;
  const evidenceChecksum = hashObject(checksums);
  const hardReasons = uniqueSorted([...packageReasonCodes, ...runtimeResult.hard]);
  const conditionalReasons = uniqueSorted(runtimeResult.conditional);
  const decision = hardReasons.length ? "rejected" : runtimeResult.pass ? "accepted" : "conditional";
  const now = new Date();
  const reviewedAt = dateOrDefault(options.reviewed_at, now.toISOString());
  const expiry = dateOrDefault(options.expiry, addDaysIso(reviewedAt, 30));
  const owner = typeof options.owner === "string" && options.owner.trim() ? options.owner.trim() : "Phase 48 security governance";
  const triggers = (baseline.requalification_triggers ?? []).filter((value) => typeof value === "string");
  const allowedScope = decision === "accepted"
    ? ["Phase 49 dependency use only after its own runtime and activation gates"]
    : decision === "conditional"
      ? ["isolated qualification evidence only", "no Phase 49 production dependency use"]
      : [];
  const allReasons = uniqueSorted([...hardReasons, ...conditionalReasons]);
  const gateChecks = {
    "SEC-01": { pass: packageSecurityPass, reason_codes: packageSecurityPass ? [] : packageReasonCodes },
    "SEC-02": { pass: runtimeResult.pass, reason_codes: runtimeResult.pass ? [] : uniqueSorted([...runtimeResult.hard, ...runtimeResult.conditional]) },
    "TOOL-02": { pass: runtimeResult.pass, reason_codes: runtimeResult.pass ? [] : uniqueSorted([...runtimeResult.hard, ...runtimeResult.conditional]) }
  };
  const report = {
    schema: SCHEMA,
    version: "48.03.1",
    run_id: runId,
    candidate: { name: safeIdentifier(manifest.name), version: safeIdentifier(manifest.version) },
    registry: REGISTRY,
    decision,
    accepted: decision === "accepted",
    package_security_pass: packageSecurityPass,
    runtime_containment_pass: runtimeResult.pass,
    reason_codes: allReasons,
    evidence_checksums: checksums,
    evidence_checksum: evidenceChecksum,
    checks: {
      manifest: { pass: manifestReasons.length === 0, reason_codes: uniqueSorted(manifestReasons) },
      lockfile: { pass: lockReasons.length === 0, reason_codes: uniqueSorted(lockReasons) },
      metadata: { pass: metadataReasons.length === 0, reason_codes: uniqueSorted(metadataReasons) },
      install_scripts: { pass: scriptReasons.length === 0, policy: "ignore-scripts", reason_codes: uniqueSorted(scriptReasons) },
      audit: { pass: auditReasons.length === 0, source: "npmjs.org", severities: counts, reason_codes: uniqueSorted(auditReasons) },
      tool_registry: { pass: boundaryReasons.includes("tool_registry_invalid") === false, reason_codes: boundaryReasons.filter((code) => code === "tool_registry_invalid") },
      network_allowlist: { pass: boundaryReasons.includes("network_allowlist_invalid") === false, reason_codes: boundaryReasons.filter((code) => code === "network_allowlist_invalid") },
      runtime_containment: runtimeResult.details,
      gates: gateChecks
    },
    governance: { owner, reviewed_at: reviewedAt, expiry, requalification_triggers: triggers, allowed_scope: allowedScope },
    packages: (baseline.packages ?? []).map((entry) => ({ name: safeIdentifier(entry.name), version: safeIdentifier(entry.version), resolved: safeRegistryUrl(entry.resolved) ? entry.resolved : "unapproved", integrity: safeIntegrity(entry.integrity), license: safeIdentifier(entry.license), repository: safeRepository(entry.repository), engine: safeEngine(entry.engine) })),
    install_command: "npm ci --ignore-scripts --registry=https://registry.npmjs.org"
  };
  const decisionDocument = {
    schema: DECISION_SCHEMA,
    qualification_schema: SCHEMA,
    run_id: runId,
    status: decision,
    accepted: decision === "accepted",
    owner,
    reviewed_at: reviewedAt,
    expiry,
    requalification_triggers: triggers,
    allowed_scope: allowedScope,
    reason_codes: allReasons,
    evidence_checksum: evidenceChecksum,
    evidence_checksums: checksums,
    requirements: gateChecks
  };
  return { report, decisionDocument, checksums, evidenceChecksum, runtimePath, packageDir };
}

function markdownFor(decision) {
  const lines = [
    "# Pi Package Qualification",
    "",
    `- Schema: ${SCHEMA}`,
    `- Decision: ${decision.status}`,
    `- Accepted: ${decision.accepted ? "true" : "false"}`,
    `- Run ID: ${decision.run_id}`,
    `- Evidence checksum: ${decision.evidence_checksum}`,
    `- Owner: ${decision.owner}`,
    `- Reviewed at: ${decision.reviewed_at}`,
    `- Expiry: ${decision.expiry}`,
    "",
    "## Scope",
    "",
    ...(decision.allowed_scope.length ? decision.allowed_scope.map((value) => `- ${value}`) : ["- none"]),
    "",
    "## Reason codes",
    "",
    ...(decision.reason_codes.length ? decision.reason_codes.map((value) => `- ${value}`) : ["- none"]),
    "",
    "## Requirements",
    "",
    ...["SEC-01", "SEC-02", "TOOL-02"].map((id) => `- ${id}: ${decision.requirements[id].pass ? "pass" : "blocked"}`),
    "",
    "This report is evidence only; it does not install packages, activate Pi, call a Provider, or modify authority state."
  ];
  return `${lines.join("\n")}\n`;
}

function shouldWriteDefaultArtifacts(options, packageDir) {
  return packageDir === DEFAULT_PACKAGE_DIR && !options.package_dir;
}

const options = args(process.argv.slice(2));
if (options.help) {
  console.log("Usage: node scripts/qualify-packages.mjs --check [--json path] [--runtime-evidence path]");
  process.exit(0);
}
try {
  const result = qualify(options);
  const output = `${JSON.stringify(result.report, null, 2)}\n`;
  const writeDefaults = shouldWriteDefaultArtifacts(options, result.packageDir);
  const reportPath = options.json ? resolve(options.json) : writeDefaults ? DEFAULT_REPORT : null;
  const decisionPath = options.decision_json ? resolve(options.decision_json) : writeDefaults ? DEFAULT_DECISION : null;
  const markdownPath = options.markdown ? resolve(options.markdown) : writeDefaults ? DEFAULT_MARKDOWN : null;
  if (reportPath) writeFileSync(reportPath, output, "utf8");
  if (decisionPath) writeFileSync(decisionPath, `${JSON.stringify(result.decisionDocument, null, 2)}\n`, "utf8");
  if (markdownPath) writeFileSync(markdownPath, markdownFor(result.decisionDocument), "utf8");
  process.stdout.write(output);
  process.exit(result.report.package_security_pass ? 0 : 1);
} catch {
  const report = {
    schema: SCHEMA,
    version: "48.03.1",
    run_id: "piq_invalid_input",
    decision: "rejected",
    accepted: false,
    package_security_pass: false,
    runtime_containment_pass: false,
    reason_codes: ["qualification_input_invalid"]
  };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exit(1);
}
