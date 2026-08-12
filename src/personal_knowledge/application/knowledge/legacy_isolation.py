"""Fail-closed state machine for quarantining legacy derived knowledge."""
from __future__ import annotations

import hashlib
import json
import re
import socket
import sqlite3
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from personal_knowledge.application.knowledge.quarantine_manifest import (
    ManifestError,
    create_manifest,
    database_fingerprint,
    fingerprint_sources,
    load_verified_manifest,
    restore_from_manifest,
    update_manifest,
)
from personal_knowledge.application.serving.snapshots import (
    activate_snapshot,
    get_active_snapshot,
    prepare_snapshot,
    validate_snapshot,
)
from personal_knowledge.application.serving.versions import record_publication
from personal_knowledge.core.chroma_client import ChromaClient, Collection
from personal_knowledge.core.sqlite import assert_foreign_key_integrity, connect_rw


DERIVED_KNOWLEDGE_TABLES = (
    "knowledge_unit_corrections",
    "knowledge_lifecycle_events",
    "knowledge_lifecycle_actions",
    "knowledge_lifecycle_manifests",
    "canonical_unit_members",
    "knowledge_unit_evidence",
    "canonical_knowledge_units",
    "knowledge_units",
    "knowledge_extraction_gates",
    "knowledge_run_items",
    "knowledge_inventory_items",
    "knowledge_delta_items",
    "knowledge_incremental_journals",
    "knowledge_l2_session_jobs",
    "knowledge_dead_refs",
    "knowledge_index_versions",
    "knowledge_response_cache",
    "knowledge_delta_inventories",
    "knowledge_inventory",
    "knowledge_inventory_registry",
    "knowledge_source_watermark",
    "knowledge_build_runs",
)
_DERIVED_SET = frozenset(DERIVED_KNOWLEDGE_TABLES)
_CONSUMER_PORTS = (8000, 8789, 8790)


class IsolationError(RuntimeError):
    """The isolation boundary could not be proven safe or was rolled back."""


@dataclass(frozen=True)
class IsolationDependencies:
    list_collections: Callable[[], list[dict[str, Any]]]
    create_empty_collection: Callable[[str], Mapping[str, Any]]
    delete_collection: Callable[[str], None]
    get_active_snapshot: Callable[[Path], Mapping[str, Any] | None]
    activate_empty_snapshot: Callable[[Path, str, str, str, Path], Mapping[str, Any]]
    active_consumers: Callable[[], Sequence[Mapping[str, Any]]]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_generation_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"kg_{timestamp}_{uuid.uuid4().hex[:8]}"


def collection_name_for(generation_id: str) -> str:
    return f"knowledge_units_empty_{generation_id}"


def _schema_tables(con: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _validate_schema(db_path: Path) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        tables = _schema_tables(con)
        missing = sorted(_DERIVED_SET - tables)
        if missing:
            raise IsolationError(f"missing knowledge tables: {','.join(missing)}")
        knowledge_shaped = {
            name for name in tables
            if name.startswith("knowledge_") or name in {"canonical_knowledge_units", "canonical_unit_members"}
        }
        unknown = sorted(knowledge_shaped - _DERIVED_SET)
        if unknown:
            raise IsolationError(f"unknown knowledge table(s): {','.join(unknown)}")
        outside_foreign_keys: list[str] = []
        for table in sorted(tables - _DERIVED_SET):
            for row in con.execute(f'PRAGMA foreign_key_list("{table}")'):
                if str(row[2]) in _DERIVED_SET:
                    outside_foreign_keys.append(f"{table}.{row[3]}->{row[2]}.{row[4]}")
        if outside_foreign_keys:
            raise IsolationError(f"unknown foreign key(s) into derived state: {outside_foreign_keys}")
        quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = list(con.execute("PRAGMA foreign_key_check"))
        if quick.lower() != "ok" or foreign_keys:
            raise IsolationError(f"database integrity failed: quick={quick} foreign_keys={len(foreign_keys)}")
        counts = {
            table: int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
            for table in DERIVED_KNOWLEDGE_TABLES
        }
        return {"quick_check": quick, "foreign_key_violations": 0, "counts": counts}
    finally:
        con.close()


def _normalize_collections(raw: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(item.get("name") or ""),
            "count": int(item.get("count") or 0),
            "checksum": str(item.get("checksum") or ""),
        }
        for item in raw
        if str(item.get("name") or "").startswith("knowledge_units")
    ]


