from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/runtime/start-agent-stack.ps1"


def test_supervisor_declares_owned_loopback_kernel_and_readiness():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "$KernelPort = 8790" in source
    assert "Key='pi-kernel'" in source
    assert "'/ready'" in source
    assert "personal_intelligence_kernel" in source
    assert "unhealthy_port_conflict" in source


def test_kernel_service_is_metadata_only_in_saved_state():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "service = $entry.Key" in source
    assert "health_url = $entry.HealthUrl" in source
    assert "prompt" not in source.lower()
