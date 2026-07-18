"""Read-first planning and atomic publication for proactive intelligence runs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from personal_knowledge.core.sqlite import assert_foreign_key_integrity, connect_rw

from .schema import (
    CANONICAL_DOMAINS, RELATION_TYPES, CoordinationDraft, CoordinationItem,
    ProactiveRun, SupportReference, canonical_domain, canonical_json, checksum,
    validate_metadata_payload,
)

REGISTRY_ID = "a.proactive_intelligence"
REGISTRY_AUTHORITY_ROLE = "proactive_intelligence"
NO_CONTROL_FRONTIER_CHECKSUM = checksum({"control_events": []})
NO_DECISION_EVENT_FRONTIER_CHECKSUM = checksum({"decision_events": []})


class ProactiveValidationError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_frontier(con: sqlite3.Connection, decision_run_id: str | None) -> str:
    if decision_run_id is None:
        return NO_DECISION_EVENT_FRONTIER_CHECKSUM
    rows = con.execute(
        "SELECT e.recommendation_id,e.sequence,e.payload_checksum FROM decision_events e "
        "JOIN decision_recommendations r ON r.recommendation_id=e.recommendation_id "
        "WHERE r.run_id=? ORDER BY e.recommendation_id,e.sequence", (decision_run_id,),
    ).fetchall()
    return checksum({"decision_events": [tuple(row) for row in rows]})


def _control_frontier(con: sqlite3.Connection) -> str:
    rows = con.execute(
        "SELECT target_authority,target_type,target_id,sequence,payload_checksum "
        "FROM proactive_control_events ORDER BY target_authority,target_type,target_id,sequence"
    ).fetchall()
    return checksum({"control_events": [tuple(row) for row in rows]})


def _source_context(con: sqlite3.Connection, source_run_id: str) -> sqlite3.Row:
    row = con.execute(
        "SELECT r.*,p.publication_sequence FROM personal_state_runs r "
        "JOIN personal_state_publications p ON p.run_id=r.run_id "
        "WHERE r.run_id=? AND r.status='committed'", (source_run_id,),
    ).fetchone()
    if row is None:
        raise ProactiveValidationError("source_run_unpublished", source_run_id)
    if checksum(json.loads(str(row["input_manifest_json"]))) != str(row["input_manifest_checksum"]):
        raise ProactiveValidationError("source_input_manifest_tampered", source_run_id)
    if checksum(json.loads(str(row["output_manifest_json"]))) != str(row["output_manifest_checksum"]):
        raise ProactiveValidationError("source_output_manifest_tampered", source_run_id)
    return row


def _decision_context(con: sqlite3.Connection, decision_run_id: str | None) -> sqlite3.Row | None:
    if decision_run_id is None:
        return None
    row = con.execute("SELECT * FROM decision_runs WHERE run_id=? AND status='committed'", (decision_run_id,)).fetchone()
    if row is None:
        raise ProactiveValidationError("decision_run_missing", decision_run_id)
    if checksum(json.loads(str(row["input_manifest_json"]))) != str(row["input_manifest_checksum"]):
        raise ProactiveValidationError("decision_input_manifest_tampered", decision_run_id)
    if checksum(json.loads(str(row["output_manifest_json"]))) != str(row["output_manifest_checksum"]):
        raise ProactiveValidationError("decision_output_manifest_tampered", decision_run_id)
    core = json.loads(str(row["output_manifest_json"]))
    if str(core.get("run_checksum")) != str(row["run_checksum"]):
        raise ProactiveValidationError("decision_run_checksum_tampered", decision_run_id)
    return row


def _validate_ref(con: sqlite3.Connection, ref: SupportReference, *, snapshot_id: str, snapshot_hash: str,
                  source_run_id: str, source_run_checksum: str, decision_run_id: str | None,
                  decision_run_checksum: str | None) -> None:
    if len(ref.record_checksum) != 64 or len(ref.source_run_checksum) != 64:
        raise ProactiveValidationError("support_checksum_invalid", ref.record_id)
    if ref.snapshot_id != snapshot_id or ref.snapshot_hash != snapshot_hash:
        raise ProactiveValidationError("support_snapshot_mismatch", ref.record_id)
    if ref.authority_id == "a.personal_change":
        if ref.source_run_id != source_run_id or ref.source_run_checksum != source_run_checksum:
            raise ProactiveValidationError("support_source_mismatch", ref.record_id)
        table_by_type = {"assertion": "personal_state_assertions", "change": "personal_state_changes", "risk": "personal_state_risks"}
        table = table_by_type.get(ref.record_type)
        if table is None:
            raise ProactiveValidationError("support_type_invalid", ref.record_type)
        row = con.execute(f"SELECT payload_checksum FROM {table} WHERE run_id=? AND {ref.record_type}_id=?", (source_run_id, ref.record_id)).fetchone()
    elif ref.authority_id == "a.decision_feedback":
        if decision_run_id is None or ref.source_run_id != decision_run_id or ref.source_run_checksum != decision_run_checksum:
            raise ProactiveValidationError("support_decision_mismatch", ref.record_id)
        table_and_id = {"recommendation": ("decision_recommendations", "recommendation_id"), "event": ("decision_events", "event_id"), "effectiveness": ("decision_effectiveness", "assessment_id")}.get(ref.record_type, (None, None))
        table, id_col = table_and_id
        if table is None:
            raise ProactiveValidationError("support_type_invalid", ref.record_type)
        if table == "decision_recommendations":
            row = con.execute(f"SELECT payload_checksum FROM {table} WHERE run_id=? AND {id_col}=?", (decision_run_id, ref.record_id)).fetchone()
        else:
            row = con.execute(f"SELECT t.payload_checksum FROM {table} t JOIN decision_recommendations r ON r.recommendation_id=t.recommendation_id WHERE r.run_id=? AND t.{id_col}=?", (decision_run_id, ref.record_id)).fetchone()
    else:
        raise ProactiveValidationError("support_authority_invalid", ref.authority_id)
    if row is None or str(row[0]) != ref.record_checksum:
        raise ProactiveValidationError("support_record_stale", ref.record_id)


def plan_run(
    db_path: Path, coordination: Iterable[CoordinationDraft], *,
    source_run_id: str, source_run_checksum: str, source_publication_sequence: int,
    decision_run_id: str | None = None, decision_run_checksum: str | None = None,
    coordination_policy: str, ranking_policy: str, noise_policy: str,
    input_manifest: Mapping[str, Any],
) -> ProactiveRun:
    drafts = tuple(coordination)
    if not drafts:
        raise ProactiveValidationError("coordination_required")
    validate_metadata_payload(input_manifest, "input_manifest")
    con = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        source = _source_context(con, source_run_id)
        if str(source["output_manifest_checksum"]) != source_run_checksum or int(source["publication_sequence"]) != source_publication_sequence:
            raise ProactiveValidationError("source_binding_changed", source_run_id)
        decision = _decision_context(con, decision_run_id)
        if decision is not None:
            if str(decision["run_checksum"]) != decision_run_checksum:
                raise ProactiveValidationError("decision_binding_changed", decision_run_id or "")
            for key in ("source_run_id", "source_run_checksum", "snapshot_id", "snapshot_hash"):
                expected = source_run_id if key == "source_run_id" else source_run_checksum if key == "source_run_checksum" else source[key]
                if str(decision[key]) != str(expected):
                    raise ProactiveValidationError("decision_source_mismatch", key)
        elif decision_run_checksum is not None:
            raise ProactiveValidationError("decision_binding_partial")
        snapshot_id, snapshot_hash = str(source["snapshot_id"]), str(source["snapshot_hash"])
        event_frontier = _event_frontier(con, decision_run_id)
        control_frontier = _control_frontier(con)
        normalized: list[CoordinationDraft] = []
        for draft in drafts:
            if draft.relation_type not in RELATION_TYPES or not draft.source_refs:
                raise ProactiveValidationError("coordination_invalid", draft.relation_type)
            domains = tuple(sorted({canonical_domain(item) for item in draft.domains}, key=CANONICAL_DOMAINS.index))
            if not 1 <= len(domains) <= 8 or not 0 <= draft.confidence <= 1:
                raise ProactiveValidationError("coordination_invalid", draft.relation_type)
            for ref in draft.source_refs:
                _validate_ref(con, ref, snapshot_id=snapshot_id, snapshot_hash=snapshot_hash,
                              source_run_id=source_run_id, source_run_checksum=source_run_checksum,
                              decision_run_id=decision_run_id, decision_run_checksum=decision_run_checksum)
            validate_metadata_payload(asdict(draft), "coordination")
            normalized.append(CoordinationDraft(**{**asdict(draft), "domains": domains,
                "source_refs": draft.source_refs, "resource_manifest": draft.resource_manifest}))
    finally:
        con.close()
    manifest = {
        "schema_version": "proactive_run_v1", "registry_id": REGISTRY_ID,
        "source_run_id": source_run_id, "source_run_checksum": source_run_checksum,
        "source_publication_sequence": source_publication_sequence,
        "decision_run_id": decision_run_id, "decision_run_checksum": decision_run_checksum,
        "decision_event_frontier_checksum": event_frontier, "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash, "control_frontier_checksum": control_frontier,
        "coordination_policy": coordination_policy, "ranking_policy": ranking_policy,
        "noise_policy": noise_policy, "request_input": input_manifest,
        "coordination_drafts": [asdict(item) for item in normalized],
    }
    input_checksum = checksum(manifest)
    run_id = f"pir_{input_checksum[:24]}"
    items: list[CoordinationItem] = []
    for draft in normalized:
        payload = {"schema_version": "proactive_coordination_v1", "run_id": run_id, **asdict(draft)}
        coordination_id = f"pci_{checksum(payload)[:24]}"
        payload = {**payload, "coordination_id": coordination_id}
        items.append(CoordinationItem(coordination_id, run_id, draft, payload, checksum(payload)))
    core = {"run_id": run_id, "input_manifest_checksum": input_checksum,
            "coordination_items": [{"coordination_id": i.coordination_id, "payload_checksum": i.payload_checksum} for i in items]}
    run_checksum = checksum(core)
    output = {**core, "run_checksum": run_checksum}
    return ProactiveRun(run_id, REGISTRY_ID, source_run_id, source_run_checksum,
        source_publication_sequence, decision_run_id, decision_run_checksum,
        event_frontier, snapshot_id, snapshot_hash, control_frontier,
        coordination_policy, ranking_policy, noise_policy, manifest, input_checksum,
        output, checksum(output), run_checksum, tuple(items))


def validate_run(db_path: Path, run: ProactiveRun) -> ProactiveRun:
    request = run.input_manifest.get("request_input")
    drafts = tuple(item.draft for item in run.coordination_items)
    expected = plan_run(db_path, drafts, source_run_id=run.source_run_id,
        source_run_checksum=run.source_run_checksum, source_publication_sequence=run.source_publication_sequence,
        decision_run_id=run.decision_run_id, decision_run_checksum=run.decision_run_checksum,
        coordination_policy=run.coordination_policy, ranking_policy=run.ranking_policy,
        noise_policy=run.noise_policy, input_manifest=request if isinstance(request, Mapping) else {})
    if expected != run:
        raise ProactiveValidationError("run_content_mismatch", run.run_id)
    return run


def _validate_existing(con: sqlite3.Connection, run: ProactiveRun) -> None:
    row = con.execute("SELECT * FROM proactive_runs WHERE run_id=?", (run.run_id,)).fetchone()
    if row is None or checksum(json.loads(str(row["input_manifest_json"]))) != str(row["input_manifest_checksum"]) or checksum(json.loads(str(row["output_manifest_json"]))) != str(row["output_manifest_checksum"]) or str(row["run_checksum"]) != run.run_checksum:
        raise ProactiveValidationError("existing_run_tampered", run.run_id)
    rows = con.execute("SELECT coordination_id,payload_json,payload_checksum FROM proactive_coordination_items WHERE run_id=? ORDER BY coordination_id", (run.run_id,)).fetchall()
    expected = sorted((i.coordination_id, canonical_json(i.payload), i.payload_checksum) for i in run.coordination_items)
    actual = sorted((str(r[0]), canonical_json(json.loads(str(r[1]))), str(r[2])) for r in rows)
    if actual != expected:
        raise ProactiveValidationError("existing_coordination_tampered", run.run_id)


def publish_run(db_path: Path, run: ProactiveRun, *, write: bool, inject_failure_at: str | None = None) -> dict[str, Any]:
    validate_run(db_path, run)
    result = {"ok": True, "run_id": run.run_id, "run_checksum": run.run_checksum,
              "written": False, "existing": False, "coordination_count": len(run.coordination_items)}
    if not write:
        return result
    con = connect_rw(Path(db_path), timeout=60)
    con.row_factory = sqlite3.Row
    try:
        assert_foreign_key_integrity(con)
        con.execute("BEGIN IMMEDIATE")
        source = _source_context(con, run.source_run_id)
        decision = _decision_context(con, run.decision_run_id)
        if str(source["output_manifest_checksum"]) != run.source_run_checksum or int(source["publication_sequence"]) != run.source_publication_sequence or str(source["snapshot_id"]) != run.snapshot_id or str(source["snapshot_hash"]) != run.snapshot_hash:
            raise ProactiveValidationError("source_binding_changed")
        if decision is not None and str(decision["run_checksum"]) != run.decision_run_checksum:
            raise ProactiveValidationError("decision_binding_changed")
        if _event_frontier(con, run.decision_run_id) != run.decision_event_frontier_checksum:
            raise ProactiveValidationError("decision_frontier_changed")
        if _control_frontier(con) != run.control_frontier_checksum:
            raise ProactiveValidationError("control_frontier_changed")
        existing = con.execute("SELECT 1 FROM proactive_runs WHERE run_id=?", (run.run_id,)).fetchone()
        if existing:
            _validate_existing(con, run)
            con.commit()
            return {**result, "existing": True}
        registry = con.execute("SELECT authority_role FROM artifact_registry_entries WHERE registry_id=?", (REGISTRY_ID,)).fetchone()
        if registry is None:
            con.execute("INSERT INTO artifact_registry_entries VALUES (?,?,?,?,?,?)", (REGISTRY_ID, "A", REGISTRY_AUTHORITY_ROLE, "R4", run.run_checksum, _now()))
        elif str(registry[0]) != REGISTRY_AUTHORITY_ROLE:
            raise ProactiveValidationError("registry_mismatch")
        con.execute("INSERT INTO proactive_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            run.run_id, run.registry_id, run.source_run_id, run.source_run_checksum,
            run.source_publication_sequence, run.decision_run_id, run.decision_run_checksum,
            run.decision_event_frontier_checksum, run.snapshot_id, run.snapshot_hash,
            run.control_frontier_checksum, run.coordination_policy, run.ranking_policy,
            run.noise_policy, canonical_json(run.input_manifest), run.input_manifest_checksum,
            canonical_json(run.output_manifest), run.output_manifest_checksum, run.run_checksum,
            "committed", _now()))
        for item in run.coordination_items:
            d = item.draft
            con.execute("INSERT INTO proactive_coordination_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                item.coordination_id, run.run_id, d.relation_type, d.subject, d.scope,
                canonical_json(d.domains), d.valid_from, d.valid_to, d.observed_at,
                d.rule_id, d.rule_version, d.confidence, d.uncertainty,
                canonical_json(d.resource_manifest), canonical_json(d.source_refs),
                canonical_json(item.payload), item.payload_checksum, _now()))
        if inject_failure_at == "after_coordination":
            raise RuntimeError("injected proactive publication failure")
        con.commit()
        return {**result, "written": True}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
