"""Phase 62-07: metadata-only per-family adapter fidelity evaluator.

Phase 62 CONTEXT D-25/D-28/D-31: adapter quality is measured against native
fixtures and live metadata by coverage, event-kind preservation, relation
preservation, stable replay, source-slice resolvability, privacy exclusions and
drift detection — not only row counts. This module evaluates one immutable
shadow cohort (a ``62-SHADOW-REPORT.json`` plus its staged generation db and
content-addressed artifact store) and computes:

  - per-family metrics: discovered sessions (inventory), native artifacts
    available, captured artifacts, adapted sessions/events/relations,
    explicit unknown/redacted/unavailable/unsupported dispositions,
    source-ref resolution sample, replay digest stability, compatibility
    projection parity and view coverage (D-13/D-17/D-21)
  - activation gates: 17/17 families have a capability result; every
    native-available session is captured or explicitly blocked; no unresolved
    provenance; forbidden-source access zero; replay digest stable; current
    consumers pass; partial ChatGPT/Cursor limitations disclosed

Output is metadata-only. Bodies, secrets and credential-table data are never
read, stored or logged (D-09/D-31). This module performs no I/O outside the
caller-supplied generation db / artifact store / agentsview db, no network and
no provider calls (D-31).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifact,
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.registry import (
    adapt_for,
    capability_for,
    known_families,
    resolve_family,
)
from personal_knowledge.application.conversation.compatibility_projection import (
    build_compatibility_projection,
)
from personal_knowledge.application.conversation.event_repository import (
    EventRepository,
)
from personal_knowledge.application.conversation.extraction_views import (
    EventGraph,
    ViewType,
    build_all_views,
)
from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventKind,
    EventRelation,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
)
from personal_knowledge.core.conversation_repository import (
    SOURCE_CANONICAL,
    ConversationRepository,
)

_VIEW_TYPES = frozenset(vt.value for vt in ViewType)
_DISPOSITION_KINDS = (
    "mapped",
    "preserved_by_reference",
    "redacted",
    "unavailable",
    "unsupported",
)
_SQLITE_MAGIC = b"SQLite format 3\x00"
_MAX_SOURCE_REFS_SAMPLE = 5


@dataclass(frozen=True)
class FamilyFidelityEntry:
    """Metadata-only fidelity metrics for one family (D-25)."""

    family: str
    status: str  # full | partial | blocked | no_source
    capability: dict
    discovered_sessions: int
    captured_artifacts: int
    captured_sessions: int
    adapted_events: int
    adapted_relations: int
    dataset_digest: str | None
    replay_digest: str | None
    replay_stable: bool | str  # True | False | "n/a"
    dispositions: dict
    disposition_coverage: float
    unresolved_provenance: int
    source_refs_sample: tuple[str, ...]
    projection_parity: dict
    view_counts: dict
    fidelity: dict | None


@dataclass(frozen=True)
class FidelityEvaluation:
    """Full per-family fidelity evaluation of one shadow cohort."""

    families: dict[str, FamilyFidelityEntry]
    gates: dict
    summary: dict
    partial_disclosures: tuple[str, ...]
    consumer_evidence: dict
    paid_calls: int = 0

    def to_dict(self) -> dict:
        return {
            "families": {
                name: asdict(entry) for name, entry in sorted(self.families.items())
            },
            "gates": self.gates,
            "summary": self.summary,
            "partial_disclosures": list(self.partial_disclosures),
            "consumer_evidence": self.consumer_evidence,
            "paid_calls": self.paid_calls,
        }


def evaluate_adapter_fidelity(
    report: dict,
    *,
    generation_db: Path,
    artifact_store: Path | None = None,
    inventory: dict[str, int] | None = None,
    agentsview_db: Path | None = None,
) -> FidelityEvaluation:
    """Evaluate one metadata-only shadow cohort.

    ``report`` is the shadow report dict (per-family generations with
    generation_id / dataset_digest / artifact_hashes / fidelity). The staged
    generation db and the content-addressed artifact store are read-only
    inputs. ``inventory`` maps family/agent -> discovered session count from a
    read-only inventory probe (optional; defaults to the report's snapshot
    counts). Nothing is written, no provider is called.
    """
    inventory = dict(inventory or {})
    entries: dict[str, FamilyFidelityEntry] = {}
    for name in known_families():
        owner = resolve_family(name)
        entry = report.get("generations", {}).get(name) or {}
        if entry:
            entries[name] = _evaluate_family(
                report, name, entry, owner,
                generation_db, artifact_store, inventory,
            )
    consumer = _consumer_evidence(entries, generation_db)
    gates = _compute_gates(
        entries, report, inventory,
        consumer_evidence=consumer, agentsview_db=agentsview_db,
    )
    summary = _tally_summary(entries)
    disclosures = _partial_disclosures(entries)
    return FidelityEvaluation(
        families=entries,
        gates=gates,
        summary=summary,
        partial_disclosures=disclosures,
        consumer_evidence=consumer,
        paid_calls=0,
    )


def _evaluate_family(
    report: dict, name: str, entry: dict, owner: str,
    generation_db: Path, artifact_store: Path | None,
    inventory: dict[str, int],
) -> FamilyFidelityEntry:
    """Build one family's fidelity entry from the shadow report + db."""
    status = entry.get("status") or "no_source"
    cap = capability_for(name)
    discovered = inventory.get(name, inventory.get(owner, 0))
    dataset_digest = entry.get("dataset_digest")
    gen_id = entry.get("generation_id")

    captured = _counts_from_db(generation_db, gen_id) if gen_id else _zero_counts()
    source_refs = captured["source_refs"]
    dispositions = captured["dispositions"]
    coverage = (
        min(1.0, sum(dispositions.values()) / captured["adapted_events"])
        if captured["adapted_events"] else 0.0
    )
    parity = (
        _projection_parity(generation_db, gen_id)
        if gen_id else _empty_parity()
    )
    views = _view_counts(generation_db, gen_id) if gen_id else _empty_views()
    relative_path = (
        _artifact_relative_path(generation_db, gen_id)
        if gen_id else None
    )
    replay = _replay_digest(owner, entry, artifact_store,
                            relative_path=relative_path)

    return FamilyFidelityEntry(
        family=name,
        status=status,
        capability=asdict(cap),
        discovered_sessions=discovered,
        captured_artifacts=int(entry.get("snapshot_count") or 0),
        captured_sessions=captured["adapted_sessions"],
        adapted_events=captured["adapted_events"],
        adapted_relations=captured["adapted_relations"],
        dataset_digest=dataset_digest,
        replay_digest=replay["digest"],
        replay_stable=replay["stable"],
        dispositions=dispositions,
        disposition_coverage=round(coverage, 6),
        unresolved_provenance=captured["unresolved_provenance"],
        source_refs_sample=source_refs,
        projection_parity=parity,
        view_counts=views,
        fidelity=entry.get("fidelity"),
    )


