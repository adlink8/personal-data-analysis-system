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
from personal_knowledge.adapters.conversation_sources.agentsview_pathless import (
    adapt_pathless_observation,
)
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

FAMILY = "grok"
ADAPTER_VERSION = "1.1.0"
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
            EventKind.ASSISTANT_MESSAGE, EventKind.DEVELOPER_MESSAGE,
            EventKind.SYSTEM_MESSAGE, EventKind.COMPACTION_SUMMARY,
            EventKind.SUBAGENT_BOUNDARY, EventKind.USAGE,
            EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(
            RelationKind.SOURCE_SESSION_CROSSWALK,
            RelationKind.COMPACTED_RANGE,
        ),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "multi_file_session_directory|agentsview_pathless_observation",
            "allowlist": ",".join(ALLOWED_RELATIVE_PATHS),
            "summary_only_fidelity": "partial",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """True when the artifact set contains the Grok summary marker."""
    if artifact.source_kind == "sqlite":
        relative = (artifact.relative_path or "").lower()
        return "sessions.db" in relative or "agentsview" in relative
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
           content=None, summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id),
        session_id=session_id, kind=kind,
        provenance=_provenance(artifact, locator, session=native_session, native_id=native_id),
        fidelity=fidelity or _fidelity(), occurred_at=occurred_at,
        content=content, summary=summary,
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
    if (
        len(artifact_set.artifacts) == 1
        and artifact_set.artifacts[0].source_kind == "sqlite"
    ):
        return adapt_pathless_observation(
            artifact_set, artifact_root=artifact_root, family=FAMILY,
            adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        )
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
            source_content = row.get("content")
            exact_content = None if source_content is None else str(source_content)
            events.append(_event(chat, session_id=session_id, kind=kind, locator=locator,
                                 native_id=row.get("id") or f"row-{index}",
                                 occurred_at=row.get("timestamp"),
                                 content=exact_content,
                                 native_session=native_session))
            usage_summary = _row_usage_summary(row)
            if usage_summary:
                events.append(_event(
                    chat, session_id=session_id, kind=EventKind.USAGE,
                    locator=f"chat_history.jsonl#usage:{index}",
                    native_id=f"{row.get('id') or f'row-{index}'}:usage",
                    occurred_at=row.get("timestamp"), content=None,
                    summary=usage_summary,
                    fidelity=_fidelity(CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                    native_session=native_session,
                ))

    # Compaction: a markdown/checkpoint file is a typed compaction summary.
    for name in ("compaction.md", "checkpoint.json", "recap.md"):
        artifact = by_path.get(name)
        if artifact is None:
            continue
        try:
            text = (artifact_root / artifact.artifact_id).read_text(encoding="utf-8")
        except OSError:
            continue
        compactor = _event(artifact, session_id=session_id, kind=EventKind.COMPACTION_SUMMARY,
                           locator=f"{name}#doc", native_id=name,
                           summary=text[:2048] or None, native_session=native_session)
        events.append(compactor)
        # Best-effort COMPACTED_RANGE: link the compaction to the last preceding
        # non-compaction event so the range references real, known endpoints.
        prior = _last_preceding_non_compaction(events, compactor.event_id)
        if prior is not None:
            relations.append(EventRelation(
                relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-compact:{compactor.event_id}:{prior.event_id}"),
                source_event_id=prior.event_id, target_event_id=compactor.event_id,
                relation_kind=RelationKind.COMPACTED_RANGE,
            ))
        else:
            compactor = _with_disposition(
                compactor,
                field_name="compacted_range",
                disposition=FieldDisposition.UNSUPPORTED,
                reason="no preceding event locatable to anchor a compacted range",
            )
            events[-1] = compactor

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
            cwd=_grok_cwd(info),
            model=_grok_model(doc, info, artifact_root, chat),
            git_branch=_grok_branch(info, doc),
            title=_grok_title(info, doc),
        ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=tuple(sorted(artifacts, key=lambda a: a.artifact_id)),
        events=tuple(events),
        fidelity=_fidelity(CONTENT_AVAILABILITY=content_level, STRUCTURE_COMPLETENESS=structure_level),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )


_USAGE_ALIASES = {
    "input_tokens": ("input_tokens", "inputTokens", "prompt_tokens", "input"),
    "output_tokens": ("output_tokens", "outputTokens", "completion_tokens", "output"),
    "cache_read": ("cache_read", "cacheRead"),
    "cache_write": ("cache_write", "cacheWrite"),
    "total_tokens": ("total_tokens", "totalTokens"),
}


def _grok_cwd(info: dict) -> str | None:
    """Working directory from summary.json ``info``.

    The native Grok export puts the project path in ``info.cwd``; older/other
    variants use ``info.project``. Support both so a schema rename does not
    silently drop the session working directory.
    """
    if not isinstance(info, dict):
        return None
    candidate = info.get("cwd")
    if candidate is None:
        candidate = info.get("project")
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _grok_model(doc: dict, info: dict, artifact_root: Path, chat) -> str | None:
    """Model id for the session.

    Prefer the native summary.json ``current_model_id`` (top-level, confirmed
    in real exports) over an ``info.model`` variant; fall back to the first
    model id observed in the chat_history transcript
    (``model_id``/``model``/``modelID``). The summary-native source is the
    authoritative current model, so it wins over a possibly-stale row-level
    model.
    """
    for source in (doc, info):
        if not isinstance(source, dict):
            continue
        candidate = source.get("current_model_id") or source.get("model")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:256]
    if chat is None:
        return None
    try:
        rows = _read_jsonl_blob(artifact_root, chat)
    except Exception:
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("model_id") or row.get("model") or row.get("modelID")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:256]
    return None


def _grok_branch(info: dict, doc: dict) -> str | None:
    """Git branch for the session from summary.json ``head_branch``.

    Real Grok exports put the branch at top-level ``head_branch``; some
    variants keep it under ``info``. Support both so a schema rename never
    silently drops the branch.
    """
    for source in (doc, info):
        if not isinstance(source, dict):
            continue
        candidate = source.get("head_branch")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()[:256]
    return None



def _grok_title(info: dict, doc: dict) -> str | None:
    """Session title: explicit title, else a bounded session_summary fallback."""
    title = info.get("title") if isinstance(info, dict) else None
    if isinstance(title, str) and title.strip():
        return title.strip()[:256]
    summary = doc.get("session_summary") if isinstance(doc, dict) else None
    if isinstance(summary, str) and summary.strip():
        return summary.strip()[:256]
    return None


def _row_usage_summary(row: dict) -> str | None:
    # Machine-parseable canonical usage summary from a chat_history row.
    # Surfaces a top-level "usage" dict and/or token fields directly on the
    # row, mapping native counters onto the canonical grammar input_tokens=X
    # output_tokens=Y [cache_read=Z cache_write=W] (only present, integers).
    usage = row.get("usage")
    data = {}
    if isinstance(usage, dict):
        data = usage
    elif isinstance(usage, (int, float)):
        data = {"usage": usage}
    for key in row:
        if key in _USAGE_ALIASES or any(
            key in aliases for aliases in _USAGE_ALIASES.values()
        ):
            if key not in data and isinstance(row[key], (int, float)):
                data[key] = row[key]
    counters: dict[str, int] = {}
    for native, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        for canonical, aliases in _USAGE_ALIASES.items():
            if native in aliases:
                counters.setdefault(canonical, int(value))
                break
    if not counters:
        return None
    return " ".join(
        f"{key}={counters[key]}" for key in _USAGE_ALIASES if key in counters
    )


def _last_preceding_non_compaction(events, current_id):
    """Return the last event emitted before ``current_id`` that is not a compaction."""
    for ev in reversed(events):
        if ev.event_id == current_id:
            continue
        if ev.kind is EventKind.COMPACTION_SUMMARY:
            continue
        return ev
    return None


def _with_disposition(event, *, field_name, disposition, reason):
    """Rebuild a frozen TypedEvent adding one field disposition."""
    return TypedEvent(
        event_id=event.event_id, session_id=event.session_id, kind=event.kind,
        provenance=event.provenance, fidelity=event.fidelity,
        field_dispositions=event.field_dispositions + (
            FieldDispositionRecord(
                field_name=field_name, disposition=disposition, reason=reason,
            ),
        ),
        occurred_at=event.occurred_at, ordinal=event.ordinal,
        native_payload_ref=event.native_payload_ref,
        content=event.content, summary=event.summary,
    )


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:128]
    return None
