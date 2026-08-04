from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_runtime_activation import RuntimeActivation, ActivationError


def test_primary_is_blocked_without_phase53_proceed_evidence(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    preview = runtime.prepare("shadow", evidence_checksum="phase53-replay")
    runtime.confirm(preview, confirmation_phrase=preview["confirmation_phrase"], idempotency_key="shadow-1")
    canary = runtime.prepare("canary", evidence_checksum="phase53-revise")
    runtime.confirm(canary, confirmation_phrase=canary["confirmation_phrase"], idempotency_key="canary-1")
    primary = runtime.prepare("primary", evidence_checksum="phase53-revise")
    assert primary["preview"]["to"] == "primary"
    runtime.close()
