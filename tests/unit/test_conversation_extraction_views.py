"""Phase 62-05 Task 1: deterministic extraction view builders.

RED tests for :mod:`personal_knowledge.application.conversation.extraction_views`.

Requirements exercised (Phase 62 CONTEXT D-20..D-24):
  - seven deterministic view builders: Turn / NativeTrace / Episode /
    CompactionWindow / Session / Topic / CrossSession (D-21)
  - stable view ids derived from generation + builder version + ordered
    evidence event set; rebuildable without re-running adapters (D-21)
  - NativeTraceView uses explicit source-native trace/turn/loop ids only;
    adjacency guesses are never labeled native (D-20)
  - EpisodeView may use versioned deterministic heuristics
  - CompactionWindowView relates a summary event to compacted/retained sets
  - Session/Topic/CrossSession views retain member view/event lineage and
    contradiction slots (D-24)
  - unknown/partial relations reduce fidelity; compaction summaries are
    navigation signals, never self-authenticating truth (D-23/D-24)

All tests are pure and deterministic (D-31: no I/O, no network).
"""

from __future__ import annotations

import hashlib

import pytest

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventKind,
    EventRelation,
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
    make_event_id,
)
from personal_knowledge.application.conversation import extraction_views
from personal_knowledge.application.conversation.extraction_views import (
    BUILDER_VERSION,
    CompactionWindowView,
    CrossSessionView,
    DerivedView,
    EpisodeView,
    EventGraph,
    NativeTraceView,
    SessionView,
    TopicView,
    TurnView,
    ViewBuildResult,
    ViewBuilderError,
    ViewType,
    build_all_views,
    build_compaction_window_views,
    build_cross_session_views,
    build_episode_views,
    build_native_trace_views,
    build_session_views,
    build_topic_views,
    build_turn_views,
    make_contradiction_id,
    make_view_id,
    view_set_digest,
)


# ------------------------------------------------------------------ fixtures

def _prov(
    native_event_id: str,
    locator: str,
    *,
    native_session_id: str | None = "s-1",
) -> Provenance:
    return Provenance(
        artifact_id="art-a",
        artifact_hash="h" * 8,
        native_locator=locator,
        native_session_id=native_session_id,
        native_event_id=native_event_id,
        contract_version="1",
    )


def _ev(
    native_id: str,
    kind: EventKind,
    *,
    session_id: str = "s-1",
    ordinal: int = 1,
    summary: str | None = None,
    fidelity: FidelityProfile | None = None,
    native_payload_ref: str | None = None,
) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id("codex", "art-a", "1", native_id),
        session_id=session_id,
        kind=kind,
        provenance=_prov(native_id, f"jsonl:{native_id}", native_session_id=session_id),
        fidelity=fidelity or FidelityProfile.complete(),
        ordinal=ordinal,
        occurred_at=f"2026-08-12T00:00:{ordinal:02d}Z",
        summary=summary,
        native_payload_ref=native_payload_ref,
    )


def _rel(rid: str, src: TypedEvent, dst: TypedEvent, kind: RelationKind) -> EventRelation:
    return EventRelation(rid, src.event_id, dst.event_id, kind)


def _session(session_id: str = "s-1", native_session_id: str | None = "s-1") -> AdaptedSession:
    return AdaptedSession(
        session_id=session_id,
        provenance=_prov(native_session_id or session_id, f"jsonl:{session_id}",
                         native_session_id=session_id),
        fidelity=FidelityProfile.complete(),
        native_session_id=native_session_id,
    )


def _graph(
    events: tuple[TypedEvent, ...],
    relations: tuple[EventRelation, ...] = (),
    sessions: tuple[AdaptedSession, ...] = (),
    *,
    generation_id: str = "gen-1",
) -> EventGraph:
    return EventGraph(
        generation_id=generation_id,
        sessions=sessions or (_session(),),
        events=events,
        relations=relations,
    )


