"""Plan 61-05: Python-canonical conversation/project-scope projection (HARNESS-01).

The canonical conversation repository is the sole authority for a safe
``conversation.thread.last|recent|select`` and the schema-bound
``conversation.project_scopes.list`` / ``conversation.project_scope.select``
reads. Project scopes are derived deterministically from canonical session
working directories (``canonical_sessions.cwd``): one scope per distinct
working directory, label = directory basename.

Every response is metadata-only and read-only. Selected-thread display text is
normalized to stable user/assistant messages and exists only inside the returned
view model: it is never retained on this service and never reaches telemetry
(which receives IDs/counts/checksums/status only). The live AgentsView database
is never referenced here and no canonical write is ever issued.
"""

from __future__ import annotations

import base64
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from personal_knowledge.application.conversation.harness_freshness import DualFreshness  # noqa: F401
from personal_knowledge.core.canonical_visibility import (
    canonical_projection_predicate,
)
from personal_knowledge.core.conversation_repository import SOURCE_CANONICAL, ConversationRepository  # noqa: F401
from personal_knowledge.intelligence.schema import SnapshotBinding, checksum
from personal_knowledge.intelligence.state_projection import (
    ProjectionError,
    normalize_candidates,
)

MAX_LIMIT = 50
MESSAGE_FIELDS = ("message_id", "role", "display_text", "created_at", "source_ref", "evidence_ref")
THREAD_METADATA_FIELDS = ("conversation_id", "project_scope_id", "label", "last_activity_at", "message_count")
SCOPE_ROW_FIELDS = ("project_scope_id", "label", "thread_count", "last_activity_at", "freshness")


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(base64.urlsafe_b64decode(str(value).encode("ascii")).decode("ascii"))
    except Exception as exc:  # transport-safe: opaque cursor only
        raise ValueError("cursor_invalid") from exc


def _basename(path: str) -> str:
    name = Path(path).name
    return name or path


def _pagination(limit: int, has_more: bool, cursor: str | None) -> dict:
    return {"limit": limit, "has_more": has_more, "cursor": cursor}


def _normalize_limit(limit: Any, default: int = 20) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        return default
    if limit < 1:
        return 1
    if limit > MAX_LIMIT:
        return MAX_LIMIT
    return limit


def _overall(freshness: Mapping[str, Any]) -> str:
    return str(freshness.get("overall_status", "unknown"))


def _limitation_text(freshness: Mapping[str, Any]) -> str:
    statuses = [
        str((freshness.get("source_to_agentsview") or {}).get("status", "unknown")),
        str((freshness.get("agentsview_to_canonical") or {}).get("status", "unknown")),
    ]
    if "unknown" in statuses:
        return "freshness unknown: a freshness leg could not be verified"
    if "missing_watermark" in statuses:
        return "missing watermark: synchronization watermarks are not available"
    if "backlog_pending" in statuses:
        return "backlog pending: some evidence has not been committed to canonical"
    if "stale" in statuses:
        return "data is stale: source or canonical sync is older than the freshness horizon"
    return "data is current and bounded to the authorized scope"


