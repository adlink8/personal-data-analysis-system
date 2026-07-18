from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sqlite3

import pytest

from personal_knowledge.intelligence.decision.runs import plan_run as plan_decision_run, publish_run as publish_decision_run
from personal_knowledge.intelligence.proactive.runs import ProactiveValidationError, plan_run, publish_run
from personal_knowledge.intelligence.proactive.schema import CoordinationDraft, SupportReference
from tests.integration.test_decision_feedback_runs import _database, _draft


def _upstream(tmp_path: Path):
    db, state_run_id = _database(tmp_path)
    decision = plan_decision_run(db, [_draft(db, state_run_id)], policy_id="p", policy_version="v1", input_manifest={})
    publish_decision_run(db, decision, write=True)
    con = sqlite3.connect(db)
    state = con.execute("SELECT output_manifest_checksum FROM personal_state_runs WHERE run_id=?", (state_run_id,)).fetchone()[0]
    seq = con.execute("SELECT publication_sequence FROM personal_state_publications WHERE run_id=?", (state_run_id,)).fetchone()[0]
    rec = con.execute("SELECT recommendation_id,payload_checksum FROM decision_recommendations").fetchone()
    con.close()
    support = SupportReference(
        authority_id="a.decision_feedback", record_type="recommendation", record_id=rec[0],
        record_checksum=rec[1], source_run_id=decision.run_id, source_run_checksum=decision.run_checksum,
        snapshot_id=decision.snapshot_id, snapshot_hash=decision.snapshot_hash,
    )
    draft = CoordinationDraft(
        relation_type="opportunity", subject="user", scope="personal",
        domains=("learning", "career"), valid_from="2026-07-18T00:00:00Z",
        valid_to="2026-08-01T00:00:00Z", observed_at="2026-07-18T00:00:00Z",
        rule_id="shared-target", rule_version="v1", confidence=0.8,
        uncertainty="fixture only", source_refs=(support,), resource_manifest=(),
    )
    return db, state_run_id, state, seq, decision, draft


def _protected(db: Path):
    con = sqlite3.connect(db)
    result = tuple(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
        "personal_state_runs", "decision_runs", "canonical_knowledge_units",
        "knowledge_lifecycle_events", "source_watermarks", "serving_snapshot_events",
    )) + (con.execute("SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1").fetchone()[0],)
    con.close()
    return result


def test_publication_is_atomic_idempotent_and_protected_authorities_are_unchanged(tmp_path: Path) -> None:
    db, state_id, state_checksum, seq, decision, draft = _upstream(tmp_path)
    before = _protected(db)
    run = plan_run(db, [draft], source_run_id=state_id, source_run_checksum=state_checksum,
                   source_publication_sequence=seq, decision_run_id=decision.run_id,
                   decision_run_checksum=decision.run_checksum, coordination_policy="coord-v1",
                   ranking_policy="rank-v1", noise_policy="noise-v1", input_manifest={})
    assert publish_run(db, run, write=False)["written"] is False
    assert publish_run(db, run, write=True)["written"] is True
    assert publish_run(db, run, write=True)["existing"] is True
    assert _protected(db) == before
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM proactive_runs").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM proactive_coordination_items").fetchone()[0] == 1
    con.close()


@pytest.mark.parametrize("field", ["source_run_checksum", "decision_run_checksum", "snapshot_hash"])
def test_mixed_or_stale_bindings_publish_nothing(tmp_path: Path, field: str) -> None:
    db, state_id, state_checksum, seq, decision, draft = _upstream(tmp_path)
    kwargs = dict(source_run_id=state_id, source_run_checksum=state_checksum,
                  source_publication_sequence=seq, decision_run_id=decision.run_id,
                  decision_run_checksum=decision.run_checksum, coordination_policy="c",
                  ranking_policy="r", noise_policy="n", input_manifest={})
    if field == "source_run_checksum": kwargs[field] = "0" * 64
    elif field == "decision_run_checksum": kwargs[field] = "0" * 64
    else: draft = replace(draft, source_refs=(replace(draft.source_refs[0], snapshot_hash="other"),))
    with pytest.raises(ProactiveValidationError):
        plan_run(db, [draft], **kwargs)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM proactive_runs").fetchone()[0] == 0


def test_fault_rolls_back_all_typed_rows(tmp_path: Path) -> None:
    db, state_id, state_checksum, seq, decision, draft = _upstream(tmp_path)
    run = plan_run(db, [draft], source_run_id=state_id, source_run_checksum=state_checksum,
                   source_publication_sequence=seq, decision_run_id=decision.run_id,
                   decision_run_checksum=decision.run_checksum, coordination_policy="c",
                   ranking_policy="r", noise_policy="n", input_manifest={})
    with pytest.raises(RuntimeError, match="injected"):
        publish_run(db, run, write=True, inject_failure_at="after_coordination")
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM proactive_runs").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM proactive_coordination_items").fetchone()[0] == 0
    con.close()
