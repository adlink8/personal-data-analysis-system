"""Phase 62-03: ChatGPT compatibility-observation adapter (family ``chatgpt``).

Current ChatGPT rows in AgentsView lack a recoverable native artifact path
(62-RESEARCH format matrix). This adapter emits an honest
compatibility-observation result bound to the AgentsView snapshot:
native reconstruction is declared unavailable, source/structure fidelity
can never be full (D-14), and no complete-looking transcript is fabricated.
"""

from __future__ import annotations

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
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    TypedEvent,
    make_event_id,
)

FAMILY = "chatgpt"
ADAPTER_VERSION = "1.0.0"
CONTRACT_VERSION = "1"


def _fidelity() -> FidelityProfile:
    """ChatGPT has no recoverable native artifact: structure/content are
    explicitly unavailable, never reported as complete (D-14)."""
    return FidelityProfile.from_levels({
        FidelityDimension.SOURCE_AVAILABILITY: FidelityLevel.UNAVAILABLE,
        FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.UNAVAILABLE,
        FidelityDimension.ORDERING_CONFIDENCE: FidelityLevel.UNKNOWN,
        FidelityDimension.RELATION_COMPLETENESS: FidelityLevel.UNAVAILABLE,
        FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.UNAVAILABLE,
        FidelityDimension.COMPACTION_VISIBILITY: FidelityLevel.UNKNOWN,
        FidelityDimension.NATIVE_ID_STABILITY: FidelityLevel.UNAVAILABLE,
    })


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(EventKind.SESSION_LIFECYCLE,),
        supported_relation_kinds=(),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "agentsview_rows_without_native_path",
            "native_reconstruction": "unavailable",
            "observation_only": "true",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """Compatibility observations bind to the AgentsView snapshot artifact."""
    return "agentsview" in (artifact.relative_path or "").lower()


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Emit an honest compatibility-observation result; never fabricate a
    native transcript."""
    if not artifact_set.artifacts:
        raise EventContractError(f"{FAMILY} adapter requires an AgentsView snapshot artifact")
    artifact = artifact_set.artifacts[0]
    session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator="agentsview")
    events: list[TypedEvent] = []
    sessions: list[AdaptedSession] = []

    # One lifecycle marker with native reconstruction explicitly unavailable.
    events.append(TypedEvent(
        event_id=session_id,
        session_id=session_id,
        kind=EventKind.SESSION_LIFECYCLE,
        provenance=Provenance(
            artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
            native_locator=f"{artifact.relative_path}#agentsview",
            native_session_id=None, native_event_id=None, contract_version=CONTRACT_VERSION,
        ),
        fidelity=_fidelity(),
        summary="ChatGPT compatibility observation: no recoverable native artifact path",
    ))
    sessions.append(AdaptedSession(
        session_id=session_id,
        provenance=Provenance(
            artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
            native_locator=f"{artifact.relative_path}#agentsview",
            native_session_id=None, native_event_id=None, contract_version=CONTRACT_VERSION,
        ),
        fidelity=_fidelity(),
    ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events), fidelity=_fidelity(),
        sessions=tuple(sessions), relations=(), warnings=(
            "native reconstruction unavailable; AgentsView text is a compatibility observation only",
        ),
    )
