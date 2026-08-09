from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_domain_gateway import (
    DEFAULT_CAPABILITY,
    OPERATIONS,
    PiDomainGateway,
)
from personal_knowledge.services.evidence_sqlite_tool import (
    DATABASE_ID,
    DESCRIPTOR_VERSION,
    EVIDENCE_SQLITE_OPERATION,
    LEASE_SKILL_ID,
    PRIVACY_CEILING,
    QUERY_ID,
    EvidenceSqliteTool,
    knowledge_research_checksum,
)


def _make_canonical_fixture(db) -> None:
    import sqlite3 as sqlite3_module

    con = sqlite3_module.connect(str(db))
    con.execute(
        """CREATE TABLE canonical_sessions (
            canonical_session_id TEXT PRIMARY KEY, primary_source TEXT, agent TEXT,
            started_at TEXT, ended_at TEXT, message_count INTEGER,
            user_message_count INTEGER, file_hash TEXT, parent_canonical_id TEXT,
            relationship_type TEXT, cwd TEXT, git_branch TEXT, model TEXT,
            evidence_eligible INTEGER NOT NULL DEFAULT 1,
            evidence_scope TEXT NOT NULL DEFAULT 'user',
            merged INTEGER NOT NULL DEFAULT 0,
            lifecycle TEXT NOT NULL DEFAULT 'active',
            superseded_by_canonical_id TEXT)"""
    )
    con.execute(
        """CREATE TABLE canonical_messages (
            canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT NOT NULL,
            source TEXT NOT NULL, source_message_ref TEXT, ordinal INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT, content_length INTEGER, timestamp TEXT,
            model TEXT, is_system INTEGER NOT NULL DEFAULT 0,
            is_sidechain INTEGER NOT NULL DEFAULT 0, content_hash TEXT,
            evidence_scope TEXT NOT NULL DEFAULT 'user')"""
    )
    con.execute(
        "INSERT INTO canonical_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "codex:gateway-session", "agentsview", "codex", "2026-08-01T00:00:00Z",
            "2026-08-01T01:00:00Z", 1, 1, "file-hash-1", None, "main", None, None,
            None, 1, "user", 0, "active", None,
        ),
    )
    con.execute(
        "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("g-1", "codex:gateway-session", "agentsview", "av:1", 1, "user",
         "redacted", 8, "2026-08-01T00:01:00Z", "gpt-4o", 0, 0, "hash-1", "user"),
    )
    con.commit()
    con.close()


def _evidence_descriptor(**overrides) -> dict:
    base: dict = {
        "database_id": DATABASE_ID,
        "query_id": QUERY_ID,
        "version": DESCRIPTOR_VERSION,
        "parameters": {"session_id": "codex:gateway-session", "after": None, "limit": 10},
        "scope": {"session_id": "codex:gateway-session"},
        "skill_id": LEASE_SKILL_ID,
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
    }
    base.update(overrides)
    return base


def test_registry_is_static_and_unknown_inputs_are_rejected():
    gateway = PiDomainGateway(capability=DEFAULT_CAPABILITY)
    assert set(OPERATIONS) >= {"domain.inspect", "domain.candidate", "session.preview", "session.confirm"}
    bad = gateway.invoke("module.call", {"task_id": "t"}, capability=DEFAULT_CAPABILITY)
    assert bad["ok"] is False and bad["error"]["code"] == "unknown_operation"
    extra = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b", "path": "secret"}, capability=DEFAULT_CAPABILITY)
    assert extra["error"]["code"] == "undeclared_input"


def test_capability_and_binding_fail_closed_without_domain_invocation():
    called = []
    gateway = PiDomainGateway(capability="cap", read_handler=lambda operation, params: called.append(operation))
    denied = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b"}, capability="wrong")
    assert denied["error"]["code"] == "capability_invalid" and called == []
    missing = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i"}, capability="cap")
    assert missing["error"]["code"] == "binding_required"


def test_read_operation_returns_safe_metadata_only():
    gateway = PiDomainGateway(capability="cap")
    result = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b"}, capability="cap")
    assert result["ok"] is True
    assert result["data"]["task_id"] == "t"
    assert "provider" not in str(result).lower()