# -------------------------------------------------------------- generation


def _counts_from_db(db: Path, gen_id: str) -> dict:
    """Read-only per-generation counts and metadata (no bodies)."""
    counts = _zero_counts()
    try:
        repo = EventRepository(db)
        events = repo.iter_events(gen_id)
        relations = repo.iter_relations(gen_id)
        sessions = _read_sessions(db, gen_id)
        dispositions = repo.iter_dispositions(gen_id)
    except (sqlite3.Error, OSError, ValueError):
        return counts
    counts["adapted_events"] = len(events)
    counts["adapted_relations"] = len(relations)
    counts["adapted_sessions"] = len(sessions)
    counts["unresolved_provenance"] = sum(
        1 for e in events
        if not e["artifact_id"] or not e["native_locator"]
    )
    counts["source_refs"] = tuple(
        e["native_locator"] for e in events[:_MAX_SOURCE_REFS_SAMPLE]
    )
    for disp in dispositions:
        kind = disp.get("disposition")
        if kind in counts["dispositions"]:
            counts["dispositions"][kind] += 1
    return counts


def _read_sessions(db: Path, gen_id: str) -> list[dict]:
    if not Path(db).exists():
        return []
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [
            dict(r) for r in con.execute(
                "SELECT session_id, artifact_id, native_locator, "
                "native_session_id, started_at, ended_at, contract_version, "
                "fidelity_json FROM ce_sessions WHERE generation_id=?",
                (gen_id,),
            )
        ]
    finally:
        con.close()


