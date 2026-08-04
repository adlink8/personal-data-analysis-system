#!/usr/bin/env node

import { readFileSync, writeFileSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const REGISTRY = "https://registry.npmjs.org";
const SCHEMA = "pi-package-qualification-v1";
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_PACKAGE_DIR = resolve(SCRIPT_DIR, "..");
const DEFAULT_BASELINE = resolve(SCRIPT_DIR, "../../../governance/manifests/ai/pi-package-baseline.json");

function args(argv) {
  const out = { check: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--check") out.check = true;
    else if (["--json", "--package-dir", "--baseline", "--audit-file", "--metadata-file"].includes(arg)) out[arg.slice(2).replaceAll("-", "_")] = argv[++i];
    else if (arg === "--help") out.help = true;
  }
  return out;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
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
    // npm.cmd is a Windows command shim and requires the platform shell.
    shell: process.platform === "win32"
  });
  if (result.error) return { ok: false };
  try {
    return { ok: true, value: JSON.parse(result.stdout || result.stderr || "{}"), exit: result.status };
  } catch {
    return { ok: false, exit: result.status };
  }
}

function metadataFor(name, version, fixture, cwd) {
  const key = `${name}@${version}`;
  if (fixture?.[key]) return { ok: true, value: fixture[key] };
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  return commandJson(npm, ["view", key, "--json", `--registry=${REGISTRY}`], cwd);
}

function auditFor(packageDir, auditFile) {
  if (auditFile) {
    try { return { ok: true, value: readJson(auditFile), exit: 0 }; } catch { return { ok: false, exit: 1 }; }
  }
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  return commandJson(npm, ["audit", "--omit=dev", "--json", `--registry=${REGISTRY}`], packageDir);
}

function advisoryCounts(audit) {
  const counts = audit?.metadata?.vulnerabilities ?? {};
  if (Object.keys(counts).length) return Object.fromEntries(["info", "low", "moderate", "high", "critical", "total"].map((key) => [key, Number(counts[key] ?? 0)]));
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
    value &&
    typeof value === "object" &&
    (value.auditReportVersion === 1 || value.auditReportVersion === 2) &&
    vulnerabilities &&
    typeof vulnerabilities === "object" &&
    requiredCounts.every((key) => Number.isFinite(vulnerabilities[key]) && vulnerabilities[key] >= 0)
  );
}

function reason(checks, code) {
  checks.push(code);
}

