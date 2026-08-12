"""Phase 62-04 Task 2: staging, validation, atomic activation and exact rollback.

RED/GREEN tests for :mod:`personal_knowledge.application.conversation.event_generations`
(the sole generation lifecycle owner):

  - prepare stages a complete generation
  - validate covers schema/FK/digests/provenance/fidelity/adapter coverage
  - activate commits the event authority + compatibility projection + version /
    watermark / fingerprint binding atomically
  - every injected failure (before commit, after authority commit in
    projection/pointer/version, checksum mismatch, stale manifest, unknown
    adapter, missing family coverage, consumer parity failure) restores the
    exact prior authority rows / compatibility tables / version / watermark /
    fingerprint
  - old generation rows and activation audit records are preserved, never
    deleted

All tests run against temporary SQLite files under tmp_path. No live database,
no var/, no network, no provider calls (D-31).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventKind,
    FidelityProfile,
    Provenance,
    TypedEvent,
    make_event_id,
)
from personal_knowledge.adapters.conversation_sources.contracts import SourceArtifact
from personal_knowledge.application.conversation.event_repository import (
    EventRepository,
    GenerationInput,
)
from personal_knowledge.application.conversation.event_generations import (
    ActivationHooks,
    GenerationActivationError,
    GenerationLifecycle,
)


def _prov(native_event_id: str, locator: str) -> Provenance:
    return Provenance(
        artifact_id="art-a", artifact_hash="h" * 8, native_locator=locator,
        native_session_id="s-1", native_event_id=native_event_id,
        contract_version="1",
    )


def _artifact() -> SourceArtifact:
    return SourceArtifact(
        artifact_id="art-a", family="codex", source_kind="file",
        content_hash="h" * 8, capture_method="sha256",
        relative_path="rollout.jsonl", byte_size=10,
    )


def _session() -> AdaptedSession:
    return AdaptedSession(
        session_id="s-1",
        provenance=_prov("s-1", "jsonl:s-1"),
        fidelity=FidelityProfile.complete(),
        native_session_id="s-1",
        started_at="2026-08-12T00:00:00Z",
        ended_at="2026-08-12T00:05:00Z",
    )


def _event(session_id: str, kind: EventKind, locator: str, *,
           native_id: str, ordinal: int, summary: str) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(
            "codex", "art-a", "1", native_id,
            kind=kind, session_id=session_id, native_locator=locator,
        ),
        session_id=session_id,
        kind=kind,
        provenance=_prov(native_id, locator),
        fidelity=FidelityProfile.complete(),
        ordinal=ordinal,
        occurred_at=f"2026-08-12T00:0{ordinal}:00Z",
        summary=summary,
    )


def _generation(dataset_digest: str, user_text: str) -> GenerationInput:
    events = [
        _event("s-1", EventKind.USER_MESSAGE, "jsonl:1", native_id="msg-1",
               ordinal=1, summary=user_text),
        _event("s-1", EventKind.ASSISTANT_MESSAGE, "jsonl:2", native_id="msg-2",
               ordinal=2, summary="assistant reply"),
        _event("s-1", EventKind.COMPACTION_SUMMARY, "jsonl:3", native_id="cmp-1",
               ordinal=3, summary="Compacted earlier turns."),
    ]
    return GenerationInput(
        family="codex",
        adapter_version="1",
        contract_version="1",
        capability_digest="cap-1",
        source_manifest_id="manifest-1",
        dataset_digest=dataset_digest,
        artifacts=(_artifact(),),
        sessions=(_session(),),
        events=tuple(events),
        relations=(),
        dispositions=(),
        warnings=(),
    )


def _activate(life: GenerationLifecycle, generation_id: str, *, digest: str,
              hooks: ActivationHooks | None = None) -> None:
    life.activate(
        generation_id,
        source_manifest_id="manifest-1",
        expected_dataset_digest=digest,
        expected_adapter_families=("codex",),
        hooks=hooks,
    )


def _snapshot(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    try:
        return {
            "authority": sorted(
                (tuple(r) for r in con.execute(
                    "SELECT generation_id, active FROM ce_generation_authority"
                )),
            ),
            "sessions": con.execute(
                "SELECT canonical_session_id, primary_source, agent FROM "
                "canonical_sessions ORDER BY canonical_session_id"
            ).fetchall(),
            "messages": con.execute(
                "SELECT canonical_message_id, role, content FROM "
                "canonical_messages ORDER BY canonical_message_id"
            ).fetchall(),
            "tools": con.execute(
                "SELECT canonical_tool_id, source_kind FROM "
                "canonical_tool_events ORDER BY canonical_tool_id"
            ).fetchall(),
            "bindings": sorted(
                (tuple(r) for r in con.execute(
                    "SELECT kind, generation_id, value FROM ce_activation_bindings"
                )),
            ),
        }
    finally:
        con.close()


@pytest.fixture()
def live(tmp_path: Path) -> tuple[Path, GenerationLifecycle, GenerationInput, GenerationInput]:
    """Baseline: gen-1 active; gen-2 staged and ready to attempt activation."""
    db = tmp_path / "conversations.sqlite"
    life = GenerationLifecycle(db)
    gen_a = _generation("ds-a", "hello from generation one")
    life.prepare(gen_a, "gen-1")
    _activate(life, "gen-1", digest=gen_a.dataset_digest)
    assert life.authority_generation_id() == "gen-1"
    gen_b = _generation("ds-b", "hello from generation two")
    life.prepare(gen_b, "gen-2")
    return db, life, gen_a, gen_b


def _failing_hook(message: str):
    def _hook(*args, **kwargs):
        raise RuntimeError(message)
    return _hook


# ---------------------------------------------------------------- lifecycle

def test_prepare_stages_generation(tmp_path: Path) -> None:
    db = tmp_path / "conversations.sqlite"
    life = GenerationLifecycle(db)
    gen = _generation("ds-a", "staged text")
    life.prepare(gen, "gen-x")
    repo = EventRepository(db)
    result = repo.validate_generation("gen-x")
    assert result["ok"] is True
    assert result["events"] == 3
    assert life.authority_generation_id() is None  # staged != active


def test_validate_reports_checksum_mismatch(live) -> None:
    db, life, gen_a, gen_b = live
    report = life.validate(
        "gen-2", source_manifest_id="manifest-1",
        expected_dataset_digest="wrong-digest",
        expected_adapter_families=("codex",),
    )
    assert report["ok"] is False
    assert "checksum" in report["failure"]


def test_validate_reports_stale_manifest(live) -> None:
    db, life, gen_a, gen_b = live
    report = life.validate(
        "gen-2", source_manifest_id="stale-manifest",
        expected_dataset_digest=gen_b.dataset_digest,
        expected_adapter_families=("codex",),
    )
    assert report["ok"] is False
    assert "manifest" in report["failure"]


def test_validate_reports_unknown_adapter(live) -> None:
    db, life, gen_a, gen_b = live
    report = life.validate(
        "gen-2", source_manifest_id="manifest-1",
        expected_dataset_digest=gen_b.dataset_digest,
        expected_adapter_families=("codex", "ghost-family"),
    )
    assert report["ok"] is False
    assert "adapter" in report["failure"]


def test_validate_reports_missing_family_coverage(live) -> None:
    db, life, gen_a, gen_b = live
    report = life.validate(
        "gen-2", source_manifest_id="manifest-1",
        expected_dataset_digest=gen_b.dataset_digest,
        expected_adapter_families=("codex", "claude"),
    )
    assert report["ok"] is False
    assert "coverage" in report["failure"]


def test_validate_passes_healthy_generation(live) -> None:
    db, life, gen_a, gen_b = live
    report = life.validate(
        "gen-2", source_manifest_id="manifest-1",
        expected_dataset_digest=gen_b.dataset_digest,
        expected_adapter_families=("codex",),
    )
    assert report["ok"] is True


# ----------------------------------------------------------- successful flow

def test_activate_success_binds_authority_projection_version(live) -> None:
    db, life, gen_a, gen_b = live
    _activate(life, "gen-2", digest=gen_b.dataset_digest)
    assert life.authority_generation_id() == "gen-2"
    # projection rows now reflect generation two (one user message + one tool?)
    con = sqlite3.connect(str(db))
    contents = [r[0] for r in con.execute(
        "SELECT content FROM canonical_messages ORDER BY ordinal"
    )]
    con.close()
    assert "hello from generation two" in contents
    assert "hello from generation one" not in contents  # old projection replaced
    # version / watermark / fingerprint bind to generation two
    bindings = dict(
        (r[0], r[1]) for r in sqlite3.connect(str(db)).execute(
            "SELECT kind, generation_id FROM ce_activation_bindings"
        )
    )
    assert bindings["projection_version"] == "gen-2"
    assert bindings["projection_watermark"] == "gen-2"
    assert bindings["projection_fingerprint"] == "gen-2"
    # old generation rows are preserved, never deleted
    repo = EventRepository(db)
    assert repo.validate_generation("gen-1")["ok"] is True
    assert repo.validate_generation("gen-2")["ok"] is True


# ------------------------------------------------- fault injection: pre-commit

def test_checksum_mismatch_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest="wrong-digest")
    assert _snapshot(db) == before
    assert life.authority_generation_id() == "gen-1"


def test_stale_manifest_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    with pytest.raises(GenerationActivationError):
        life.activate(
            "gen-2", source_manifest_id="stale-manifest",
            expected_dataset_digest=gen_b.dataset_digest,
            expected_adapter_families=("codex",),
        )
    assert _snapshot(db) == before


def test_unknown_adapter_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    with pytest.raises(GenerationActivationError):
        life.activate(
            "gen-2", source_manifest_id="manifest-1",
            expected_dataset_digest=gen_b.dataset_digest,
            expected_adapter_families=("codex", "ghost-family"),
        )
    assert _snapshot(db) == before


def test_consumer_parity_failure_blocks_activation(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    hooks = ActivationHooks(
        consumer_parity=lambda: {"ok": False, "reason": "user_turn_parity_mismatch"},
    )
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest=gen_b.dataset_digest, hooks=hooks)
    assert _snapshot(db) == before
    assert life.authority_generation_id() == "gen-1"


# ------------------------------------------- fault injection: post-authority

def test_projection_write_failure_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    hooks = ActivationHooks(projection_writer=_failing_hook("projection write boom"))
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest=gen_b.dataset_digest, hooks=hooks)
    assert _snapshot(db) == before
    assert life.authority_generation_id() == "gen-1"


def test_authority_pointer_failure_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    hooks = ActivationHooks(authority_writer=_failing_hook("pointer write boom"))
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest=gen_b.dataset_digest, hooks=hooks)
    assert _snapshot(db) == before


def test_version_binding_failure_restores_exact_state(live) -> None:
    db, life, gen_a, gen_b = live
    before = _snapshot(db)
    hooks = ActivationHooks(version_binder=_failing_hook("version bind boom"))
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest=gen_b.dataset_digest, hooks=hooks)
    assert _snapshot(db) == before
    assert life.authority_generation_id() == "gen-1"
    # exact fingerprint restoration
    con = sqlite3.connect(str(db))
    fp = con.execute(
        "SELECT generation_id, value FROM ce_activation_bindings "
        "WHERE kind='projection_fingerprint'"
    ).fetchone()
    con.close()
    assert fp[0] == "gen-1"


# ------------------------------------------------------ preservation + rollback

def test_old_generation_rows_and_audit_preserved_after_failure(live) -> None:
    db, life, gen_a, gen_b = live
    with pytest.raises(GenerationActivationError):
        _activate(life, "gen-2", digest="wrong-digest")
    repo = EventRepository(db)
    # failed generation stays staged/preserved
    assert repo.validate_generation("gen-2")["events"] == 3
    assert repo.validate_generation("gen-1")["events"] == 3
    # activation audit preserves both attempts
    con = sqlite3.connect(str(db))
    log = con.execute(
        "SELECT generation_id, outcome FROM ce_activation_log "
        "ORDER BY attempted_at"
    ).fetchall()
    con.close()
    outcomes = [o for _g, o in log]
    assert "success" in outcomes
    assert "failure" in outcomes


def test_rollback_to_previous_generation(live) -> None:
    db, life, gen_a, gen_b = live
    _activate(life, "gen-2", digest=gen_b.dataset_digest)
    assert life.authority_generation_id() == "gen-2"
    life.rollback_to("gen-1")
    assert life.authority_generation_id() == "gen-1"
    con = sqlite3.connect(str(db))
    contents = [r[0] for r in con.execute(
        "SELECT content FROM canonical_messages ORDER BY ordinal"
    )]
    bindings = dict((r[0], r[1]) for r in con.execute(
        "SELECT kind, generation_id FROM ce_activation_bindings"
    ))
    con.close()
    assert "hello from generation one" in contents
    assert bindings["projection_version"] == "gen-1"
    # generation two rows are still preserved, not deleted
    assert EventRepository(db).validate_generation("gen-2")["ok"] is True


def test_repository_has_no_activation_surface(live) -> None:
    db, life, gen_a, gen_b = live
    repo = EventRepository(db)
    public = [n for n in dir(repo) if not n.startswith("_")]
    assert not any("activate" in n.lower() for n in public)
