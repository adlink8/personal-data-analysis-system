from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "personal_intelligence_kernel"
SCRIPT = APP / "scripts" / "qualify-packages.mjs"
REPORT = ROOT / "ops" / "reports" / "audits" / "pi-package-qualification.json"
DECISION = ROOT / "governance" / "manifests" / "ai" / "pi-package-decision.json"
MARKDOWN = ROOT / "ops" / "reports" / "audits" / "pi-package-qualification.md"
BASELINE = ROOT / "governance" / "manifests" / "ai" / "pi-package-baseline.json"
TOOL_REGISTRY = ROOT / "governance" / "manifests" / "ai" / "pi-tool-registry.json"
NETWORK_ALLOWLIST = ROOT / "governance" / "manifests" / "ai" / "pi-network-allowlist.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_object(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def _iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_decision(document: dict, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    assert document["schema"] == "pi-package-decision-v1"
    assert document["qualification_schema"] == "pi-package-qualification-v1"
    assert document["status"] in {"accepted", "conditional", "rejected"}
    assert isinstance(document["owner"], str) and document["owner"].strip()
    reviewed = datetime.fromisoformat(document["reviewed_at"].replace("Z", "+00:00"))
    expiry = datetime.fromisoformat(document["expiry"].replace("Z", "+00:00"))
    assert reviewed <= now + timedelta(minutes=2)
    assert expiry > now
    assert document["requalification_triggers"]
    assert all(isinstance(value, str) and value.strip() for value in document["requalification_triggers"])
    assert isinstance(document["allowed_scope"], list)
    assert re.fullmatch(r"[0-9a-f]{64}", document["evidence_checksum"])
    assert set(document["evidence_checksums"]) == {
        "package_json", "package_lock", "package_baseline", "tool_registry", "network_allowlist", "runtime_evidence"
    }
    for key, value in document["evidence_checksums"].items():
        assert value is None or re.fullmatch(r"[0-9a-f]{64}", value), key
    assert document["accepted"] is (document["status"] == "accepted")
    assert document["status"] != "accepted" or all(document["requirements"][key]["pass"] for key in ("SEC-01", "SEC-02", "TOOL-02"))


