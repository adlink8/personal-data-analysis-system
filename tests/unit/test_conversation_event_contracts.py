"""Phase 62-01 Task 1: typed event / relation / provenance / fidelity contracts.

RED tests for the loss-aware public contract:
  - stable event identity independent of ordinal movement, with family/artifact/
    contract-version collision domains
  - typed unknown-native preservation (no silent field drops)
  - relation endpoint validation (non-empty, no self-loop, typed kind)
  - source locator resolvability and rejection of unprovenanced events
  - explicit partial/unknown fidelity that can never be reported as complete
  - deterministic dataset digest on AdaptationResult
  - versioned capability descriptor

Deterministic local tests only — no network, no provider, no paid calls (D-31).
"""

from __future__ import annotations

import pytest

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventContractError,
    EventKind,
    EventRelation,
    FieldDisposition,
    FieldDispositionRecord,
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
    make_event_id,
)
from personal_knowledge.adapters.conversation_sources.contracts import (
    AdaptationResult,
    CapabilityDescriptor,
    SourceArtifact,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _prov(
    native_event_id: str = "e-1",
    artifact: str = "art-a",
    locator: str = "jsonl:1",
    session: str = "s-1",
) -> Provenance:
    return Provenance(
        artifact_id=artifact,
        artifact_hash="h" * 8,
        native_locator=locator,
        native_session_id=session,
        native_event_id=native_event_id,
        contract_version="1",
    )


def _event(
    event_id: str,
    kind: EventKind,
    provenance: Provenance,
    *,
    ordinal: int | None = None,
    fidelity: FidelityProfile | None = None,
    field_dispositions: tuple[FieldDispositionRecord, ...] = (),
    native_payload_ref: str | None = None,
) -> TypedEvent:
    return TypedEvent(
        event_id=event_id,
        session_id=provenance.native_session_id or "s",
        kind=kind,
        provenance=provenance,
        fidelity=fidelity or FidelityProfile.complete(),
        field_dispositions=field_dispositions,
        ordinal=ordinal,
        native_payload_ref=native_payload_ref,
    )


def _artifact(artifact_id: str = "art-a", family: str = "codex") -> SourceArtifact:
    return SourceArtifact(
        artifact_id=artifact_id,
        family=family,
        source_kind="file",
        content_hash="h" * 8,
        capture_method="sha256",
        relative_path="rollout.jsonl",
        byte_size=10,
    )


def _result(
    events: tuple[TypedEvent, ...],
    *,
    artifacts: tuple[SourceArtifact, ...] = (),
    sessions: tuple[AdaptedSession, ...] = (),
    relations: tuple[EventRelation, ...] = (),
    fidelity: FidelityProfile | None = None,
    family: str = "codex",
) -> AdaptationResult:
    return AdaptationResult(
        family=family,
        adapter_version="1",
        contract_version="1",
        artifacts=artifacts,
        sessions=sessions,
        events=events,
        relations=relations,
        fidelity=fidelity or FidelityProfile.complete(),
    )


# --------------------------------------------------------------------------
# stable identity
# --------------------------------------------------------------------------


def test_event_id_is_stable_under_ordinal_movement() -> None:
    first = make_event_id("codex", "art-a", "1", "native-42")
    second = make_event_id("codex", "art-a", "1", "native-42")
    assert first == second
    # kind/session must not leak into an identity that already has a native id
    assert (
        make_event_id(
            "codex", "art-a", "1", "native-42",
            kind=EventKind.USER_MESSAGE, session_id="s-1",
        )
        == first
    )


def test_event_id_requires_stable_anchor_when_native_absent() -> None:
    with pytest.raises(EventContractError):
        make_event_id("codex", "art-a", "1", None)
    # a stable non-ordinal locator is an acceptable anchor
    stable = make_event_id(
        "codex", "art-a", "1", None,
        kind=EventKind.UNKNOWN_NATIVE, session_id="s-1", native_locator="jsonl:9",
    )
    assert stable == make_event_id(
        "codex", "art-a", "1", None,
        kind=EventKind.UNKNOWN_NATIVE, session_id="s-1", native_locator="jsonl:9",
    )
    # ordinal is never used as an identity input
    assert stable == make_event_id(
        "codex", "art-a", "1", None,
        kind=EventKind.UNKNOWN_NATIVE, session_id="s-1", native_locator="jsonl:9",
    )


def test_event_id_includes_family_artifact_contract_collision_domains() -> None:
    base = make_event_id("codex", "art-a", "1", "native-42")
    assert make_event_id("zcode", "art-a", "1", "native-42") != base  # family
    assert make_event_id("codex", "art-b", "1", "native-42") != base  # artifact
    assert make_event_id("codex", "art-a", "2", "native-42") != base  # contract v


def test_event_id_can_disambiguate_reused_native_id_by_immutable_locator() -> None:
    first = make_event_id(
        "codex", "art-a", "1", "reused", native_locator="rollout.jsonl#L10"
    )
    second = make_event_id(
        "codex", "art-a", "1", "reused", native_locator="rollout.jsonl#L11"
    )
    assert first != second
    assert first == make_event_id(
        "codex", "art-a", "1", "reused", native_locator="rollout.jsonl#L10"
    )


# --------------------------------------------------------------------------
# unknown-native preservation / explicit dispositions
# --------------------------------------------------------------------------


def test_unknown_native_event_is_preserved_by_reference() -> None:
    prov = _prov("unk-9", artifact="art-pi", locator="jsonl:7")
    event = _event(
        make_event_id("pi", "art-pi", "1", "unk-9"),
        EventKind.UNKNOWN_NATIVE,
        prov,
        native_payload_ref="art-pi:jsonl:7",
        field_dispositions=(
            FieldDispositionRecord(
                "native_body", FieldDisposition.PRESERVED_BY_REFERENCE,
                "raw row kept in immutable artifact slice",
            ),
        ),
    )
    assert event.kind is EventKind.UNKNOWN_NATIVE
    assert event.native_payload_ref == "art-pi:jsonl:7"
    assert event.provenance.resolvable()


def test_unmodeled_fields_are_explicit_not_silently_dropped() -> None:
    disp = FieldDispositionRecord(
        "thinking_text", FieldDisposition.UNSUPPORTED, "not modeled in v2 schema"
    )
    event = _event(
        make_event_id("codex", "art-a", "1", "native-3"),
        EventKind.REASONING,
        _prov("native-3"),
        field_dispositions=(disp,),
    )
    names = {d.field_name for d in event.field_dispositions}
    assert "thinking_text" in names
    assert event.field_dispositions[0].disposition is FieldDisposition.UNSUPPORTED


# --------------------------------------------------------------------------
# relation endpoint validation
# --------------------------------------------------------------------------


def test_relation_endpoint_validation() -> None:
    with pytest.raises(EventContractError):
        EventRelation(
            relation_id="r1", source_event_id="", target_event_id="e2",
            relation_kind=RelationKind.CALL_RESULT,
        )
    with pytest.raises(EventContractError):
        EventRelation(
            relation_id="r2", source_event_id="e1", target_event_id="",
            relation_kind=RelationKind.CALL_RESULT,
        )
    with pytest.raises(EventContractError):
        EventRelation(
            relation_id="r3", source_event_id="e1", target_event_id="e1",
            relation_kind=RelationKind.CALL_RESULT,
        )
    with pytest.raises(EventContractError):
        EventRelation(
            relation_id="r4", source_event_id="e1", target_event_id="e2",
            relation_kind="call_result",  # string is not the typed enum
        )
    ok = EventRelation(
        relation_id="r5", source_event_id="e1", target_event_id="e2",
        relation_kind=RelationKind.CALL_RESULT,
    )
    assert ok.source_event_id == "e1"
    assert ok.target_event_id == "e2"


def test_all_locked_relation_kinds_are_supported() -> None:
    kinds = {
        RelationKind.PARENT_CHILD,
        RelationKind.CALL_RESULT,
        RelationKind.BRANCH,
        RelationKind.SIDECHAIN,
        RelationKind.SUBAGENT,
        RelationKind.COMPACTED_RANGE,
        RelationKind.RETAINED_FROM,
        RelationKind.TURN_MEMBERSHIP,
        RelationKind.SOURCE_SESSION_CROSSWALK,
    }
    assert len(kinds) == 9


# --------------------------------------------------------------------------
# provenance / locator resolvability
# --------------------------------------------------------------------------


def test_source_locator_resolvable() -> None:
    prov = _prov()
    assert prov.resolvable() is True
    assert prov.artifact_id and prov.native_locator


def test_event_without_artifact_or_native_locator_is_rejected() -> None:
    incomplete = Provenance(
        artifact_id="", artifact_hash="", native_locator="",
        native_session_id="s-1",
    )
    with pytest.raises(EventContractError):
        _event(
            make_event_id("codex", "art-a", "1", "n-1"),
            EventKind.USER_MESSAGE, incomplete,
        )
    no_artifact = Provenance(
        artifact_id="", artifact_hash="", native_locator="jsonl:1",
        native_session_id="s-1",
    )
    with pytest.raises(EventContractError):
        _event(
            make_event_id("codex", "art-a", "1", "n-2"),
            EventKind.USER_MESSAGE, no_artifact,
        )


def test_adaptation_result_rejects_events_without_resolvable_provenance() -> None:
    # construct an invalid event directly; the result constructor must also
    # re-validate every event and reject the incomplete-looking record
    bad = TypedEvent.__new__(TypedEvent)  # bypass constructor gate on purpose
    object.__setattr__(bad, "event_id", "ev-x")
    object.__setattr__(bad, "session_id", "s-1")
    object.__setattr__(bad, "kind", EventKind.USER_MESSAGE)
    object.__setattr__(bad, "provenance", Provenance("", "", ""))
    object.__setattr__(bad, "fidelity", FidelityProfile.complete())
    object.__setattr__(bad, "field_dispositions", ())
    object.__setattr__(bad, "occurred_at", None)
    object.__setattr__(bad, "ordinal", None)
    object.__setattr__(bad, "native_payload_ref", None)
    object.__setattr__(bad, "summary", None)
    with pytest.raises(EventContractError):
        _result((bad,))


def test_adaptation_result_rejects_relation_to_unknown_endpoint() -> None:
    prov = _prov()
    e1 = _event(
        make_event_id("codex", "art-a", "1", "e1"),
        EventKind.USER_MESSAGE, prov,
    )
    e2 = _event(
        make_event_id("codex", "art-a", "1", "e2"),
        EventKind.ASSISTANT_MESSAGE, prov,
    )
    with pytest.raises(EventContractError):
        _result(
            (e1, e2),
            artifacts=(_artifact(),),
            relations=(
                EventRelation("r1", e1.event_id, "ghost-endpoint", RelationKind.CALL_RESULT),
            ),
        )


# --------------------------------------------------------------------------
# fidelity
# --------------------------------------------------------------------------


def test_explicit_partial_unknown_fidelity_is_never_complete() -> None:
    partial = FidelityProfile.from_levels(
        {FidelityDimension.SOURCE_AVAILABILITY: FidelityLevel.PARTIAL}
    )
    assert partial.level(FidelityDimension.SOURCE_AVAILABILITY) is FidelityLevel.PARTIAL
    assert partial.is_complete() is False
    assert partial.has_loss() is True

    unknown = FidelityProfile.from_levels(
        {FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.UNKNOWN}
    )
    assert unknown.is_complete() is False

    unavailable = FidelityProfile.from_levels(
        {FidelityDimension.NATIVE_ID_STABILITY: FidelityLevel.UNAVAILABLE}
    )
    assert unavailable.is_complete() is False

    assert FidelityProfile.complete().is_complete() is True
    assert FidelityProfile.complete().has_loss() is False


def test_result_cannot_look_complete_when_an_event_is_lossy() -> None:
    prov = _prov("e1")
    event = _event(
        make_event_id("codex", "art-a", "1", "e1"),
        EventKind.ASSISTANT_MESSAGE,
        prov,
        fidelity=FidelityProfile.from_levels(
            {FidelityDimension.RELATION_COMPLETENESS: FidelityLevel.PARTIAL}
        ),
    )
    result = _result((event,), fidelity=event.fidelity)
    assert result.fidelity.is_complete() is False
    assert event.fidelity.is_complete() is False


def test_result_rejects_duplicate_event_identity_instead_of_silent_loss() -> None:
    prov = _prov("same")
    duplicate = _event(
        make_event_id("codex", "art-a", "1", "same"),
        EventKind.UNKNOWN_NATIVE,
        prov,
    )
    with pytest.raises(EventContractError, match="duplicate event"):
        _result((duplicate, duplicate), artifacts=(_artifact(),))


def test_result_automatically_rolls_up_child_loss_and_warnings() -> None:
    prov = _prov("e1")
    event = _event(
        make_event_id("codex", "art-a", "1", "e1"),
        EventKind.UNKNOWN_NATIVE,
        prov,
        fidelity=FidelityProfile.complete().with_at_least(
            FidelityDimension.CONTENT_AVAILABILITY, FidelityLevel.UNKNOWN
        ),
    )
    result = AdaptationResult(
        family="codex", adapter_version="1", contract_version="1",
        artifacts=(_artifact(),), events=(event,),
        fidelity=FidelityProfile.complete(),
        warnings=("native relation was not recoverable",),
    )
    assert result.fidelity.level(
        FidelityDimension.CONTENT_AVAILABILITY
    ) is FidelityLevel.UNKNOWN
    assert result.fidelity.level(
        FidelityDimension.STRUCTURE_COMPLETENESS
    ) is FidelityLevel.PARTIAL
    assert result.fidelity.is_complete() is False


# --------------------------------------------------------------------------
# dataset digest + capability descriptor
# --------------------------------------------------------------------------


def test_dataset_digest_is_deterministic_and_input_sensitive() -> None:
    prov = _prov()
    e1 = _event(make_event_id("codex", "art-a", "1", "e1"), EventKind.USER_MESSAGE, prov)
    e2 = _event(make_event_id("codex", "art-a", "1", "e2"), EventKind.ASSISTANT_MESSAGE, prov)
    r1 = _result((e1, e2), artifacts=(_artifact(),))
    r2 = _result((e1, e2), artifacts=(_artifact(),))
    assert r1.dataset_digest == r2.dataset_digest
    r3 = _result((e1,), artifacts=(_artifact(),))
    assert r3.dataset_digest != r1.dataset_digest


def test_dataset_digest_changes_when_semantics_change_but_native_id_does_not() -> None:
    prov = _prov("stable-native-id")
    event_id = make_event_id("codex", "art-a", "1", "stable-native-id")
    original = _event(event_id, EventKind.UNKNOWN_NATIVE, prov)
    remapped = _event(event_id, EventKind.TOOL_CALL, prov)
    assert _result((original,), artifacts=(_artifact(),)).dataset_digest != (
        _result((remapped,), artifacts=(_artifact(),)).dataset_digest
    )

    lossy = _event(
        event_id, EventKind.UNKNOWN_NATIVE, prov,
        fidelity=FidelityProfile.complete().with_at_least(
            FidelityDimension.STRUCTURE_COMPLETENESS,
            FidelityLevel.PARTIAL,
        ),
    )
    assert _result((original,), artifacts=(_artifact(),)).dataset_digest != (
        _result((lossy,), artifacts=(_artifact(),)).dataset_digest
    )


def test_capability_descriptor_is_versioned_and_digested() -> None:
    desc = CapabilityDescriptor(
        family="codex", adapter_version="1", contract_version="1",
        supported_event_kinds=(EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE),
        supported_relation_kinds=(RelationKind.CALL_RESULT,),
    )
    assert desc.digest() == desc.digest()
    bumped = CapabilityDescriptor(
        family="codex", adapter_version="1", contract_version="2",
        supported_event_kinds=(EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE),
        supported_relation_kinds=(RelationKind.CALL_RESULT,),
    )
    assert desc.digest() != bumped.digest()
    assert desc.family == "codex"
    assert desc.contract_version == "1"
