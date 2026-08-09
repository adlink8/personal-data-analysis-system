"""Plan 61-05 Task 1 RED contract: canonical conversation/project-scope projection.

Python canonical authority is the sole source for safe `conversation.thread.last`
/ `conversation.thread.recent` / `conversation.thread.select`,
`conversation.project_scopes.list` and `conversation.project_scope.select`.
The Kernel Session store owns only new empty-session metadata; it never writes
canonical bodies. Every list/select response is metadata-only and read-only.

Selected `ConversationThreadView` messages are normalized user/assistant display
messages with stable message ID, role, display text, created time,
source/evidence ref, pagination/truncation and freshness. Thinking, raw Tool
bodies, `input_json`, provider bodies, credentials and private diagnostics never
appear; foreign/legacy/live-AgentsView sources and unknown/foreign/stale scopes
are rejected or safe-stated. Only IDs/counts/checksums/status may reach
receipt/log/telemetry fixtures, and selected-thread text never leaves the safe
ephemeral projection boundary.

Implementation target (Plan 61-05 Task 2):
    src/personal_knowledge/services/harness_conversation_service.py
      HarnessConversationService(*, repository, freshness_provider,
                                 telemetry=None)
        .thread_last(*, limit=20) -> dict
        .thread_recent(*, limit=20, cursor=None) -> dict
        .thread_select(*, conversation_id, limit=20, after=None) -> dict
        .project_scopes_list() -> dict
        .project_scope_select(*, project_scope_id, limit=20, after=None) -> dict
    freshness_provider: callable returning a DualFreshness (harness_freshness).

Project scopes are derived deterministically from canonical session working
directories (`canonical_sessions.cwd`): one scope per distinct working
directory, label = directory basename. This fixture models `/work/alpha` and
`/work/beta`. Do not use live data/ or var/ databases.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.adapters.agentsview import REQUIRED_TABLES, SourceProbe  # noqa: E402
from personal_knowledge.core.conversation_repository import (  # noqa: E402
    ConversationRepository,
    SOURCE_CANONICAL,
    SOURCE_LEGACY,
)

try:  # RED until Plan 61-05 Task 2 creates both modules.
    from personal_knowledge.application.conversation.harness_freshness import (  # noqa: F401
        project_freshness,
    )
    from personal_knowledge.services.harness_conversation_service import (  # noqa: F401
        HarnessConversationService,
    )
    _HARNESS_SERVICE_AVAILABLE = True
    _HARNESS_SERVICE_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # expected RED: modules not implemented yet
    _HARNESS_SERVICE_AVAILABLE = False
    _HARNESS_SERVICE_IMPORT_ERROR = exc


def _require_service() -> None:
    if not _HARNESS_SERVICE_AVAILABLE:
        pytest.fail(
            "RED: harness_conversation_service.py / harness_freshness.py missing "
            f"(expected for 61-05 Task 1 RED): {_HARNESS_SERVICE_IMPORT_ERROR}",
            pytrace=False,
        )


# ---------------------------------------------------------------------------
# Deterministic fixtures
# ---------------------------------------------------------------------------

SENTINELS = {
    "thinking": "PRIVATE_THINKING_SENTINEL_2c7f0a",
    "tool": "PRIVATE_TOOL_BODY_SENTINEL_6a1d3b",
    "toolInput": "PRIVATE_TOOL_INPUT_SENTINEL_7d2b4e",
    "prompt": "PRIVATE_PROMPT_SENTINEL_9f3a1c",
    "completion": "PRIVATE_COMPLETION_SENTINEL_3e6f0b",
    "credential": "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
    "secret": "PRIVATE_SECRET_SENTINEL_1b5e7c",
}
# Visible normalized display text must appear in the selected thread but must
# never reach telemetry, the service object state, or any other boundary.
DISPLAY_MARKERS = (
    "alpha-2-user-1",
    "alpha-2-assistant-1",
    "alpha-1-user-1",
    "alpha-1-assistant-1",
    "beta-1-user-1",
    "beta-1-assistant-1",
)
FORBIDDEN_KEYS = ("body", "content", "prompt", "completion", "credential", "secret")

ALPHA_1 = "codex:alpha-2026-08-08"
ALPHA_2 = "codex:alpha-2026-08-09"
ALPHA_EMPTY = "codex:alpha-empty"
BETA_1 = "codex:beta-2026-08-09"

_CANONICAL_SESSIONS_COLS = (
    "canonical_session_id", "primary_source", "agent", "started_at", "ended_at",
    "message_count", "user_message_count", "file_hash", "parent_canonical_id",
    "relationship_type", "cwd", "git_branch", "model", "evidence_eligible",
    "evidence_scope", "merged", "lifecycle", "superseded_by_canonical_id",
)
_CANONICAL_MESSAGES_COLS = (
    "canonical_message_id", "canonical_session_id", "source", "source_message_ref",
    "ordinal", "role", "content", "content_length", "timestamp", "model",
    "is_system", "is_sidechain", "content_hash", "evidence_scope",
)


def _make_canonical_db(dest: Path) -> Path:
    con = sqlite3.connect(str(dest))
    con.execute(
        f"CREATE TABLE canonical_sessions ({', '.join(c + ' TEXT' for c in _CANONICAL_SESSIONS_COLS)})"
    )
    con.execute(
        f"CREATE TABLE canonical_messages ({', '.join(c + ' TEXT' for c in _CANONICAL_MESSAGES_COLS)})"
    )

    def _session(session_id: str, started: str, ended: str | None, count: int, cwd: str) -> tuple:
        return (
            session_id, "agentsview", "codex", started, ended, count,
            1 if count else 0, f"fh-{session_id.split(':')[-1]}", None, "main",
            cwd, "main", "gpt-4o", 1, "user", 0, "active", None,
        )

    sessions = [
        _session(ALPHA_1, "2026-08-08T09:00:00Z", "2026-08-08T09:30:00Z", 2, "/work/alpha"),
        _session(ALPHA_2, "2026-08-09T08:00:00Z", "2026-08-09T08:20:00Z", 2, "/work/alpha"),
        _session(ALPHA_EMPTY, "2026-08-09T06:00:00Z", None, 0, "/work/alpha"),
        _session(BETA_1, "2026-08-09T07:00:00Z", "2026-08-09T07:15:00Z", 4, "/work/beta"),
    ]
    con.executemany(
        f"INSERT INTO canonical_sessions VALUES ({','.join('?' for _ in _CANONICAL_SESSIONS_COLS)})",
        sessions,
    )

    def _message(message_id: str, session_id: str, ordinal: int, role: str, content: str, ts: str) -> tuple:
        return (
            message_id, session_id, "agentsview", f"av:{message_id}", ordinal, role,
            content, len(content), ts, "gpt-4o", 0, 0, f"h-{message_id}", "user",
        )

    messages = [
        _message("cm-a1-1", ALPHA_1, 1, "user", "alpha-1-user-1", "2026-08-08T09:00:00Z"),
        _message("cm-a1-2", ALPHA_1, 2, "assistant", "alpha-1-assistant-1", "2026-08-08T09:05:00Z"),
        _message("cm-a1-3", ALPHA_1, 3, "tool", SENTINELS["tool"], "2026-08-08T09:06:00Z"),
        _message("cm-a1-4", ALPHA_1, 4, "system", SENTINELS["secret"], "2026-08-08T09:07:00Z"),
        _message("cm-a2-1", ALPHA_2, 1, "user", "alpha-2-user-1", "2026-08-09T08:05:00Z"),
        _message("cm-a2-2", ALPHA_2, 2, "assistant", "alpha-2-assistant-1", "2026-08-09T08:10:00Z"),
        _message("cm-b1-1", BETA_1, 1, "user", "beta-1-user-1", "2026-08-09T07:00:00Z"),
        _message("cm-b1-2", BETA_1, 2, "assistant", "beta-1-assistant-1", "2026-08-09T07:05:00Z"),
        _message("cm-b1-3", BETA_1, 3, "developer", SENTINELS["thinking"], "2026-08-09T07:06:00Z"),
        _message("cm-b1-4", BETA_1, 4, "tool", SENTINELS["toolInput"], "2026-08-09T07:07:00Z"),
    ]
    con.executemany(
        f"INSERT INTO canonical_messages VALUES ({','.join('?' for _ in _CANONICAL_MESSAGES_COLS)})",
        messages,
    )
    con.commit()
    con.close()
    return dest


def _make_probe() -> SourceProbe:
    return SourceProbe(
        source_path="/tmp/fixture/agentsview_sessions.db",
        integrity_check="ok",
        user_version=1,
        journal_mode="wal",
        table_count=len(REQUIRED_TABLES),
        required_tables_present=list(REQUIRED_TABLES),
        required_tables_missing=[],
        missing_columns={},
        counts={"sessions": 4, "messages": 10},
    )


NOW = "2026-08-09T08:30:00Z"
STALE_AFTER_SECONDS = 1800


def _freshness_provider(
    *,
    source_watermark: str | None = "2026-08-09T07:00:00Z",
    canonical_watermark: str | None = "2026-08-09T08:10:00Z",
    source_backlog: int = 0,
    canonical_backlog: int = 0,
) -> Callable[[], Any]:
    def _provider():
        _require_service()
        return project_freshness(
            source_probe=_make_probe(),
            source_watermark=source_watermark,
            source_backlog=source_backlog,
            canonical_watermark=canonical_watermark,
            canonical_backlog=canonical_backlog,
            now=NOW,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    return _provider


def _make_service(
    tmp_path: Path,
    *,
    telemetry: Callable[[dict], None] | None = None,
    repository: ConversationRepository | None = None,
    **freshness_kwargs,
):
    _require_service()
    db = _make_canonical_db(tmp_path / "canonical.sqlite")
    repo = repository or ConversationRepository(source=SOURCE_CANONICAL, canonical_db=db)
    return HarnessConversationService(
        repository=repo,
        freshness_provider=_freshness_provider(**freshness_kwargs),
        telemetry=telemetry,
    )


def _walk_private(node, path, errors):
    if node is None:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if any(fragment in key.lower() for fragment in FORBIDDEN_KEYS):
                errors.append(f"forbidden key {key!r} at {path}")
            _walk_private(value, f"{path}.{key}", errors)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_private(value, f"{path}[{index}]", errors)
    elif isinstance(node, str):
        for name, sentinel in SENTINELS.items():
            if sentinel in node:
                errors.append(f"sentinel {name!r} leaked at {path}")
        for marker in DISPLAY_MARKERS:
            if marker in node:
                errors.append(f"display text marker leaked at {path}: {marker!r}")


def _assert_no_private(value, label: str) -> None:
    errors: list[str] = []
    _walk_private(value, label, errors)
    assert not errors, f"{label} leaked private data: " + "; ".join(errors)


def _assert_two_leg_freshness(freshness) -> None:
    assert isinstance(freshness, dict)
    assert "source_to_agentsview" in freshness and "agentsview_to_canonical" in freshness, (
        "responses must carry both freshness legs, never one number"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_service_requires_canonical_source_only(tmp_path: Path):
    """legacy/live sources are rejected: canonical is the sole thread authority."""
    _require_service()
    db = _make_canonical_db(tmp_path / "legacy.db")
    legacy_repo = ConversationRepository(source=SOURCE_LEGACY, legacy_db=db, canonical_db=db)
    with pytest.raises(ValueError):
        HarnessConversationService(
            repository=legacy_repo,
            freshness_provider=_freshness_provider(),
        )


def test_thread_last_resolves_from_canonical_only(tmp_path: Path):
    service = _make_service(tmp_path)
    result = service.thread_last()
    assert result["ok"] is True
    view = result["data"]
    assert view["conversation_id"] == ALPHA_2, "last conversation must be the most recently active canonical session"
    assert view["project_scope_id"] == "/work/alpha"
    assert {m["role"] for m in view["messages"]} <= {"user", "assistant"}
    for message in view["messages"]:
        assert set(message) == {
            "message_id", "role", "display_text", "created_at", "source_ref", "evidence_ref",
        }, "selected message fields are fixed and stable"
        assert message["display_text"] in DISPLAY_MARKERS
        assert message["created_at"]
        assert message["source_ref"]
        assert message["evidence_ref"]
    assert "pagination" in view and view["pagination"]["limit"] >= 1
    assert isinstance(view["truncated"], bool)
    _assert_two_leg_freshness(view["freshness"])
    assert view["state"] in {"current", "stale", "unknown", "empty", "partial"}
    assert isinstance(view["limitation"], str) and view["limitation"]
    _assert_no_private(result, "thread_last")


def test_thread_recent_returns_metadata_only(tmp_path: Path):
    service = _make_service(tmp_path)
    result = service.thread_recent(limit=10)
    assert result["ok"] is True
    recent = result["data"]
    ids = [item["conversation_id"] for item in recent["conversations"]]
    assert ids == [ALPHA_2, BETA_1, ALPHA_1], "recent conversations sort by last activity desc"
    for item in recent["conversations"]:
        assert set(item) <= {
            "conversation_id", "project_scope_id", "label", "last_activity_at", "message_count",
        }, "recent list is metadata-only"
        assert all(
            key not in item for key in ("display_text", "content", "messages")
        )
    assert "pagination" in recent and recent["pagination"]["limit"] >= 1
    _assert_two_leg_freshness(recent["freshness"])
    _assert_no_private(result, "thread_recent")


def test_thread_select_normalizes_user_assistant_only(tmp_path: Path):
    """tool/developer/system messages (with sentinels) never enter the view."""
    service = _make_service(tmp_path)
    result = service.thread_select(conversation_id=BETA_1, limit=20)
    assert result["ok"] is True
    view = result["data"]
    assert view["conversation_id"] == BETA_1
    roles = [m["role"] for m in view["messages"]]
    assert roles == ["user", "assistant"], "only normalized user/assistant messages are projected"
    assert [m["display_text"] for m in view["messages"]] == ["beta-1-user-1", "beta-1-assistant-1"]
    for message in view["messages"]:
        assert set(message) == {
            "message_id", "role", "display_text", "created_at", "source_ref", "evidence_ref",
        }
    _assert_no_private(result, "thread_select")


def test_thread_select_pagination_stable_ids(tmp_path: Path):
    """Pagination preserves stable message/source/evidence identity across pages."""
    service = _make_service(tmp_path)
    page1 = service.thread_select(conversation_id=ALPHA_2, limit=1, after=None)
    assert page1["ok"] is True
    view1 = page1["data"]
    assert [m["message_id"] for m in view1["messages"]] == ["cm-a2-1"]
    assert view1["pagination"]["has_more"] is True
    assert view1["pagination"]["cursor"] is not None, "a cursor must be returned when more exist"
    cursor = view1["pagination"]["cursor"]

    page2 = service.thread_select(conversation_id=ALPHA_2, limit=1, after=cursor)
    assert page2["ok"] is True
    view2 = page2["data"]
    assert [m["message_id"] for m in view2["messages"]] == ["cm-a2-2"]
    assert view2["pagination"]["has_more"] is False
    assert view1["messages"][0]["message_id"] not in {
        m["message_id"] for m in view2["messages"]
    }, "pages must not overlap"
    assert view1["messages"][0]["source_ref"] == "av:cm-a2-1"
    assert view2["messages"][0]["source_ref"] == "av:cm-a2-2"
    assert view1["messages"][0]["evidence_ref"] != view2["messages"][0]["evidence_ref"]
    _assert_no_private(page2, "thread_select page2")


def test_thread_select_truncation_and_partial_state(tmp_path: Path):
    service = _make_service(tmp_path)
    truncated = service.thread_select(conversation_id=ALPHA_2, limit=1, after=None)
    assert truncated["ok"] is True
    assert truncated["data"]["truncated"] is True
    assert truncated["data"]["pagination"]["has_more"] is True
    full = service.thread_select(conversation_id=ALPHA_2, limit=20, after=None)
    assert full["data"]["truncated"] is False
    assert full["data"]["pagination"]["has_more"] is False
    assert isinstance(full["data"]["limitation"], str) and full["data"]["limitation"]


def test_thread_select_empty_is_explicit(tmp_path: Path):
    """An empty canonical thread is an explicit empty state, never current/history."""
    service = _make_service(tmp_path)
    result = service.thread_select(conversation_id=ALPHA_EMPTY, limit=20)
    assert result["ok"] is True
    view = result["data"]
    assert view["messages"] == []
    assert view["state"] == "empty"
    assert isinstance(view["limitation"], str) and view["limitation"]
    _assert_no_private(result, "thread_select empty")


def test_project_scopes_list_returns_only_allowlisted_fields(tmp_path: Path):
    service = _make_service(tmp_path)
    result = service.project_scopes_list()
    assert result["ok"] is True
    data = result["data"]
    by_label = {item["label"]: item for item in data["scopes"]}
    assert set(by_label) == {"alpha", "beta"}
    alpha = by_label["alpha"]
    assert set(alpha) == {
        "project_scope_id", "label", "thread_count", "last_activity_at", "freshness",
    }, "scope rows expose only the allowlisted metadata fields"
    assert alpha["thread_count"] == 3, "alpha has 3 canonical sessions"
    assert alpha["last_activity_at"] == "2026-08-09T08:10:00Z"
    _assert_two_leg_freshness(alpha["freshness"])
    beta = by_label["beta"]
    assert beta["thread_count"] == 1
    assert beta["last_activity_at"] == "2026-08-09T07:05:00Z"
    assert data["state"] in {"current", "stale", "unknown"}
    assert isinstance(data["limitation"], str) and data["limitation"]
    _assert_no_private(result, "project_scopes_list")


def test_project_scope_select_is_read_only_no_canonical_mutation(tmp_path: Path):
    service = _make_service(tmp_path)
    db_bytes_before = (tmp_path / "canonical.sqlite").read_bytes()
    result = service.project_scope_select(project_scope_id="/work/alpha", limit=10)
    assert result["ok"] is True
    db_bytes_after = (tmp_path / "canonical.sqlite").read_bytes()
    assert db_bytes_before == db_bytes_after, "project_scope.select must never mutate canonical data"
    _assert_no_private(result, "project_scope_select")


def test_project_scope_select_paginated_stable_thread_ids(tmp_path: Path):
    service = _make_service(tmp_path)
    page1 = service.project_scope_select(project_scope_id="/work/alpha", limit=1, after=None)
    assert page1["ok"] is True
    data1 = page1["data"]
    assert data1["project_scope_id"] == "/work/alpha"
    assert data1["label"] == "alpha"
    assert [t["conversation_id"] for t in data1["threads"]] == [ALPHA_2]
    assert data1["pagination"]["has_more"] is True
    assert data1["pagination"]["cursor"] is not None
    for thread in data1["threads"]:
        assert set(thread) == {"conversation_id", "label", "last_activity_at", "message_count"}

    page2 = service.project_scope_select(
        project_scope_id="/work/alpha", limit=1, after=data1["pagination"]["cursor"]
    )
    assert page2["ok"] is True
    assert [t["conversation_id"] for t in page2["data"]["threads"]] == [ALPHA_1]
    assert page2["data"]["pagination"]["has_more"] is False
    assert data1["threads"][0]["conversation_id"] not in {
        t["conversation_id"] for t in page2["data"]["threads"]
    }, "scope pages must not overlap and IDs stay stable"
    _assert_two_leg_freshness(page2["data"]["freshness"])


def test_unknown_and_foreign_scope_are_rejected(tmp_path: Path):
    """Unknown/foreign project scopes are rejected, never silently accepted."""
    service = _make_service(tmp_path)
    unknown = service.project_scope_select(project_scope_id="scope:definitely-missing", limit=10)
    assert unknown["ok"] is False, "unknown scope must be rejected"
    assert unknown["status"] == "error"
    assert unknown["error"]["code"] in {"unknown_scope", "foreign_scope"}
    foreign = service.project_scope_select(project_scope_id="project:/other/team", limit=10)
    assert foreign["ok"] is False, "foreign scope must be rejected"
    assert foreign["error"]["code"] in {"unknown_scope", "foreign_scope"}
    _assert_no_private(unknown, "unknown scope envelope")
    _assert_no_private(foreign, "foreign scope envelope")


def test_stale_scope_is_safe_stated_not_current(tmp_path: Path):
    """A stale canonical leg makes the selected scope stale, never current."""
    service = _make_service(tmp_path, canonical_watermark="2026-08-09T06:00:00Z")
    result = service.project_scope_select(project_scope_id="/work/alpha", limit=10)
    assert result["ok"] is True
    data = result["data"]
    assert data["state"] == "stale", "stale canonical leg must surface as stale"
    leg = data["freshness"]["agentsview_to_canonical"]
    assert leg["status"] == "stale"
    assert "stale" in data["limitation"].lower()
    _assert_no_private(result, "stale scope")


def test_no_live_agentsview_database_is_referenced(tmp_path: Path):
    """The live AgentsView DB path never leaks into any projection response."""
    from personal_knowledge.core.project_paths import AGENTSVIEW_DB  # noqa: PLC0415

    service = _make_service(tmp_path)
    responses = [
        service.thread_last(),
        service.thread_recent(limit=5),
        service.thread_select(conversation_id=ALPHA_2, limit=5),
        service.project_scopes_list(),
        service.project_scope_select(project_scope_id="/work/alpha", limit=5),
    ]
    live_path = str(AGENTSVIEW_DB).replace("\\", "/")
    for response in responses:
        assert live_path not in json.dumps(response), "live AgentsView DB path must never be exposed"


def test_telemetry_receives_ids_counts_checksums_status_only(tmp_path: Path):
    """Receipt/log/telemetry fixtures receive no display text or private payload."""
    recorder: list[dict] = []
    service = _make_service(tmp_path, telemetry=recorder.append)
    service.thread_select(conversation_id=BETA_1, limit=5)
    service.project_scope_select(project_scope_id="/work/alpha", limit=5)
    assert recorder, "the service must emit telemetry records for navigation reads"
    payload = json.dumps(recorder)
    for marker in DISPLAY_MARKERS:
        assert marker not in payload, f"telemetry received display text marker {marker!r}"
    for sentinel in SENTINELS.values():
        assert sentinel not in payload, "telemetry received a private sentinel"
    _assert_no_private(recorder, "telemetry records")


def test_selected_thread_text_never_retained_outside_ephemeral_boundary(tmp_path: Path):
    """Selected-thread display text exists only in the returned view model."""
    service = _make_service(tmp_path)
    service.thread_select(conversation_id=ALPHA_2, limit=5)
    service.thread_select(conversation_id=BETA_1, limit=5)
    state = str(vars(service))
    for marker in DISPLAY_MARKERS:
        assert marker not in state, f"service retained display text {marker!r}"
    for sentinel in SENTINELS.values():
        assert sentinel not in state, "service retained a private sentinel"


def test_thread_select_source_and_evidence_refs_are_stable(tmp_path: Path):
    """source_ref and evidence_ref are present and stable across calls."""
    service = _make_service(tmp_path)
    first = service.thread_select(conversation_id=ALPHA_2, limit=5)["data"]["messages"]
    second = service.thread_select(conversation_id=ALPHA_2, limit=5)["data"]["messages"]
    assert first == second, "repeat selects return identical stable message identity"
    by_id = {m["message_id"]: m for m in first}
    assert by_id["cm-a2-1"]["source_ref"] == "av:cm-a2-1"
    assert by_id["cm-a2-2"]["source_ref"] == "av:cm-a2-2"