def _assert_no_sensitive_content(value: object) -> None:
    sensitive_keys = {"api_key", "apikey", "secret", "token", "password", "cookie", "authorization", "proxy"}
    if isinstance(value, dict):
        for key, child in value.items():
            assert key.lower() not in sensitive_keys, key
            _assert_no_sensitive_content(child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_sensitive_content(child)
    elif isinstance(value, str):
        assert not re.search(r"(?:[A-Za-z]:\\|/home/|/Users/|-----BEGIN|sk-[A-Za-z0-9])", value)


def _fixture(tmp_path: Path, *, runtime: dict | None = None) -> tuple[Path, Path, Path, Path]:
    package_dir = tmp_path / "package"
    package_dir.mkdir(exist_ok=True)
    shutil.copy2(APP / "package.json", package_dir / "package.json")
    shutil.copy2(APP / "package-lock.json", package_dir / "package-lock.json")
    baseline = tmp_path / "baseline.json"
    tool_registry = tmp_path / "tool-registry.json"
    network_allowlist = tmp_path / "network-allowlist.json"
    shutil.copy2(BASELINE, baseline)
    shutil.copy2(TOOL_REGISTRY, tool_registry)
    shutil.copy2(NETWORK_ALLOWLIST, network_allowlist)
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({
        "auditReportVersion": 2,
        "vulnerabilities": {},
        "metadata": {"vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "total": 0}},
    }), encoding="utf-8")
    metadata = {}
    for entry in json.loads(baseline.read_text(encoding="utf-8"))["packages"]:
        metadata[f'{entry["name"]}@{entry["version"]}'] = {
            "version": entry["version"],
            "license": entry["license"],
            "engines": {"node": entry["engine"]},
            "repository": {"url": f'git+{entry["repository"]}.git'},
            "dist": {"tarball": entry["resolved"], "integrity": entry["integrity"]},
        }
    metadata_file = tmp_path / "metadata.json"
    metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
    runtime_file = tmp_path / "runtime.json"
    if runtime is not None:
        runtime_file.write_text(json.dumps(runtime), encoding="utf-8")
    return package_dir, baseline, tool_registry, network_allowlist, audit, metadata_file, runtime_file


def _run_fixture(tmp_path: Path, *, runtime: dict | None = None, mutate=None):
    package_dir, baseline, tool_registry, network_allowlist, audit, metadata, runtime_file = _fixture(tmp_path, runtime=runtime)
    mutate and mutate(tool_registry, network_allowlist)
    report = tmp_path / "report.json"
    decision = tmp_path / "decision.json"
    markdown = tmp_path / "report.md"
    command = [
        "node", str(SCRIPT), "--check", "--package-dir", str(package_dir), "--baseline", str(baseline),
        "--tool-registry", str(tool_registry), "--network-allowlist", str(network_allowlist),
        "--audit-file", str(audit), "--metadata-file", str(metadata), "--runtime-evidence", str(runtime_file),
        "--json", str(report), "--decision-json", str(decision), "--markdown", str(markdown),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    return result, json.loads(report.read_text(encoding="utf-8")), json.loads(decision.read_text(encoding="utf-8")), markdown.read_text(encoding="utf-8"), (package_dir, baseline, tool_registry, network_allowlist, runtime_file)


def _valid_runtime(package_dir: Path, baseline: Path, tool_registry: Path, network_allowlist: Path) -> dict:
    checksums = {
        "package_json": _sha256(package_dir / "package.json"),
        "package_lock": _sha256(package_dir / "package-lock.json"),
        "package_baseline": _sha256(baseline),
        "tool_registry": _sha256(tool_registry),
        "network_allowlist": _sha256(network_allowlist),
    }
    run_id = f'piq_{_hash_object(checksums)[:24]}'
    runtime = {
        "schema": "pi-runtime-containment-v1",
        "status": "passed",
        "run_id": run_id,
        "evidence_checksums": checksums,
        "containment_pass": True,
        "privacy_pass": True,
        "protected_fingerprints_unchanged": True,
        "tests_passed": True,
        "expiry": _iso(30),
    }
    runtime["runtime_evidence_checksum"] = _hash_object(runtime)
    return runtime


def test_missing_containment_is_conditional_and_never_accepted(tmp_path: Path) -> None:
    result, report, decision, markdown, _ = _run_fixture(tmp_path)
    assert result.returncode == 0
    assert report["decision"] == decision["status"] == "conditional"
    assert report["run_id"] == decision["run_id"]
    assert report["evidence_checksum"] == decision["evidence_checksum"]
    assert "runtime_evidence_missing" in report["reason_codes"]
    assert "Decision: conditional" in markdown
    assert "Accepted: false" in markdown


def test_valid_containment_can_only_accept_same_run(tmp_path: Path) -> None:
    package_dir, baseline, tool_registry, network_allowlist, *_ = _fixture(tmp_path)
    runtime = _valid_runtime(package_dir, baseline, tool_registry, network_allowlist)
    result, report, decision, _, _ = _run_fixture(tmp_path, runtime=runtime)
    assert result.returncode == 0
    assert report["decision"] == decision["status"] == "accepted"
    assert all(decision["requirements"][key]["pass"] for key in ("SEC-01", "SEC-02", "TOOL-02"))


def test_tampered_runtime_evidence_checksum_is_rejected(tmp_path: Path) -> None:
    package_dir, baseline, tool_registry, network_allowlist, *_ = _fixture(tmp_path)
    runtime = _valid_runtime(package_dir, baseline, tool_registry, network_allowlist)
    runtime["tests_passed"] = False
    result, report, _, _, _ = _run_fixture(tmp_path, runtime=runtime)
    assert result.returncode == 0
    assert report["decision"] == "rejected"
    assert "runtime_evidence_mixed_run" in report["reason_codes"]


@pytest.mark.parametrize("boundary,reason", [
    ("tool", "tool_registry_invalid"),
    ("network", "network_allowlist_invalid"),
])
def test_tampered_runtime_boundary_evidence_is_rejected(tmp_path: Path, boundary: str, reason: str) -> None:
    if boundary == "tool":
        def tamper(tool: Path, network: Path) -> None:
            value = json.loads(tool.read_text(encoding="utf-8"))
            value["tools"].append(copy.deepcopy(value["tools"][0]))
            tool.write_text(json.dumps(value), encoding="utf-8")
    else:
        def tamper(tool: Path, network: Path) -> None:
            value = json.loads(network.read_text(encoding="utf-8"))
            value["hosts"] = ["unknown.invalid"]
            network.write_text(json.dumps(value), encoding="utf-8")
    result, report, decision, _, _ = _run_fixture(tmp_path, mutate=tamper)
    assert result.returncode != 0
    assert report["decision"] == decision["status"] == "rejected"
    assert reason in report["reason_codes"]


def test_deleted_required_evidence_is_rejected(tmp_path: Path) -> None:
    package_dir, baseline, tool_registry, network_allowlist, audit, metadata, runtime_file = _fixture(tmp_path)
    baseline.unlink()
    result = subprocess.run([
        "node", str(SCRIPT), "--check", "--package-dir", str(package_dir), "--baseline", str(baseline),
        "--tool-registry", str(tool_registry), "--network-allowlist", str(network_allowlist),
        "--audit-file", str(audit), "--metadata-file", str(metadata), "--runtime-evidence", str(runtime_file),
    ], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode != 0
    assert json.loads(result.stdout)["decision"] == "rejected"


@pytest.mark.parametrize("mutator,reason", [
    (lambda value: value.update(status="mystery"), "runtime_evidence_unknown_status"),
    (lambda value: value.update(run_id="piq_mixed"), "runtime_evidence_mixed_run"),
])
def test_unknown_or_mixed_runtime_status_is_rejected(tmp_path: Path, mutator, reason: str) -> None:
    package_dir, baseline, tool_registry, network_allowlist, *_ = _fixture(tmp_path)
    runtime = _valid_runtime(package_dir, baseline, tool_registry, network_allowlist)
    mutator(runtime)
    result, report, _, _, _ = _run_fixture(tmp_path, runtime=runtime)
    assert report["decision"] == "rejected"
    assert reason in report["reason_codes"]


def test_decision_dates_owner_triggers_scope_and_privacy_are_governed() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    _assert_decision(decision)
    _assert_no_sensitive_content(decision)
    _assert_no_sensitive_content(report)
    assert report["schema"] == decision["qualification_schema"]
    assert report["decision"] == decision["status"]
    assert report["run_id"] == decision["run_id"]
    assert report["evidence_checksum"] == decision["evidence_checksum"]


@pytest.mark.parametrize("field", ["owner", "expiry", "requalification_triggers"])
def test_missing_governance_fields_are_rejected(field: str) -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    decision.pop(field)
    with pytest.raises((AssertionError, KeyError)):
        _assert_decision(decision)


def test_stale_dates_unknown_status_and_sensitive_key_value_are_rejected() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    stale = copy.deepcopy(decision)
    stale["expiry"] = "2020-01-01T00:00:00Z"
    with pytest.raises(AssertionError):
        _assert_decision(stale)
    unknown = copy.deepcopy(decision)
    unknown["status"] = "approved"
    with pytest.raises(AssertionError):
        _assert_decision(unknown)
    sensitive = copy.deepcopy(decision)
    sensitive["api_key"] = "redacted"
    with pytest.raises(AssertionError):
        _assert_no_sensitive_content(sensitive)


def test_markdown_is_allowlisted_projection_of_decision() -> None:
    decision = json.loads(DECISION.read_text(encoding="utf-8"))
    markdown = MARKDOWN.read_text(encoding="utf-8")
    assert f'Decision: {decision["status"]}' in markdown
    assert f'Run ID: {decision["run_id"]}' in markdown
    assert f'Evidence checksum: {decision["evidence_checksum"]}' in markdown
    assert "D:\\" not in markdown
    assert "sk-" not in markdown
