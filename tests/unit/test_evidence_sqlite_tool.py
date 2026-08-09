"""Phase 61 Wave 0: bounded evidence SQLite Tool - descriptor/query policy unit tests.

HARNESS-03 / R-61-03 / R-61-04. Pure validation and deterministic derivation
without touching a database. Physical-schema leakage, tampering, lease drift,
privacy-ceiling mismatch and hostile values must all fail closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.evidence_sqlite_tool import (
    DATABASE_ID,
    DESCRIPTOR_VERSION,
    EVIDENCE_MESSAGES_PARAMETERS,
    EVIDENCE_SQLITE_OPERATION,
    EVIDENCE_SQLITE_RECEIPT_SCHEMA,
    EVIDENCE_SQLITE_SCHEMA,
    LEASE_SKILL_ID,
    MAX_BYTES,
    MAX_ROWS,
    PRIVACY_CEILING,
    QUERY_ID,
    TIMEOUT_MS,
    EvidenceSqliteError,
    EvidenceSqliteTool,
    derive_statement_display,
    knowledge_research_checksum,
    query_checksum,
)


def _valid_descriptor(**overrides: object) -> dict:
    base: dict = {
        "database_id": DATABASE_ID,
        "query_id": QUERY_ID,
        "version": DESCRIPTOR_VERSION,
        "parameters": {"session_id": "codex:session-123", "after": "2026-08-01T00:00:00Z", "limit": 10},
        "scope": {"session_id": "codex:session-123"},
        "binding": "binding-1",
        "skill_id": LEASE_SKILL_ID,
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
    }
    base.update(overrides)
    return base


def _tool() -> EvidenceSqliteTool:
    return EvidenceSqliteTool(db_path=Path("__nonexistent_fixture_for_validation_only__"))


# ---------------------------------------------------------------------------
# Deterministic server-derived statement_display and checksum binding
# ---------------------------------------------------------------------------


def test_statement_display_is_deterministic_and_uses_approved_descriptor_only() -> None:
    display = derive_statement_display(QUERY_ID, EVIDENCE_MESSAGES_PARAMETERS)
    assert display == "conversation.evidence_messages.v1(session_id, after, limit)"
    assert display == derive_statement_display(QUERY_ID, EVIDENCE_MESSAGES_PARAMETERS)  # deterministic
    assert display.count(QUERY_ID) == 1


def test_statement_display_never_contains_physical_schema_or_values() -> None:
    display = derive_statement_display(QUERY_ID, EVIDENCE_MESSAGES_PARAMETERS)
    lower = display.lower()
    for fragment in (
        "select", "from", "where", "join", "insert", "update", "delete", "drop",
        "alter", "attach", "pragma", "canonical_messages", "canonical_sessions",
        "session_source_links", "canonical_tool_events", "sqlite_master",
        "codex:session-123", "2026-08-01T00:00:00Z",
    ):
        assert fragment not in lower, f"physical schema/value leaked into display: {fragment}"
    assert ";" not in display and "--" not in display


def test_query_checksum_binds_display_query_id_version_and_name_set() -> None:
    display = derive_statement_display(QUERY_ID, EVIDENCE_MESSAGES_PARAMETERS)
    base = query_checksum(
        query_id=QUERY_ID, version=DESCRIPTOR_VERSION,
        parameter_names=EVIDENCE_MESSAGES_PARAMETERS, statement_display=display,
    )
    assert len(base) == 64
    # tamper each bound component -> checksum changes
    assert base != query_checksum(
        query_id=QUERY_ID, version=DESCRIPTOR_VERSION,
        parameter_names=EVIDENCE_MESSAGES_PARAMETERS, statement_display=display + " (tampered)",
    )
    assert base != query_checksum(
        query_id="conversation.evidence_messages.v2", version=DESCRIPTOR_VERSION,
        parameter_names=EVIDENCE_MESSAGES_PARAMETERS, statement_display=display,
    )
    assert base != query_checksum(
        query_id=QUERY_ID, version="1.0.1",
        parameter_names=EVIDENCE_MESSAGES_PARAMETERS, statement_display=display,
    )
    assert base != query_checksum(
        query_id=QUERY_ID, version=DESCRIPTOR_VERSION,
        parameter_names=("limit", "session_id"), statement_display=display,
    )
    # parameter-name set is canonicalized (sorted) before binding
    assert base == query_checksum(
        query_id=QUERY_ID, version=DESCRIPTOR_VERSION,
        parameter_names=("limit", "session_id", "after"), statement_display=display,
    )


def test_caller_supplied_statement_display_override_is_rejected() -> None:
    descriptor = _valid_descriptor(statement_display="attacker.com/sql")
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code == "undeclared_input"


# ---------------------------------------------------------------------------
# Approved descriptor / lease / privacy policy (fail closed before execution)
# ---------------------------------------------------------------------------


def test_approved_descriptor_passes_policy_validation_before_db_access() -> None:
    # Policy validation must be reached before any DB open; the fixture path
    # does not exist, so reaching execution would raise database_unavailable.
    descriptor = _valid_descriptor()
    try:
        _tool().invoke(descriptor)
    except EvidenceSqliteError as exc:
        assert exc.code != "database_unavailable"
        pytest.fail(f"policy validation rejected an approved descriptor: {exc.code}")


def test_unknown_query_id_rejected() -> None:
    descriptor = _valid_descriptor(query_id="INSERT INTO canonical_messages VALUES (1)")
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code in {"unknown_query", "sql_forbidden"}


def test_unknown_database_id_or_path_tamper_rejected() -> None:
    for tampered in ("/etc/passwd", "../../var/db/personal_system.sqlite", "unknown_database_v9"):
        with pytest.raises(EvidenceSqliteError) as exc:
            _tool().invoke(_valid_descriptor(database_id=tampered))
        assert exc.value.code == "database_unknown"


def test_version_mismatch_rejected() -> None:
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(_valid_descriptor(version="9.9.9"))
    assert exc.value.code == "version_mismatch"


def test_absent_or_foreign_lease_rejected_before_execution() -> None:
    for overrides in (
        {"skill_id": None},
        {"skill_id": "system.diagnosis"},
        {"skill_id": "snapshot.release"},
        {"skill_id": "personal.daily_brief"},
    ):
        descriptor = _valid_descriptor(**overrides)
        with pytest.raises(EvidenceSqliteError) as exc:
            _tool().invoke(descriptor)
        assert exc.value.code == "lease_invalid"


def test_supporting_skill_recursion_rejected() -> None:
    descriptor = _valid_descriptor(supporting_skills=["knowledge.maintenance"])
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code == "supporting_skill_rejected"


def test_stale_or_foreign_manifest_checksum_rejected() -> None:
    descriptor = _valid_descriptor(manifest_checksum="0" * 64)
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code == "manifest_drift"


def test_privacy_ceiling_mismatch_rejected() -> None:
    for ceiling in ("R0", "R2"):
        descriptor = _valid_descriptor(privacy_ceiling=ceiling)
        with pytest.raises(EvidenceSqliteError) as exc:
            _tool().invoke(descriptor)
        assert exc.value.code == "privacy_ceiling_mismatch"


def test_missing_binding_rejected_at_adapter() -> None:
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(_valid_descriptor(binding=None))
    assert exc.value.code == "binding_required"


def test_undeclared_and_callable_inputs_rejected() -> None:
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(_valid_descriptor(extra_field="x"))
    assert exc.value.code == "undeclared_input"
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(_valid_descriptor(parameters=lambda: None))
    assert exc.value.code == "descriptor_invalid"


# ---------------------------------------------------------------------------
# Typed parameter validation and hostile values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parameters",
    [
        {"session_id": "codex:s", "after": "2026-08-01T00:00:00Z", "limit": 10, "evil": "x"},
        {"after": "2026-08-01T00:00:00Z", "limit": 10},  # missing session_id
        {"session_id": 42, "after": "2026-08-01T00:00:00Z", "limit": 10},  # wrong type
        {"session_id": "codex:s", "after": 42, "limit": 10},
        {"session_id": "codex:s", "after": "2026-08-01T00:00:00Z", "limit": True},
        {"session_id": "codex:s", "after": "2026-08-01T00:00:00Z", "limit": 0},
        {"session_id": "codex:s", "after": "2026-08-01T00:00:00Z", "limit": 51},
        {"session_id": "../secret", "after": "2026-08-01T00:00:00Z", "limit": 10},
        {"session_id": "a b c", "after": "2026-08-01T00:00:00Z", "limit": 10},
    ],
)
def test_typed_parameter_violations_rejected(parameters: dict) -> None:
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(_valid_descriptor(parameters=parameters))
    assert exc.value.code in {"parameter_invalid", "path_forbidden", "limit_exceeded"}


@pytest.mark.parametrize(
    "value",
    [
        "codex:s; DROP TABLE canonical_messages",
        "codex:s -- comment",
        "INSERT INTO canonical_messages VALUES (1)",
        "UPDATE canonical_messages SET content='x'",
        "DELETE FROM canonical_messages",
        "ATTACH DATABASE '/etc/passwd' AS x",
        "SELECT load_extension('lib.so')",
        "PRAGMA journal_mode=WAL",
        "PRAGMA query_only=OFF",
        "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
    ],
)
def test_hostile_sql_fragments_in_parameters_rejected(value: str) -> None:
    descriptor = _valid_descriptor(parameters={
        "session_id": "codex:s", "after": value, "limit": 10,
    })
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code == "sql_forbidden"


def test_hostile_scope_rejected() -> None:
    descriptor = _valid_descriptor(scope={"session_id": "codex:s; DROP TABLE x"})
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(descriptor)
    assert exc.value.code in {"sql_forbidden", "scope_denied"}
    unknown_scope = _valid_descriptor(scope={"project": "anything"})
    with pytest.raises(EvidenceSqliteError) as exc:
        _tool().invoke(unknown_scope)
    assert exc.value.code == "scope_denied"


# ---------------------------------------------------------------------------
# Receipt contract fields (static expectations shared with integration tests)
# ---------------------------------------------------------------------------


def test_receipt_contract_constants_are_locked() -> None:
    assert EVIDENCE_SQLITE_OPERATION == "evidence.sqlite_query"
    assert EVIDENCE_SQLITE_SCHEMA == "pi_evidence_sqlite_v1"
    assert EVIDENCE_SQLITE_RECEIPT_SCHEMA == "pi_evidence_sqlite_receipt_v1"
    assert QUERY_ID == "conversation.evidence_messages.v1"
    assert DESCRIPTOR_VERSION == "1.0.0"
    assert DATABASE_ID == "canonical_conversation_v1"
    assert LEASE_SKILL_ID == "knowledge.research"
    assert PRIVACY_CEILING == "R1"
    assert MAX_ROWS == 50
    assert MAX_BYTES == 16384
    assert TIMEOUT_MS == 3000
    assert tuple(sorted(EVIDENCE_MESSAGES_PARAMETERS)) == ("after", "limit", "session_id")