@pytest.fixture()
def simple_turn_graph() -> EventGraph:
    """Two explicit turns with native turn-boundary anchors."""
    b1 = _ev("tb-1", EventKind.TURN_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    a1 = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=3)
    b2 = _ev("tb-2", EventKind.TURN_BOUNDARY, ordinal=4)
    m2 = _ev("msg-3", EventKind.USER_MESSAGE, ordinal=5)
    a2 = _ev("msg-4", EventKind.ASSISTANT_MESSAGE, ordinal=6)
    return _graph(
        (b1, m1, a1, b2, m2, a2),
        (
            _rel("r-t1a", b1, m1, RelationKind.TURN_MEMBERSHIP),
            _rel("r-t1b", b1, a1, RelationKind.TURN_MEMBERSHIP),
            _rel("r-t2a", b2, m2, RelationKind.TURN_MEMBERSHIP),
            _rel("r-t2b", b2, a2, RelationKind.TURN_MEMBERSHIP),
        ),
    )


@pytest.fixture()
def compaction_graph() -> EventGraph:
    """Pi-like compaction: a summary compacting earlier events, retaining one."""
    c1 = _ev("c1", EventKind.USER_MESSAGE, ordinal=1)
    c2 = _ev("c2", EventKind.ASSISTANT_MESSAGE, ordinal=2)
    kept = _ev("kept", EventKind.ASSISTANT_MESSAGE, ordinal=3)
    summary = _ev(
        "sum-1",
        EventKind.COMPACTION_SUMMARY,
        ordinal=4,
        summary="earlier turn compacted",
    )
    return _graph(
        (c1, c2, kept, summary),
        (
            _rel("r-comp-1", summary, c1, RelationKind.COMPACTED_RANGE),
            _rel("r-comp-2", summary, c2, RelationKind.COMPACTED_RANGE),
            _rel("r-ret-1", summary, kept, RelationKind.RETAINED_FROM),
        ),
    )


# ------------------------------------------------------------------ view ids

def test_view_ids_are_stable_and_deterministic() -> None:
    refs = ("ev-a", "ev-b")
    a = make_view_id(ViewType.NATIVE_TRACE, "gen-1", BUILDER_VERSION, refs)
    b = make_view_id(ViewType.NATIVE_TRACE, "gen-1", BUILDER_VERSION, refs)
    assert a == b
    assert a.startswith("view:")


def test_view_ids_change_with_generation_or_builder_version_or_evidence() -> None:
    refs = ("ev-a", "ev-b")
    base = make_view_id(ViewType.EPISODE, "gen-1", "1", refs)
    assert base != make_view_id(ViewType.EPISODE, "gen-2", "1", refs)
    assert base != make_view_id(ViewType.EPISODE, "gen-1", "2", refs)
    assert base != make_view_id(ViewType.EPISODE, "gen-1", "1", ("ev-a", "ev-c"))
    assert make_view_id(ViewType.TURN, "gen-1", "1", refs) != base


def test_view_ids_ignore_evidence_ordering() -> None:
    a = make_view_id(ViewType.TURN, "gen-1", "1", ("ev-b", "ev-a"))
    b = make_view_id(ViewType.TURN, "gen-1", "1", ("ev-a", "ev-b"))
    assert a == b


# ---------------------------------------------------------------- TurnView

def test_turn_views_group_by_native_turn_membership(simple_turn_graph: EventGraph) -> None:
    views = build_turn_views(simple_turn_graph)
    assert len(views) == 2
    for view in views:
        assert isinstance(view, TurnView)
        assert view.session_id == "s-1"
        assert view.generation_id == "gen-1"
        assert len(view.members) == 3  # boundary + two members
        assert len(view.evidence_event_refs) == 3
        # every member must be a real event id in the graph
        event_ids = {e.event_id for e in simple_turn_graph.events}
        assert set(view.members) <= event_ids


def test_turn_views_rebuild_deterministically(simple_turn_graph: EventGraph) -> None:
    first = build_turn_views(simple_turn_graph)
    second = build_turn_views(simple_turn_graph)
    assert [(v.view_id, v.members) for v in first] == [
        (v.view_id, v.members) for v in second
    ]


