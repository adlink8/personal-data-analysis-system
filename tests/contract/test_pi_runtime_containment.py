from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps" / "personal_intelligence_kernel"
PROBE = APP / "src" / "runtime" / "containment-probe.mjs"
REGISTRY_PATH = ROOT / "governance" / "manifests" / "ai" / "pi-tool-registry.json"
NETWORK_PATH = ROOT / "governance" / "manifests" / "ai" / "pi-network-allowlist.json"
OUTPUT_KEYS = {
    "schema",
    "version",
    "package_versions",
    "node_version",
    "counts",
    "tool_names",
    "reason_codes",
    "fixture_checksums",
}
PACKAGE_VERSIONS = {
    "@earendil-works/pi-ai": "0.83.0",
    "@earendil-works/pi-coding-agent": "0.83.0",
    "@earendil-works/pi-storage-sqlite-node": "0.83.0",
}
SAFE_REASONS = {
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
    "temporary_state_cleaned",
}


def _fingerprint(path: Path) -> tuple[bool, int | None, str | None]:
    if not path.exists():
        return False, None, None
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return True, stat.st_size, digest


def _protected_snapshot(extra: list[Path] | None = None) -> dict[str, tuple[bool, int | None, str | None]]:
    paths = [
        ROOT / "data" / "canonical" / "agent" / "structured" / "db" / "agent_conversations.sqlite",
        ROOT / "data" / "canonical" / "agent" / "structured" / "db" / "agent_data.sqlite",
        ROOT / "var" / "db" / "personal_system.sqlite",
        ROOT / "var" / "db" / "knowledge_index_active.txt",
        ROOT / "var" / "db" / "conversation_source.txt",
        ROOT / "var" / "db" / "personal_wiki_projection.sqlite",
    ]
    paths.extend(extra or [])
    snapshot = {}
    for path in paths:
        try:
            key = path.relative_to(ROOT).as_posix()
        except ValueError:
            key = f"external:{path.name}"
        snapshot[key] = _fingerprint(path)
    return snapshot


def _run_probe(*, secret: str, path_marker: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PI_CONTAINMENT_FIXTURE_SECRET"] = secret
    env["OPENAI_API_KEY"] = secret
    env["PI_CONTAINMENT_PATH_MARKER"] = path_marker
    return subprocess.run(
        ["node", str(PROBE)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _parse_report(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.stdout.strip(), result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert set(report) == OUTPUT_KEYS
    return report


def _assert_registry_contract(registry: dict) -> None:
    assert registry["schema"] == "pi-tool-registry-v1"
    names = [tool["name"] for tool in registry["tools"]]
    assert sorted(names) == ["domain_candidate", "domain_inspect"]
    assert len(names) == len(set(names))
    event_ids = [event for tool in registry["tools"] for event in tool["event_ids"]]
    assert len(event_ids) == len(set(event_ids))
    assert registry["forbidden_builtin_tools"] == ["bash", "edit", "find", "grep", "ls", "read", "write"]
    for tool in registry["tools"]:
        assert tool["kind"] == "synthetic_domain"
        for capability in ("filesystem", "process", "network", "credentials", "authority_writes"):
            assert tool["capabilities"][capability] == []


def _assert_network_allowlist_contract(allowlist: dict) -> None:
    assert allowlist["schema"] == "pi-network-allowlist-v1"
    assert allowlist["default"] == "deny"
    assert allowlist["hosts"] == []
    assert allowlist["ports"] == []
    assert allowlist["methods"] == []
    assert allowlist["policy"] == {
        "provider_calls": 0,
        "unknown_hosts": "deny",
        "network": "offline",
    }


def test_runtime_containment_zero_ambient_and_zero_mutation(tmp_path: Path) -> None:
    secret = "PI-CONTAINMENT-SECRET-7f3c1a"
    path_marker = str(tmp_path / "never-echo-this-path")
    session_store = tmp_path / "fixture-session-store.json"
    candidate_store = tmp_path / "fixture-candidate-store.json"
    session_store.write_text('{"session":"fixture"}\n', encoding="utf-8")
    candidate_store.write_text('{"candidate":"fixture"}\n', encoding="utf-8")
    before = _protected_snapshot([session_store, candidate_store])

    result = _run_probe(secret=secret, path_marker=path_marker)
    after = _protected_snapshot([session_store, candidate_store])
    report = _parse_report(result)

    assert result.returncode == 0, result.stderr
    assert before == after
    assert report["schema"] == "pi-runtime-containment-v1"
    assert report["version"] == "48.02.1"
    assert report["package_versions"] == PACKAGE_VERSIONS
    assert re.fullmatch(r"\d+\.\d+\.\d+", report["node_version"])
    assert report["tool_names"] == ["domain_candidate", "domain_inspect"]
    assert report["counts"] == {
        "extensions": 0,
        "skills": 0,
        "prompt_templates": 0,
        "themes": 0,
        "context_files": 0,
        "forbidden_tools": 0,
        "fixture_files": 18,
        "provider_calls": 0,
    }
    assert set(report["reason_codes"]) <= SAFE_REASONS
    assert "temporary_state_cleaned" in report["reason_codes"]
    assert len(report["fixture_checksums"]) >= 12
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in report["fixture_checksums"].values())
    output = result.stdout + result.stderr
    assert secret not in output
    assert path_marker not in output
    assert "unknown.invalid" not in output
    assert "provider disabled" not in output


def test_tool_registry_rejects_duplicate_tool_and_event_identifiers() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    _assert_registry_contract(registry)

    duplicate_tool = copy.deepcopy(registry)
    duplicate_tool["tools"].append(copy.deepcopy(duplicate_tool["tools"][0]))
    with pytest.raises(AssertionError):
        _assert_registry_contract(duplicate_tool)

    duplicate_event = copy.deepcopy(registry)
    duplicate_event["tools"][1]["event_ids"].append(duplicate_event["tools"][0]["event_ids"][0])
    with pytest.raises(AssertionError):
        _assert_registry_contract(duplicate_event)


def test_phase_48_network_allowlist_rejects_any_host() -> None:
    allowlist = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))
    _assert_network_allowlist_contract(allowlist)
    forged = copy.deepcopy(allowlist)
    forged["hosts"].append("unknown.invalid")
    with pytest.raises(AssertionError):
        _assert_network_allowlist_contract(forged)