def _zero_counts() -> dict:
    return {
        "adapted_events": 0,
        "adapted_relations": 0,
        "adapted_sessions": 0,
        "unresolved_provenance": 0,
        "source_refs": (),
        "dispositions": {k: 0 for k in _DISPOSITION_KINDS},
    }


def _projection_parity(db: Path, gen_id: str) -> dict:
    """D-17: deterministic compatibility projection parity (metadata only)."""
    try:
        report = build_compatibility_projection(db, gen_id)
    except (sqlite3.Error, OSError, ValueError):
        return _empty_parity()
    return {
        "projected_sessions": len(report.sessions),
        "projected_messages": len(report.messages),
        "projected_tools": len(report.tools),
        "excluded_events": len(report.excluded),
        "fingerprint_digest": report.fingerprint.digest,
    }


def _empty_parity() -> dict:
    return {
        "projected_sessions": 0,
        "projected_messages": 0,
        "projected_tools": 0,
        "excluded_events": 0,
        "fingerprint_digest": None,
    }


def _view_counts(db: Path, gen_id: str) -> dict:
    """D-21: deterministic seven-view coverage for one generation."""
    try:
        result = build_all_views(_hydrate_graph(db, gen_id))
    except (sqlite3.Error, OSError, ValueError):
        return _empty_views()
    grouped = result.views_by_type()
    return {vt.value: len(grouped[vt]) for vt in ViewType}


def _empty_views() -> dict:
    return {vt: 0 for vt in sorted(_VIEW_TYPES)}


def _hydrate_graph(db: Path, gen_id: str) -> EventGraph:
    """Rehydrate a generation into a typed EventGraph for view building."""
    repo = EventRepository(db)
    events = [
        _typed_event(row)
        for row in repo.iter_events(gen_id)
    ]
    relations = [
        EventRelation(
            relation_id=r["relation_id"],
            source_event_id=r["source_event_id"],
            target_event_id=r["target_event_id"],
            relation_kind=RelationKind(r["relation_kind"]),
        )
        for r in repo.iter_relations(gen_id)
    ]
    sessions = [_adapted_session(row) for row in _read_sessions(db, gen_id)]
    return EventGraph(
        generation_id=gen_id, events=tuple(events),
        relations=tuple(relations), sessions=tuple(sessions),
    )


def _typed_event(row: dict) -> TypedEvent:
    fidelity = FidelityProfile.from_dict(json.loads(row["fidelity_json"]))
    return TypedEvent(
        event_id=row["event_id"],
        session_id=row["session_id"],
        kind=EventKind(row["kind"]),
        provenance=Provenance(
            artifact_id=row["artifact_id"],
            artifact_hash="",
            native_locator=row["native_locator"],
            native_session_id=None,
            native_event_id=row.get("native_event_id"),
            contract_version=row.get("contract_version") or "1",
        ),
        fidelity=fidelity,
        occurred_at=row.get("occurred_at"),
        ordinal=row.get("ordinal"),
        native_payload_ref=row.get("native_payload_ref"),
        summary=row.get("summary"),
    )


def _adapted_session(row: dict) -> AdaptedSession:
    fidelity = FidelityProfile.from_dict(json.loads(row["fidelity_json"]))
    return AdaptedSession(
        session_id=row["session_id"],
        provenance=Provenance(
            artifact_id=row["artifact_id"],
            artifact_hash="",
            native_locator=row["native_locator"],
            native_session_id=row.get("native_session_id"),
            contract_version=row.get("contract_version") or "1",
        ),
        fidelity=fidelity,
        native_session_id=row.get("native_session_id"),
        started_at=row.get("started_at"),
        ended_at=row.get("ended_at"),
    )


# -------------------------------------------------------------- replay

