"""Phase 62: generation-bound canonical v2 event repository.

The only persistence seam for the v2 event authority (Phase 62 CONTEXT D-16/D-17).

Responsibilities:
  - stage a complete generation transactionally: source artifacts, adapter run,
    sessions, typed events, relations, field dispositions
  - validate a staged generation (integrity + FK + counts)
  - provide generation-scoped reads and native-locator lookup
  - provide read-only authority-generation queries

Explicitly NOT owned here (later Phase 62 plans): activation of the authority
pointer, compatibility projection building, views, and extraction policy. This
repository never changes ``ce_generation_authority``; it only reads it.

Phase 62-04 additions (still no authority mutation): additive
``ce_activation_bindings`` / ``ce_activation_log`` tables for the generation
lifecycle owner, read-only authority/binding snapshots, and transaction-bound
low-level writes (:func:`write_bindings` / :func:`record_activation_attempt`).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventRelation,
    FieldDispositionRecord,
    Provenance,
    TypedEvent,
)
from personal_knowledge.adapters.conversation_sources.contracts import SourceArtifact
from personal_knowledge.application.conversation.event_schema import (
    SCHEMA_VERSION,
    create_v2_schema,
)


class EventRepositoryError(RuntimeError):
    """A v2 generation write or read violated the event-authority contract."""


@dataclass(frozen=True)
class GenerationInput:
    """One complete, validated adaptation result ready to stage as a generation."""

    family: str
    adapter_version: str
    contract_version: str
    capability_digest: str
    source_manifest_id: str
    dataset_digest: str
    artifacts: tuple[SourceArtifact, ...] = ()
    sessions: tuple[AdaptedSession, ...] = ()
    events: tuple[TypedEvent, ...] = ()
    relations: tuple[EventRelation, ...] = ()
    dispositions: tuple[FieldDispositionRecord, ...] = ()
    warnings: tuple[str, ...] = ()


def _fidelity_json(profile) -> str:
    return json.dumps(profile.to_dict(), sort_keys=True)


def _insert_artifacts(
    con: sqlite3.Connection, gen: GenerationInput, generation_id: str
) -> None:
    for artifact in gen.artifacts:
        con.execute(
            "INSERT OR IGNORE INTO ce_source_artifacts "
            "(artifact_id, family, source_kind, content_hash, capture_method, "
            " relative_path, byte_size, schema_digest, privacy_dispositions) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                artifact.artifact_id,
                artifact.family or gen.family,
                artifact.source_kind,
                artifact.content_hash,
                artifact.capture_method,
                artifact.relative_path,
                artifact.byte_size,
                artifact.schema_digest,
                json.dumps(list(artifact.privacy_dispositions), sort_keys=True),
            ),
        )


def _insert_sessions(
    con: sqlite3.Connection, gen: GenerationInput, generation_id: str
) -> None:
    for session in gen.sessions:
        con.execute(
            "INSERT OR IGNORE INTO ce_sessions "
            "(generation_id, session_id, family, native_session_id, started_at, "
            " ended_at, artifact_id, native_locator, contract_version, fidelity_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                generation_id,
                session.session_id,
                gen.family,
                session.native_session_id,
                session.started_at,
                session.ended_at,
                session.provenance.artifact_id,
                session.provenance.native_locator,
                session.provenance.contract_version or gen.contract_version,
                _fidelity_json(session.fidelity),
            ),
        )


def _insert_events(
    con: sqlite3.Connection, gen: GenerationInput, generation_id: str
) -> None:
    for event in gen.events:
        con.execute(
            "INSERT OR IGNORE INTO ce_events "
            "(generation_id, event_id, session_id, kind, artifact_id, "
            " native_locator, native_event_id, occurred_at, ordinal, "
            " native_payload_ref, summary, contract_version, fidelity_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                generation_id,
                event.event_id,
                event.session_id,
                event.kind.value,
                event.provenance.artifact_id,
                event.provenance.native_locator,
                event.provenance.native_event_id,
                event.occurred_at,
                event.ordinal,
                event.native_payload_ref,
                event.summary,
                event.provenance.contract_version or gen.contract_version,
                _fidelity_json(event.fidelity),
            ),
        )
        for disp in event.field_dispositions:
            con.execute(
                "INSERT OR IGNORE INTO ce_field_dispositions "
                "(generation_id, event_id, field_name, disposition, reason) "
                "VALUES (?,?,?,?,?)",
                (
                    generation_id,
                    event.event_id,
                    disp.field_name,
                    disp.disposition.value,
                    disp.reason,
                ),
            )


def _insert_relations(
    con: sqlite3.Connection, gen: GenerationInput, generation_id: str
) -> None:
    for relation in gen.relations:
        con.execute(
            "INSERT OR IGNORE INTO ce_event_relations "
            "(generation_id, relation_id, source_event_id, target_event_id, "
            " relation_kind) VALUES (?,?,?,?,?)",
            (
                generation_id,
                relation.relation_id,
                relation.source_event_id,
                relation.target_event_id,
                relation.relation_kind.value,
            ),
        )


def _insert_dispositions(
    con: sqlite3.Connection, gen: GenerationInput, generation_id: str
) -> None:
    for disp in gen.dispositions:
        con.execute(
            "INSERT OR IGNORE INTO ce_field_dispositions "
            "(generation_id, event_id, field_name, disposition, reason) "
            "VALUES (?,?,?,?,?)",
            (
                generation_id,
                disp.event_id if hasattr(disp, "event_id") else _default_event(gen),
                disp.field_name,
                disp.disposition.value,
                disp.reason,
            ),
        )


_ACTIVATION_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS ce_activation_bindings (
        kind TEXT PRIMARY KEY, generation_id TEXT NOT NULL,
        value TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS ce_activation_log (
        attempt_id TEXT PRIMARY KEY, generation_id TEXT NOT NULL,
        outcome TEXT NOT NULL, reason TEXT, attempted_at TEXT NOT NULL)""",
)


