"""Phase 62 session-context contract: AdaptedSession context fields survive
capture -> repository persistence with additive schema.

Red first: the new fields (cwd/git_branch/model/title/stop_reason) must be
persisted into ce_sessions and included in the dataset digest when present.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.conversation.event_generations import (
    GenerationLifecycle,
)
from personal_knowledge.application.conversation.event_repository import (
    GenerationInput,
)
from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventContractError,
    EventKind,
    FidelityProfile,
    Provenance,
    TypedEvent,
    dataset_digest,
    make_event_id,
)
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifact,
)


def _artifact() -> SourceArtifact:
    return SourceArtifact(
        artifact_id="art1", family="codex", source_kind="file",
        content_hash="h1", capture_method="sha256",
        relative_path="s1.jsonl", byte_size=10,
    )


def _provenance(artifact: SourceArtifact) -> Provenance:
    return Provenance(
        artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
        native_locator="s1.jsonl#L1", native_session_id="s1",
        contract_version="1",
    )


def _session(artifact: SourceArtifact, **overrides) -> AdaptedSession:
    base = dict(
        session_id="sid1", provenance=_provenance(artifact),
        fidelity=FidelityProfile.from_levels({}),
        native_session_id="n1",
    )
    base.update(overrides)
    return AdaptedSession(**base)


def test_session_context_fields_accepted() -> None:
    art = _artifact()
    session = _session(
        art, cwd=r"C:\work\proj", git_branch="main", model="gpt-5",
        title="Session title", stop_reason="end_turn",
    )
    assert session.cwd == r"C:\work\proj"
    assert session.git_branch == "main"
    assert session.model == "gpt-5"
    assert session.title == "Session title"
    assert session.stop_reason == "end_turn"


def test_session_context_fields_default_none() -> None:
    session = _session(_artifact())
    assert session.cwd is None
    assert session.git_branch is None
    assert session.model is None
    assert session.title is None
    assert session.stop_reason is None


def test_digest_changes_with_context_fields() -> None:
    art = _artifact()
    plain = dataset_digest(
        family="codex", adapter_version="1", contract_version="1",
        artifacts=(art,), sessions=(_session(art),), events=(), relations=(),
    )
    rich = dataset_digest(
        family="codex", adapter_version="1", contract_version="1",
        artifacts=(art,),
        sessions=(_session(art, cwd=r"C:\work"),),
        events=(), relations=(),
    )
    assert plain != rich


def test_repository_persists_context_fields(tmp_path: Path) -> None:
    db = tmp_path / "gen.sqlite"
    art = _artifact()
    session = _session(
        art, cwd=r"C:\work\proj", git_branch="main", model="gpt-5",
        title="Session title", stop_reason="end_turn",
    )
    event = TypedEvent(
        event_id=make_event_id("codex", art.artifact_id, "1", "e1",
                              kind=EventKind.SESSION_LIFECYCLE, session_id=session.session_id),
        session_id=session.session_id, kind=EventKind.SESSION_LIFECYCLE,
        provenance=session.provenance, fidelity=session.fidelity,
    )
    life = GenerationLifecycle(db)
    gen = GenerationInput(
        family="codex", adapter_version="1", contract_version="1",
        capability_digest="cap1", source_manifest_id="m1",
        dataset_digest="d1", artifacts=(art,), sessions=(session,),
        events=(event,), relations=(), dispositions=(), warnings=(),
    )
    life.prepare(gen, "gen1")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT cwd, git_branch, model, title, stop_reason FROM ce_sessions",
        ).fetchone()
    finally:
        con.close()
    assert row == (r"C:\work\proj", "main", "gpt-5", "Session title", "end_turn")
