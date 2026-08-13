"""Phase 62-03: Grok multi-file session directory adapter (family ``grok``).

Grok exports a multi-file session directory (summary, transcript, events,
updates, compaction/checkpoint/recap files, subagents, terminal —
62-RESEARCH format matrix). Capture snapshots a declared allowlisted file
set; this adapter preserves cross-file relationships as typed relations and
reports summary-only fidelity as partial, never complete.
"""

from __future__ import annotations

import json
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.contracts import (
    AdaptationResult,
    CapabilityDescriptor,
    SourceArtifact,
    SourceArtifactSet,
)
from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventContractError,
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

FAMILY = "grok"
ADAPTER_VERSION = "1.0.0"
CONTRACT_VERSION = "1"

# Declared allowlist for the directory capture (D-08): conversation files only.
ALLOWED_RELATIVE_PATHS: tuple[str, ...] = (
    "summary.json",
    "summary.md",
    "chat_history.jsonl",
    "events.jsonl",
    "updates.jsonl",
    "compaction.md",
    "checkpoint.json",
    "recap.md",
    "requests.jsonl",
    "subagents.json",
    "terminal.jsonl",
)

_COMPLETE = {
    FidelityDimension.SOURCE_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.ORDERING_CONFIDENCE: FidelityLevel.COMPLETE,
    FidelityDimension.RELATION_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.COMPACTION_VISIBILITY: FidelityLevel.COMPLETE,
    FidelityDimension.NATIVE_ID_STABILITY: FidelityLevel.COMPLETE,
}


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(
            EventKind.SESSION_LIFECYCLE, EventKind.USER_MESSAGE,
            EventKind.ASSISTANT_MESSAGE, EventKind.COMPACTION_SUMMARY,
            EventKind.SUBAGENT_BOUNDARY, EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(RelationKind.SOURCE_SESSION_CROSSWALK,),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "multi_file_session_directory",
            "allowlist": ",".join(ALLOWED_RELATIVE_PATHS),
            "summary_only_fidelity": "partial",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """True when the artifact set contains the Grok summary marker."""
    if artifact.source_kind != "file":
        return False
    if Path(artifact.relative_path).name not in (
        "summary.json", "summary.md", "chat_history.jsonl"
    ):
        return False
    try:
        head = (artifact_root / artifact.artifact_id).read_text(encoding="utf-8")[:512]
    except OSError:
        return False
    return (
        "# Summary" in head or "grok_session" in head or '"role"' in head
        or '"session_summary"' in head
    )


def _provenance(artifact: SourceArtifact, locator: str, *, session: str | None, native_id: str | None) -> Provenance:
    return Provenance(
        artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
        native_locator=locator, native_session_id=session or None,
        native_event_id=native_id, contract_version=CONTRACT_VERSION,
    )


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id),
        session_id=session_id, kind=kind,
        provenance=_provenance(artifact, locator, session=native_session, native_id=native_id),
        fidelity=fidelity or _fidelity(), occurred_at=occurred_at, summary=summary,
    )