class EventRepository:
    """Generation-bound persistence for the canonical v2 event authority."""

    def __init__(self, db: Path) -> None:
        self.db = Path(db)

    # ------------------------------------------------------------------ schema

    def create_schema(self) -> None:
        """Apply additive v2 DDL (idempotent; legacy tables untouched)."""
        create_v2_schema(self.db)
        con = sqlite3.connect(str(self.db))
        try:
            con.execute("PRAGMA foreign_keys=ON")
            for statement in _ACTIVATION_DDL:
                con.execute(statement)
            con.commit()
        finally:
            con.close()

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if readonly:
            con = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        else:
            con = sqlite3.connect(str(self.db))
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    # ------------------------------------------------------------------ write

    def write_generation(
        self, gen: GenerationInput, generation_id: str
    ) -> str:
        """Stage a complete generation in one transaction (idempotent replay).

        Any validation/FK failure rolls back the whole transaction, so a
        partial generation is never left behind.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        con = self._connect()
        try:
            con.execute("BEGIN")
            con.execute(
                "INSERT OR IGNORE INTO ce_event_generations "
                "(generation_id, status, source_manifest_id, dataset_digest, created_at) "
                "VALUES (?, 'staged', ?, ?, ?)",
                (generation_id, gen.source_manifest_id, gen.dataset_digest, now),
            )
            _insert_artifacts(con, gen, generation_id)
            con.execute(
                "INSERT OR IGNORE INTO ce_adapter_runs "
                "(run_id, generation_id, family, adapter_version, contract_version, "
                " capability_digest, warnings, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"run-{generation_id}",
                    generation_id,
                    gen.family,
                    gen.adapter_version,
                    gen.contract_version,
                    gen.capability_digest,
                    json.dumps(list(gen.warnings), sort_keys=True),
                    now,
                ),
            )
            _insert_sessions(con, gen, generation_id)
            _insert_events(con, gen, generation_id)
            _insert_relations(con, gen, generation_id)
            _insert_dispositions(con, gen, generation_id)
            con.commit()
        except sqlite3.IntegrityError as exc:
            con.rollback()
            raise EventRepositoryError(
                f"write_generation failed (foreign key / generation constraint): {exc}"
            ) from exc
        finally:
            con.close()
        return generation_id

    # --------------------------------------------------------------- validate

    def validate_generation(self, generation_id: str) -> dict:
        """Return integrity/FK/count results for one generation (read-only)."""
        con = self._connect(readonly=True)
        try:
            exists = con.execute(
                "SELECT 1 FROM ce_event_generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
            if not exists:
                return {
                    "ok": False,
                    "generation_id": generation_id,
                    "events": 0,
                    "sessions": 0,
                    "relations": 0,
                    "dispositions": 0,
                    "artifacts": 0,
                    "integrity": "generation_absent",
                    "fk_violations": [],
                }
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk_violations = con.execute("PRAGMA foreign_key_check").fetchall()
            counts = {
                "events": con.execute(
                    "SELECT COUNT(*) FROM ce_events WHERE generation_id=?", (generation_id,)
                ).fetchone()[0],
                "sessions": con.execute(
                    "SELECT COUNT(*) FROM ce_sessions WHERE generation_id=?", (generation_id,)
                ).fetchone()[0],
                "relations": con.execute(
                    "SELECT COUNT(*) FROM ce_event_relations WHERE generation_id=?",
                    (generation_id,),
                ).fetchone()[0],
                "dispositions": con.execute(
                    "SELECT COUNT(*) FROM ce_field_dispositions WHERE generation_id=?",
                    (generation_id,),
                ).fetchone()[0],
                "artifacts": con.execute(
                    "SELECT COUNT(*) FROM ce_source_artifacts"
                ).fetchone()[0],
            }
            return {
                "ok": integrity == "ok" and not fk_violations,
                "generation_id": generation_id,
                "integrity": integrity,
                "fk_violations": [list(row) for row in fk_violations],
                **counts,
            }
        finally:
            con.close()

    # ---------------------------------------------------------------- reads

    def iter_events(self, generation_id: str) -> list[dict]:
        con = self._connect(readonly=True)
        try:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT event_id, session_id, kind, artifact_id, native_locator, "
                    "native_event_id, occurred_at, ordinal, native_payload_ref, "
                    "summary, contract_version, fidelity_json "
                    "FROM ce_events WHERE generation_id=? ORDER BY ordinal, event_id",
                    (generation_id,),
                )
            ]
        finally:
            con.close()

    def iter_relations(self, generation_id: str) -> list[dict]:
        con = self._connect(readonly=True)
        try:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT relation_id, source_event_id, target_event_id, relation_kind "
                    "FROM ce_event_relations WHERE generation_id=? "
                    "ORDER BY relation_id",
                    (generation_id,),
                )
            ]
        finally:
            con.close()

    def iter_dispositions(self, generation_id: str) -> list[dict]:
        con = self._connect(readonly=True)
        try:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT event_id, field_name, disposition, reason "
                    "FROM ce_field_dispositions WHERE generation_id=? "
                    "ORDER BY event_id, field_name",
                    (generation_id,),
                )
            ]
        finally:
            con.close()

    def lookup_by_native_locator(
        self, native_locator: str, generation_id: str | None = None
    ) -> list[dict]:
        """Find events by native locator within one generation (or the
        authority generation when none is given)."""
        if generation_id is None:
            generation_id = self.authority_generation_id()
            if generation_id is None:
                return []
        con = self._connect(readonly=True)
        try:
            return [
                dict(r)
                for r in con.execute(
                    "SELECT event_id, session_id, kind, artifact_id, native_locator, "
                    "native_event_id, occurred_at, ordinal, native_payload_ref, summary "
                    "FROM ce_events WHERE generation_id=? AND native_locator=? "
                    "ORDER BY ordinal",
                    (generation_id, native_locator),
                )
            ]
        finally:
            con.close()

    # ------------------------------------------------------- authority (RO)

    def authority_generation_id(self) -> str | None:
        """Read-only: the generation marked active in the authority table."""
        con = self._connect(readonly=True)
        try:
            row = con.execute(
                "SELECT generation_id FROM ce_generation_authority "
                "WHERE active=1 ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()

    def write_bindings(
        self, con: sqlite3.Connection, generation_id: str,
        values: dict[str, str],
    ) -> None:
        """Bind projection/version/watermark/fingerprint values (transaction-bound).

        The caller owns the transaction so the binding commits or rolls back
        atomically with the authority pointer and the compatibility projection.
        """
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for kind, value in sorted(values.items()):
            con.execute(
                "INSERT OR REPLACE INTO ce_activation_bindings "
                "(kind, generation_id, value, updated_at) VALUES (?,?,?,?)",
                (kind, generation_id, value, now),
            )

    def record_attempt_log(
        self, generation_id: str, outcome: str, reason: str | None = None
    ) -> None:
        """Append a metadata-only audit record (separate transaction, best-effort).

        Written outside the activation transaction so a failed activation still
        leaves an audit trail (D-09). Never blocks or masks the activation error.
        """
        import hashlib
        import uuid
        from datetime import datetime, timezone

        attempt_id = hashlib.sha256(
            f"{generation_id}|{outcome}|{uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()[:24]
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            con = sqlite3.connect(str(self.db))
            try:
                con.execute(
                    "INSERT INTO ce_activation_log "
                    "(attempt_id, generation_id, outcome, reason, attempted_at) "
                    "VALUES (?,?,?,?,?)",
                    (attempt_id, generation_id, outcome, reason, now),
                )
                con.commit()
            finally:
                con.close()
        except sqlite3.Error:  # pragma: no cover - audit must never block activation
            pass

    def query_authority_events_by_native_locator(
        self, native_locator: str
    ) -> list[dict]:
        """Read-only active-generation query; empty until an authority activates."""
        return self.lookup_by_native_locator(native_locator)


def _default_event(gen: GenerationInput) -> str:
    """Fallback target for a disposition lacking an explicit event id."""
    if gen.events:
        return gen.events[0].event_id
    raise EventRepositoryError(
        "field disposition requires an event_id and generation contains no events"
    )