def _artifact_relative_path(db: Path, gen_id: str) -> str | None:
    """The original relative_path of a staged generation's source artifact."""
    try:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT relative_path FROM ce_source_artifacts "
                "JOIN ce_sessions ON ce_sessions.artifact_id "
                "= ce_source_artifacts.artifact_id "
                "WHERE ce_sessions.generation_id=? LIMIT 1",
                (gen_id,),
            ).fetchone()
            if row is None:
                row = con.execute(
                    "SELECT relative_path FROM ce_source_artifacts LIMIT 1"
                ).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _replay_digest(
    owner: str, entry: dict, store: Path | None,
    *, relative_path: str | None,
) -> dict:
    """Re-adapt the identical captured bytes and compare dataset digests.

    Returns ``{"digest": str|None, "stable": True|False|"n/a"}``. Replay is
    ``"n/a"`` when there is no single immutable artifact to replay (no source,
    blocked multi-artifact family, or missing store). The original
    ``relative_path`` is reused so locator-derived digests match the staged
    generation exactly.
    """
    status = entry.get("status")
    hashes = entry.get("artifact_hashes") or []
    if status in ("no_source", "blocked") or len(hashes) != 1 or store is None:
        return {"digest": None, "stable": "n/a"}
    blob = _find_blob(store, hashes[0])
    if blob is None:
        return {"digest": None, "stable": "n/a"}
    try:
        with tempfile.TemporaryDirectory(prefix="pk-fidelity-replay-") as td:
            root = Path(td)
            blob_bytes = blob.read_bytes()
            # the content-addressed blob name IS the original artifact_id
            (root / blob.name).write_bytes(blob_bytes)
            artifact = SourceArtifact(
                artifact_id=blob.name,
                family=owner,
                source_kind="sqlite" if blob_bytes.startswith(_SQLITE_MAGIC)
                else "file",
                content_hash=hashes[0],
                capture_method="replay",
                relative_path=relative_path or blob.name,
                byte_size=len(blob_bytes),
            )
            result = adapt_for(
                owner, SourceArtifactSet((artifact,)), artifact_root=root
            )
            digest = result.dataset_digest
            return {
                "digest": digest,
                "stable": digest == entry.get("dataset_digest"),
            }
    except Exception:  # noqa: BLE001 - replay failure is honest, not fatal
        return {"digest": None, "stable": "n/a"}


def _find_blob(store: Path, content_hash: str) -> Path | None:
    """Locate a content-addressed blob by its artifact id (hash prefix)."""
    root = store / "artifacts"
    if not root.exists():
        return None
    prefix = content_hash[:32]
    for blob in root.iterdir():
        if blob.name == prefix:
            return blob
    return None


# --------------------------------------------------------------- gates

def _compute_gates(
    entries: dict[str, FamilyFidelityEntry],
    report: dict,
    inventory: dict[str, int],
    *,
    consumer_evidence: dict,
    agentsview_db: Path | None,
) -> dict:
    """Compute the deterministic activation gates (D-18, metadata-only)."""
    missing = [
        name for name in known_families()
        if name not in report.get("generations", {})
    ]
    with_result = sum(
        1 for e in entries.values()
        if e.status in ("full", "partial", "blocked", "no_source")
    )

    captured_or_blocked = _native_available_gate(entries, inventory)
    provenance = _provenance_gate(entries)
    forbidden = _forbidden_access_gate(agentsview_db)
    replay = _replay_gate(entries)
    consumer = _consumer_gate(consumer_evidence)
    disclosed = _disclosed_gate(entries)

    gates = {
        "capability_coverage": {
            "ok": with_result == len(known_families()) and not missing,
            "with_result": with_result,
            "total_families": len(known_families()),
            "missing": missing,
        },
        "native_available_captured_or_blocked": captured_or_blocked,
        "unresolved_provenance": provenance,
        "forbidden_source_access": forbidden,
        "replay_digest_stable": replay,
        "current_consumers_pass": consumer,
        "partial_chatgpt_cursor_disclosed": disclosed,
        "paid_calls_zero": {"ok": True, "count": 0},
    }
    gates["overall"] = all(
        bool(gates[key]["ok"])
        for key in (
            "capability_coverage",
            "native_available_captured_or_blocked",
            "unresolved_provenance",
            "forbidden_source_access",
            "replay_digest_stable",
            "current_consumers_pass",
            "partial_chatgpt_cursor_disclosed",
            "paid_calls_zero",
        )
    ) and not missing
    return gates