def plan_isolation(
    *,
    db_path: Path,
    pointer_path: Path,
    quarantine_root: Path,
    source_paths: Mapping[str, Path],
    dependencies: IsolationDependencies | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    deps = dependencies or default_dependencies()
    generation = generation_id or new_generation_id()
    schema = _validate_schema(db_path)
    active = deps.get_active_snapshot(db_path)
    if not active or not active.get("snapshot_id"):
        raise IsolationError("active serving snapshot missing")
    pointer = pointer_path.read_text(encoding="utf-8").strip() if pointer_path.exists() else ""
    expected = str((((active.get("members") or {}).get("knowledge_retrieval") or {}).get("location_ref") or ""))
    if not pointer or pointer != expected:
        raise IsolationError(f"active pointer drift: pointer={pointer!r} snapshot={expected!r}")
    consumers = [dict(item) for item in deps.active_consumers()]
    return {
        "ok": True,
        "write": False,
        "generation_id": generation,
        "collection_name": collection_name_for(generation),
        "target_db": str(db_path.resolve()),
        "quarantine_dir": str((quarantine_root / generation).resolve()),
        "active_snapshot_id": str(active["snapshot_id"]),
        "active_pointer": pointer,
        "old_collections": _normalize_collections(deps.list_collections()),
        "target_tables": list(DERIVED_KNOWLEDGE_TABLES),
        "derived_state": schema,
        "source_fingerprints": fingerprint_sources(source_paths),
        "active_consumers": consumers,
        "safe_to_apply": not consumers,
    }


def _clear_and_seed_empty_generation(
    db_path: Path,
    *,
    generation_id: str,
    collection_name: str,
    collection_checksum: str,
) -> None:
    con = connect_rw(db_path, timeout=60)
    try:
        assert_foreign_key_integrity(con)
        con.execute("BEGIN IMMEDIATE")
        for table in DERIVED_KNOWLEDGE_TABLES:
            con.execute(f'DELETE FROM "{table}"')
        empty_hash = hashlib.sha256(b"[]").hexdigest()
        con.execute(
            "INSERT INTO knowledge_build_runs "
            "(run_id,run_type,generated_at,input_hash,schema_version,status,stats_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                generation_id,
                "index",
                _now(),
                empty_hash,
                "v1",
                "current",
                json.dumps({"mode": "empty_isolation_generation", "unit_count": 0}, sort_keys=True),
            ),
        )
        con.execute(
            "INSERT INTO knowledge_index_versions "
            "(version_id,build_id,collection_name,canonical_build_id,unit_count,status,created_at,activated_at,checksum) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"kiv_{generation_id}", generation_id, collection_name, generation_id,
                0, "active", _now(), _now(), collection_checksum,
            ),
        )
        assert_foreign_key_integrity(con)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _verify_empty_state(db_path: Path, generation_id: str, collection_name: str) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
        violations = list(con.execute("PRAGMA foreign_key_check"))
        counts = {
            table: int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
            for table in DERIVED_KNOWLEDGE_TABLES
        }
        wrong = {
            table: count for table, count in counts.items()
            if count != (1 if table in {"knowledge_build_runs", "knowledge_index_versions"} else 0)
        }
        run = con.execute("SELECT run_id,status FROM knowledge_build_runs").fetchone()
        index = con.execute(
            "SELECT build_id,collection_name,unit_count,status FROM knowledge_index_versions"
        ).fetchone()
        ok = (
            quick.lower() == "ok" and not violations and not wrong
            and run == (generation_id, "current")
            and index == (generation_id, collection_name, 0, "active")
        )
        return {
            "ok": ok,
            "quick_check": quick,
            "foreign_key_violations": len(violations),
            "counts": counts,
            "unexpected_counts": wrong,
        }
    finally:
        con.close()


def _rollback_after_failure(
    *,
    manifest_path: Path,
    db_path: Path,
    pointer_path: Path,
    dependencies: IsolationDependencies,
    new_collection: str,
    collection_created: bool,
) -> dict[str, Any]:
    restored = restore_from_manifest(manifest_path, db_path=db_path, pointer_path=pointer_path)
    if collection_created:
        dependencies.delete_collection(new_collection)
    manifest = load_verified_manifest(manifest_path)
    sources_after = fingerprint_sources(
        {name: Path(item["path"]) for name, item in manifest["source_fingerprints"].items()}
    )
    if sources_after != manifest["source_fingerprints"]:
        raise IsolationError("rollback completed but source fingerprint drift remains")
    return restored


