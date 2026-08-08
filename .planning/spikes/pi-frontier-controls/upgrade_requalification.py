"""Spike 009: deterministic SDK drift detection and legacy rollback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def qualify(lock: dict[str, object], registry: dict[str, object]) -> dict[str, object]:
    reasons = []
    for field in ("version", "integrity", "api_fingerprint", "event_fingerprint", "dependency_fingerprint"):
        if lock.get(field) != registry.get(field):
            reasons.append(f"{field}_drift")
    return {"accepted": not reasons, "reasons": reasons, "registry_checksum": digest(registry)}


def main() -> None:
    package_lock_path = Path(__file__).parents[3] / ".planning" / "spikes" / "pi-embedded-personal-kernel" / "prototype" / "agent-runtime" / "package-lock.json"
    package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
    package = package_lock["packages"]["node_modules/@earendil-works/pi-coding-agent"]
    dependencies = package.get("dependencies", {})
    baseline = {
        "package": "@earendil-works/pi-coding-agent",
        "version": package["version"],
        "integrity": package.get("integrity", "lockfile-present"),
        "api_fingerprint": digest({"noTools": "builtin", "customTools": "ToolDefinition[]", "sessionSubscribe": True}),
        "event_fingerprint": digest(["agent_start", "tool_execution_start", "tool_execution_end", "agent_end"]),
        "dependency_fingerprint": digest(sorted(dependencies.items())),
    }
    accepted = qualify(baseline, baseline)
    version_drift = qualify(baseline, {**baseline, "version": "0.84.0"})
    event_drift = qualify(baseline, {**baseline, "event_fingerprint": digest(["agent_start", "tool_execution_start", "agent_end", "new_event"])} )
    report = {
        "package": baseline["package"],
        "observed_version": baseline["version"],
        "baseline": accepted,
        "version_drift": version_drift,
        "event_drift": event_drift,
        "feature_flag": "pi" if accepted["accepted"] else "legacy",
        "rollback_after_drift": "legacy" if not version_drift["accepted"] else "pi",
        "package_dependency_count": len(dependencies),
    }
    assert accepted["accepted"]
    assert not version_drift["accepted"] and "version_drift" in version_drift["reasons"]
    assert not event_drift["accepted"] and "event_fingerprint_drift" in event_drift["reasons"]
    assert report["rollback_after_drift"] == "legacy"
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
