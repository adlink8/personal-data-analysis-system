"""Phase 62-04: v2 conversation orchestration (dry-run / shadow / activation).

The `pk-sync conversations --v2-*` seams (62-04 plan Task 3):
:func:`probe_conversation_sources` (dry-run, metadata-only), 
:func:`shadow_conversation_generation` (capture + adapt + stage NON-active
generations + metadata-only report), and :func:`activate_conversation_generation`
(activates ONLY via :mod:`.event_generations`; fires a metadata-only post-commit
delta only after success). :func:`add_conversations_v2_args` /
:func:`cmd_conversations_v2` are the CLI surface consumed by
:mod:`.application.sync`.

Command-level fail-closed gates run before the lifecycle: uncovered sources,
blocked/privacy-gated families, unknown family, missing coverage, stale manifest
and checksum mismatch all prevent activation. This module never touches the
live canonical stores (D-15/D-31); staging goes to a caller-supplied shadow db.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.contracts import (
    AdaptationResult,
    SourceArtifact,
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.registry import (
    adapt_for,
    capability_for,
    known_families,
    resolve_family,
    select_adapter,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.application.conversation.event_generations import (
    GenerationActivationError,
    GenerationLifecycle,
)
from personal_knowledge.application.conversation.event_repository import (
    GenerationInput,
)


# --------------------------------------------------------------------- probe


def _probe_artifact(relative: str, size: int) -> SourceArtifact:
    """A minimal artifact used only by ``select_adapter`` detection."""
    return SourceArtifact(
        artifact_id=relative,
        family="",
        source_kind="file",
        content_hash="probe",
        capture_method="probe",
        relative_path=relative,
        byte_size=size,
    )


def probe_conversation_sources(
    *,
    source_root: Path,
    byte_limit: int = 1_000_000,
    count_limit: int = 200,
) -> dict:
    """Dry-run probe: every registered family's capability + event estimates.

    Metadata-only; nothing is staged and no canonical database is created.
    """
    import tempfile

    if not source_root.exists():
        raise FileNotFoundError(f"v2 source root missing: {source_root}")
    detected = _detect_families(source_root)

    items: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="pk-v2-probe-") as td:
        store = Path(td)
        for name in known_families():
            owner = resolve_family(name)
            cap = capability_for(name)
            matches = detected.get(owner, [])
            status = "detected" if matches else "no_source"
            event_estimate = 0
            if status == "detected" and len(matches) == 1:
                event_estimate = _estimate_events(
                    matches[0], store, owner, byte_limit, count_limit
                )
            items.append({
                "family": name,
                "adapter_version": cap.adapter_version,
                "contract_version": cap.contract_version,
                "event_kind_count": len(cap.supported_event_kinds),
                "relation_kind_count": len(cap.supported_relation_kinds),
                "status": status,
                "snapshot_estimate": len(matches),
                "event_estimate": event_estimate,
            })
    return {
        "mode": "dry-run",
        "source_root": str(source_root),
        "probed_families": items,
    }


def _detect_families(source_root: Path) -> dict[str, list[Path]]:
    """Map each source file to its detected family (no generic fallback)."""
    detected: dict[str, list[Path]] = {}
    for f in sorted(p for p in source_root.iterdir() if p.is_file()):
        family = select_adapter(
            _probe_artifact(f.name, f.stat().st_size), artifact_root=source_root
        )
        if family:
            detected.setdefault(family, []).append(f)
    return detected


def _estimate_events(
    path: Path, store: Path, family: str, byte_limit: int, count_limit: int,
) -> int:
    """Best-effort typed event count for a single detected file."""
    try:
        artifact, blob = capture_file(
            path, store, relative_path=path.name,
            byte_limit=byte_limit, count_limit=count_limit,
        )
        result = adapt_for(
            family, SourceArtifactSet((artifact,)), artifact_root=blob.parent
        )
        return len(result.events)
    except Exception:  # noqa: BLE001 - estimate is best-effort
        return 0


# -------------------------------------------------------------------- shadow


def _adapt_source_file(
    path: Path, store: Path, *, byte_limit: int, count_limit: int, family: str,
) -> tuple[SourceArtifact, AdaptationResult]:
    artifact, blob = capture_file(
        path, store, relative_path=path.name,
        byte_limit=byte_limit, count_limit=count_limit,
    )
    result = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent
    )
    return artifact, result


def _status_for(result: AdaptationResult, artifact: SourceArtifact) -> str:
    """full | partial | blocked for one adapted family."""
    blocked = any(
        d.startswith("blocked:") for d in artifact.privacy_dispositions
    )
    if blocked:
        return "blocked"
    if result.fidelity.has_loss() or result.warnings:
        return "partial"
    return "full"


def shadow_conversation_generation(
    *,
    source_root: Path,
    db: Path,
    artifact_store: Path,
    report_path: Path,
    byte_limit: int = 1_000_000,
    count_limit: int = 200,
) -> dict:
    """Explicit shadow: capture, adapt, and stage NON-active v2 generations.

    One staged generation per detected family. Writes a metadata-only JSON
    report (hashes/fidelity/counts, never bodies). The authority pointer is
    never touched here: activation is a separate explicit step.
    """
    if not source_root.exists():
        raise FileNotFoundError(f"v2 source root missing: {source_root}")
    artifact_store.mkdir(parents=True, exist_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)

    by_family = _detect_families(source_root)
    uncovered = sorted(
        f.name for f in source_root.iterdir()
        if f.is_file() and f.name not in _all_detected_names(by_family)
    )
    life = GenerationLifecycle(db)
    generations = _stage_all_families(
        life, by_family, artifact_store, byte_limit=byte_limit,
        count_limit=count_limit,
    )
    report = {
        "mode": "shadow",
        "source_root": str(source_root),
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "generations": generations,
        "uncovered_sources": uncovered,
        "summary": {
            "full": sum(1 for g in generations.values() if g["status"] == "full"),
            "partial": sum(1 for g in generations.values() if g["status"] == "partial"),
            "blocked": sum(1 for g in generations.values() if g["status"] == "blocked"),
            "no_source": sum(1 for g in generations.values() if g["status"] == "no_source"),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _all_detected_names(by_family: dict[str, list[Path]]) -> set[str]:
    names: set[str] = set()
    for paths in by_family.values():
        names.update(p.name for p in paths)
    return names


def _stage_all_families(
    life: GenerationLifecycle,
    by_family: dict[str, list[Path]],
    store: Path,
    *,
    byte_limit: int,
    count_limit: int,
) -> dict[str, dict]:
    """Stage one generation per known family and return metadata-only entries."""
    generations: dict[str, dict] = {}
    for name in known_families():
        owner = resolve_family(name)
        matches = by_family.get(owner, [])
        base = {
            "family": owner,
            "status": "no_source",
            "snapshot_count": len(matches),
            "event_count": 0,
            "generation_id": None,
            "source_manifest_id": None,
            "artifact_hashes": [],
            "dataset_digest": None,
            "fidelity": None,
            "privacy_blocked": False,
            "reason": None,
        }
        if matches:
            base["status"] = "blocked"
            base["reason"] = "unsupported_artifact_set"
            if len(matches) == 1:
                base.update(_stage_family(
                    life, owner, matches[0], store,
                    byte_limit=byte_limit, count_limit=count_limit,
                ))
        generations[name] = base
    return generations


def _stage_family(
    life: GenerationLifecycle, family: str, path: Path, store: Path,
    *, byte_limit: int, count_limit: int,
) -> dict:
    """Stage one family's generation and return its metadata-only entry."""
    blocked = {
        "status": "blocked", "reason": None, "generation_id": None,
        "snapshot_count": 1, "event_count": 0, "source_manifest_id": None,
        "artifact_hashes": [], "dataset_digest": None, "fidelity": None,
        "privacy_blocked": False,
    }
    try:
        artifact, result = _adapt_source_file(
            path, store, byte_limit=byte_limit,
            count_limit=count_limit, family=family,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed into a blocked status
        blocked["reason"] = f"adapt_failed:{type(exc).__name__}"
        return blocked

    cap = capability_for(family)
    generation_id = f"shadow-{family}-{result.dataset_digest[:10]}"
    manifest_id = f"manifest-{family}-{artifact.content_hash[:12]}"
    gen = GenerationInput(
        family=result.family,
        adapter_version=result.adapter_version,
        contract_version=result.contract_version,
        capability_digest=cap.digest(),
        source_manifest_id=manifest_id,
        dataset_digest=result.dataset_digest,
        artifacts=result.artifacts,
        sessions=result.sessions,
        events=result.events,
        relations=result.relations,
        dispositions=result.field_dispositions,
        warnings=result.warnings,
    )
    life.prepare(gen, generation_id)
    status = _status_for(result, artifact)
    return {
        "generation_id": generation_id,
        "status": status,
        "snapshot_count": 1,
        "event_count": len(result.events),
        "source_manifest_id": manifest_id,
        "artifact_hashes": [artifact.content_hash],
        "dataset_digest": result.dataset_digest,
        "fidelity": result.fidelity.to_dict(),
        "privacy_blocked": status == "blocked",
        "reason": None,
    }


# ---------------------------------------------------------------- activation


def activate_conversation_generation(
    *,
    db: Path,
    generation_id: str,
    report: dict,
    expected_adapter_families: tuple[str, ...],
    hooks=None,
    delta_publisher=None,
) -> dict:
    """Explicit activation: delegates ONLY to the generation lifecycle.

    Command-level fail-closed gates (uncovered sources, blocked/privacy gate)
    run first; unknown family / missing coverage / stale manifest / checksum
    mismatch are enforced by :class:`GenerationLifecycle`. The delta is
    metadata-only and fires only after success."""
    entry = _report_entry(report, generation_id)
    if entry.get("status") == "blocked" or entry.get("privacy_blocked"):
        raise GenerationActivationError(
            f"privacy_gate_blocked: privacy gate blocks activation of "
            f"generation {generation_id}",
            generation_id=generation_id, reason="privacy_gate_blocked",
        )
    uncovered = report.get("uncovered_sources") or []
    if uncovered:
        raise GenerationActivationError(
            f"uncovered_sources prevent activation: {uncovered}",
            generation_id=generation_id, reason="uncovered_sources",
        )

    families = expected_adapter_families or (entry["family"],)
    life = GenerationLifecycle(db)
    result = life.activate(
        generation_id,
        source_manifest_id=entry["source_manifest_id"],
        expected_dataset_digest=entry["dataset_digest"],
        expected_adapter_families=tuple(families),
        hooks=hooks,
    )
    delta = {"published": False, "reason": "v2_delta_not_configured"}
    if delta_publisher is not None:
        delta = delta_publisher({
            "generation_id": generation_id,
            "projection_digest": result["projection_digest"],
            "dataset_digest": entry["dataset_digest"],
            "artifact_hashes": entry.get("artifact_hashes", []),
            "event_count": entry.get("event_count", 0),
        })
    result["delta"] = delta
    return result


def _report_entry(report: dict, generation_id: str) -> dict:
    """Find the generation entry in the shadow report; fail closed if absent."""
    for family, item in (report.get("generations") or {}).items():
        if item.get("generation_id") == generation_id:
            entry = dict(item)
            entry["family"] = family
            return entry
    raise GenerationActivationError(
        f"generation {generation_id} is not in the shadow report",
        generation_id=generation_id, reason="generation_not_in_report",
    )


# ------------------------------------------------------------------- CLI glue


def add_conversations_v2_args(parser: argparse.ArgumentParser) -> None:
    """Add the additive Phase 62-04 v2 flags (explicit/opt-in; default behavior
    unchanged until Plan 62-08)."""
    parser.add_argument(
        "--v2-dry-run",
        action="store_true",
        help="Phase 62 v2: probe every family capability and snapshot/event "
             "estimate (metadata-only, no canonical writes)",
    )
    parser.add_argument(
        "--v2-shadow",
        action="store_true",
        help="Phase 62 v2: capture sources, adapt, and stage NON-active v2 "
             "generations plus a metadata-only report",
    )
    parser.add_argument(
        "--v2-activate",
        metavar="GENERATION_ID",
        default=None,
        help="Phase 62 v2: explicitly activate a staged generation (delegates "
             "only to event_generations; default never activates)",
    )
    parser.add_argument(
        "--v2-source",
        type=Path,
        default=None,
        help="Phase 62 v2: source root for v2 dry-run/shadow (default: none)",
    )
    parser.add_argument(
        "--v2-db",
        type=Path,
        default=Path("data") / "staging" / "v2" / "agent_conversations_v2.sqlite",
        help="Phase 62 v2: shadow database (default: data/staging/v2, never "
             "the live canonical store)",
    )
    parser.add_argument(
        "--v2-artifact-store",
        type=Path,
        default=Path("data") / "staging" / "v2" / "artifacts",
        help="Phase 62 v2: content-addressed artifact store",
    )
    parser.add_argument(
        "--v2-report",
        type=Path,
        default=Path("data") / "staging" / "v2" / "report.json",
        help="Phase 62 v2: metadata-only shadow report path",
    )
    parser.add_argument(
        "--v2-families",
        default=None,
        help="Phase 62 v2: comma-separated expected adapter families for "
             "activation (default: the generation's own family)",
    )


def cmd_conversations_v2(args) -> int:
    """CLI routing for the explicit v2 modes (dry-run / shadow / activation).

    Metadata-only outputs; writes only to the caller-supplied shadow database
    (D-15/D-31, zero-paid)."""
    if args.v2_dry_run:
        report = probe_conversation_sources(source_root=args.v2_source)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.v2_shadow:
        report = shadow_conversation_generation(
            source_root=args.v2_source,
            db=args.v2_db,
            artifact_store=args.v2_artifact_store,
            report_path=args.v2_report,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n[shadow] metadata-only report: {args.v2_report}")
        print("[shadow] no generation activated; use --v2-activate explicitly.")
        return 0

    if args.v2_activate:
        if not args.v2_report.exists():
            print(f"[error] v2 shadow report missing: {args.v2_report}")
            return 1
        try:
            report = json.loads(args.v2_report.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"[error] cannot read v2 report: {exc}")
            return 1
        families = tuple(
            f.strip() for f in (args.v2_families or "").split(",") if f.strip()
        ) or None
        try:
            result = activate_conversation_generation(
                db=args.v2_db,
                generation_id=args.v2_activate,
                report=report,
                expected_adapter_families=tuple(families) if families else (),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on the command line
            print(f"[error] v2 activation blocked: {exc}")
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("[error] internal: unreachable v2 mode")
    return 2


__all__ = [
    "activate_conversation_generation",
    "add_conversations_v2_args",
    "cmd_conversations_v2",
    "probe_conversation_sources",
    "shadow_conversation_generation",
]
