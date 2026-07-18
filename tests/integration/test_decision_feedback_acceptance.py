from __future__ import annotations

import json
import sqlite3

from personal_knowledge.intelligence.decision.cli import main as cli_main, run_acceptance
from tests.integration.test_decision_feedback_concurrency import _published


def test_metadata_only_acceptance_proves_sandbox_loop_and_zero_live_mutation(tmp_path) -> None:
    db, _ = _published(tmp_path)
    pointer = tmp_path / "active.txt"
    pointer.write_text("fixture", encoding="utf-8")
    result = run_acceptance(db, pointer_path=pointer)
    assert result["ok"] is True
    assert result["technical_status"] == "passed"
    assert result["release_status"] == "release_blocked"
    assert result["sandbox"]["accepted_history_length"] == 7
    assert result["sandbox"]["rejected_history_length"] == 2
    assert result["sandbox"]["causal_claim"] is False
    assert result["fingerprints"]["before"] == result["fingerprints"]["after"]
    assert result["fingerprints"]["unchanged"] is True
    for field in ("persisted_rows", "mutations", "private_bodies", "external_actions", "network_calls", "paid_calls"):
        assert result[field] == 0


def test_acceptance_preserves_phase24_statuses_and_checksums_verbatim(tmp_path) -> None:
    db, _ = _published(tmp_path)
    result = run_acceptance(db, pointer_path=tmp_path / "missing.txt")
    checkpoints = {row["checkpoint"]: row for row in result["phase24"]["checkpoints"]}
    expected = {
        "24-02-CHECKPOINT": "awaiting_human",
        "24-03-CHECKPOINT": "human_verification_required",
        "24-04-CHECKPOINT": "blocked_on_human_and_quality_gates",
    }
    assert {name: row["status"] for name, row in checkpoints.items()} == expected
    assert all(len(row["checksum"]) == 64 for row in checkpoints.values())
    assert result["phase24"]["human_review_strict"]["ok"] is False
    assert result["phase24"]["lifecycle_strict"]["ok"] is False


def test_acceptance_cli_is_explicitly_dry_run_metadata_only(tmp_path, capsys) -> None:
    db, _ = _published(tmp_path)
    pointer = tmp_path / "active.txt"
    pointer.write_text("fixture", encoding="utf-8")
    code = cli_main([
        "--db", str(db), "acceptance", "--dry-run", "--metadata-only",
        "--active-pointer", str(pointer), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is payload["metadata_only"] is True


def test_schema_unapplied_is_allowlisted_without_migration(tmp_path) -> None:
    db, _ = _published(tmp_path)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=OFF")
    for table in (
        "decision_events", "decision_effectiveness", "decision_outcomes", "decision_actions",
        "decision_confirmations", "decision_support_refs", "decision_recommendations", "decision_runs",
    ):
        con.execute(f"DROP TABLE {table}")
    con.commit(); con.close()
    result = run_acceptance(db, pointer_path=tmp_path / "missing.txt")
    assert result["ok"] is True
    assert result["live"]["decision_schema_applied"] is False
    assert result["live"]["decision_status"]["reason"] == "decision_schema_unapplied"


def test_corrupted_live_decision_chain_blocks_technical_status(tmp_path) -> None:
    db, rec = _published(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DROP TRIGGER trg_decision_events_immutable_update")
    con.execute(
        "UPDATE decision_events SET payload_json='{}' WHERE recommendation_id=? AND sequence=1",
        (rec.recommendation_id,),
    )
    con.commit(); con.close()
    result = run_acceptance(db, pointer_path=tmp_path / "missing.txt")
    assert result["ok"] is False
    assert result["technical_status"] == "failed"
    assert result["release_status"] == "release_blocked"
    assert result["live"]["decision_status"]["ok"] is False
    assert result["live"]["decision_status"]["reason"] == "event_checksum_mismatch"
