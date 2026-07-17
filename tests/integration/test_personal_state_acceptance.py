from __future__ import annotations

import json
import sqlite3

from personal_knowledge.intelligence.cli import main as cli_main, run_acceptance
from tests.contract.test_personal_state_interfaces import _service


def _analysis_counts(db_path):
    con = sqlite3.connect(db_path)
    try:
        return tuple(
            con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "personal_state_runs", "personal_state_assertions", "personal_state_evidence",
                "personal_state_changes", "personal_state_risks",
            )
        )
    finally:
        con.close()


def test_acceptance_replays_without_any_authority_or_analysis_mutation(tmp_path) -> None:
    db_path, _, _, _ = _service(tmp_path)
    pointer = tmp_path / "active.txt"
    pointer.write_text("fixture-active", encoding="utf-8")
    counts_before = _analysis_counts(db_path)

    first = run_acceptance(db_path, pointer_path=pointer, limit=5)
    second = run_acceptance(db_path, pointer_path=pointer, limit=5)

    assert first == second
    assert first["ok"] is True
    assert first["mutations"] == 0
    assert first["private_bodies"] == 0
    assert first["candidate"]["persisted_rows"] == 0
    assert first["fingerprints"]["unchanged"] is True
    assert first["fingerprints"]["before"] == first["fingerprints"]["after"]
    assert first["run_plan"]["run_plan_id"].startswith("psp_")
    assert len(first["run_plan"]["checksum"]) == 64
    assert _analysis_counts(db_path) == counts_before


def test_acceptance_preserves_truthful_phase24_release_blockers(tmp_path) -> None:
    db_path, _, _, _ = _service(tmp_path)
    result = run_acceptance(db_path, pointer_path=tmp_path / "missing.txt")

    assert result["status"] == "release_blocked"
    assert result["phase24"]["release_blocked"] is True
    assert result["phase24"]["human_review_strict"]["ok"] is False
    assert result["phase24"]["lifecycle_strict"]["ok"] is False
    statuses = {row["checkpoint"]: row["status"] for row in result["phase24"]["checkpoints"]}
    assert statuses["24-02-CHECKPOINT"] == "awaiting_human"
    assert statuses["24-03-CHECKPOINT"] == "human_verification_required"
    assert statuses["24-04-CHECKPOINT"] == "blocked_on_human_and_quality_gates"
    serialized = json.dumps(result, ensure_ascii=False)
    assert '"approved"' not in serialized.lower()
    assert '"pass"' not in serialized.lower()


def test_acceptance_cli_emits_metadata_only_json(tmp_path, capsys) -> None:
    db_path, _, _, _ = _service(tmp_path)
    pointer = tmp_path / "active.txt"
    pointer.write_text("fixture-active", encoding="utf-8")
    code = cli_main([
        "--db", str(db_path), "acceptance", "--dry-run", "--metadata-only",
        "--active-pointer", str(pointer), "--json",
    ])
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["dry_run"] is result["metadata_only"] is True
    assert result["mutations"] == result["private_bodies"] == 0