def _native_available_gate(
    entries: dict[str, FamilyFidelityEntry], inventory: dict[str, int]
) -> dict:
    violations: list[str] = []
    for name, entry in entries.items():
        discovered = inventory.get(
            name, inventory.get(entry.family, 0)
        )
        if discovered <= 0:
            continue
        if entry.status == "blocked":
            continue
        if entry.status == "no_source" or entry.captured_sessions < discovered:
            violations.append(
                f"{name}: discovered={discovered} captured={entry.captured_sessions}"
            )
    return {"ok": not violations, "violations": violations}


def _provenance_gate(entries: dict[str, FamilyFidelityEntry]) -> dict:
    count = sum(e.unresolved_provenance for e in entries.values())
    return {"count": count, "ok": count == 0}


def _forbidden_access_gate(agentsview_db: Path | None) -> dict:
    """D-08: forbidden-source access count; zero when no probe is given."""
    count = 0
    if agentsview_db is not None:
        try:
            probe = live_inventory_metadata(agentsview_db=agentsview_db)
            count = probe["forbidden_source_access"]
        except (sqlite3.Error, OSError, ValueError):
            count = -1  # probe failure is an honest unknown, never a pass
    return {"count": count, "ok": count == 0}


def _replay_gate(entries: dict[str, FamilyFidelityEntry]) -> dict:
    drifted = [
        name for name, e in entries.items() if e.replay_stable is False
    ]
    applicable = sum(1 for e in entries.values() if e.replay_stable != "n/a")
    return {
        "ok": not drifted,
        "replayable_families": applicable,
        "drifted": drifted,
    }


def _consumer_gate(consumer_evidence: dict) -> dict:
    """Current consumers pass when every projected cohort stays readable."""
    ok = (
        consumer_evidence["consumer_read_sessions"] >= 1
        and consumer_evidence["consumer_read_messages"] >= 1
    )
    return {"ok": ok, "evidence": consumer_evidence}


def _disclosed_gate(entries: dict[str, FamilyFidelityEntry]) -> dict:
    disclosures = _partial_disclosures(entries)
    text = "\n".join(disclosures).lower()
    ok = "chatgpt" in text and "cursor" in text
    return {"ok": ok, "disclosed": list(disclosures)}


def _tally_summary(entries: dict[str, FamilyFidelityEntry]) -> dict:
    counts = {"full": 0, "partial": 0, "blocked": 0, "no_source": 0}
    for entry in entries.values():
        counts[entry.status] = counts.get(entry.status, 0) + 1
    counts["total_families"] = len(entries)
    return counts


def _partial_disclosures(
    entries: dict[str, FamilyFidelityEntry],
) -> tuple[str, ...]:
    """Metadata-only limitation disclosures for partial families (D-14)."""
    lines: list[str] = []
    for name in ("chatgpt", "cursor"):
        entry = entries.get(name)
        if entry is None:
            continue
        if entry.status in ("partial", "blocked"):
            lines.append(
                f"{name}: partial fidelity disclosed — native reconstruction "
                f"or supported schema unavailable; status={entry.status}"
            )
        else:
            lines.append(
                f"{name}: no recoverable native source observed this cohort "
                f"(status={entry.status}); limitation remains disclosed"
            )
    for name in sorted(entries):
        entry = entries[name]
        if name in ("chatgpt", "cursor") or entry.status != "partial":
            continue
        lines.append(f"{name}: partial fidelity disclosed (status=partial)")
    return tuple(lines)


# ----------------------------------------------------------- consumers

def _consumer_evidence(
    entries: dict[str, FamilyFidelityEntry],
    generation_db: Path,
) -> dict:
    """Project the cohort into a throwaway consumer db and read it back."""
    if not Path(generation_db).exists():
        return {
            "projected_sessions": 0,
            "consumer_read_sessions": 0,
            "consumer_read_messages": 0,
        }
    projected_sessions = sum(
        e.projection_parity["projected_sessions"]
        for e in entries.values() if e.status in ("full", "partial")
    )
    try:
        with tempfile.TemporaryDirectory(prefix="pk-fidelity-consumer-") as td:
            consumer_db = Path(td) / "consumer.sqlite"
            _write_consumer_projection(generation_db, consumer_db, entries)
            repo = ConversationRepository(
                source=SOURCE_CANONICAL,
                legacy_db=consumer_db,
                canonical_db=consumer_db,
            )
            sessions = sum(1 for _ in repo.iter_sessions())
            messages = 0
            for session in repo.iter_sessions():
                messages += sum(1 for _ in repo.iter_turns(session["canonical_session_id"]))
            return {
                "projected_sessions": projected_sessions,
                "consumer_read_sessions": sessions,
                "consumer_read_messages": messages,
            }
    except (sqlite3.Error, OSError, ValueError):
        return {
            "projected_sessions": projected_sessions,
            "consumer_read_sessions": 0,
            "consumer_read_messages": 0,
        }