def test_turn_view_reports_native_boundary_ids() -> None:
    b1 = _ev("tb-1", EventKind.TURN_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    graph = _graph(
        (b1, m1),
        (_rel("r-1", b1, m1, RelationKind.TURN_MEMBERSHIP),),
    )
    views = build_turn_views(graph)
    assert len(views) == 1
    assert b1.event_id in views[0].evidence_event_refs
    assert "native_turn" in dict(views[0].metadata).get("flags", "")


def test_turn_view_without_boundary_is_partial_not_native() -> None:
    a = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=1)
    b = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=2)
    graph = _graph((a, b))
    views = build_turn_views(graph)
    # no explicit native turn boundary => no fabricated turn views
    assert views == ()


# ------------------------------------------------------- NativeTraceView

def test_native_trace_uses_explicit_native_loop_id_only() -> None:
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    m2 = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=3)
    graph = _graph(
        (loop, m1, m2),
        (
            _rel("r-l1", loop, m1, RelationKind.TURN_MEMBERSHIP),
            _rel("r-l2", loop, m2, RelationKind.TURN_MEMBERSHIP),
        ),
    )
    views = build_native_trace_views(graph)
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, NativeTraceView)
    assert view.native_trace_id == "loop-1"
    assert loop.event_id in view.evidence_event_refs
    assert set(view.members) == {loop.event_id, m1.event_id, m2.event_id}


def test_native_trace_never_fabricated_from_adjacency() -> None:
    a = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=1)
    b = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=2)
    graph = _graph((a, b))
    views = build_native_trace_views(graph)
    assert views == ()
    # even with a heuristic-like sidechain relation, without a native anchor
    # the view must not claim native identity
    graph2 = _graph((a, b), (_rel("r-s", a, b, RelationKind.SIDECHAIN),))
    assert build_native_trace_views(graph2) == ()


def test_native_trace_partial_member_reduces_fidelity() -> None:
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    partial = _ev(
        "msg-1",
        EventKind.USER_MESSAGE,
        ordinal=2,
        fidelity=FidelityProfile.from_levels(
            {FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.PARTIAL}
        ),
    )
    graph = _graph(
        (loop, partial),
        (_rel("r-l1", loop, partial, RelationKind.TURN_MEMBERSHIP),),
    )
    views = build_native_trace_views(graph)
    assert len(views) == 1
    assert not views[0].fidelity.is_complete()
    assert (
        views[0].fidelity.level(FidelityDimension.RELATION_COMPLETENESS)
        is FidelityLevel.PARTIAL
    )


# ---------------------------------------------------------- EpisodeView

def test_episode_uses_deterministic_relation_components() -> None:
    b1 = _ev("tb-1", EventKind.TURN_BOUNDARY, ordinal=1)
    a1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    a2 = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=3)
    b2 = _ev("tb-2", EventKind.TURN_BOUNDARY, ordinal=4)
    a3 = _ev("msg-3", EventKind.USER_MESSAGE, ordinal=5)
    graph = _graph(
        (b1, a1, a2, b2, a3),
        (
            _rel("r-e1", b1, a1, RelationKind.PARENT_CHILD),
            _rel("r-e2", a1, a2, RelationKind.PARENT_CHILD),
            _rel("r-e3", b2, a3, RelationKind.PARENT_CHILD),
        ),
    )
    views = build_episode_views(graph)
    # two disconnected relation components => two episodes
    assert len(views) == 2
    for view in views:
        assert isinstance(view, EpisodeView)
        assert view.heuristics
    assert all(
        set(v.evidence_event_refs) == set(v.members) for v in views
    )


def test_episode_session_fallback_is_partial_and_tagged() -> None:
    a = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=1)
    b = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=2)
    graph = _graph((a, b))
    views = build_episode_views(graph)
    assert len(views) == 1
    assert "session_fallback" in views[0].heuristics
    assert not views[0].fidelity.is_complete()


