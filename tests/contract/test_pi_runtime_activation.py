from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_runtime_activation import ActivationError, RuntimeActivation


def test_fresh_runtime_defaults_to_legacy_and_requires_exact_confirmation(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    assert runtime.current()["mode"] == "legacy"
    prepared = runtime.prepare("shadow", evidence_checksum="synthetic-evidence")
    try:
        runtime.confirm(prepared, confirmation_phrase="wrong", idempotency_key="i1")
    except ActivationError as exc:
        assert exc.code == "confirmation_mismatch"
    else: raise AssertionError("upgrade without exact confirmation")
    state = runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="i1")
    assert state["mode"] == "shadow"; runtime.close()


def test_downgrade_preserves_append_only_history(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    p = runtime.prepare("shadow", evidence_checksum="e"); runtime.confirm(p, confirmation_phrase=p["confirmation_phrase"], idempotency_key="i1")
    state = runtime.downgrade("kernel_failed")
    assert state["mode"] == "legacy" and state["sequence"] == 2
    assert runtime.db.execute("SELECT COUNT(*) FROM activation_events").fetchone()[0] == 2; runtime.close()
