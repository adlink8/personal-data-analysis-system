from __future__ import annotations

from pathlib import Path


def test_phase_50_authority_boundaries_remain_separate():
    root = Path(__file__).resolve().parents[2]
    assert (root / "apps/personal_intelligence_kernel/src/tasks/ledger.mjs").is_file()
    assert (root / "apps/personal_intelligence_kernel/src/sessions/store.mjs").is_file()
    assert (root / "apps/personal_intelligence_kernel/src/candidates/store.mjs").is_file()
    text = (root / "apps/personal_intelligence_kernel/src/candidates/store.mjs").read_text(encoding="utf-8")
    assert "pi_kernel_candidates.sqlite" in text
    assert "serving_lifecycle_forbidden" in text
    assert not (root / "ops/runtime/start-agent-stack.ps1").read_text(encoding="utf-8").startswith("# phase 50")
