"""D-17 consumers select the active v2 projection without deleting legacy rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge import delta_build, eligibility
from personal_knowledge.core.conversation_repository import (
    SOURCE_CANONICAL,
    ConversationRepository,
)
from personal_knowledge.services.harness_conversation_service import (
    HarnessConversationService,
)


class _Freshness:
    def to_dict(self) -> dict:
        return {
            "overall_status": "current",
            "source_to_agentsview": {"status": "current"},
            "agentsview_to_canonical": {"status": "current"},
        }


def _coexist_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE canonical_sessions (
                canonical_session_id TEXT PRIMARY KEY, primary_source TEXT,
                agent TEXT, started_at TEXT, ended_at TEXT,
                message_count INTEGER, user_message_count INTEGER,
                file_hash TEXT, parent_canonical_id TEXT,
                relationship_type TEXT, cwd TEXT, git_branch TEXT, model TEXT,
                evidence_eligible INTEGER, evidence_scope TEXT, merged INTEGER,
                lifecycle TEXT, superseded_by_canonical_id TEXT
            );
            CREATE TABLE canonical_messages (
                canonical_message_id TEXT PRIMARY KEY,
                canonical_session_id TEXT, source TEXT,
                source_message_ref TEXT, ordinal INTEGER, role TEXT,
                content TEXT, content_length INTEGER, timestamp TEXT,
                model TEXT, is_system INTEGER, is_sidechain INTEGER,
                content_hash TEXT, evidence_scope TEXT
            );
            CREATE TABLE canonical_tool_events (
                canonical_tool_id TEXT PRIMARY KEY,
                canonical_session_id TEXT, source TEXT, source_kind TEXT,
                tool_name TEXT, category TEXT, status TEXT, input TEXT,
                output TEXT, tool_use_ordinal INTEGER, evidence_scope TEXT
            );
            CREATE TABLE ce_generation_authority (
                generation_id TEXT PRIMARY KEY, active INTEGER, updated_at TEXT
            );
            """
        )
        con.executemany(
            "INSERT INTO canonical_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "legacy-session", "legacy", "codex", "2026-08-01", None,
                    1, 1, None, None, None, "/legacy", None, None, 1, "user",
                    0, "active", None,
                ),
                (
                    "v2|gen-active|session", "agentsview", "chatgpt",
                    "2026-08-02", None, 1, 1, None, None, None, "/v2", None,
                    None, 1, "user", 0, "active", None,
                ),
            ),
        )
        legacy_body = "legacy message body long enough for eligibility but not active"
        v2_body = "active v2 message body long enough for eligibility and consumers"
        con.executemany(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    "legacy-message", "legacy-session", "legacy", "legacy:1",
                    1, "user", legacy_body, len(legacy_body),
                    "2026-08-03T00:00:00Z", None, 0, 0, "legacy-hash", "user",
                ),
                (
                    "v2|gen-active|message", "v2|gen-active|session",
                    "agentsview", "v2:1", 1, "user", v2_body, len(v2_body),
                    "2026-08-02T00:00:00Z", None, 0, 0, "v2-hash", "user",
                ),
            ),
        )
        con.execute(
            "INSERT INTO ce_generation_authority VALUES "
            "('gen-active', 1, '2026-08-15T00:00:00Z')"
        )
        con.commit()
    finally:
        con.close()
    return path


def _harness(db: Path) -> HarnessConversationService:
    return HarnessConversationService(
        repository=ConversationRepository(
            source=SOURCE_CANONICAL, canonical_db=db, legacy_db=db,
        ),
        freshness_provider=_Freshness,
    )


def test_active_v2_scope_is_shared_by_knowledge_and_harness_consumers(
    tmp_path: Path,
) -> None:
    db = _coexist_db(tmp_path / "coexist.sqlite")

    items, _stats = eligibility.compute_eligible_messages(db)
    assert [item.evidence_ref for item in items] == ["v2|gen-active|message"]
    eligibility_checksum = eligibility.compute_source_checksum(db)
    delta_checksum = delta_build.compute_source_checksum(db)

    service = _harness(db)
    assert service.thread_last()["data"]["conversation_id"] == (
        "v2|gen-active|session"
    )
    assert service.thread_select(conversation_id="legacy-session")["error"][
        "code"
    ] == "conversation_unknown"

    con = sqlite3.connect(db)
    try:
        con.execute(
            "UPDATE canonical_messages SET content='changed legacy body' "
            "WHERE canonical_message_id='legacy-message'"
        )
        con.commit()
    finally:
        con.close()
    assert eligibility.compute_source_checksum(db) == eligibility_checksum
    assert delta_build.compute_source_checksum(db) == delta_checksum


def test_no_active_authority_keeps_legacy_compatibility_reads(tmp_path: Path) -> None:
    db = _coexist_db(tmp_path / "legacy-visible.sqlite")
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE ce_generation_authority SET active=0")
        con.commit()
    finally:
        con.close()

    items, _stats = eligibility.compute_eligible_messages(db)
    assert {item.evidence_ref for item in items} == {
        "legacy-message", "v2|gen-active|message",
    }
    assert _harness(db).thread_last()["data"]["conversation_id"] == (
        "legacy-session"
    )
