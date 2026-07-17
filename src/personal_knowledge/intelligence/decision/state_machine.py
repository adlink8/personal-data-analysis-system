"""Permission-safe append-only recommendation decision and action streams."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from personal_knowledge.core.sqlite import assert_foreign_key_integrity, connect_rw

from .schema import (
    GENESIS_SENTINEL,
    SCHEMA_VERSION,
    DecisionEvent,
    DecisionReceipt,
    DecisionState,
    canonical_json,
    checksum,
)


_ACTION_STATES = frozenset({"planned", "started", "completed", "abandoned", "not_taken"})
_CONFIRMATIONS = frozenset({"accept", "reject", "defer", "revoke_before_action"})
_FORBIDDEN_ACTION_KEYS = frozenset(
    {"command", "url", "uri", "connector", "credential", "token", "dispatch_target", "executable"}
)
_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://")


class DecisionStateError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise DecisionStateError("invalid_time", field) from exc
    if parsed.tzinfo is None:
        raise DecisionStateError("invalid_time", f"{field}:timezone_required")
    return parsed.astimezone(timezone.utc)


def _validate_actor(actor_class: str, actor_identity_hash: str) -> None:
    if actor_class != "user":
        raise DecisionStateError("human_actor_required", actor_class)
    if len(actor_identity_hash) != 64:
        raise DecisionStateError("actor_identity_hash_invalid")


def _reject_action_metadata(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key).lower()
            if label in _FORBIDDEN_ACTION_KEYS:
                raise DecisionStateError("forbidden_action_field", f"{path}.{label}")
            _reject_action_metadata(item, f"{path}.{label}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_action_metadata(item, f"{path}[{index}]")
    elif isinstance(value, str) and _URL_RE.search(value):
        raise DecisionStateError("forbidden_action_field", path)


def _load_recommendation(con: sqlite3.Connection, recommendation_id: str) -> tuple[sqlite3.Row, dict[str, Any], sqlite3.Row]:
    row = con.execute(
        "SELECT * FROM decision_recommendations WHERE recommendation_id=?", (recommendation_id,)
    ).fetchone()
    if row is None:
        raise DecisionStateError("recommendation_missing", recommendation_id)
    try:
        payload = json.loads(str(row["payload_json"]))
    except json.JSONDecodeError as exc:
        raise DecisionStateError("recommendation_payload_invalid", recommendation_id) from exc
    if checksum(payload) != str(row["payload_checksum"]):
        raise DecisionStateError("recommendation_checksum_mismatch", recommendation_id)
    run = con.execute("SELECT * FROM decision_runs WHERE run_id=?", (row["run_id"],)).fetchone()
    if run is None:
        raise DecisionStateError("decision_run_missing", str(row["run_id"]))
    for column in ("input_manifest", "output_manifest"):
        try:
            value = json.loads(str(run[f"{column}_json"]))
        except json.JSONDecodeError as exc:
            raise DecisionStateError("decision_run_manifest_invalid", column) from exc
        if checksum(value) != str(run[f"{column}_checksum"]):
            raise DecisionStateError("decision_run_checksum_mismatch", column)
    return row, payload, run


def _typed_payload(con: sqlite3.Connection, event_type: str, record_id: str) -> dict[str, Any]:
    table = "decision_confirmations" if event_type == "confirmation" else "decision_actions"
    id_column = "confirmation_id" if event_type == "confirmation" else "action_id"
    row = con.execute(f"SELECT payload_json,payload_checksum FROM {table} WHERE {id_column}=?", (record_id,)).fetchone()
    if row is None:
        raise DecisionStateError("typed_record_missing", record_id)
    try:
        payload = json.loads(str(row["payload_json"]))
    except json.JSONDecodeError as exc:
        raise DecisionStateError("typed_record_payload_invalid", record_id) from exc
    if checksum(payload) != str(row["payload_checksum"]):
        raise DecisionStateError("typed_record_checksum_mismatch", record_id)
    return payload


def _confirmation_transition(current: str, action_state: str | None, decision: str) -> str:
    legal = (
        (current == "proposed" and decision in {"accept", "reject", "defer"})
        or (current == "deferred" and decision in {"accept", "reject", "defer"})
        or (current == "accepted" and action_state is None and decision == "revoke_before_action")
    )
    if not legal:
        raise DecisionStateError("illegal_confirmation_transition", f"{current}:{decision}")
    return {
        "accept": "accepted", "reject": "rejected", "defer": "deferred",
        "revoke_before_action": "revoked",
    }[decision]


def _action_transition(confirmation_state: str, current: str | None, next_state: str) -> str:
    legal = False
    if confirmation_state == "accepted":
        if current is None:
            legal = next_state in {"planned", "not_taken"}
        elif current == "planned":
            legal = next_state in {"started", "abandoned", "not_taken"}
        elif current == "started":
            legal = next_state in {"completed", "abandoned"}
    if not legal:
        raise DecisionStateError("illegal_action_transition", f"{current}:{next_state}")
    return next_state


def _project(con: sqlite3.Connection, recommendation_id: str) -> DecisionState:
    recommendation, _, run = _load_recommendation(con, recommendation_id)
    rows = con.execute(
        "SELECT * FROM decision_events WHERE recommendation_id=? ORDER BY sequence", (recommendation_id,)
    ).fetchall()
    if not rows:
        raise DecisionStateError("genesis_missing", recommendation_id)
    events: list[DecisionEvent] = []
    confirmation_state = "proposed"
    action_state: str | None = None
    prior_checksum = GENESIS_SENTINEL
    for expected_sequence, row in enumerate(rows, start=1):
        sequence = int(row["sequence"])
        if sequence != expected_sequence:
            raise DecisionStateError("event_sequence_invalid", f"expected={expected_sequence},actual={sequence}")
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError as exc:
            raise DecisionStateError("event_payload_invalid", str(row["event_id"])) from exc
        payload_checksum = str(row["payload_checksum"])
        if checksum(payload) != payload_checksum:
            raise DecisionStateError("event_checksum_mismatch", str(row["event_id"]))
        event_type = str(row["event_type"])
        previous = str(row["previous_event_checksum"])
        if previous != prior_checksum:
            raise DecisionStateError("event_chain_mismatch", str(row["event_id"]))
        if sequence == 1:
            required = {
                "event_type": "recommendation_published",
                "sequence": 1,
                "recommendation_id": recommendation_id,
                "recommendation_checksum": str(recommendation["payload_checksum"]),
                "decision_run_id": str(run["run_id"]),
                "decision_run_checksum": str(run["run_checksum"]),
                "source_run_id": str(run["source_run_id"]),
                "source_run_checksum": str(run["source_run_checksum"]),
                "source_publication_sequence": int(run["source_publication_sequence"]),
                "snapshot_id": str(run["snapshot_id"]),
                "snapshot_hash": str(run["snapshot_hash"]),
                "previous_event_checksum": GENESIS_SENTINEL,
            }
            if event_type != "recommendation_published" or any(payload.get(key) != value for key, value in required.items()):
                raise DecisionStateError("genesis_binding_mismatch", recommendation_id)
            if str(row["typed_record_id"]) != recommendation_id:
                raise DecisionStateError("genesis_binding_mismatch", recommendation_id)
        else:
            if event_type not in {"confirmation", "action"}:
                raise DecisionStateError("unsupported_event_type", event_type)
            typed = _typed_payload(con, event_type, str(row["typed_record_id"]))
            if payload.get("typed_record_checksum") != checksum(typed):
                raise DecisionStateError("event_typed_record_mismatch", str(row["event_id"]))
            expected_event = {
                "event_type": event_type,
                "sequence": sequence,
                "recommendation_id": recommendation_id,
                "recommendation_checksum": str(recommendation["payload_checksum"]),
                "typed_record_id": str(row["typed_record_id"]),
                "previous_event_checksum": previous,
            }
            if any(payload.get(key) != value for key, value in expected_event.items()):
                raise DecisionStateError("event_binding_mismatch", str(row["event_id"]))
            if (
                typed.get("recommendation_id") != recommendation_id
                or typed.get("recommendation_checksum") != str(recommendation["payload_checksum"])
                or typed.get("expected_sequence") != sequence - 1
                or typed.get("actor_class") != "user"
                or len(str(typed.get("actor_identity_hash", ""))) != 64
            ):
                raise DecisionStateError("typed_record_binding_mismatch", str(row["typed_record_id"]))
            if event_type == "confirmation":
                decision = str(typed["decision"])
                if typed.get("cognitive_type") != "user_confirmation" or decision not in _CONFIRMATIONS:
                    raise DecisionStateError("typed_record_binding_mismatch", str(row["typed_record_id"]))
                if _parse_time(str(typed.get("occurred_at", "")), "occurred_at") > _parse_time(
                    str(recommendation["expires_at"]), "expires_at"
                ):
                    raise DecisionStateError("recommendation_expired", recommendation_id)
                confirmation_state = _confirmation_transition(confirmation_state, action_state, decision)
            else:
                next_action = str(typed["action_state"])
                if typed.get("record_type") != "action_attestation" or next_action not in _ACTION_STATES:
                    raise DecisionStateError("typed_record_binding_mismatch", str(row["typed_record_id"]))
                action_state = _action_transition(confirmation_state, action_state, next_action)
        events.append(DecisionEvent(
            event_id=str(row["event_id"]), recommendation_id=recommendation_id,
            sequence=sequence, event_type=event_type, typed_record_id=str(row["typed_record_id"]),
            previous_event_checksum=previous, payload=payload, payload_checksum=payload_checksum,
        ))
        prior_checksum = payload_checksum
    return DecisionState(
        recommendation_id=recommendation_id,
        recommendation_checksum=str(recommendation["payload_checksum"]),
        confirmation_state=confirmation_state,
        action_state=action_state,
        events=tuple(events),
    )


def project_history(db_path: Path, recommendation_id: str) -> DecisionState:
    con = sqlite3.connect(f"file:{Path(db_path).resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        return _project(con, recommendation_id)
    finally:
        con.close()


def _existing_receipt(
    con: sqlite3.Connection,
    *,
    table: str,
    id_column: str,
    recommendation_id: str,
    actor_identity_hash: str,
    idempotency_key: str,
    payload: Mapping[str, Any],
) -> DecisionReceipt | None:
    row = con.execute(
        f"SELECT {id_column},payload_json,payload_checksum FROM {table} "
        "WHERE recommendation_id=? AND actor_identity_hash=? AND idempotency_key=?",
        (recommendation_id, actor_identity_hash, idempotency_key),
    ).fetchone()
    if row is None:
        return None
    if canonical_json(json.loads(str(row["payload_json"]))) != canonical_json(payload) or str(row["payload_checksum"]) != checksum(payload):
        raise DecisionStateError("idempotency_conflict", idempotency_key)
    event = con.execute(
        "SELECT event_id,sequence,payload_checksum FROM decision_events WHERE typed_record_id=?",
        (row[id_column],),
    ).fetchone()
    if event is None:
        raise DecisionStateError("typed_event_missing", str(row[id_column]))
    return DecisionReceipt(str(row[id_column]), str(event["event_id"]), recommendation_id,
                           int(event["sequence"]), str(row["payload_checksum"]))


def _append_event(
    con: sqlite3.Connection,
    *,
    recommendation_id: str,
    recommendation_checksum: str,
    event_type: str,
    typed_record_id: str,
    typed_payload_checksum: str,
    sequence: int,
    previous_event_checksum: str,
    occurred_at: str,
) -> tuple[str, str]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "sequence": sequence,
        "recommendation_id": recommendation_id,
        "recommendation_checksum": recommendation_checksum,
        "typed_record_id": typed_record_id,
        "typed_record_checksum": typed_payload_checksum,
        "previous_event_checksum": previous_event_checksum,
        "occurred_at": occurred_at,
    }
    event_id = f"dev_{checksum(payload)[:24]}"
    payload_checksum = checksum(payload)
    con.execute(
        "INSERT INTO decision_events VALUES (?,?,?,?,?,?,?,?,?)",
        (event_id, recommendation_id, sequence, event_type, typed_record_id,
         previous_event_checksum, canonical_json(payload), payload_checksum, occurred_at),
    )
    return event_id, payload_checksum


def record_confirmation(
    db_path: Path,
    *,
    recommendation_id: str,
    recommendation_checksum: str,
    decision: str,
    actor_class: str,
    actor_identity_hash: str,
    reason_code: str,
    expected_sequence: int,
    idempotency_key: str,
    occurred_at: str,
    inject_failure_at: str | None = None,
) -> DecisionReceipt:
    if decision not in _CONFIRMATIONS:
        raise DecisionStateError("invalid_confirmation", decision)
    _validate_actor(actor_class, actor_identity_hash)
    occurred = _parse_time(occurred_at, "occurred_at")
    if not reason_code or not idempotency_key:
        raise DecisionStateError("confirmation_metadata_required")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "cognitive_type": "user_confirmation",
        "recommendation_id": recommendation_id,
        "recommendation_checksum": recommendation_checksum,
        "decision": decision,
        "actor_class": actor_class,
        "actor_identity_hash": actor_identity_hash,
        "reason_code": reason_code,
        "expected_sequence": expected_sequence,
        "idempotency_key": idempotency_key,
        "occurred_at": occurred_at,
    }
    con = connect_rw(Path(db_path), timeout=60)
    con.row_factory = sqlite3.Row
    try:
        assert_foreign_key_integrity(con)
        con.execute("BEGIN IMMEDIATE")
        state = _project(con, recommendation_id)
        rec, _, _ = _load_recommendation(con, recommendation_id)
        if str(rec["payload_checksum"]) != recommendation_checksum:
            raise DecisionStateError("recommendation_checksum_mismatch", recommendation_id)
        if occurred > _parse_time(str(rec["expires_at"]), "expires_at"):
            raise DecisionStateError("recommendation_expired", recommendation_id)
        existing = _existing_receipt(
            con, table="decision_confirmations", id_column="confirmation_id",
            recommendation_id=recommendation_id, actor_identity_hash=actor_identity_hash,
            idempotency_key=idempotency_key, payload=payload,
        )
        if existing is not None:
            con.commit()
            return existing
        if expected_sequence != state.events[-1].sequence:
            raise DecisionStateError("stale_expected_sequence", str(expected_sequence))
        _confirmation_transition(state.confirmation_state, state.action_state, decision)
        confirmation_id = f"dcf_{checksum(payload)[:24]}"
        payload_checksum = checksum(payload)
        con.execute(
            "INSERT INTO decision_confirmations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (confirmation_id, recommendation_id, recommendation_checksum, decision,
             actor_class, actor_identity_hash, reason_code, expected_sequence,
             idempotency_key, canonical_json(payload), payload_checksum, occurred_at),
        )
        if inject_failure_at == "after_typed_record":
            raise RuntimeError("injected decision state failure after typed record")
        event_id, _ = _append_event(
            con, recommendation_id=recommendation_id,
            recommendation_checksum=recommendation_checksum, event_type="confirmation",
            typed_record_id=confirmation_id, typed_payload_checksum=payload_checksum,
            sequence=expected_sequence + 1,
            previous_event_checksum=state.events[-1].payload_checksum,
            occurred_at=occurred_at,
        )
        if inject_failure_at == "after_event":
            raise RuntimeError("injected decision state failure after event")
        con.commit()
        return DecisionReceipt(confirmation_id, event_id, recommendation_id,
                               expected_sequence + 1, payload_checksum)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def record_action(
    db_path: Path,
    *,
    recommendation_id: str,
    recommendation_checksum: str,
    action_state: str,
    source_class: str,
    actor_class: str,
    actor_identity_hash: str,
    reason_code: str,
    expected_sequence: int,
    idempotency_key: str,
    occurred_at: str,
    external_ref_checksum: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    inject_failure_at: str | None = None,
) -> DecisionReceipt:
    if action_state not in _ACTION_STATES:
        raise DecisionStateError("invalid_action_state", action_state)
    if source_class not in {"user_attested", "user_external_ref"}:
        raise DecisionStateError("invalid_action_source", source_class)
    _validate_actor(actor_class, actor_identity_hash)
    _parse_time(occurred_at, "occurred_at")
    if not reason_code or not idempotency_key:
        raise DecisionStateError("action_metadata_required")
    if external_ref_checksum is not None and len(external_ref_checksum) != 64:
        raise DecisionStateError("external_ref_checksum_invalid")
    if source_class == "user_external_ref" and external_ref_checksum is None:
        raise DecisionStateError("external_ref_checksum_required")
    metadata = dict(metadata or {})
    _reject_action_metadata(metadata)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "action_attestation",
        "recommendation_id": recommendation_id,
        "recommendation_checksum": recommendation_checksum,
        "action_state": action_state,
        "source_class": source_class,
        "actor_class": actor_class,
        "actor_identity_hash": actor_identity_hash,
        "reason_code": reason_code,
        "expected_sequence": expected_sequence,
        "idempotency_key": idempotency_key,
        "external_ref_checksum": external_ref_checksum,
        "metadata": metadata,
        "occurred_at": occurred_at,
    }
    con = connect_rw(Path(db_path), timeout=60)
    con.row_factory = sqlite3.Row
    try:
        assert_foreign_key_integrity(con)
        con.execute("BEGIN IMMEDIATE")
        state = _project(con, recommendation_id)
        rec, _, _ = _load_recommendation(con, recommendation_id)
        if str(rec["payload_checksum"]) != recommendation_checksum:
            raise DecisionStateError("recommendation_checksum_mismatch", recommendation_id)
        existing = _existing_receipt(
            con, table="decision_actions", id_column="action_id",
            recommendation_id=recommendation_id, actor_identity_hash=actor_identity_hash,
            idempotency_key=idempotency_key, payload=payload,
        )
        if existing is not None:
            con.commit()
            return existing
        if expected_sequence != state.events[-1].sequence:
            raise DecisionStateError("stale_expected_sequence", str(expected_sequence))
        _action_transition(state.confirmation_state, state.action_state, action_state)
        action_id = f"dac_{checksum(payload)[:24]}"
        payload_checksum = checksum(payload)
        con.execute(
            "INSERT INTO decision_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (action_id, recommendation_id, recommendation_checksum, action_state,
             source_class, actor_class, actor_identity_hash, reason_code,
             expected_sequence, idempotency_key, external_ref_checksum,
             canonical_json(payload), payload_checksum, occurred_at),
        )
        if inject_failure_at == "after_typed_record":
            raise RuntimeError("injected decision state failure after typed record")
        event_id, _ = _append_event(
            con, recommendation_id=recommendation_id,
            recommendation_checksum=recommendation_checksum, event_type="action",
            typed_record_id=action_id, typed_payload_checksum=payload_checksum,
            sequence=expected_sequence + 1,
            previous_event_checksum=state.events[-1].payload_checksum,
            occurred_at=occurred_at,
        )
        if inject_failure_at == "after_event":
            raise RuntimeError("injected decision state failure after event")
        con.commit()
        return DecisionReceipt(action_id, event_id, recommendation_id,
                               expected_sequence + 1, payload_checksum)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


__all__ = ["DecisionStateError", "project_history", "record_action", "record_confirmation"]