def test_episode_views_rebuild_deterministically() -> None:
    b1 = _ev("tb-1", EventKind.TURN_BOUNDARY, ordinal=1)
    a1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    graph = _graph((b1, a1), (_rel("r-1", b1, a1, RelationKind.PARENT_CHILD),))
    assert [(v.view_id, v.members) for v in build_episode_views(graph)] == [
        (v.view_id, v.members) for v in build_episode_views(graph)
    ]


# -------------------------------------------------- CompactionWindowView

def test_compaction_window_relates_summary_to_compacted_and_retained(
    compaction_graph: EventGraph,
) -> None:
    views = build_compaction_window_views(compaction_graph)
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, CompactionWindowView)
    assert view.summary_event_id.startswith("ev|") or view.summary_event_id
    assert len(view.compacted_event_refs) == 2
    assert len(view.retained_event_refs) == 1
    assert "compaction" in view.view_type.value
    # the summary event is evidence, not truth
    assert set(view.evidence_event_refs) == set(view.members)


def test_compaction_summary_without_range_relations_is_partial() -> None:
    summary = _ev("sum-1", EventKind.COMPACTION_SUMMARY, ordinal=1, summary="no ranges")
    graph = _graph((summary,))
    views = build_compaction_window_views(graph)
    assert len(views) == 1
    assert not views[0].fidelity.is_complete()
    assert views[0].compacted_event_refs == ()
    assert views[0].retained_event_refs == ()
    # must never claim complete coverage of the compacted range
    assert (
        views[0].fidelity.level(FidelityDimension.COMPACTION_VISIBILITY)
        is FidelityLevel.PARTIAL
    )


def test_compaction_window_retained_event_never_double_marked() -> None:
    c1 = _ev("c1", EventKind.USER_MESSAGE, ordinal=1)
    summary = _ev("sum-1", EventKind.COMPACTION_SUMMARY, ordinal=2, summary="x")
    graph = _graph(
        (c1, summary),
        (
            _rel("r-c", summary, c1, RelationKind.COMPACTED_RANGE),
            _rel("r-r", summary, c1, RelationKind.RETAINED_FROM),
        ),
    )
    views = build_compaction_window_views(graph)
    assert len(views) == 1
    # both compacted and retained refs are exposed; the contradiction is slotted
    assert views[0].compacted_event_refs
    assert views[0].retained_event_refs
    assert views[0].contradictions


# ------------------------------------------------------------ SessionView

def test_session_view_retains_member_views_and_events(
    simple_turn_graph: EventGraph,
) -> None:
    member_views: tuple[DerivedView, ...] = (
        build_turn_views(simple_turn_graph)
        + build_native_trace_views(simple_turn_graph)
        + build_episode_views(simple_turn_graph)
        + build_compaction_window_views(simple_turn_graph)
    )
    views = build_session_views(simple_turn_graph, member_views)
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, SessionView)
    # lineage must include the member view ids
    view_ids = {v.view_id for v in member_views}
    assert view_ids <= set(view.lineage)
    # every session event appears in members/evidence
    event_ids = {e.event_id for e in simple_turn_graph.events}
    assert event_ids <= set(view.members)
    assert event_ids <= set(view.evidence_event_refs)


def test_session_view_surfaces_contradiction_slot() -> None:
    c1 = _ev("c1", EventKind.USER_MESSAGE, ordinal=1)
    summary = _ev("sum-1", EventKind.COMPACTION_SUMMARY, ordinal=2, summary="x")
    graph = _graph(
        (c1, summary),
        (
            _rel("r-c", summary, c1, RelationKind.COMPACTED_RANGE),
            _rel("r-r", summary, c1, RelationKind.RETAINED_FROM),
        ),
    )
    views = build_session_views(graph, ())
    assert len(views) == 1
    assert views[0].contradictions


def test_session_view_identity_collision_is_a_contradiction() -> None:
    # same native event id, different canonical event ids -> identity collision
    e1 = _ev("same-native", EventKind.USER_MESSAGE, ordinal=1)
    e2 = TypedEvent(
        event_id=make_event_id("codex", "art-b", "1", "same-native"),
        session_id="s-1",
        kind=EventKind.ASSISTANT_MESSAGE,
        provenance=_prov("same-native", "jsonl:dup"),
        fidelity=FidelityProfile.complete(),
        ordinal=2,
    )
    graph = _graph((e1, e2), sessions=(_session(),))
    views = build_session_views(graph, ())
    assert len(views) == 1
    assert any(
        c.kind == "native_id_collision" for c in views[0].contradictions
    )


