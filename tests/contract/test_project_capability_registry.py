from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from personal_knowledge.services.capability_registry import (
    CapabilityRegistryError,
    descriptor_snapshot,
    load_registry,
    operation_checksum,
    registry_checksum,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "governance/manifests/capabilities/project-capabilities.json"


def test_registry_loads_with_stable_checksum_and_profiles() -> None:
    registry = load_registry()
    assert registry["schema"] == "project-capability-registry-v1"
    assert registry["checksum"] == registry_checksum(registry)
    assert len(registry["operations"]) >= 15
    assert all(operation["checksum"] == operation_checksum(operation) for operation in registry["operations"])
    assert len(descriptor_snapshot(registry)["operations"]) == len(registry["operations"])


def _base() -> dict:
    return copy.deepcopy(load_registry())


@pytest.mark.parametrize(
    ("label", "mutator"),
    [
        ("schema", lambda r: r.update(schema="wrong")),
        ("version", lambda r: r.update(version="bad")),
        ("registry_checksum", lambda r: r.update(checksum="0" * 64)),
        ("operations_type", lambda r: r.update(operations={})),
        ("duplicate_id", lambda r: r["operations"].append(copy.deepcopy(r["operations"][0]))),
        ("unknown_profile", lambda r: r["operations"][0].update(profiles=["admin"])),
        ("privacy", lambda r: r["operations"][0].update(privacy_ceiling="R9")),
        ("authority", lambda r: r["operations"][0].update(authority_class="table")),
        ("side_effect", lambda r: r["operations"][0].update(side_effect_class="delete")),
        ("timeout", lambda r: r["operations"][0].update(timeout_ms=0)),
        ("budget_provider", lambda r: r["operations"][0]["budget"].update(provider_calls=1)),
        ("idempotency", lambda r: r["operations"][0]["idempotency"].update(required=False)),
        ("confirmation", lambda r: r["operations"][0]["confirmation"].update(required=True)),
        ("status", lambda r: r["operations"][0].update(status="active-ish")),
        ("operation_checksum", lambda r: r["operations"][0].update(checksum="0" * 64)),
        ("alias_collision", lambda r: r["operations"][0].update(aliases=[{"name": r["operations"][1]["id"], "version": "1.0.0", "deprecated": True}])),
    ],
)
def test_registry_rejects_negative_fixture(label, mutator) -> None:
    registry = _base()
    mutator(registry)
    with pytest.raises(CapabilityRegistryError):
        validate_registry(registry)


def test_generator_is_deterministic_and_checkable(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    command = [sys.executable, "tools/supported/generate_capability_descriptors.py", "--write", "--output-dir", str(output)]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert first.returncode == second.returncode == 0
    before = {path.name: path.read_bytes() for path in output.glob("*.json")}
    assert subprocess.run([sys.executable, "tools/supported/generate_capability_descriptors.py", "--check", "--output-dir", str(output)], cwd=ROOT).returncode == 0
    touched = next(iter(output.glob("*.json")))
    touched.write_text(touched.read_text(encoding="utf-8") + "drift", encoding="utf-8")
    assert subprocess.run([sys.executable, "tools/supported/generate_capability_descriptors.py", "--check", "--output-dir", str(output)], cwd=ROOT).returncode != 0
    assert {name: value for name, value in before.items() if name != touched.name} == {path.name: path.read_bytes() for path in output.glob("*.json") if path != touched}