def apply_isolation(
    *,
    db_path: Path,
    pointer_path: Path,
    quarantine_root: Path,
    source_paths: Mapping[str, Path],
    dependencies: IsolationDependencies | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    deps = dependencies or default_dependencies()
    generation = generation_id or new_generation_id()
    plan = plan_isolation(
        db_path=db_path,
        pointer_path=pointer_path,
        quarantine_root=quarantine_root,
        source_paths=source_paths,
        dependencies=deps,
        generation_id=generation,
    )
    if plan["active_consumers"]:
        raise IsolationError(f"knowledge consumer(s) still active: {plan['active_consumers']}")
    manifest_path, _ = create_manifest(
        db_path=db_path,
        pointer_path=pointer_path,
        quarantine_root=quarantine_root,
        generation_id=generation,
        source_paths=source_paths,
        active_snapshot_id=plan["active_snapshot_id"],
        old_collections=plan["old_collections"],
        derived_tables=list(DERIVED_KNOWLEDGE_TABLES),
    )
    collection_name = plan["collection_name"]
    collection_created = False
    try:
        empty = dict(deps.create_empty_collection(collection_name))
        collection_created = bool(empty.get("created", True))
        if int(empty.get("count", -1)) != 0 or not empty.get("checksum"):
            raise IsolationError("new Chroma collection is not provably empty")
        _clear_and_seed_empty_generation(
            db_path,
            generation_id=generation,
            collection_name=collection_name,
            collection_checksum=str(empty["checksum"]),
        )
        activation = dict(
            deps.activate_empty_snapshot(
                db_path, generation, collection_name, str(empty["checksum"]), manifest_path
            )
        )
        if not activation.get("ok") or activation.get("projection_ok") is not True:
            raise IsolationError(f"snapshot activation projection failed: {activation}")
        state = _verify_empty_state(db_path, generation, collection_name)
        if not state["ok"]:
            raise IsolationError(f"empty generation verification failed: {state}")
        active = deps.get_active_snapshot(db_path)
        pointer = pointer_path.read_text(encoding="utf-8").strip() if pointer_path.exists() else ""
        if str((active or {}).get("snapshot_id") or "") != str(activation.get("snapshot_id") or ""):
            raise IsolationError("snapshot authority does not match activated empty generation")
        if pointer != collection_name:
            raise IsolationError("active pointer does not match empty collection")
        collections_after = _normalize_collections(deps.list_collections())
        names_after = {item["name"] for item in collections_after}
        old_names = {item["name"] for item in plan["old_collections"]}
        if not old_names.issubset(names_after):
            raise IsolationError("one or more legacy Chroma collections disappeared")
        sources_after = fingerprint_sources(source_paths)
        if sources_after != plan["source_fingerprints"]:
            raise IsolationError("source fingerprint changed during isolation")
        document = update_manifest(
            manifest_path,
            status="applied",
            applied_at=_now(),
            empty_collection={"name": collection_name, "count": 0, "checksum": str(empty["checksum"])},
            active_snapshot_after=str(activation["snapshot_id"]),
            database_after=database_fingerprint(db_path),
            source_fingerprints_after=sources_after,
            old_collections_after=collections_after,
            verification=state,
            paid_calls=0,
        )
        return {
            "ok": True,
            "generation_id": generation,
            "manifest_path": str(manifest_path.resolve()),
            "backup_path": document["backup"]["path"],
            "collection_name": collection_name,
            "snapshot_id": str(activation["snapshot_id"]),
            "verification": state,
            "paid_calls": 0,
        }
    except Exception as exc:
        try:
            restored = _rollback_after_failure(
                manifest_path=manifest_path,
                db_path=db_path,
                pointer_path=pointer_path,
                dependencies=deps,
                new_collection=collection_name,
                collection_created=collection_created,
            )
            update_manifest(
                manifest_path,
                status="rolled_back_after_failure",
                failed_at=_now(),
                failure_type=type(exc).__name__,
                restoration=restored,
                paid_calls=0,
            )
        except Exception as rollback_exc:
            raise IsolationError(
                f"isolation failed and restoration could not be proven: {type(exc).__name__}; "
                f"restore={type(rollback_exc).__name__}: {rollback_exc}"
            ) from rollback_exc
        raise IsolationError(f"isolation failed and was fully restored: {exc}") from exc


def rollback_isolation(
    *,
    manifest_path: Path,
    db_path: Path | None = None,
    pointer_path: Path | None = None,
    dependencies: IsolationDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or default_dependencies()
    consumers = [dict(item) for item in deps.active_consumers()]
    if consumers:
        raise IsolationError(f"knowledge consumer(s) still active for rollback: {consumers}")
    try:
        document = load_verified_manifest(manifest_path)
        restored = restore_from_manifest(manifest_path, db_path=db_path, pointer_path=pointer_path)
    except ManifestError as exc:
        raise IsolationError(f"manifest verification failed: {exc}") from exc
    empty = document.get("empty_collection") or {}
    name = str(empty.get("name") or "")
    if name:
        deps.delete_collection(name)
    update_manifest(
        manifest_path,
        status="rolled_back_explicitly",
        rolled_back_at=_now(),
        restoration=restored,
        paid_calls=0,
    )
    return {"ok": True, "manifest_path": str(manifest_path.resolve()), **restored, "paid_calls": 0}


def _collection_details(client: ChromaClient, raw: Mapping[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "")
    collection = Collection(client, str(raw.get("id") or ""), name, raw.get("dimension"))
    count = collection.count()
    ids: list[str] = []
    offset = 0
    while True:
        batch = (collection.get(limit=2000, offset=offset, include=[]) or {}).get("ids") or []
        if not batch:
            break
        ids.extend(str(item) for item in batch)
        offset += len(batch)
        if len(batch) < 2000:
            break
    checksum = hashlib.sha256("".join(sorted(ids)).encode("utf-8")).hexdigest()
    return {"name": name, "count": count, "checksum": checksum}


def _list_collections() -> list[dict[str, Any]]:
    client = ChromaClient()
    return [
        _collection_details(client, raw)
        for raw in client.list_collections()
        if str(raw.get("name") or "").startswith("knowledge_units")
    ]


def _create_empty_collection(name: str) -> dict[str, Any]:
    client = ChromaClient()
    existing = {str(item.get("name") or "") for item in client.list_collections()}
    collection = client.get_or_create_collection(
        name,
        metadata={"hnsw:space": "cosine", "generation": "legacy_isolation_empty_v1"},
    )
    detail = _collection_details(client, {"id": collection.id, "name": collection.name})
    return {**detail, "created": name not in existing}


def _delete_collection(name: str) -> None:
    ChromaClient().delete_collection_by_name(name)


def _active_consumers() -> list[dict[str, Any]]:
    if socket.gethostname() and __import__("os").name != "nt":
        raise IsolationError("consumer detection is only implemented for the supported Windows runtime")
    completed = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=15, check=False
    )
    if completed.returncode != 0:
        raise IsolationError("could not prove local knowledge consumers are stopped")
    listeners: dict[tuple[int, int], dict[str, Any]] = {}
    pattern = re.compile(r"^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE)
    for line in completed.stdout.splitlines():
        match = pattern.match(line)
        if match and int(match.group(1)) in _CONSUMER_PORTS:
            port, pid = int(match.group(1)), int(match.group(2))
            listeners[(port, pid)] = {"port": port, "pid": pid}
    return list(listeners.values())


def _inspect_collection(name: str) -> Mapping[str, Any]:
    client = ChromaClient()
    for raw in client.list_collections():
        if str(raw.get("name") or "") == name:
            return {"exists": True, **_collection_details(client, raw)}
    return {"exists": False, "name": name, "count": 0, "checksum": ""}


def build_empty_snapshot_members(
    current: Mapping[str, Any],
    *,
    generation_id: str,
    collection_name: str,
    collection_checksum: str,
    manifest_path: Path,
    publications: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Replace only the three knowledge roles with newly published versions."""
    members: dict[str, dict[str, Any]] = {}
    for role, raw in (current.get("members") or {}).items():
        members[str(role)] = {
            key: raw.get(key)
            for key in (
                "artifact_version_id", "version", "checksum", "location_kind", "location_ref",
                "producer_run_id", "evidence_version_id", "watermark_id", "metadata",
            )
            if raw.get(key) is not None
        }
        if "metadata" not in members[str(role)]:
            try:
                members[str(role)]["metadata"] = json.loads(str(raw.get("metadata_json") or "{}"))
            except json.JSONDecodeError:
                members[str(role)]["metadata"] = {}
    members["canonical_knowledge"] = {
        "artifact_version_id": publications["canonical_knowledge"]["artifact_version_id"],
        "version": generation_id,
        "checksum": hashlib.sha256(b"[]").hexdigest(),
        "location_kind": "sqlite_table",
        "location_ref": "canonical_knowledge_units",
        "producer_run_id": generation_id,
        "watermark_id": publications["canonical_knowledge"]["watermark_id"],
        "metadata": {"unit_count": 0, "mode": "empty_isolation_generation"},
    }
    members["knowledge_retrieval"] = {
        "artifact_version_id": publications["knowledge_retrieval"]["artifact_version_id"],
        "version": f"kiv_{generation_id}",
        "checksum": collection_checksum,
        "location_kind": "chroma_collection",
        "location_ref": collection_name,
        "producer_run_id": generation_id,
        "watermark_id": publications["knowledge_retrieval"]["watermark_id"],
        "metadata": {"unit_count": 0, "canonical_build_id": generation_id},
    }
    members["knowledge_evaluation"] = {
        "artifact_version_id": publications["knowledge_evaluation"]["artifact_version_id"],
        "version": generation_id,
        "checksum": hashlib.sha256(f"empty-evaluation:{generation_id}".encode("utf-8")).hexdigest(),
        "location_kind": "evaluation_run",
        "location_ref": str(manifest_path.resolve()),
        "producer_run_id": generation_id,
        "watermark_id": publications["knowledge_evaluation"]["watermark_id"],
        "metadata": {"status": "not_applicable_empty_generation", "unit_count": 0},
    }
    return members


def _publish_empty_roles(
    db_path: Path,
    current: Mapping[str, Any],
    *,
    generation_id: str,
    collection_name: str,
    collection_checksum: str,
    manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    current_members = current.get("members") or {}
    canonical_message = current_members.get("canonical_message") or {}
    source_marker = f"{canonical_message.get('checksum') or canonical_message.get('version')}:{generation_id}"
    empty_checksum = hashlib.sha256(b"[]").hexdigest()
    canonical = record_publication(
        db_path,
        registry_id="s.knowledge_unit",
        version=generation_id,
        checksum=empty_checksum,
        location_kind="sqlite_table",
        location_ref="canonical_knowledge_units",
        source_key="canonical_message",
        watermark_value=source_marker,
        producer_run_id=generation_id,
        evidence_version_id=canonical_message.get("artifact_version_id"),
        metadata={"unit_count": 0, "mode": "empty_isolation_generation"},
    )
    retrieval = record_publication(
        db_path,
        registry_id="r.knowledge_index",
        version=f"kiv_{generation_id}",
        checksum=collection_checksum,
        location_kind="chroma_collection",
        location_ref=collection_name,
        source_key="canonical_knowledge",
        watermark_value=generation_id,
        producer_run_id=generation_id,
        evidence_version_id=canonical["artifact_version_id"],
        metadata={"unit_count": 0, "canonical_build_id": generation_id},
    )
    evaluation_checksum = hashlib.sha256(f"empty-evaluation:{generation_id}".encode("utf-8")).hexdigest()
    evaluation = record_publication(
        db_path,
        registry_id="a.knowledge_evaluation",
        version=generation_id,
        checksum=evaluation_checksum,
        location_kind="evaluation_run",
        location_ref=str(manifest_path.resolve()),
        source_key="knowledge_retrieval",
        watermark_value=generation_id,
        producer_run_id=generation_id,
        evidence_version_id=retrieval["artifact_version_id"],
        metadata={"status": "not_applicable_empty_generation", "unit_count": 0},
    )
    return {
        "canonical_knowledge": canonical,
        "knowledge_retrieval": retrieval,
        "knowledge_evaluation": evaluation,
    }


def _activate_empty_snapshot(
    db_path: Path,
    generation_id: str,
    collection_name: str,
    collection_checksum: str,
    manifest_path: Path,
) -> Mapping[str, Any]:
    current = get_active_snapshot(db_path)
    if not current:
        raise IsolationError("active serving snapshot missing before activation")
    publications = _publish_empty_roles(
        db_path,
        current,
        generation_id=generation_id,
        collection_name=collection_name,
        collection_checksum=collection_checksum,
        manifest_path=manifest_path,
    )
    members = build_empty_snapshot_members(
        current,
        generation_id=generation_id,
        collection_name=collection_name,
        collection_checksum=collection_checksum,
        manifest_path=manifest_path,
        publications=publications,
    )
    draft = prepare_snapshot(db_path, members, eval_gate_ref=None, write=True)
    required = set(members)
    validated = validate_snapshot(
        db_path,
        str(draft["snapshot_id"]),
        collection_inspector=_inspect_collection,
        required_roles=required,
        require_gate=False,
    )
    if not validated.get("ok"):
        raise IsolationError(f"empty snapshot validation failed: {validated}")
    manifest = load_verified_manifest(manifest_path)
    pointer_path = Path(str(manifest["pointer"]["path"]))
    return activate_snapshot(db_path, str(draft["snapshot_id"]), pointer_path=pointer_path)


def default_dependencies() -> IsolationDependencies:
    return IsolationDependencies(
        list_collections=_list_collections,
        create_empty_collection=_create_empty_collection,
        delete_collection=_delete_collection,
        get_active_snapshot=get_active_snapshot,
        activate_empty_snapshot=_activate_empty_snapshot,
        active_consumers=_active_consumers,
    )