# -------------------------------------------------------------- TopicView

def test_topic_view_derived_from_compaction_and_file_anchors(
    compaction_graph: EventGraph,
) -> None:
    views = build_topic_views(compaction_graph)
    # one summary anchor => at least one topic view
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, TopicView)
    assert view.topic_key
    # topic lineage retains the summary and its evidence events
    assert "sum-1" in " ".join(
        ev for ev in view.lineage
    ) or any("sum-1" in x for x in view.lineage)


def test_topic_view_uses_file_context_anchor() -> None:
    fc = _ev("fc-1", EventKind.FILE_CONTEXT, ordinal=1, native_payload_ref="src/a.py")
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    graph = _graph(
        (fc, m1),
        (_rel("r-fc", fc, m1, RelationKind.PARENT_CHILD),),
    )
    views = build_topic_views(graph)
    assert len(views) == 1
    assert "file:" in views[0].topic_key
    assert fc.event_id in views[0].evidence_event_refs


def test_topic_view_none_without_anchors() -> None:
    a = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=1)
    b = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=2)
    assert build_topic_views(_graph((a, b))) == ()


# ------------------------------------------------------ CrossSessionView

def test_cross_session_view_links_by_crosswalk_relation() -> None:
    sa = _ev("sa-1", EventKind.USER_MESSAGE, ordinal=1, session_id="s-a")
    sb = _ev("sb-1", EventKind.ASSISTANT_MESSAGE, ordinal=1, session_id="s-b")
    graph = _graph(
        (sa, sb),
        (
            _rel(
                "r-x",
                sa,
                sb,
                RelationKind.SOURCE_SESSION_CROSSWALK,
            ),
        ),
        sessions=(_session("s-a"), _session("s-b")),
    )
    views = build_cross_session_views(graph)
    assert len(views) == 1
    view = views[0]
    assert isinstance(view, CrossSessionView)
    assert set(view.session_ids) == {"s-a", "s-b"}
    assert sa.event_id in view.evidence_event_refs
    assert sb.event_id in view.evidence_event_refs


def test_cross_session_native_id_collision_is_a_contradiction() -> None:
    # distinct canonical event ids (different artifacts) but the same native
    # event id across two sessions => deterministic cross-session collision
    sa = TypedEvent(
        event_id=make_event_id("codex", "art-a", "1", "same-native"),
        session_id="s-a",
        kind=EventKind.USER_MESSAGE,
        provenance=_prov("same-native", "jsonl:sa", native_session_id="s-a"),
        fidelity=FidelityProfile.complete(),
        ordinal=1,
    )
    sb = TypedEvent(
        event_id=make_event_id("codex", "art-b", "1", "same-native"),
        session_id="s-b",
        kind=EventKind.ASSISTANT_MESSAGE,
        provenance=Provenance(
            artifact_id="art-b",
            artifact_hash="h" * 8,
            native_locator="jsonl:sb",
            native_session_id="s-b",
            native_event_id="same-native",
            contract_version="1",
        ),
        fidelity=FidelityProfile.complete(),
        ordinal=1,
    )
    graph = _graph(
        (sa, sb),
        (),
        sessions=(_session("s-a"), _session("s-b")),
    )
    views = build_cross_session_views(graph)
    assert len(views) == 1
    assert any(
        c.kind == "native_id_collision" for c in views[0].contradictions
    )


def test_cross_session_view_none_without_links() -> None:
    sa = _ev("sa-1", EventKind.USER_MESSAGE, ordinal=1, session_id="s-a")
    sb = _ev("sb-1", EventKind.ASSISTANT_MESSAGE, ordinal=1, session_id="s-b")
    graph = _graph((sa, sb), sessions=(_session("s-a"), _session("s-b")))
    assert build_cross_session_views(graph) == ()


