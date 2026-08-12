"""Phase 62-05 Task 3: generation/policy-bound view persistence.

RED tests for :mod:`personal_knowledge.application.conversation.view_repository`.

Requirements exercised (Phase 62 CONTEXT D-16/D-21/D-22/D-24):
  - views are persisted as additive companion tables beside the v2 event
    authority; headers, membership/lineage, fidelity, builder/policy versions
    and lifecycle are stored (D-16/D-21)
  - views reference only one active/staged event generation and are
    replaceable/rebuildable (idempotent) with a deterministic digest (D-21)
  - policy revision produces a new scheduling output but never changes raw
    artifact/event/view identities (D-22)
  - lineage resolution and contradiction slots survive persistence (D-24)
  - view persistence creates no fact authority: it cannot write canonical
    compatibility messages, KU tables, or the authority pointer (D-16/D-17)

All tests run against temporary SQLite files under tmp_path. No live database,
no var/, no network, no provider calls (D-31).
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventKind,
    EventRelation,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
    make_event_id,
)
from personal_knowledge.application.conversation.event_repository import (
    EventRepository,
    GenerationInput,
)
from personal_knowledge.application.conversation.event_schema import create_v2_schema
from personal_knowledge.application.conversation.extraction_policy import (
    DEFAULT_POLICY,
    ExtractionPolicy,
    PriorityBand,
    policy_digest,
)
from personal_knowledge.application.conversation.extraction_views import (
    BUILDER_VERSION,
    EventGraph,
    ViewBuildResult,
    ViewType,
    build_all_views,
)
from personal_knowledge.application.conversation.view_repository import (
    ViewLifecycle,
    ViewRepository,
    ViewRepositoryError,
    VIEW_TABLES,
)


# ------------------------------------------------------------------ fixtures

def _prov(nid: str, session: str) -> Provenance:
    return Provenance(
        artifact_id="art-a", artifact_hash="h" * 8,
        native_locator=f"jsonl:{nid}", native_session_id=session,
        native_event_id=nid, contract_version="1",
    )


def _ev(nid: str, kind: EventKind, ordinal: int, session: str = "s-a") -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id("codex", "art-a", "1", nid),
        session_id=session, kind=kind, provenance=_prov(nid, session),
        fidelity=FidelityProfile.complete(), ordinal=ordinal,
        occurred_at=f"2026-08-{ordinal:02d}T00:00:00Z",
    )


def _session(sid: str) -> AdaptedSession:
    return AdaptedSession(
        session_id=sid, provenance=_prov(sid, sid),
        fidelity=FidelityProfile.complete(), native_session_id=sid,
    )


def _graph(*, generation_id: str = "gen-1", prefix: str = "") -> EventGraph:
    b1 = _ev(f"{prefix}tb-1", EventKind.TURN_BOUNDARY, 1)
    m1 = _ev(f"{prefix}m-1", EventKind.USER_MESSAGE, 2)
    m2 = _ev(f"{prefix}m-2", EventKind.ASSISTANT_MESSAGE, 3)
    c1 = _ev(f"{prefix}c-1", EventKind.USER_MESSAGE, 4)
    kept = _ev(f"{prefix}kept-1", EventKind.ASSISTANT_MESSAGE, 5)
    sum1 = _ev(f"{prefix}sum-1", EventKind.COMPACTION_SUMMARY, 6)
    x1 = _ev(f"{prefix}x-1", EventKind.ASSISTANT_MESSAGE, 1, session="s-b")
    return EventGraph(
        generation_id=generation_id,
        sessions=(_session("s-a"), _session("s-b")),
        events=(b1, m1, m2, c1, kept, sum1, x1),
        relations=(
            EventRelation("r-t1", b1.event_id, m1.event_id, RelationKind.TURN_MEMBERSHIP),
            EventRelation("r-t2", b1.event_id, m2.event_id, RelationKind.TURN_MEMBERSHIP),
            EventRelation("r-c1", sum1.event_id, c1.event_id, RelationKind.COMPACTED_RANGE),
            EventRelation("r-r1", sum1.event_id, kept.event_id, RelationKind.RETAINED_FROM),
            EventRelation(
                "r-x", sum1.event_id, x1.event_id,
                RelationKind.SOURCE_SESSION_CROSSWALK,
            ),
        ),
    )


def _gen_input_from(graph: EventGraph) -> GenerationInput:
    from personal_knowledge.adapters.conversation_sources.contracts import SourceArtifact

    return GenerationInput(
        family="codex", adapter_version="1", contract_version="1",
        capability_digest="cap-1", source_manifest_id="manifest-1",
        dataset_digest="ds-1",
        artifacts=(
            SourceArtifact(
                artifact_id="art-a", family="codex", source_kind="file",
                content_hash="h" * 8, capture_method="sha256",
                relative_path="rollout.jsonl", byte_size=10,
            ),
        ),
        sessions=graph.sessions,
        events=graph.events, relations=graph.relations, dispositions=(),
        warnings=(),
    )


@pytest.fixture()
def repo(tmp_path: Path) -> ViewRepository:
    db = tmp_path / "conversations.sqlite"
    create_v2_schema(db)
    event_repo = EventRepository(db)
    event_repo.create_schema()
    # stage generation gen-1 so the view repository has a real generation to bind
    event_repo.write_generation(
        _gen_input_from(_graph(generation_id="gen-1")), generation_id="gen-1"
    )
    repository = ViewRepository(db)
    repository.create_schema()
    return repository


@pytest.fixture()
def build_result() -> ViewBuildResult:
    return build_all_views(_graph(generation_id="gen-1"))


def _session_first_policy() -> ExtractionPolicy:
    return ExtractionPolicy(
        policy_id="policy-session-first", version="2",
        priority_bands=(
            PriorityBand(order=1, allowed_view_types=(ViewType.SESSION,)),
            PriorityBand(
                order=2,
                allowed_view_types=(
                    ViewType.COMPACTION_WINDOW,
                    ViewType.TURN,
                    ViewType.NATIVE_TRACE,
                    ViewType.EPISODE,
                ),
            ),
            PriorityBand(order=3, allowed_view_types=(ViewType.TOPIC,)),
            PriorityBand(order=4, allowed_view_types=(ViewType.CROSS_SESSION,)),
        ),
    )


# --------------------------------------------------------- schema

def test_view_schema_is_additive_and_keeps_authority_tables(repo: ViewRepository) -> None:
    con = sqlite3.connect(str(repo.db))
    tables = {
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    con.close()
    for table in VIEW_TABLES:
        assert table in tables, f"missing view table {table}"
    # the v2 authority tables are preserved untouched
    assert "ce_events" in tables
    assert "ce_generation_authority" in tables


def test_view_repository_exposes_no_activation_surface(repo: ViewRepository) -> None:
    public = [n for n in dir(repo) if not n.startswith("_")]
    assert not any("activ" in n.lower() for n in public)


# ------------------------------------------------------- idempotent save

def test_save_and_rebuild_is_idempotent(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    first = repo.save_view_revision(build_result, DEFAULT_POLICY)
    second = repo.save_view_revision(build_result, DEFAULT_POLICY)
    assert first == second
    assert first.view_digest == second.view_digest
    assert first.view_count == len(build_result.views)
    assert first.policy_digest == digest
    stored = repo.read_views("gen-1", digest)
    assert len(stored) == len(build_result.views)
    assert {v["view_id"] for v in stored} == {v.view_id for v in build_result.views}


def test_saved_views_round_trip_full_fidelity(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    stored = repo.read_views("gen-1", digest)
    original = {v.view_id: v.to_dict() for v in build_result.views}
    for row in stored:
        assert row["view_id"] in original
        original_row = original[row["view_id"]]
        assert set(row["members"]) == set(original_row["members"])
        assert set(row["evidence_event_refs"]) == set(
            original_row["evidence_event_refs"]
        )
        assert row["view_type"] == original_row["view_type"]
        assert row["fidelity"] == original_row["fidelity"]


# ------------------------------------------------------ policy revision

def test_policy_revision_changes_scheduling_not_event_ids(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    d_default = policy_digest(DEFAULT_POLICY)
    session_first = _session_first_policy()
    d_session = policy_digest(session_first)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    repo.save_view_revision(build_result, session_first)

    revisions = repo.policy_revisions("gen-1")
    digests = {r.policy_digest for r in revisions}
    assert {d_default, d_session} <= digests

    # same raw views stored under both policies: only scheduling differs
    default_views = repo.read_views("gen-1", d_default)
    session_views = repo.read_views("gen-1", d_session)
    assert {v["view_id"] for v in default_views} == {
        v["view_id"] for v in session_views
    }


def test_rebuild_same_policy_is_single_revision(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    revisions = repo.policy_revisions("gen-1")
    assert len(revisions) == 1


# ----------------------------------------------------- generation drift

def test_generation_drift_keeps_old_generation_views_intact(
    repo: ViewRepository,
) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    event_repo = EventRepository(repo.db)
    # stage gen-1 and gen-2 with distinct event sets (gen-1 already staged)
    gen1 = build_all_views(_graph(generation_id="gen-1"))
    gen2_graph = _graph(generation_id="gen-2", prefix="g2-")
    event_repo.write_generation(
        _gen_input_from(gen2_graph), generation_id="gen-2"
    )
    gen2 = build_all_views(gen2_graph)
    repo.save_view_revision(gen1, DEFAULT_POLICY)
    repo.save_view_revision(gen2, DEFAULT_POLICY)

    # gen-1 views remain fully queryable after gen-2 activation shadow
    assert len(repo.read_views("gen-1", digest)) == len(gen1.views)
    assert len(repo.read_views("gen-2", digest)) == len(gen2.views)


def test_views_cannot_reference_unknown_generation(repo: ViewRepository) -> None:
    with pytest.raises(ViewRepositoryError, match="generation"):
        repo.save_view_revision(
            build_all_views(_graph(generation_id="gen-ghost")), DEFAULT_POLICY
        )


def test_no_cross_generation_membership(repo: ViewRepository) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    gen1 = build_all_views(_graph(generation_id="gen-1"))
    gen2_graph = _graph(generation_id="gen-2", prefix="g2-")
    EventRepository(repo.db).write_generation(
        _gen_input_from(gen2_graph), generation_id="gen-2"
    )
    gen2 = build_all_views(gen2_graph)
    repo.save_view_revision(gen1, DEFAULT_POLICY)
    repo.save_view_revision(gen2, DEFAULT_POLICY)
    gen1_members = {
        eid for v in repo.read_views("gen-1", digest) for eid in v["members"]
    }
    gen2_members = {
        eid for v in repo.read_views("gen-2", digest) for eid in v["members"]
    }
    assert not (gen1_members & gen2_members)


# -------------------------------------------------------- stale marking

def test_mark_stale_updates_lifecycle(repo: ViewRepository, build_result: ViewBuildResult) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    assert repo.lifecycle_status("gen-1", digest) == ViewLifecycle.ACTIVE
    repo.mark_stale("gen-1", digest, reason="generation superseded")
    assert repo.lifecycle_status("gen-1", digest) == ViewLifecycle.STALE
    views = repo.read_views("gen-1", digest)
    assert views
    assert all(v["lifecycle"] == ViewLifecycle.STALE.value for v in views)


# ----------------------------------------------------- lineage resolution

def test_resolve_lineage_returns_members_lineage_and_contradictions(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    session_view = next(
        v for v in build_result.views if v.view_type is ViewType.SESSION
    )
    resolved = repo.resolve_lineage("gen-1", session_view.view_id, digest)
    assert resolved["view_id"] == session_view.view_id
    assert set(resolved["members"]) == set(session_view.members)
    assert set(resolved["lineage"]) == set(session_view.lineage)
    assert set(resolved["evidence_event_refs"]) == set(
        session_view.evidence_event_refs
    )


def test_compaction_window_contradictions_persist(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    # introduce a retained-and-compacted contradiction and rebuild: the event
    # that the summary already compacted is also declared retained
    graph = _graph(generation_id="gen-1")
    events = list(graph.events)
    sum_event = next(e for e in events if e.kind is EventKind.COMPACTION_SUMMARY)
    compacted_target = next(
        r.target_event_id for r in graph.relations
        if r.relation_kind is RelationKind.COMPACTED_RANGE
        and r.source_event_id == sum_event.event_id
    )
    relations = list(graph.relations)
    relations.append(
        EventRelation(
            "r-rc", sum_event.event_id, compacted_target, RelationKind.RETAINED_FROM
        )
    )
    result = build_all_views(
        EventGraph(
            generation_id=graph.generation_id,
            sessions=graph.sessions,
            events=tuple(events),
            relations=tuple(relations),
        )
    )
    digest = policy_digest(DEFAULT_POLICY)
    repo.save_view_revision(result, DEFAULT_POLICY)
    comp = next(
        v for v in result.views if v.view_type is ViewType.COMPACTION_WINDOW
    )
    assert comp.contradictions
    resolved = repo.resolve_lineage("gen-1", comp.view_id, digest)
    assert resolved["contradictions"]
    assert any(c["kind"] == "retained_and_compacted" for c in resolved["contradictions"])


# ------------------------------------------------- no authority mutation

def test_view_persistence_writes_no_canonical_or_authority_rows(
    repo: ViewRepository, build_result: ViewBuildResult,
) -> None:
    con = sqlite3.connect(str(repo.db))
    con.execute("CREATE TABLE IF NOT EXISTS canonical_messages (id TEXT)")
    con.execute(
        "INSERT INTO canonical_messages VALUES ('pre-existing')"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS ce_generation_authority "
        "(generation_id TEXT PRIMARY KEY, active INTEGER DEFAULT 0)"
    )
    con.commit()
    con.close()

    repo.save_view_revision(build_result, DEFAULT_POLICY)

    con = sqlite3.connect(str(repo.db))
    canonical_count = con.execute(
        "SELECT COUNT(*) FROM canonical_messages"
    ).fetchone()[0]
    authority_count = con.execute(
        "SELECT COUNT(*) FROM ce_generation_authority"
    ).fetchone()[0]
    con.close()
    # view persistence never touched compatibility or authority rows
    assert canonical_count == 1
    assert authority_count == 0


def test_view_digest_is_stable_across_rebuild(repo: ViewRepository, build_result: ViewBuildResult) -> None:
    digest = policy_digest(DEFAULT_POLICY)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    first = repo.view_digest("gen-1", digest)
    repo.save_view_revision(build_result, DEFAULT_POLICY)
    assert first == repo.view_digest("gen-1", digest)
    assert first is not None