class HarnessConversationService:
    """Read-only canonical navigation authority with safe explicit state envelopes.

    Requires an explicit ``canonical`` repository; legacy/live sources are
    rejected because canonical is the sole conversation history authority.
    """

    def __init__(
        self,
        *,
        repository: ConversationRepository,
        freshness_provider: Callable[[], DualFreshness],
        telemetry: Callable[[dict], None] | None = None,
    ) -> None:
        if getattr(repository, "source", None) != SOURCE_CANONICAL:
            raise ValueError("harness conversation service requires an explicit canonical repository (source='canonical')")
        self._repository = repository
        self._db = Path(repository.canonical_db)
        self._freshness_provider = freshness_provider
        self._telemetry = telemetry

    # ------------------------------------------------------------------
    # Internal helpers (all read-only, connection-per-call)
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self._db.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        return con

    def _freshness(self) -> dict:
        return self._freshness_provider().to_dict()

    def _emit_telemetry(self, record: dict) -> None:
        if self._telemetry is not None:
            self._telemetry(record)

    @staticmethod
    def _sessions(con: sqlite3.Connection) -> list[dict]:
        """Canonical sessions plus per-session last message activity (metadata only)."""
        projection_filter, projection_params = canonical_projection_predicate(
            con, "s.canonical_session_id"
        )
        rows = con.execute(
            "SELECT s.canonical_session_id AS session_id, s.cwd, s.message_count, "
            "MAX(CASE WHEN m.role IN ('user', 'assistant') THEN m.timestamp END) AS last_activity "
            "FROM canonical_sessions s "
            "LEFT JOIN canonical_messages m ON m.canonical_session_id = s.canonical_session_id "
            f"WHERE {projection_filter} "
            "GROUP BY s.canonical_session_id "
            "ORDER BY last_activity DESC",
            projection_params,
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _normalized_messages(con: sqlite3.Connection, session_id: str, *, limit: int, offset: int) -> tuple[list[dict], bool]:
        """Project only normalized user/assistant display messages with stable identity."""
        projection_filter, projection_params = canonical_projection_predicate(
            con, "canonical_session_id"
        )
        rows = con.execute(
            "SELECT canonical_message_id, role, content, timestamp, source_message_ref, content_hash "
            "FROM canonical_messages "
            "WHERE canonical_session_id = ? AND "
            f"{projection_filter} AND role IN ('user', 'assistant') "
            "ORDER BY ordinal ASC",
            (session_id, *projection_params),
        ).fetchall()
        total = len(rows)
        page = rows[offset : offset + limit]
        has_more = (offset + len(page)) < total
        messages: list[dict] = []
        for row in page:
            messages.append(
                {
                    "message_id": row["canonical_message_id"],
                    "role": row["role"],
                    "display_text": row["content"] or "",
                    "created_at": row["timestamp"] or "",
                    "source_ref": row["source_message_ref"] or "",
                    "evidence_ref": row["content_hash"] or "",
                }
            )
        return messages, has_more

    def _thread_view(self, session: dict, messages: list[dict], *, limit: int, has_more: bool, cursor: str | None) -> dict:
        freshness = self._freshness()
        if not messages:
            state = "empty"
        elif has_more:
            state = "partial"
        else:
            state = _overall(freshness)
        return {
            "ok": True,
            "data": {
                "conversation_id": session["session_id"],
                "project_scope_id": session.get("cwd"),
                "messages": messages,
                "pagination": _pagination(limit, has_more, cursor),
                "truncated": has_more,
                "freshness": freshness,
                "state": state,
                "limitation": _limitation_text(freshness),
            },
        }

    def _envelope_error(self, code: str) -> dict:
        return {"ok": False, "status": "error", "error": {"code": code}}

    # ------------------------------------------------------------------
    # conversation.thread.last / recent / select (canonical only)
    # ------------------------------------------------------------------

    def thread_last(self, *, limit: int = 20) -> dict:
        """Most recently active canonical conversation as a safe thread view."""
        limit = _normalize_limit(limit)
        try:
            with self._connect() as con:
                sessions = self._sessions(con)
                active = [item for item in sessions if item.get("last_activity")]
                if not active:
                    return self._empty_thread_view(limit, con)
                newest = active[0]
                messages, has_more = self._normalized_messages(
                    con, newest["session_id"], limit=limit, offset=0
                )
                return self._thread_view(newest, messages, limit=limit, has_more=has_more, cursor=None)
        except sqlite3.Error:
            return self._envelope_error("domain_unavailable")

    def _empty_thread_view(self, limit: int, con: sqlite3.Connection) -> dict:
        freshness = self._freshness()
        return {
            "ok": True,
            "data": {
                "conversation_id": None,
                "project_scope_id": None,
                "messages": [],
                "pagination": _pagination(limit, False, None),
                "truncated": False,
                "freshness": freshness,
                "state": "empty",
                "limitation": "empty: no canonical conversation exists yet",
            },
        }

    def thread_recent(self, *, limit: int = 20, cursor: str | None = None) -> dict:
        """Metadata-only recent canonical conversations sorted by last activity."""
        limit = _normalize_limit(limit)
        try:
            offset = _decode_cursor(cursor)
        except ValueError:
            return self._envelope_error("cursor_invalid")
        try:
            with self._connect() as con:
                sessions = self._sessions(con)
                active = [item for item in sessions if item.get("last_activity") and item.get("message_count")]
                page = active[offset : offset + limit]
                has_more = (offset + len(page)) < len(active)
                items = [
                    {
                        "conversation_id": item["session_id"],
                        "project_scope_id": item.get("cwd"),
                        "label": _basename(item.get("cwd") or ""),
                        "last_activity_at": item.get("last_activity"),
                        "message_count": item.get("message_count"),
                    }
                    for item in page
                ]
                return {
                    "ok": True,
                    "data": {
                        "conversations": items,
                        "pagination": _pagination(
                            limit,
                            has_more,
                            _encode_cursor(offset + len(page)) if has_more else None,
                        ),
                        "freshness": self._freshness(),
                    },
                }
        except sqlite3.Error:
            return self._envelope_error("domain_unavailable")

    def thread_select(self, *, conversation_id: str, limit: int = 20, after: str | None = None) -> dict:
        """Selected canonical thread normalized to user/assistant messages only."""
        limit = _normalize_limit(limit)
        try:
            offset = _decode_cursor(after)
        except ValueError:
            return self._envelope_error("cursor_invalid")
        try:
            with self._connect() as con:
                projection_filter, projection_params = (
                    canonical_projection_predicate(
                        con, "canonical_session_id"
                    )
                )
                row = con.execute(
                    "SELECT canonical_session_id AS session_id, cwd, message_count "
                    "FROM canonical_sessions WHERE canonical_session_id = ? AND "
                    f"{projection_filter}",
                    (conversation_id, *projection_params),
                ).fetchone()
                if row is None:
                    return self._envelope_error("conversation_unknown")
                session = dict(row)
                messages, has_more = self._normalized_messages(con, conversation_id, limit=limit, offset=offset)
                self._emit_telemetry(
                    {
                        "operation": "conversation.thread.select",
                        "conversation_id": conversation_id,
                        "message_count": len(messages),
                        "status": "ok",
                    }
                )
                return self._thread_view(
                    session,
                    messages,
                    limit=limit,
                    has_more=has_more,
                    cursor=_encode_cursor(offset + len(messages)) if has_more else None,
                )
        except sqlite3.Error:
            return self._envelope_error("domain_unavailable")

    # ------------------------------------------------------------------
    # conversation.project_scopes.list / conversation.project_scope.select
    # ------------------------------------------------------------------

    def project_scopes_list(self) -> dict:
        """Allowlisted scope rows only; freshness is two typed legs."""
        try:
            with self._connect() as con:
                sessions = self._sessions(con)
                grouped: dict[str, list[dict]] = {}
                for item in sessions:
                    cwd = item.get("cwd") or ""
                    grouped.setdefault(cwd, []).append(item)
                scopes: list[dict] = []
                for cwd in sorted(grouped):
                    group = grouped[cwd]
                    last_activity = max(
                        (item.get("last_activity") for item in group if item.get("last_activity")),
                        default=None,
                    )
                    scopes.append(
                        {
                            "project_scope_id": cwd,
                            "label": _basename(cwd),
                            "thread_count": len(group),
                            "last_activity_at": last_activity,
                            "freshness": self._freshness(),
                        }
                    )
                freshness = self._freshness()
                return {
                    "ok": True,
                    "data": {
                        "scopes": scopes,
                        "state": _overall(freshness),
                        "limitation": _limitation_text(freshness),
                    },
                }
        except sqlite3.Error:
            return self._envelope_error("domain_unavailable")

    def project_scope_select(self, *, project_scope_id: str, limit: int = 20, after: str | None = None) -> dict:
        """Read-only selected-scope projection with paginated recent-thread metadata."""
        limit = _normalize_limit(limit)
        try:
            offset = _decode_cursor(after)
        except ValueError:
            return self._envelope_error("cursor_invalid")
        try:
            with self._connect() as con:
                sessions = self._sessions(con)
                group = [item for item in sessions if (item.get("cwd") or "") == project_scope_id]
                if not group:
                    return self._envelope_error("unknown_scope")
                active = [item for item in group if item.get("last_activity") and item.get("message_count")]
                page = active[offset : offset + limit]
                has_more = (offset + len(page)) < len(active)
                threads = [
                    {
                        "conversation_id": item["session_id"],
                        "label": _basename(item.get("cwd") or ""),
                        "last_activity_at": item.get("last_activity"),
                        "message_count": item.get("message_count"),
                    }
                    for item in page
                ]
                freshness = self._freshness()
                self._emit_telemetry(
                    {
                        "operation": "conversation.project_scope.select",
                        "project_scope_id": project_scope_id,
                        "thread_count": len(threads),
                        "status": "ok",
                    }
                )
                return {
                    "ok": True,
                    "data": {
                        "project_scope_id": project_scope_id,
                        "label": _basename(project_scope_id),
                        "threads": threads,
                        "pagination": _pagination(
                            limit,
                            has_more,
                            _encode_cursor(offset + len(page)) if has_more else None,
                        ),
                        "freshness": freshness,
                        "state": _overall(freshness),
                        "limitation": _limitation_text(freshness),
                    },
                }
        except sqlite3.Error:
            return self._envelope_error("domain_unavailable")


class HarnessModelProjectionError(Exception):
    """Fail-closed projection derivation error with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


class HarnessModelProjectionProvider:
    """Plan 61-09: derive a versioned personal-model projection (HARNESS-07).

    The provider reads ONLY the bound review adapter/ledger (D-28) and every
    confirmed-accepted candidate is validated through
    ``state_projection.normalize_candidates`` -- the sole normalization/
    validation path (D-20/D-21/D-22) -- against its own immutable agentsview
    snapshot binding before a safe metadata-only envelope is derived. A
    candidate is projection input only when its effective review state is a
    confirmed accept/edit; drafts, ignored, undone, mixed-snapshot or private
    content is never projected. The envelope carries provenance_class:
    inference, version, scope, valid/observed time, confidence/uncertainty, the
    two typed freshness legs, support/conflict refs and counts, supersession,
    limitations and status -- without raw Evidence bodies, drafts, ignored
    Candidates or any canonical/promotion claim (T-61-PROJ-01). The provider
    never reads raw Evidence bodies, never references canonical/promotion/
    rollback/watermark/active-pointer/permission/value state and never writes
    anything (T-61-CANON-02).
    """

    # Serving-role -> typed evidence artifact mapping for the shared
    # normalization vocabulary (EVIDENCE_TYPES in intelligence/schema).
    _EVIDENCE_ARTIFACT_TYPE = {
        "source.agentsview": "turn",
        "agent.conversation.canonical": "canonical_message",
    }

    def __init__(self, *, review_adapter: Any, review_db: Path | str | None = None) -> None:
        self.review_adapter = review_adapter
        self.review_db = review_db

    # ------------------------------------------------------------------
    # Review ledger reads (read-only, connection-per-call)
    # ------------------------------------------------------------------

    def _review_feedback_rows(self) -> list[dict[str, Any]]:
        db = getattr(self.review_adapter, "db_path", None) or self.review_db
        if db is None:
            return []
        db_path = Path(db)
        if not db_path.exists():
            return []
        con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT feedback_id, candidate_id, action, version, "
                "referenced_feedback_id, disposition, recorded_at "
                "FROM candidate_review_feedback ORDER BY rowid"
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []
        finally:
            con.close()

    @staticmethod
    def _effective_review_state(candidate_id: str, rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        """Replay the append-only review history to one fail-closed effective state.

        accept/edit confirms acceptance; ignore records an exclusion; undo
        reverts the referenced gesture so a confirmed accept/edit is no longer
        projection input. Unknown or malformed history fails closed (never
        accepted).
        """
        by_feedback = {str(row.get("feedback_id") or ""): row for row in rows}
        accepted = False
        ignored = False
        disposition: Any = None
        review: Mapping[str, Any] | None = None
        for row in rows:
            if str(row.get("candidate_id") or "") != candidate_id:
                continue
            action = str(row.get("action") or "")
            if action in ("accept", "edit"):
                accepted, ignored = True, False
                disposition = row.get("disposition")
                review = row
            elif action == "ignore":
                accepted, ignored = False, True
            elif action == "undo":
                referenced = row.get("referenced_feedback_id")
                ref_action = str((by_feedback.get(str(referenced) or "") or {}).get("action") or "")
                if ref_action == "ignore":
                    ignored = False
                elif ref_action in ("accept", "edit"):
                    accepted = False
                else:
                    accepted, ignored = False, False
        return {
            "accepted": accepted,
            "ignored": ignored,
            "disposition": disposition,
            "review": review,
        }

    # ------------------------------------------------------------------
    # state_projection normalization/validation path
    # ------------------------------------------------------------------

    @staticmethod
    def _snapshot_for(candidate: Mapping[str, Any]) -> SnapshotBinding:
        observation = candidate.get("observation")
        snapshot_ref = ""
        if isinstance(observation, Mapping):
            snapshot_ref = str(observation.get("snapshot") or "")
        if not snapshot_ref.startswith("agentsview@"):
            raise HarnessModelProjectionError(
                "snapshot_invalid", "accepted candidate must bind an agentsview snapshot"
            )
        snapshot_hash = snapshot_ref.split("@", 1)[1]
        members: dict[str, dict[str, Any]] = {}
        for ev in candidate.get("evidence") or []:
            if not isinstance(ev, Mapping):
                continue
            role = str(ev.get("serving_role") or "")
            if not role:
                continue
            members[role] = {
                "artifact_version_id": str(ev.get("artifact_version_id") or ""),
                "privacy_class": str(ev.get("privacy_class") or "R2"),
            }
        return SnapshotBinding(
            snapshot_id=snapshot_ref,
            snapshot_hash=snapshot_hash,
            members=members,
        )

    def _normalize_input(self, candidate: Mapping[str, Any], snapshot: SnapshotBinding) -> dict[str, Any]:
        evidence: list[dict[str, Any]] = []
        for ev in candidate.get("evidence") or []:
            if not isinstance(ev, Mapping):
                continue
            row = dict(ev)
            row["snapshot_id"] = snapshot.snapshot_id
            row["snapshot_hash"] = snapshot.snapshot_hash
            role = str(ev.get("serving_role") or "")
            row["artifact_type"] = self._EVIDENCE_ARTIFACT_TYPE.get(role, "turn")
            evidence.append(row)
        return {
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_hash": snapshot.snapshot_hash,
            "assertion_kind": "goal",
            "provenance_class": "inference",
            "derivation": "synthesis",
            "subject": "user",
            "domain": "work",
            "scope": str(candidate.get("scope") or ""),
            "predicate": "derived_context",
            "value": {
                "conclusion_ref": str(candidate.get("candidate_id") or ""),
                "event_ref": str(candidate.get("event_id") or ""),
                "reflection_key": str(candidate.get("reflection_key") or ""),
            },
            "valid_from": str(candidate.get("valid_from") or ""),
            "valid_to": candidate.get("valid_to") or None,
            "observed_at": str(candidate.get("observed_at") or ""),
            "confidence": float(candidate.get("confidence") or 0.5),
            "uncertainty_reason": str(candidate.get("uncertainty") or "accepted review derivation"),
            "lifecycle": "current",
            "evidence": evidence,
        }

    def _validate_accepted(self, accepted: list[tuple[Mapping[str, Any], dict[str, Any]]]) -> None:
        """The only normalization/validation path for accepted review material.

        ``normalize_candidates`` enforces the 61-09 invariants: inference derives
        only from synthesis, draft/ignored/pending lifecycle values reject,
        mixed-snapshot evidence rejects and private/secret payloads reject.
        """
        for candidate, _state in accepted:
            snapshot = self._snapshot_for(candidate)
            normalize_candidates(
                [self._normalize_input(candidate, snapshot)],
                snapshot=snapshot,
            )

    # ------------------------------------------------------------------
    # Safe projection envelope
    # ------------------------------------------------------------------

    def _empty_projection(self, scope: str, limitation: str) -> dict[str, Any]:
        return {
            "projection_id": "projection_" + checksum({"scope": scope, "empty": True})[:24],
            "version": 0,
            "provenance_class": "inference",
            "scope": scope,
            "valid_from": None,
            "valid_to": None,
            "observed_at": None,
            "confidence": None,
            "uncertainty": ["unknown_no_evidence"],
            "freshness": {},
            "support_refs": [],
            "support_count": 0,
            "conflict_refs": [],
            "conflict_count": 0,
            "conflicts": [],
            "supersession": None,
            "limitations": [limitation],
            "status": "unknown",
        }

    @staticmethod
    def _projection_status(
        *,
        accepted: list[tuple[Mapping[str, Any], dict[str, Any]]],
        reviewed_not_accepted: bool,
        superseded_ids: list[str],
        primary: Mapping[str, Any],
    ) -> str:
        if not accepted:
            return "unknown"
        if reviewed_not_accepted:
            return "uncertain"
        if (primary.get("conflict_refs")) and not superseded_ids:
            return "conflict"
        return "uncertain" if float(primary.get("confidence") or 0.5) < 0.6 else "current"

    def get(
        self,
        *,
        scope: str,
        binding: Any = None,
        task_id: Any = None,
        idempotency_key: Any = None,
    ) -> dict[str, Any]:
        """Derive one safe versioned projection for the approved scope.

        ``task_id``/``idempotency_key``/``binding`` are accepted identifiers of
        the caller only; the provider derives exclusively from the confirmed
        accepted review state bound to the adapter/ledger.
        """
        if not isinstance(scope, str) or not scope.strip():
            raise HarnessModelProjectionError("scope_required")
        if isinstance(binding, Mapping) and binding.get("scope") is not None and str(binding.get("scope")) != scope:
            raise HarnessModelProjectionError("binding_scope_mismatch")

        adapter = self.review_adapter
        candidates = getattr(adapter, "candidates", None)
        if adapter is None or not isinstance(candidates, Mapping) or not candidates:
            return self._empty_projection(scope, "no bound accepted review state is available")

        rows = self._review_feedback_rows()
        scope_candidates = [
            candidate for candidate in candidates.values()
            if isinstance(candidate, Mapping) and str(candidate.get("scope") or "") == scope
        ]
        if not scope_candidates:
            return self._empty_projection(scope, "scope has no reviewable accepted content")

        reviewed = [
            (candidate, self._effective_review_state(str(candidate.get("candidate_id") or ""), rows))
            for candidate in scope_candidates
        ]
        accepted = [
            (candidate, state) for candidate, state in reviewed
            if state["accepted"] and str(state.get("disposition") or "") != "defer_judgment"
        ]
        if not accepted:
            return self._empty_projection(scope, "scope has no confirmed accepted review content")

        reviewed_not_accepted = bool([
            item for item in reviewed
            if item[1]["ignored"] or (item[1]["review"] is not None and not item[1]["accepted"])
        ])

        # Accepted content is resolved in review order; the latest accepted
        # inference replaces the previous one (replace_existing or a plain later
        # accept), while keep_existing/coexist_by_context leave the current
        # content in place and only defer_judgment stays unprojected.
        accepted_sorted = sorted(
            accepted,
            key=lambda item: (
                str((item[1].get("review") or {}).get("recorded_at") or ""),
                int((item[1].get("review") or {}).get("version") or 0),
                str(item[0].get("candidate_id") or ""),
            ),
        )
        primary: Mapping[str, Any] | None = None
        superseded_ids: list[str] = []
        for candidate, state in accepted_sorted:
            disposition = str(state.get("disposition") or "")
            if disposition == "defer_judgment":
                continue
            if primary is None:
                primary = candidate
                continue
            if disposition == "keep_existing" or disposition == "coexist_by_context":
                continue
            superseded_ids.append(str(primary["candidate_id"]))
            primary = candidate
        if primary is None:
            return self._empty_projection(scope, "scope has no projected accepted content")

        # Validate every accepted candidate through the shared normalization path.
        try:
            self._validate_accepted(accepted)
        except ProjectionError as exc:
            raise HarnessModelProjectionError(exc.code, exc.detail) from exc

        state_by_id = {str(candidate.get("candidate_id") or ""): state for candidate, state in accepted}
        primary_state = state_by_id[str(primary["candidate_id"])]
        disposition = primary_state.get("disposition")
        confidence = float(primary.get("confidence") or 0.5)
        status = self._projection_status(
            accepted=accepted,
            reviewed_not_accepted=reviewed_not_accepted,
            superseded_ids=superseded_ids,
            primary=primary,
        )

        support_refs = [str(ref) for ref in (primary.get("support_refs") or [])]
        conflict_refs = [str(ref) for ref in (primary.get("conflict_refs") or [])]
        conflicts = [
            {"ref": ref, "disposition": disposition} if disposition else {"ref": ref}
            for ref in conflict_refs
        ]
        uncertainty = [f"source:{primary.get('uncertainty') or 'accepted review derivation'}"]
        if confidence < 0.6:
            uncertainty.append("low_confidence")
        if status == "conflict":
            uncertainty.append("unresolved_conflict")
        limitations = ["derived projection; not a personal fact or stable label"]
        if reviewed_not_accepted:
            limitations.append("scope review state is not uniformly confirmed accepted; projection is not current")
        if superseded_ids:
            limitations.append("replaced accepted inference(s) recorded in supersession")
        if status == "conflict":
            limitations.append("accepted content references conflicting evidence")
        if confidence < 0.6:
            limitations.append("inference confidence is low; treat as uncertain derived context")

        version = max(1, len(accepted))
        projection_id = "projection_" + checksum({
            "scope": scope,
            "version": version,
            "candidate_ids": sorted(str(candidate.get("candidate_id") or "") for candidate, _state in accepted),
            "primary_candidate_id": str(primary["candidate_id"]),
            "valid_from": primary.get("valid_from"),
            "observed_at": primary.get("observed_at"),
            "support_refs": support_refs,
            "conflict_refs": conflict_refs,
        })[:24]
        freshness = primary.get("freshness")
        if not isinstance(freshness, Mapping):
            freshness = {}
        supersession: Any = None
        if superseded_ids:
            supersession = {
                "replaced_candidate_ids": sorted(superseded_ids),
                "current_candidate_id": str(primary["candidate_id"]),
            }

        return {
            "projection_id": projection_id,
            "version": version,
            "provenance_class": "inference",
            "scope": scope,
            "valid_from": primary.get("valid_from"),
            "valid_to": primary.get("valid_to"),
            "observed_at": primary.get("observed_at"),
            "confidence": confidence,
            "uncertainty": uncertainty,
            "freshness": dict(freshness),
            "support_refs": support_refs,
            "support_count": len(support_refs),
            "conflict_refs": conflict_refs,
            "conflict_count": len(conflict_refs),
            "conflicts": conflicts,
            "supersession": supersession,
            "limitations": limitations,
            "status": status,
        }


__all__ = [
    "MESSAGE_FIELDS",
    "SCOPE_ROW_FIELDS",
    "THREAD_METADATA_FIELDS",
    "HarnessConversationService",
    "HarnessModelProjectionError",
    "HarnessModelProjectionProvider",
    "MAX_LIMIT",
]
