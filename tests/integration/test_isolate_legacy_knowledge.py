from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.legacy_isolation import (
    DERIVED_KNOWLEDGE_TABLES,
    IsolationDependencies,
    IsolationError,
    apply_isolation,
    build_empty_snapshot_members,
    plan_isolation,
    rollback_isolation,
)
from personal_knowledge.application.knowledge.quarantine_manifest import (
    database_fingerprint,
)


def _create_database(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        PRAGMA foreign_keys=ON;
        CREATE TABLE source_messages(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE google_events(id TEXT PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE knowledge_build_runs(
            run_id TEXT PRIMARY KEY, run_type TEXT NOT NULL, generated_at TEXT NOT NULL,
            input_hash TEXT NOT NULL, schema_version TEXT NOT NULL, status TEXT NOT NULL,
            stats_json TEXT
        );
        CREATE TABLE knowledge_inventory_registry(inventory_id TEXT PRIMARY KEY);
        CREATE TABLE knowledge_inventory(inventory_id TEXT PRIMARY KEY);
        CREATE TABLE knowledge_inventory_items(id INTEGER PRIMARY KEY, inventory_id TEXT);
        CREATE TABLE knowledge_run_items(id INTEGER PRIMARY KEY, run_id TEXT, inventory_id TEXT);
        CREATE TABLE knowledge_response_cache(cache_key TEXT PRIMARY KEY);
        CREATE TABLE knowledge_extraction_gates(gate_id TEXT PRIMARY KEY, run_id TEXT, inventory_id TEXT);
        CREATE TABLE knowledge_units(unit_id TEXT PRIMARY KEY, run_id TEXT);
        CREATE TABLE knowledge_unit_evidence(id INTEGER PRIMARY KEY, unit_id TEXT);
        CREATE TABLE canonical_knowledge_units(canonical_unit_id TEXT PRIMARY KEY, run_id TEXT);
        CREATE TABLE canonical_unit_members(id INTEGER PRIMARY KEY, canonical_unit_id TEXT, member_unit_id TEXT);
        CREATE TABLE knowledge_index_versions(
            version_id TEXT PRIMARY KEY, build_id TEXT NOT NULL,
            collection_name TEXT NOT NULL, canonical_build_id TEXT,
            unit_count INTEGER NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, activated_at TEXT, checksum TEXT
        );
        CREATE TABLE knowledge_dead_refs(id INTEGER PRIMARY KEY);
        CREATE TABLE knowledge_delta_inventories(delta_inventory_id TEXT PRIMARY KEY);
        CREATE TABLE knowledge_delta_items(id INTEGER PRIMARY KEY, delta_inventory_id TEXT);
        CREATE TABLE knowledge_incremental_journals(journal_id TEXT PRIMARY KEY);
        CREATE TABLE knowledge_l2_session_jobs(run_id TEXT, session_id TEXT, PRIMARY KEY(run_id, session_id));
        CREATE TABLE knowledge_lifecycle_manifests(manifest_id TEXT PRIMARY KEY);
        CREATE TABLE knowledge_lifecycle_actions(action_id TEXT PRIMARY KEY, manifest_id TEXT, unit_id TEXT);
        CREATE TABLE knowledge_lifecycle_events(event_id TEXT PRIMARY KEY, manifest_id TEXT, action_id TEXT, unit_id TEXT);
        CREATE TABLE knowledge_unit_corrections(correction_id TEXT PRIMARY KEY, event_id TEXT, unit_id TEXT);
        CREATE TABLE knowledge_source_watermark(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE serving_authority(singleton_id INTEGER PRIMARY KEY, active_snapshot_id TEXT);
        """
    )
    con.execute("INSERT INTO source_messages VALUES ('source-1','keep me')")
    con.execute("INSERT INTO google_events VALUES ('google-1','keep me too')")
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES (?,?,?,?,?,?,?)",
        ("old-run", "extraction", "2026-01-01T00:00:00Z", "old", "v1", "current", "{}"),
    )
    for table, columns, values in (
        ("knowledge_inventory_registry", "inventory_id", ("old-inventory",)),
        ("knowledge_inventory", "inventory_id", ("old-inventory",)),
        ("knowledge_inventory_items", "id,inventory_id", (1, "old-inventory")),
        ("knowledge_run_items", "id,run_id,inventory_id", (1, "old-run", "old-inventory")),
        ("knowledge_response_cache", "cache_key", ("old-cache",)),
        ("knowledge_extraction_gates", "gate_id,run_id,inventory_id", ("old-gate", "old-run", "old-inventory")),
        ("knowledge_units", "unit_id,run_id", ("old-unit", "old-run")),
        ("knowledge_unit_evidence", "id,unit_id", (1, "old-unit")),
        ("canonical_knowledge_units", "canonical_unit_id,run_id", ("old-canonical", "old-run")),
        ("canonical_unit_members", "id,canonical_unit_id,member_unit_id", (1, "old-canonical", "old-unit")),
        ("knowledge_index_versions", "version_id,build_id,collection_name,canonical_build_id,unit_count,status,created_at", ("old-index", "old-run", "knowledge_units_old", "old-run", 1, "active", "2026-01-01T00:00:00Z")),
        ("knowledge_dead_refs", "id", (1,)),
        ("knowledge_delta_inventories", "delta_inventory_id", ("old-delta",)),
        ("knowledge_delta_items", "id,delta_inventory_id", (1, "old-delta")),
        ("knowledge_incremental_journals", "journal_id", ("old-journal",)),
        ("knowledge_l2_session_jobs", "run_id,session_id", ("old-run", "old-session")),
        ("knowledge_lifecycle_manifests", "manifest_id", ("old-manifest",)),
        ("knowledge_lifecycle_actions", "action_id,manifest_id,unit_id", ("old-action", "old-manifest", "old-canonical")),
        ("knowledge_lifecycle_events", "event_id,manifest_id,action_id,unit_id", ("old-event", "old-manifest", "old-action", "old-canonical")),
        ("knowledge_unit_corrections", "correction_id,event_id,unit_id", ("old-correction", "old-event", "old-canonical")),
        ("knowledge_source_watermark", "key,value", ("current", "old-watermark")),
    ):
        marks = ",".join("?" for _ in values)
        con.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({marks})', values)
    con.execute("INSERT INTO serving_authority VALUES (1,'snapshot-old')")
    con.commit()
    con.close()


class FakeRuntime:
    def __init__(self, pointer: Path, *, projection_ok: bool = True, consumers: tuple[dict, ...] = ()) -> None:
        self.pointer = pointer
        self.projection_ok = projection_ok
        self.consumers = consumers
        self.collections = {"knowledge_units_old": {"count": 1, "checksum": "old-checksum"}}
        self.deleted: list[str] = []

    def dependencies(self) -> IsolationDependencies:
        return IsolationDependencies(
            list_collections=self.list_collections,
            create_empty_collection=self.create_empty_collection,
            delete_collection=self.delete_collection,
            get_active_snapshot=self.get_active_snapshot,
            activate_empty_snapshot=self.activate_empty_snapshot,
            active_consumers=lambda: list(self.consumers),
        )

    def get_active_snapshot(self, db_path: Path) -> dict:
        con = sqlite3.connect(db_path)
        snapshot_id = con.execute(
            "SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1"
        ).fetchone()[0]
        con.close()
        active_collection = (
            self.pointer.read_text(encoding="utf-8").strip()
            if self.pointer.exists()
            else "knowledge_units_old"
        )
        return {
            "snapshot_id": snapshot_id,
            "members": {
                "canonical_conversation": {"location_ref": "source_messages"},
                "canonical_knowledge": {"location_ref": "canonical_knowledge_units"},
                "knowledge_retrieval": {"location_ref": active_collection},
                "knowledge_evaluation": {"location_ref": "old-eval.json"},
            },
        }

    def list_collections(self) -> list[dict]:
        return [
            {"name": name, "count": value["count"], "checksum": value["checksum"]}
            for name, value in sorted(self.collections.items())
        ]

    def create_empty_collection(self, name: str) -> dict:
        self.collections[name] = {"count": 0, "checksum": "empty-checksum"}
        return {"name": name, **self.collections[name], "created": True}

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        self.collections.pop(name, None)

    def activate_empty_snapshot(
        self,
        db_path: Path,
        generation_id: str,
        collection_name: str,
        collection_checksum: str,
        manifest_path: Path,
    ) -> dict:
        con = sqlite3.connect(db_path)
        con.execute("UPDATE serving_authority SET active_snapshot_id=? WHERE singleton_id=1", (f"snapshot-{generation_id}",))
        con.commit()
        con.close()
        self.pointer.write_text(collection_name, encoding="utf-8")
        return {
            "ok": True,
            "projection_ok": self.projection_ok,
            "snapshot_id": f"snapshot-{generation_id}",
        }


def _paths(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, Path]]:
    db = tmp_path / "personal_system.sqlite"
    _create_database(db)
    pointer = tmp_path / "knowledge_index_active.txt"
    pointer.write_text("knowledge_units_old", encoding="utf-8")
    source = tmp_path / "canonical.sqlite"
    _create_database(source)
    return db, pointer, tmp_path / "quarantine", {"canonical": source}


def test_plan_is_read_only_and_never_targets_source_tables(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    runtime = FakeRuntime(pointer)
    before = database_fingerprint(db)

    result = plan_isolation(
        db_path=db,
        pointer_path=pointer,
        quarantine_root=quarantine,
        source_paths=sources,
        dependencies=runtime.dependencies(),
        generation_id="kg_test_plan",
    )

    assert result["write"] is False
    assert result["generation_id"] == "kg_test_plan"
    assert set(result["target_tables"]) == set(DERIVED_KNOWLEDGE_TABLES)
    assert "source_messages" not in result["target_tables"]
    assert "google_events" not in result["target_tables"]
    assert database_fingerprint(db) == before
    assert not quarantine.exists()


def test_apply_quarantines_old_state_and_leaves_one_empty_generation(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    runtime = FakeRuntime(pointer)
    source_before = database_fingerprint(sources["canonical"])

    result = apply_isolation(
        db_path=db,
        pointer_path=pointer,
        quarantine_root=quarantine,
        source_paths=sources,
        dependencies=runtime.dependencies(),
        generation_id="kg_test_apply",
    )

    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert Path(manifest["backup"]["path"]).exists()
    assert database_fingerprint(sources["canonical"]) == source_before
    assert "knowledge_units_old" in runtime.collections
    assert runtime.collections[result["collection_name"]]["count"] == 0
    assert pointer.read_text(encoding="utf-8") == result["collection_name"]

    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT body FROM source_messages").fetchone()[0] == "keep me"
        for table in DERIVED_KNOWLEDGE_TABLES:
            count = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            expected = 1 if table in {"knowledge_build_runs", "knowledge_index_versions"} else 0
            assert count == expected, table
    finally:
        con.close()


def test_projection_failure_restores_authority_pointer_and_database(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    runtime = FakeRuntime(pointer, projection_ok=False)
    before = database_fingerprint(db)

    with pytest.raises(IsolationError, match="projection"):
        apply_isolation(
            db_path=db,
            pointer_path=pointer,
            quarantine_root=quarantine,
            source_paths=sources,
            dependencies=runtime.dependencies(),
            generation_id="kg_test_projection_fail",
        )

    assert database_fingerprint(db) == before
    assert pointer.read_text(encoding="utf-8") == "knowledge_units_old"
    assert "knowledge_units_empty_kg_test_projection_fail" in runtime.deleted
    con = sqlite3.connect(db)
    try:
        assert con.execute("SELECT active_snapshot_id FROM serving_authority").fetchone()[0] == "snapshot-old"
    finally:
        con.close()


def test_manifest_drift_is_refused_and_does_not_modify_database(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    runtime = FakeRuntime(pointer)
    result = apply_isolation(
        db_path=db,
        pointer_path=pointer,
        quarantine_root=quarantine,
        source_paths=sources,
        dependencies=runtime.dependencies(),
        generation_id="kg_test_manifest_drift",
    )
    before = database_fingerprint(db)
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_db"] = str(tmp_path / "other.sqlite")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(IsolationError, match="manifest"):
        rollback_isolation(
            manifest_path=manifest_path,
            db_path=db,
            pointer_path=pointer,
            dependencies=runtime.dependencies(),
        )
    assert database_fingerprint(db) == before


def test_active_consumer_and_unknown_knowledge_table_fail_closed(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    runtime = FakeRuntime(pointer, consumers=({"port": 8000, "pid": 123},))
    before = database_fingerprint(db)
    with pytest.raises(IsolationError, match="consumer"):
        apply_isolation(
            db_path=db,
            pointer_path=pointer,
            quarantine_root=quarantine,
            source_paths=sources,
            dependencies=runtime.dependencies(),
            generation_id="kg_test_consumer",
        )
    assert database_fingerprint(db) == before

    con = sqlite3.connect(db)
    con.execute("CREATE TABLE knowledge_surprise(id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    with pytest.raises(IsolationError, match="unknown knowledge table"):
        plan_isolation(
            db_path=db,
            pointer_path=pointer,
            quarantine_root=quarantine,
            source_paths=sources,
            dependencies=FakeRuntime(pointer).dependencies(),
            generation_id="kg_test_unknown",
        )


def test_unknown_foreign_key_into_derived_state_fails_closed(tmp_path: Path) -> None:
    db, pointer, quarantine, sources = _paths(tmp_path)
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE outside_owner(id INTEGER PRIMARY KEY, unit_id TEXT REFERENCES knowledge_units(unit_id))"
    )
    con.commit()
    con.close()

    with pytest.raises(IsolationError, match="foreign key"):
        plan_isolation(
            db_path=db,
            pointer_path=pointer,
            quarantine_root=quarantine,
            source_paths=sources,
            dependencies=FakeRuntime(pointer).dependencies(),
            generation_id="kg_test_fk",
        )


def test_empty_snapshot_members_preserve_each_roles_nonregressing_watermark(tmp_path: Path) -> None:
    current = {
        "members": {
            "canonical_message": {"watermark_id": "wm-message", "metadata_json": "{}"},
            "canonical_knowledge": {"watermark_id": "wm-knowledge", "metadata_json": "{}"},
            "knowledge_retrieval": {"watermark_id": "wm-retrieval", "metadata_json": "{}"},
            "knowledge_evaluation": {"watermark_id": "wm-evaluation", "metadata_json": "{}"},
        }
    }

    members = build_empty_snapshot_members(
        current,
        generation_id="kg_test_watermarks",
        collection_name="knowledge_units_empty_kg_test_watermarks",
        collection_checksum="empty-checksum",
        manifest_path=tmp_path / "manifest.json",
    )

    assert members["canonical_knowledge"]["watermark_id"] == "wm-knowledge"
    assert members["knowledge_retrieval"]["watermark_id"] == "wm-retrieval"
    assert members["knowledge_evaluation"]["watermark_id"] == "wm-evaluation"
