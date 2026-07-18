from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from personal_knowledge.intelligence.calibration.protocols import REQUIRED_METRICS, build_protocol, freeze_protocol
from personal_knowledge.intelligence.calibration.schema import TABLES, inspect_schema, migrate
from personal_knowledge.intelligence.pilot.outcomes import record_outcome_observation
from personal_knowledge.intelligence.pilot.workflow import read_event_stream

from tests.integration.test_project_pilot_outcomes import ACTOR, _completed


def setup_protocol(tmp_path: Path):
    env, case = _completed(tmp_path / "pilot")
    record_outcome_observation(
        env["pilot"], case_id=case.case_id, observed_value=1, actual_time_minutes=18,
        actual_cost=0, completion="completed", quality=1, satisfaction=.9,
        side_effects=(), regret=0, confounders=(), source="pytest receipt",
        observed_at="2026-07-18T09:31:00Z", expected_sequence=5,
        idempotency_key="observation", actor_identity_hash=ACTOR,
    )
    outcome = next(x for x in read_event_stream(env["pilot"], case.case_id) if x["event_type"] == "outcome_observed")
    db = tmp_path / "calibration.sqlite"; migrate(db, write=True)
    protocol = build_protocol(
        question="Which local runtime path should the project use?", domain="project",
        external_snapshot_id=case.external_snapshot_id, external_snapshot_hash=case.external_snapshot_hash,
        provider="codex-chatgpt", model="gpt-5.4", prompt_version="calibration-v1",
        schema_version="decision_analysis_candidate_v1", temperature=0,
        max_output_tokens=4096, max_total_tokens=27000,
        cohort=({"case_id": case.case_id, "case_checksum": case.payload_checksum,
                 "outcome_event_checksum": outcome["payload_checksum"]},),
        exclusions=("non-project", "missing-complete-outcome"),
        window_start="2026-07-18T14:00:00Z", window_end="2026-07-18T15:00:00Z",
        thresholds={name: 0 for name in REQUIRED_METRICS}, minimum_evidence=2,
        frozen_at="2026-07-18T13:00:00Z",
    )
    return env, db, protocol


def _counts(db: Path):
    con=sqlite3.connect(db)
    try: return {t:con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally: con.close()


def test_freeze_is_atomic_idempotent_append_only_and_source_preserving(tmp_path: Path) -> None:
    env, db, protocol = setup_protocol(tmp_path)
    before = Path(env["pilot"]).read_bytes()
    assert freeze_protocol(db, env["pilot"], protocol)["dry_run"]
    assert freeze_protocol(db, env["pilot"], protocol, write=True)["written"]
    assert freeze_protocol(db, env["pilot"], protocol, write=True)["existing"]
    assert Path(env["pilot"]).read_bytes() == before
    assert inspect_schema(db)["append_only_trigger_count"] == 14
    con=sqlite3.connect(db)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("UPDATE calibration_protocols SET protocol_status='frozen'")
    con.close()


def test_tamper_cross_cohort_and_fault_paths_fail_closed(tmp_path: Path) -> None:
    env, db, protocol = setup_protocol(tmp_path)
    bad = build_protocol(**{**{
        "question": protocol.payload["question"], "domain": "project",
        "external_snapshot_id": protocol.payload["common_external_snapshot"]["snapshot_id"],
        "external_snapshot_hash": protocol.payload["common_external_snapshot"]["snapshot_hash"],
        "provider": "codex-chatgpt", "model": "gpt-5.4", "prompt_version": "calibration-v1",
        "schema_version": "decision_analysis_candidate_v1", "temperature": 0,
        "max_output_tokens": 4096, "max_total_tokens": 27000,
        "cohort": ({**protocol.payload["cohort"][0], "case_checksum": "0"*64},),
        "exclusions": tuple(protocol.payload["exclusions"]), "window_start": "2026-07-18T14:00:00Z",
        "window_end": "2026-07-18T15:00:00Z", "thresholds": protocol.payload["thresholds"],
        "minimum_evidence": 2, "frozen_at": "2026-07-18T13:00:00Z"}})
    with pytest.raises(Exception, match="cohort_case_checksum_mismatch"):
        freeze_protocol(db, env["pilot"], bad, write=True)
    with pytest.raises(RuntimeError, match="injected"):
        freeze_protocol(db, env["pilot"], protocol, write=True, fault_at="after_protocol")
    assert not any(_counts(db).values())