# ------------------------------------------------------------ build_all

def test_build_all_returns_all_seven_view_types() -> None:
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    c1 = _ev("c1", EventKind.USER_MESSAGE, ordinal=3)
    summary = _ev("sum-1", EventKind.COMPACTION_SUMMARY, ordinal=4, summary="c")
    other = _ev("o-1", EventKind.ASSISTANT_MESSAGE, ordinal=1, session_id="s-b")
    graph = _graph(
        (loop, m1, c1, summary, other),
        (
            _rel("r-l", loop, m1, RelationKind.TURN_MEMBERSHIP),
            _rel("r-c", summary, c1, RelationKind.COMPACTED_RANGE),
            _rel(
                "r-x",
                summary,
                other,
                RelationKind.SOURCE_SESSION_CROSSWALK,
            ),
        ),
        sessions=(_session(), _session("s-b")),
    )
    result = build_all_views(graph)
    assert isinstance(result, ViewBuildResult)
    assert result.generation_id == "gen-1"
    assert result.builder_version == BUILDER_VERSION
    by_type = {v.view_type: v for v in result.views}
    assert set(by_type) == set(ViewType)
    assert result.digest


def test_build_all_is_deterministic_and_rebuildable() -> None:
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    graph = _graph(
        (loop, m1),
        (_rel("r-l", loop, m1, RelationKind.TURN_MEMBERSHIP),),
    )
    a = build_all_views(graph)
    b = build_all_views(graph)
    assert a.digest == b.digest
    assert [v.view_id for v in a.views] == [v.view_id for v in b.views]
    assert view_set_digest(a) == view_set_digest(b)


def test_build_all_snapshot_does_not_need_re_adapter() -> None:
    # rebuilding from the same immutable event snapshot yields the same views
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    graph = _graph((loop, m1), (_rel("r-l", loop, m1, RelationKind.TURN_MEMBERSHIP),))
    a = build_all_views(graph)
    assert build_all_views(graph).digest == a.digest


def test_build_all_changes_digest_when_policy_evidence_changes() -> None:
    loop = _ev("loop-1", EventKind.LOOP_BOUNDARY, ordinal=1)
    m1 = _ev("msg-1", EventKind.USER_MESSAGE, ordinal=2)
    m2 = _ev("msg-2", EventKind.ASSISTANT_MESSAGE, ordinal=3)
    graph_a = _graph((loop, m1), (_rel("r-l", loop, m1, RelationKind.TURN_MEMBERSHIP),))
    graph_b = _graph(
        (loop, m1, m2),
        (
            _rel("r-l", loop, m1, RelationKind.TURN_MEMBERSHIP),
            _rel("r-l2", loop, m2, RelationKind.TURN_MEMBERSHIP),
        ),
    )
    assert build_all_views(graph_a).digest != build_all_views(graph_b).digest


def test_builder_error_on_unknown_relation_or_event() -> None:
    b = _ev("tb-1", EventKind.TURN_BOUNDARY, ordinal=1)
    ghost = TypedEvent(
        event_id="ghost-event",
        session_id="s-1",
        kind=EventKind.USER_MESSAGE,
        provenance=_prov("ghost", "jsonl:ghost"),
        fidelity=FidelityProfile.complete(),
    )
    # the event graph is the validation boundary: a relation referencing an
    # event outside the generation is rejected at construction
    with pytest.raises(ViewBuilderError):
        _graph(
            (b,),
            (_rel("r-ghost", b, ghost, RelationKind.TURN_MEMBERSHIP),),
        )


def test_contradiction_ids_are_deterministic() -> None:
    a = make_contradiction_id("native_id_collision", "ev-x", "ev-y")
    b = make_contradiction_id("native_id_collision", "ev-x", "ev-y")
    assert a == b
    # a contradiction between two events is symmetric: argument order never
    # changes the deterministic id
    assert make_contradiction_id("native_id_collision", "ev-y", "ev-x") == a
    assert make_contradiction_id("native_id_collision", "ev-x", "ev-z") != a