def test_guarded_write_requires_binding_and_routes_through_interface():
    class Stub:
        def invoke(self, operation, **params):
            return {"ok": True, "operation": operation, "data": {"sequence": 1}}

    gateway = PiDomainGateway(capability="cap", service=Stub())
    result = gateway.invoke("session.preview", {"task_id": "t", "idempotency_key": "i", "binding": "b", "session_id": "s", "transition": "generate", "payload": {}, "actor_identity_hash": "a", "expected_sequence": 1, "now": "2026-08-04T00:00:00Z"}, capability="cap")
    assert result["ok"] is True


def test_evidence_sqlite_query_is_registered_static_read_operation():
    assert EVIDENCE_SQLITE_OPERATION in OPERATIONS
    spec = OPERATIONS[EVIDENCE_SQLITE_OPERATION]
    assert spec["kind"] == "read"
    assert spec["privacy"] == PRIVACY_CEILING
    # no statement_display / SQL / path / callable override can enter the map
    assert "statement_display" not in spec["allowed"]
    assert "sql" not in spec["allowed"] and "path" not in spec["allowed"]


def test_gateway_denies_foreign_lease_manifest_privacy_and_override_before_adapter():
    gateway = PiDomainGateway(capability="cap")  # no DB and no evidence_tool injected
    base = {"task_id": "t", "idempotency_key": "i", "binding": "b"}
    lease = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(skill_id="system.diagnosis")}, capability="cap")
    assert lease["ok"] is False and lease["error"]["code"] == "lease_invalid"
    drift = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(manifest_checksum="0" * 64)}, capability="cap")
    assert drift["error"]["code"] == "manifest_drift"
    privacy = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(privacy_ceiling="R0")}, capability="cap")
    assert privacy["error"]["code"] == "privacy_ceiling_mismatch"
    override = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(), "statement_display": "attacker.com/sql"}, capability="cap")
    assert override["error"]["code"] == "undeclared_input"


def test_gateway_adapter_repeats_query_id_scope_and_database_denial(tmp_path):
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db)
    gateway = PiDomainGateway(capability="cap", evidence_tool=EvidenceSqliteTool(db_path=db))
    base = {"task_id": "t", "idempotency_key": "i", "binding": "b"}
    unknown = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(query_id="DROP TABLE canonical_messages")}, capability="cap")
    assert unknown["error"]["code"] == "unknown_query"
    scope = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(scope={"project": "anything"})}, capability="cap")
    assert scope["error"]["code"] == "scope_denied"
    path = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(database_id="../../var/db/personal_system.sqlite")}, capability="cap")
    assert path["error"]["code"] == "database_unknown"
    binding = gateway.invoke(EVIDENCE_SQLITE_OPERATION, {**base, **_evidence_descriptor(), "binding": None}, capability="cap")
    assert binding["error"]["code"] == "binding_required"


def test_gateway_routes_evidence_success_with_capability_checksum(tmp_path):
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db)
    gateway = PiDomainGateway(capability="cap", evidence_tool=EvidenceSqliteTool(db_path=db))
    result = gateway.invoke(
        EVIDENCE_SQLITE_OPERATION,
        {"task_id": "t", "idempotency_key": "i", "binding": "b", **_evidence_descriptor()},
        capability="cap",
    )
    assert result["ok"] is True and result["status"] == "success"
    data = result["data"]
    assert data["query_id"] == QUERY_ID
    assert data["database_id"] == DATABASE_ID
    assert data["capability_checksum"] == OPERATIONS[EVIDENCE_SQLITE_OPERATION]["checksum"]
    assert data["row_count"] == 1
    assert data["rows"][0]["message_id"] == "g-1"
    # safe envelope never exposes physical schema or bodies
    assert "canonical_messages" not in str(result).lower()


# ---------------------------------------------------------------------------
# Plan 61-08 Task 1 RED contract: fixed `candidate.review` gateway provider
# (HARNESS-06 / T-61-REVIEW-01 / T-61-REVIEW-02 / T-61-LEAK-04)
#
# The gateway registers exactly one guarded `candidate.review` provider whose
# allowed field set matches the review request shape
# {candidate_id, action, expected_version, edited_payload?, edited_payload_checksum?,
#  explicit_confirmation?, confirmation_token?, conflict_disposition?, feedback_id?,
#  task_id, binding, idempotency_key} (capability is a loopback header). Private
# fields, batch/override inputs and wrong capability/binding/idempotency fail
# closed before any review work.
# ---------------------------------------------------------------------------