def _read_jsonl_blob(root: Path, artifact: SourceArtifact) -> list[dict]:
    try:
        text = (root / artifact.artifact_id).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one captured Grok session directory into typed events/relations."""
    if not artifact_set.artifacts:
        raise EventContractError(f"{FAMILY} adapter requires at least one artifact")
    artifacts = artifact_set.artifacts
    by_path = {Path(a.relative_path).name: a for a in artifacts}

    session_id = make_event_id(FAMILY, artifacts[0].artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator="session")
    events: list[TypedEvent] = []
    relations: list[EventRelation] = []
    warnings: list[str] = []
    native_session = None

    summary_artifact = by_path.get("summary.md")
    if summary_artifact is not None:
        try:
            summary_text = (artifact_root / summary_artifact.artifact_id).read_text(encoding="utf-8")
        except OSError:
            summary_text = ""
        native_session = _first_line(summary_text)
        events.append(_event(summary_artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                             locator="summary.md#doc", native_id="summary",
                             summary=summary_text[:2048] or None, native_session=native_session))

    summary_json = by_path.get("summary.json")
    if summary_json is not None:
        try:
            doc = json.loads(
                (artifact_root / summary_json.artifact_id).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            doc = {}
        info = doc.get("info") if isinstance(doc.get("info"), dict) else {}
        native_session = str(info.get("id") or Path(summary_json.relative_path).parent.name)
        session_id = make_event_id(
            FAMILY, summary_json.artifact_id, CONTRACT_VERSION, native_session,
            kind=EventKind.SESSION_LIFECYCLE,
        )
        events.append(_event(
            summary_json, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
            locator=f"{summary_json.relative_path}#info", native_id=native_session,
            occurred_at=doc.get("created_at"), native_session=native_session,
        ))
        if doc.get("session_summary"):
            events.append(_event(
                summary_json, session_id=session_id,
                kind=EventKind.COMPACTION_SUMMARY,
                locator=f"{summary_json.relative_path}#session_summary",
                native_id=f"{native_session}:summary",
                occurred_at=doc.get("updated_at"),
                summary=str(doc.get("session_summary"))[:2048],
                fidelity=_fidelity(
                    CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                    STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                    RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                ),
                native_session=native_session,
            ))

    chat = by_path.get("chat_history.jsonl")
    if chat is not None:
        for index, row in enumerate(_read_jsonl_blob(artifact_root, chat)):
            role = row.get("role")
            kind = EventKind.USER_MESSAGE if role == "user" else (
                EventKind.ASSISTANT_MESSAGE if role in ("assistant", "model") else None)
            locator = f"chat_history.jsonl#{index}"
            if kind is None:
                events.append(_event(chat, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                                     locator=locator, native_id=row.get("id") or f"row-{index}",
                                     occurred_at=row.get("timestamp"),
                                     fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                                        RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                                        CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                                     native_session=native_session))
                continue
            events.append(_event(chat, session_id=session_id, kind=kind, locator=locator,
                                 native_id=row.get("id") or f"row-{index}",
                                 occurred_at=row.get("timestamp"),
                                 summary=str(row.get("content") or "")[:2048] or None,
                                 native_session=native_session))

    # Compaction: a markdown/checkpoint file is a typed compaction summary.
    for name in ("compaction.md", "checkpoint.json", "recap.md"):
        artifact = by_path.get(name)
        if artifact is None:
            continue
        try:
            text = (artifact_root / artifact.artifact_id).read_text(encoding="utf-8")
        except OSError:
            continue
        events.append(_event(artifact, session_id=session_id, kind=EventKind.COMPACTION_SUMMARY,
                             locator=f"{name}#doc", native_id=name,
                             summary=text[:2048] or None, native_session=native_session))

    # Subagents: cross-file relation from subagent entries to the parent session.
    sub_artifact = by_path.get("subagents.json")
    if sub_artifact is not None:
        try:
            sub_doc = json.loads((artifact_root / sub_artifact.artifact_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sub_doc = []
        subs = sub_doc if isinstance(sub_doc, list) else sub_doc.get("subagents", [])
        parent = next((e for e in events if e.kind is EventKind.SESSION_LIFECYCLE), None)
        for index, sub in enumerate(subs if isinstance(subs, list) else []):
            if not isinstance(sub, dict):
                continue
            ev = _event(sub_artifact, session_id=session_id, kind=EventKind.SUBAGENT_BOUNDARY,
                        locator=f"subagents.json#{index}", native_id=sub.get("id") or f"sub-{index}",
                        occurred_at=sub.get("created_at"),
                        summary=str(sub.get("name") or sub.get("task") or "")[:256] or None,
                        native_session=native_session)
            events.append(ev)
            if parent is not None:
                relations.append(EventRelation(
                    relation_id=make_event_id(FAMILY, sub_artifact.artifact_id, CONTRACT_VERSION,
                                              f"rel-cross:{ev.event_id}:{parent.event_id}"),
                    source_event_id=ev.event_id, target_event_id=parent.event_id,
                    relation_kind=RelationKind.SOURCE_SESSION_CROSSWALK,
                ))

    # Fidelity: summary-only is honest partial; a chat history file raises content fidelity.
    has_chat = chat is not None
    content_level = FidelityLevel.COMPLETE if has_chat else FidelityLevel.PARTIAL
    structure_level = FidelityLevel.COMPLETE if (has_chat or summary_artifact is not None) else FidelityLevel.PARTIAL

    sessions: list[AdaptedSession] = []
    if summary_artifact is not None:
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(summary_artifact, "summary.md#doc",
                                   session=native_session, native_id="summary"),
            fidelity=_fidelity(CONTENT_AVAILABILITY=content_level),
            native_session_id=native_session,
        ))
    elif summary_json is not None:
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(
                summary_json, f"{summary_json.relative_path}#info",
                session=native_session, native_id=native_session,
            ),
            fidelity=_fidelity(
                CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
            ),
            native_session_id=native_session,
            started_at=doc.get("created_at") if isinstance(doc, dict) else None,
            ended_at=doc.get("updated_at") if isinstance(doc, dict) else None,
        ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=tuple(sorted(artifacts, key=lambda a: a.artifact_id)),
        events=tuple(events),
        fidelity=_fidelity(CONTENT_AVAILABILITY=content_level, STRUCTURE_COMPLETENESS=structure_level),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:128]
    return None