function qualify(options) {
  const packageDir = resolve(options.package_dir ?? DEFAULT_PACKAGE_DIR);
  const baseline = readJson(resolve(options.baseline ?? DEFAULT_BASELINE));
  const manifest = readJson(join(packageDir, "package.json"));
  const lock = readJson(join(packageDir, "package-lock.json"));
  const checks = [];
  const manifestReasons = [];
  const lockReasons = [];
  const metadataReasons = [];
  const scriptReasons = [];
  const auditReasons = [];

  if (baseline.schema !== "pi-package-baseline-v1") reason(checks, "baseline_schema_mismatch");
  const allowedStatuses = new Set(baseline.allowed_statuses ?? []);
  if (!allowedStatuses.has(baseline.candidate?.status)) reason(checks, "baseline_status_not_allowed");
  if (manifest.name !== baseline.candidate?.name || manifest.version !== baseline.candidate?.version) reason(manifestReasons, "candidate_identity_mismatch");
  if (manifest.type !== "module") reason(manifestReasons, "esm_required");
  if (manifest.engines?.node !== baseline.node?.engine) reason(manifestReasons, "engine_mismatch");
  const lifecycle = new Set(["preinstall", "install", "postinstall", "prepare"]);
  if (Object.keys(manifest.scripts ?? {}).some((key) => lifecycle.has(key))) reason(scriptReasons, "unapproved_install_script");

  const direct = new Map((baseline.packages ?? []).map((entry) => [entry.name, entry]));
  const directDeps = manifest.dependencies ?? {};
  if (Object.keys(directDeps).sort().join("\0") !== [...direct.keys()].sort().join("\0")) reason(manifestReasons, "dependency_set_mismatch");
  for (const entry of baseline.packages ?? []) {
    if (directDeps[entry.name] !== entry.version || !/^\d+\.\d+\.\d+$/.test(directDeps[entry.name] ?? "")) reason(manifestReasons, "non_exact_dependency");
    if (lock.packages?.[""]?.dependencies?.[entry.name] !== entry.version) reason(lockReasons, "lockfile_direct_version_drift");
  }

  const baselineOverrides = baseline.overrides ?? {};
  const manifestOverrides = manifest.overrides ?? {};
  if (JSON.stringify(manifestOverrides) !== JSON.stringify(baselineOverrides)) reason(manifestReasons, "override_outside_manifest");
  for (const [name, version] of Object.entries(baselineOverrides)) {
    const entries = matchingEntries(lock, name);
    if (!entries.length) reason(lockReasons, "override_missing");
    for (const [, value] of entries) {
      if (value.version !== version) reason(lockReasons, "transitive_version_drift");
      if (!value.resolved || !value.integrity) reason(lockReasons, "missing_integrity");
      if (value.resolved && !safeRegistryUrl(value.resolved)) reason(lockReasons, "unapproved_registry_host");
    }
  }
  for (const [name, expected] of Object.entries(baseline.transitive_pi_packages ?? {})) {
    for (const [, value] of matchingEntries(lock, name)) if (value.version !== expected) reason(lockReasons, "transitive_version_drift");
  }
  for (const entry of baseline.packages ?? []) {
    const matches = matchingEntries(lock, entry.name);
    if (!matches.length) reason(lockReasons, "package_missing_from_lockfile");
    for (const [, value] of matches) {
      if (value.version !== entry.version) reason(lockReasons, "version_drift");
      if (value.integrity !== entry.integrity) reason(lockReasons, value.integrity ? "integrity_mismatch" : "missing_integrity");
      if (!value.resolved || !safeRegistryUrl(value.resolved)) reason(lockReasons, "unapproved_registry_host");
    }
  }
  for (const [key, value] of lockEntries(lock)) {
    const name = packageName(key);
    if (value.hasInstallScript) {
      const known = (baseline.install_scripts?.known_ignored_packages ?? []).some((item) => item.name === name && item.version === value.version);
      if (!known) reason(scriptReasons, "unapproved_install_script");
    }
  }

  const metadataFixture = options.metadata_file ? readJson(resolve(options.metadata_file)) : undefined;
  for (const entry of baseline.packages ?? []) {
    const result = metadataFor(entry.name, entry.version, metadataFixture, packageDir);
    const metadata = result.value;
    const dist = metadata?.dist ?? {};
    const repository = normalizedRepository(metadata?.repository);
    if (!result.ok) reason(metadataReasons, "metadata_unavailable");
    if (metadata?.version !== entry.version || dist.integrity !== entry.integrity) reason(metadataReasons, "metadata_version_or_integrity_mismatch");
    if (!safeRegistryUrl(dist.tarball) || dist.tarball !== entry.resolved) reason(metadataReasons, "metadata_registry_mismatch");
    if (metadata?.license !== entry.license) reason(metadataReasons, "license_mismatch");
    if (repository !== entry.repository) reason(metadataReasons, "repository_mismatch");
    if (metadata?.engines?.node !== entry.engine) reason(metadataReasons, "engine_mismatch");
  }

  const auditResult = auditFor(packageDir, options.audit_file);
  const audit = auditResult.value;
  const counts = advisoryCounts(audit);
  if (counts.high > 0 || counts.critical > 0) reason(auditReasons, "audit_high_or_critical");
  if (counts.total > 0) reason(auditReasons, "audit_not_clean");
  if (!auditResult.ok || !isAuditReport(audit)) reason(auditReasons, "audit_unavailable");

  const allReasons = [...checks, ...manifestReasons, ...lockReasons, ...metadataReasons, ...scriptReasons, ...auditReasons].sort();
  const packageSecurityPass = allReasons.length === 0;
  const report = {
    schema: SCHEMA,
    candidate: { name: manifest.name, version: manifest.version },
    registry: REGISTRY,
    decision: packageSecurityPass ? "conditional" : "rejected",
    package_security_pass: packageSecurityPass,
    runtime_containment_pass: false,
    accepted: false,
    reason_codes: [...new Set(allReasons)],
    checks: {
      manifest: { pass: manifestReasons.length === 0, reason_codes: [...new Set(manifestReasons)].sort() },
      lockfile: { pass: lockReasons.length === 0, reason_codes: [...new Set(lockReasons)].sort() },
      metadata: { pass: metadataReasons.length === 0, reason_codes: [...new Set(metadataReasons)].sort() },
      install_scripts: { pass: scriptReasons.length === 0, policy: "ignore-scripts", reason_codes: [...new Set(scriptReasons)].sort() },
      audit: { pass: auditReasons.length === 0, source: "npmjs.org", severities: counts, reason_codes: [...new Set(auditReasons)].sort() },
      compatibility: { pass: false, required_plan: "48-02", package_security_pass_is_not_acceptance: true }
    },
    packages: (baseline.packages ?? []).map((entry) => ({ name: entry.name, version: entry.version, resolved: entry.resolved, integrity: entry.integrity, license: entry.license, repository: entry.repository, engine: entry.engine })),
    install_command: "npm ci --ignore-scripts --registry=https://registry.npmjs.org"
  };
  return report;
}

const options = args(process.argv.slice(2));
if (options.help) {
  console.log("Usage: node scripts/qualify-packages.mjs --check [--json path]");
  process.exit(0);
}
try {
  const report = qualify(options);
  const output = `${JSON.stringify(report, null, 2)}\n`;
  if (options.json) writeFileSync(resolve(options.json), output, "utf8");
  process.stdout.write(output);
  process.exit(report.package_security_pass ? 0 : 1);
} catch {
  const report = { schema: SCHEMA, candidate: { name: "unknown", version: "unknown" }, registry: REGISTRY, decision: "rejected", package_security_pass: false, runtime_containment_pass: false, accepted: false, reason_codes: ["qualification_input_invalid"] };
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  process.exit(1);
}