CANDIDATE_REVIEW_OPERATION = "candidate.review"

CANDIDATE_REVIEW_ALLOWED = {
    "candidate_id", "action", "expected_version", "edited_payload",
    "edited_payload_checksum", "explicit_confirmation", "confirmation_token",
    "conflict_disposition", "feedback_id", "task_id", "binding", "idempotency_key",
}

CANDIDATE_REVIEW_PRIVATE = {
    "body", "content", "prompt", "completion", "credential", "secret", "sql",
    "statement", "token", "password", "path",
}


def _candidate_review_params(**overrides) -> dict:
    params = {
        "candidate_id": "cand_review_001",
        "action": "accept",
        "expected_version": 1,
        "explicit_confirmation": True,
        "confirmation_token": "confirm-token-001",
        "task_id": "t",
        "idempotency_key": "i",
        "binding": "b",
    }
    params.update(overrides)
    return params


def test_gateway_registers_candidate_review_as_guarded_write():
    assert CANDIDATE_REVIEW_OPERATION in OPERATIONS, (
        "RED: PiDomainGateway must register candidate.review (expected for 61-08 Task 1 RED)"
    )
    spec = OPERATIONS[CANDIDATE_REVIEW_OPERATION]
    assert spec["kind"] == "guarded_write", "candidate review is a guarded write, never a read or a raw dispatch"
    missing = sorted(CANDIDATE_REVIEW_ALLOWED - set(spec["allowed"]))
    assert not missing, f"RED: candidate.review provider must accept the review shape: missing {missing}"
    assert not (set(spec["allowed"]) & CANDIDATE_REVIEW_PRIVATE), (
        "candidate.review must never accept private payload fields"
    )


def test_gateway_candidate_review_fails_closed_on_capability_binding_and_idempotency():
    if CANDIDATE_REVIEW_OPERATION not in OPERATIONS:
        pytest.fail(
            "RED: PiDomainGateway must register candidate.review before capability "
            "gating can be enforced (expected for 61-08 Task 1 RED)",
            pytrace=False,
        )
    gateway = PiDomainGateway(capability="cap")
    base = _candidate_review_params()
    denied = gateway.invoke(CANDIDATE_REVIEW_OPERATION, base, capability="wrong")
    assert denied["ok"] is False and denied["error"]["code"] == "capability_invalid"
    no_binding = gateway.invoke(CANDIDATE_REVIEW_OPERATION, {**base, "binding": None}, capability="cap")
    assert no_binding["error"]["code"] == "binding_required"
    no_idem = gateway.invoke(CANDIDATE_REVIEW_OPERATION, {**base, "idempotency_key": ""}, capability="cap")
    assert no_idem["error"]["code"] == "idempotency_key_required"


def test_gateway_candidate_review_rejects_undeclared_batch_override_and_private_fields():
    if CANDIDATE_REVIEW_OPERATION not in OPERATIONS:
        pytest.fail(
            "RED: PiDomainGateway must register candidate.review before undeclared "
            "input gating can be enforced (expected for 61-08 Task 1 RED)",
            pytrace=False,
        )
    gateway = PiDomainGateway(capability="cap")
    for label, extra in [
        ("batch accept", {"batch": True}),
        ("batch candidate ids", {"candidate_ids": ["cand_a", "cand_b"]}),
        ("provider override", {"provider": "model.wake"}),
        ("operation override", {"operation": "canonical.promote"}),
        ("authority override", {"authority": "canonical.promote"}),
        ("private prompt", {"prompt": "PRIVATE_PROMPT_SENTINEL"}),
        ("private secret", {"secret": "PRIVATE_SECRET_SENTINEL"}),
        ("raw path", {"path": "/etc/passwd"}),
    ]:
        result = gateway.invoke(CANDIDATE_REVIEW_OPERATION, {**_candidate_review_params(), **extra}, capability="cap")
        assert result["ok"] is False, f"{label} must fail closed"
        assert result["error"]["code"] == "undeclared_input", f"{label} must be undeclared_input"
