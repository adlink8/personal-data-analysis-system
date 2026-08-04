import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const root = resolve(import.meta.dirname, "../../..");
const script = resolve(root, "apps/personal_intelligence_kernel/scripts/qualify-packages.mjs");
const baselinePath = resolve(root, "governance/manifests/ai/pi-package-baseline.json");
const baseline = JSON.parse(readFileSync(baselinePath, "utf8"));
const packageJson = JSON.parse(readFileSync(resolve(root, "apps/personal_intelligence_kernel/package.json"), "utf8"));
const lock = JSON.parse(readFileSync(resolve(root, "apps/personal_intelligence_kernel/package-lock.json"), "utf8"));

function fixture(mutator, audit = { auditReportVersion: 2, vulnerabilities: {}, metadata: { vulnerabilities: { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 } } }) {
  const dir = mkdtempSync(join(tmpdir(), "pi-package-qualification-"));
  const pkg = structuredClone(packageJson);
  const lck = structuredClone(lock);
  const base = structuredClone(baseline);
  mutator?.({ pkg, lck, base });
  const metadata = Object.fromEntries(base.packages.map((entry) => [
    `${entry.name}@${entry.version}`,
    { version: entry.version, license: entry.license, engines: { node: entry.engine }, repository: { url: `git+${entry.repository}.git` }, dist: { tarball: entry.resolved, integrity: entry.integrity } }
  ]));
  const auditPath = join(dir, "audit.json");
  const metadataPath = join(dir, "metadata.json");
  writeFileSync(join(dir, "package.json"), JSON.stringify(pkg));
  writeFileSync(join(dir, "package-lock.json"), JSON.stringify(lck));
  writeFileSync(join(dir, "baseline.json"), JSON.stringify(base));
  writeFileSync(auditPath, JSON.stringify(audit));
  writeFileSync(metadataPath, JSON.stringify(metadata));
  const result = spawnSync(process.execPath, [script, "--check", "--package-dir", dir, "--baseline", join(dir, "baseline.json"), "--audit-file", auditPath, "--metadata-file", metadataPath], { encoding: "utf8", cwd: root });
  const report = JSON.parse(result.stdout);
  rmSync(dir, { recursive: true, force: true });
  return { result, report };
}

test("package-qualification clean security pass remains conditional", () => {
  const { result, report } = fixture();
  assert.equal(result.status, 0);
  assert.equal(report.package_security_pass, true);
  assert.equal(report.accepted, false);
  assert.equal(report.decision, "conditional");
});

test("package-qualification rejects High advisory", () => {
  const { result, report } = fixture(undefined, { vulnerabilities: { undici: { severity: "high" } }, metadata: { vulnerabilities: { total: 1, high: 1 } } });
  assert.notEqual(result.status, 0);
  assert.ok(report.reason_codes.includes("audit_high_or_critical"));
});

test("package-qualification rejects malformed audit report", () => {
  const { result, report } = fixture(undefined, {});
  assert.notEqual(result.status, 0);
  assert.ok(report.reason_codes.includes("audit_unavailable"));
});

test("package-qualification rejects audit envelope without numeric totals", () => {
  const { result, report } = fixture(undefined, { auditReportVersion: 2, metadata: { vulnerabilities: {} } });
  assert.notEqual(result.status, 0);
  assert.ok(report.reason_codes.includes("audit_unavailable"));
});

test("package-qualification rejects unknown install script", () => {
  const { result, report } = fixture(({ lck }) => { lck.packages["node_modules/unknown-script"] = { version: "1.0.0", resolved: "https://registry.npmjs.org/unknown-script/-/unknown-script-1.0.0.tgz", integrity: "sha512-unknown", license: "MIT", hasInstallScript: true }; });
  assert.notEqual(result.status, 0);
  assert.ok(report.reason_codes.includes("unapproved_install_script"));
});

test("package-qualification rejects altered integrity and registry host", () => {
  const integrity = fixture(({ lck }) => { lck.packages["node_modules/@earendil-works/pi-ai"].integrity = "sha512-altered"; });
  assert.notEqual(integrity.result.status, 0);
  assert.ok(integrity.report.reason_codes.includes("integrity_mismatch"));
  const host = fixture(({ lck }) => { lck.packages["node_modules/@earendil-works/pi-ai"].resolved = "https://evil.example/pi-ai.tgz"; });
  assert.notEqual(host.result.status, 0);
  assert.ok(host.report.reason_codes.includes("unapproved_registry_host"));
});