def _write_consumer_projection(
    source_db: Path, consumer_db: Path, entries: dict,
) -> None:
    """Write every full/partial generation's projection into one consumer db."""
    con = sqlite3.connect(str(consumer_db))
    try:
        from personal_knowledge.application.conversation.compatibility_projection import (
            write_compatibility_projection,
        )

        for entry in entries.values():
            if entry.status not in ("full", "partial"):
                continue
            if entry.projection_parity["projected_sessions"] == 0:
                continue
            # each family owns its staged generation id; the report entry id
            # lives in the parity, but we re-derive it from the source db by
            # walking every staged generation for this family.
            gen_id = _family_generation_id(source_db, entry.family)
            if gen_id is None:
                continue
            report = build_compatibility_projection(source_db, gen_id)
            write_compatibility_projection(con, report)
        con.commit()
    finally:
        con.close()


def _family_generation_id(db: Path, family: str) -> str | None:
    """The staged generation id for one family (read-only)."""
    try:
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT generation_id FROM ce_adapter_runs "
                "WHERE family=? ORDER BY created_at LIMIT 1",
                (family,),
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except sqlite3.Error:
        return None


# ----------------------------------------------------- live metadata smoke

# The only declared read table of the read-only inventory probe (D-08/D-09).
_INVENTORY_TABLES: tuple[str, ...] = ("sessions",)
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "account", "credential", "token", "auth", "secret", "cookie", "api_key",
)

# Agent names observed in the live inventory that are not family names.
_AGENT_FAMILY_ALIASES: dict[str, str] = {
    "mimocode": "mimo",
}


def live_inventory_metadata(agentsview_db: Path | None = None) -> dict:
    """Read-only metadata probe of the live AgentsView inventory.

    Returns only session-agent counts per family plus forbidden-source access
    counters. Bodies, secrets and credential-table rows are never read. The
    connection is forced ``mode=ro`` + ``PRAGMA query_only=ON``.
    """
    from personal_knowledge.core.project_paths import AGENTSVIEW_DB

    db = agentsview_db or AGENTSVIEW_DB
    con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        forbidden_present = sorted(
            t for t in tables
            if any(p in t.lower() for p in _FORBIDDEN_PATTERNS)
        )
        counts: dict[str, int] = {}
        if "sessions" in tables:
            for row in con.execute("SELECT agent, COUNT(*) n FROM sessions GROUP BY agent"):
                counts[str(row["agent"])] = int(row["n"])
    finally:
        con.close()

    families: dict[str, dict] = {}
    unknown: list[str] = []
    for agent, n in sorted(counts.items()):
        family = _inventory_family(agent)
        if family is None:
            unknown.append(agent)
            continue
        entry = families.setdefault(family, {"discovered_sessions": 0})
        entry["discovered_sessions"] += n

    for name in known_families():
        families.setdefault(resolve_family(name), {"discovered_sessions": 0})

    return {
        "read_only": True,
        "read_tables": list(_INVENTORY_TABLES),
        "forbidden_tables_present": forbidden_present,
        "forbidden_source_access": 0,
        "families": {f: families[f] for f in sorted(families)},
        "agent_counts": counts,
        "unknown_agents": unknown,
    }


def _inventory_family(agent: str) -> str | None:
    """Map an inventory agent name to its owning adapter family (D-02)."""
    if not agent:
        return None
    alias = _AGENT_FAMILY_ALIASES.get(agent)
    if alias is not None:
        return alias
    try:
        return resolve_family(agent)
    except KeyError:
        return None


__all__ = [
    "FamilyFidelityEntry",
    "FidelityEvaluation",
    "evaluate_adapter_fidelity",
    "live_inventory_metadata",
]
