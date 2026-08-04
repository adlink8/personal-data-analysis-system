from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_runtime_activation import RuntimeActivation


def test_forced_failure_downgrades_exactly_to_legacy_without_deleting_history(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    prepared = runtime.prepare("shadow", evidence_checksum="synthetic"); runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="shadow-1")
    state = runtime.downgrade("declared_kernel_failure")
    assert state["mode"] == "legacy"
    assert runtime.db.execute("SELECT COUNT(*) FROM activation_events").fetchone()[0] == 2
    runtime.close()
