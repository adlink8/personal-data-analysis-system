"""Phase 14 Wave 1.1：knowledge_unit schema 迁移。

在 ``personal_system.sqlite`` 新增 6 张知识单元表：
  - knowledge_build_runs
  - knowledge_units
  - knowledge_unit_evidence
  - canonical_knowledge_units
  - canonical_unit_members
  - knowledge_index_versions

迁移幂等，默认 dry-run/inspect；不修改 memory_items。

用法::

    python migrate_add_knowledge_unit_tables.py --inspect
    python migrate_add_knowledge_unit_tables.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402
from personal_knowledge.core.sqlite import connect_rw  # noqa: E402

INVENTORY_REGISTRY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_inventory_registry (
    inventory_id    TEXT PRIMARY KEY,
    inventory_kind  TEXT NOT NULL CHECK(inventory_kind IN ('full','delta')),
    created_at      TEXT NOT NULL
);
"""

RUN_ITEMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_run_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    inventory_id    TEXT NOT NULL REFERENCES knowledge_inventory_registry(inventory_id),
    position        INTEGER NOT NULL,
    evidence_ref    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','in_flight','retryable','succeeded','abstained','terminal_failed')),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    lease_started_at TEXT,
    last_error_class TEXT,
    cache_key       TEXT,
    response_hash   TEXT,
    unit_count      INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT,
    UNIQUE(run_id, position)
);
"""

EXTRACTION_GATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_extraction_gates (
    gate_id         TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    inventory_id    TEXT NOT NULL REFERENCES knowledge_inventory_registry(inventory_id),
    gate_status     TEXT NOT NULL CHECK(gate_status IN ('passed','failed','awaiting_pilot_threshold')),
    gate_json       TEXT NOT NULL,
    evaluated_at    TEXT NOT NULL
);
"""

SCHEMA_SQL = f"""
-- 构建运行记录（每次抽取/merge/index build 的版本合同）
CREATE TABLE IF NOT EXISTS knowledge_build_runs (
    run_id          TEXT PRIMARY KEY,
    run_type        TEXT NOT NULL CHECK(run_type IN ('extraction','merge','index','promote','incremental')),
    generated_at    TEXT NOT NULL,
    source_build_id TEXT,  -- 上游 canonical conversation build ID
    input_hash      TEXT NOT NULL,
    prompt_version  TEXT,
    schema_version  TEXT NOT NULL DEFAULT 'v1',
    model           TEXT,
    embedding_model TEXT,
    config_hash     TEXT,
    git_sha         TEXT,
    dataset_hash    TEXT,  -- 输出内容 hash（幂等校验）
    status          TEXT NOT NULL CHECK(status IN ('staging','validated','current','blocked','aborted','pending','in_flight','succeeded','abstained','retryable','terminal_failed','rolled_back','candidate','active','deprecated')),
    stats_json      TEXT,
    supersedes_id   TEXT
);

-- 知识单元（draft，来自 LLM 抽取）
CREATE TABLE IF NOT EXISTS knowledge_units (
    unit_id         TEXT PRIMARY KEY,  -- v1|sha256(run_id|bundle_hash|ordinal)
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    unit_type       TEXT NOT NULL CHECK(unit_type IN ('preference','habit','personal_fact','project_decision','capability','tool_usage')),
    subject         TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    confidence      REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    evidence_quote  TEXT NOT NULL,
    lifecycle       TEXT NOT NULL DEFAULT 'current' CHECK(lifecycle IN ('current','deprecated','superseded','conflict')),
    source_session_id   TEXT,
    source_message_ref  TEXT,
    source_agent    TEXT,
    evidence_scope  TEXT NOT NULL DEFAULT 'user' CHECK(evidence_scope IN ('user','assistant','system','sidechain','subagent')),
    status          TEXT NOT NULL DEFAULT 'staging' CHECK(status IN ('staging','current','rejected')),
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    supersedes_id   TEXT
);

-- 知识单元 ↔ 证据关联（多对一）
CREATE TABLE IF NOT EXISTS knowledge_unit_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id         TEXT NOT NULL REFERENCES knowledge_units(unit_id),
    evidence_ref    TEXT NOT NULL,  -- canonical_message_id
    evidence_type   TEXT NOT NULL DEFAULT 'message',
    UNIQUE(unit_id, evidence_ref)
);

-- canonical 知识单元（去重合并后的权威版本）
CREATE TABLE IF NOT EXISTS canonical_knowledge_units (
    canonical_unit_id   TEXT PRIMARY KEY,  -- cu|sha256(subject|unit_type|answer_hash)
    subject         TEXT NOT NULL,
    unit_type       TEXT NOT NULL CHECK(unit_type IN ('preference','habit','personal_fact','project_decision','capability','tool_usage')),
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    confidence      REAL NOT NULL,
    lifecycle       TEXT NOT NULL DEFAULT 'current',
    status          TEXT NOT NULL DEFAULT 'staging' CHECK(status IN ('staging','current','review','rejected')),
    version         INTEGER NOT NULL DEFAULT 1,
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    merge_reason    TEXT,
    supersedes_id   TEXT,
    created_at      TEXT NOT NULL
);

-- canonical unit 成员链接（哪些 draft units 合并成这个 canonical）
CREATE TABLE IF NOT EXISTS canonical_unit_members (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_unit_id   TEXT NOT NULL REFERENCES canonical_knowledge_units(canonical_unit_id),
    member_unit_id      TEXT NOT NULL REFERENCES knowledge_units(unit_id),
    UNIQUE(canonical_unit_id, member_unit_id)
);

-- 知识索引版本（Chroma collection 的版本指针）
CREATE TABLE IF NOT EXISTS knowledge_index_versions (
    version_id      TEXT PRIMARY KEY,
    build_id        TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    collection_name TEXT NOT NULL,
    canonical_build_id TEXT,
    unit_count      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN ('candidate','active','rolled_back')),
    created_at      TEXT NOT NULL,
    activated_at    TEXT,
    checksum        TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_ku_run ON knowledge_units(run_id);
CREATE INDEX IF NOT EXISTS idx_ku_subject ON knowledge_units(subject);
CREATE INDEX IF NOT EXISTS idx_ku_type ON knowledge_units(unit_type);
CREATE INDEX IF NOT EXISTS idx_ku_status ON knowledge_units(status);
CREATE INDEX IF NOT EXISTS idx_kue_unit ON knowledge_unit_evidence(unit_id);
CREATE INDEX IF NOT EXISTS idx_cku_subject ON canonical_knowledge_units(subject);
CREATE INDEX IF NOT EXISTS idx_cku_status ON canonical_knowledge_units(status);
CREATE INDEX IF NOT EXISTS idx_cum_canonical ON canonical_unit_members(canonical_unit_id);
CREATE INDEX IF NOT EXISTS idx_kiv_status ON knowledge_index_versions(status);

-- === Phase 14 Plan 02: production backfill ===

-- 冻结 inventory（一次 run 的权威输入清单）
CREATE TABLE IF NOT EXISTS knowledge_inventory (
    inventory_id    TEXT PRIMARY KEY,  -- 由完整 dataset hash 派生
    generated_at    TEXT NOT NULL,
    source_db_path  TEXT NOT NULL,
    source_checksum TEXT NOT NULL,     -- canonical DB schema hash + count
    item_count      INTEGER NOT NULL,  -- authoritative count
    coarse_count    INTEGER NOT NULL DEFAULT 0,  -- SQL 粗筛 count（解释差异用）
    dataset_hash    TEXT NOT NULL,     -- 全量有序 content hash 的 Merkle hash
    time_range_min  TEXT,
    time_range_max  TEXT,
    report_json     TEXT               -- 隐私安全统计（无原文）
);

{INVENTORY_REGISTRY_TABLE_SQL}

CREATE TRIGGER IF NOT EXISTS trg_knowledge_inventory_registry
AFTER INSERT ON knowledge_inventory
BEGIN
    INSERT OR IGNORE INTO knowledge_inventory_registry
        (inventory_id, inventory_kind, created_at)
    VALUES (NEW.inventory_id, 'full', NEW.generated_at);
END;

INSERT OR IGNORE INTO knowledge_inventory_registry
    (inventory_id, inventory_kind, created_at)
SELECT inventory_id, 'full', generated_at FROM knowledge_inventory;

-- inventory 逐项明细（每条 evidence 的冻结记录）
CREATE TABLE IF NOT EXISTS knowledge_inventory_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id    TEXT NOT NULL REFERENCES knowledge_inventory(inventory_id),
    position        INTEGER NOT NULL,  -- 有序位置（恢复用）
    evidence_ref    TEXT NOT NULL,     -- canonical_message_id
    content_hash    TEXT NOT NULL,
    session_id      TEXT,
    source          TEXT,
    agent           TEXT,
    time_bucket     TEXT,              -- YYYY-MM
    length_bucket   TEXT,              -- short/mid/long
    has_injection   INTEGER NOT NULL DEFAULT 0,
    eligibility     TEXT NOT NULL DEFAULT 'eligible',
    UNIQUE(inventory_id, position)
);

-- run work-item 状态机（逐项持久化）
{RUN_ITEMS_TABLE_SQL}

-- 内容寻址 response cache（LLM 原始响应）
CREATE TABLE IF NOT EXISTS knowledge_response_cache (
    cache_key       TEXT PRIMARY KEY,  -- model|prompt_hash|schema_hash|input_hash|config_hash
    run_id          TEXT,
    model           TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    schema_hash     TEXT NOT NULL,
    input_hash      TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    response_text   TEXT NOT NULL,     -- 原始 LLM 响应
    response_hash   TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    tokens_total    INTEGER
);

-- extraction gate decision（机器可读）
{EXTRACTION_GATES_TABLE_SQL}

-- Plan 02 索引
CREATE INDEX IF NOT EXISTS idx_kii_inventory ON knowledge_inventory_items(inventory_id);
CREATE INDEX IF NOT EXISTS idx_kri_run ON knowledge_run_items(run_id);
CREATE INDEX IF NOT EXISTS idx_kri_status ON knowledge_run_items(status);
CREATE INDEX IF NOT EXISTS idx_krc_input ON knowledge_response_cache(input_hash);
CREATE INDEX IF NOT EXISTS idx_keg_run ON knowledge_extraction_gates(run_id);

-- === Phase 14 Plan 05: rag feedback & canary ===

CREATE TABLE IF NOT EXISTS rag_runs (
    run_id          TEXT PRIMARY KEY,
    collection_name TEXT NOT NULL,
    index_version   TEXT,
    canonical_build_id TEXT,
    extraction_run_id TEXT,
    route           TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_retrieval_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES rag_runs(run_id),
    query_hash      TEXT NOT NULL,
    top_k           INTEGER NOT NULL,
    returned_ids    TEXT NOT NULL,
    scores          TEXT,
    route           TEXT NOT NULL,
    latency_ms      REAL,
    index_version   TEXT,
    canonical_build_id TEXT,
    extraction_run_id TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rag_feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_id    INTEGER REFERENCES rag_retrieval_items(id),
    label           TEXT NOT NULL CHECK(label IN ('helpful','wrong','stale','missing')),
    labeled_at      TEXT,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_rr_query ON rag_retrieval_items(query_hash);
CREATE INDEX IF NOT EXISTS idx_rf_retrieval ON rag_feedback(retrieval_id);

-- Plan 07: incremental delta inventory + source watermark
CREATE TABLE IF NOT EXISTS knowledge_delta_inventories (
    delta_inventory_id   TEXT PRIMARY KEY,
    source_before_checksum TEXT NOT NULL,
    source_after_checksum  TEXT NOT NULL,
    ordered_dataset_hash   TEXT NOT NULL,
    new_count              INTEGER DEFAULT 0,
    modified_count         INTEGER DEFAULT 0,
    deleted_count          INTEGER DEFAULT 0,
    model                  TEXT NOT NULL,
    prompt_version         TEXT,
    schema_version         TEXT,
    config_hash            TEXT,
    created_at             TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_knowledge_delta_inventory_registry
AFTER INSERT ON knowledge_delta_inventories
BEGIN
    INSERT OR IGNORE INTO knowledge_inventory_registry
        (inventory_id, inventory_kind, created_at)
    VALUES (NEW.delta_inventory_id, 'delta', NEW.created_at);
END;

INSERT OR IGNORE INTO knowledge_inventory_registry
    (inventory_id, inventory_kind, created_at)
SELECT delta_inventory_id, 'delta', created_at FROM knowledge_delta_inventories;

CREATE TABLE IF NOT EXISTS knowledge_delta_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    delta_inventory_id  TEXT NOT NULL REFERENCES knowledge_delta_inventories(delta_inventory_id),
    ref                 TEXT NOT NULL,
    change_type         TEXT NOT NULL CHECK(change_type IN ('new','modified','deleted')),
    content_hash_before TEXT,
    content_hash_after  TEXT,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_di_delta ON knowledge_delta_items(delta_inventory_id);
CREATE INDEX IF NOT EXISTS idx_di_ref ON knowledge_delta_items(ref);

CREATE TABLE IF NOT EXISTS knowledge_source_watermark (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- === Phase 23: typed artifact versions + composite serving authority ===
CREATE TABLE IF NOT EXISTS artifact_registry_entries (
    registry_id     TEXT PRIMARY KEY,
    layer           TEXT NOT NULL CHECK(layer IN ('D','S','R','A')),
    authority_role  TEXT NOT NULL UNIQUE,
    privacy_class   TEXT NOT NULL CHECK(privacy_class IN ('R1','R2','R3','R4')),
    definition_hash TEXT NOT NULL CHECK(length(definition_hash) > 0),
    registered_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_versions (
    artifact_version_id TEXT PRIMARY KEY,
    registry_id         TEXT NOT NULL REFERENCES artifact_registry_entries(registry_id),
    version             TEXT NOT NULL,
    checksum            TEXT NOT NULL CHECK(length(checksum) > 0),
    location_kind       TEXT NOT NULL,
    location_ref        TEXT NOT NULL,
    lifecycle           TEXT NOT NULL CHECK(lifecycle IN ('draft','validated','published','superseded','rolled_back')),
    privacy_class       TEXT NOT NULL CHECK(privacy_class IN ('R1','R2','R3','R4')),
    producer_run_id     TEXT,
    evidence_version_id TEXT REFERENCES artifact_versions(artifact_version_id),
    metadata_json       TEXT NOT NULL DEFAULT '{{}}',
    created_at          TEXT NOT NULL,
    UNIQUE(registry_id, version, checksum)
);

CREATE TABLE IF NOT EXISTS source_watermarks (
    watermark_id        TEXT PRIMARY KEY,
    registry_id         TEXT NOT NULL REFERENCES artifact_registry_entries(registry_id),
    source_key          TEXT NOT NULL,
    value               TEXT NOT NULL,
    artifact_version_id TEXT NOT NULL REFERENCES artifact_versions(artifact_version_id),
    recorded_at         TEXT NOT NULL,
    UNIQUE(registry_id, source_key, value)
);

CREATE TABLE IF NOT EXISTS serving_snapshots (
    snapshot_id      TEXT PRIMARY KEY,
    manifest_json    TEXT NOT NULL,
    manifest_hash    TEXT NOT NULL UNIQUE CHECK(length(manifest_hash) > 0),
    status           TEXT NOT NULL CHECK(status IN ('draft','validated','retired')),
    eval_gate_ref    TEXT,
    created_at       TEXT NOT NULL,
    validated_at     TEXT
);

CREATE TABLE IF NOT EXISTS serving_snapshot_members (
    snapshot_id         TEXT NOT NULL REFERENCES serving_snapshots(snapshot_id),
    serving_role        TEXT NOT NULL,
    artifact_version_id TEXT NOT NULL REFERENCES artifact_versions(artifact_version_id),
    watermark_id        TEXT REFERENCES source_watermarks(watermark_id),
    PRIMARY KEY(snapshot_id, serving_role),
    UNIQUE(snapshot_id, artifact_version_id)
);

CREATE TABLE IF NOT EXISTS serving_authority (
    singleton_id       INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    active_snapshot_id TEXT REFERENCES serving_snapshots(snapshot_id),
    activated_at       TEXT,
    activation_event_id TEXT
);
INSERT OR IGNORE INTO serving_authority(singleton_id) VALUES (1);

CREATE TABLE IF NOT EXISTS serving_snapshot_events (
    event_id        TEXT PRIMARY KEY,
    snapshot_id     TEXT REFERENCES serving_snapshots(snapshot_id),
    action          TEXT NOT NULL CHECK(action IN ('prepare','validate','activate','rollback','refuse','projection_drift','projection_repair')),
    previous_snapshot_id TEXT REFERENCES serving_snapshots(snapshot_id),
    detail_json     TEXT NOT NULL DEFAULT '{{}}',
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_versions_registry ON artifact_versions(registry_id, created_at);
CREATE INDEX IF NOT EXISTS idx_source_watermarks_registry ON source_watermarks(registry_id, source_key, recorded_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_members_version ON serving_snapshot_members(artifact_version_id);
CREATE INDEX IF NOT EXISTS idx_snapshot_events_snapshot ON serving_snapshot_events(snapshot_id, created_at);

CREATE TRIGGER IF NOT EXISTS trg_artifact_versions_immutable_update
BEFORE UPDATE ON artifact_versions BEGIN
    SELECT RAISE(ABORT, 'artifact versions are immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_artifact_versions_immutable_delete
BEFORE DELETE ON artifact_versions BEGIN
    SELECT RAISE(ABORT, 'artifact versions are immutable');
END;
CREATE TRIGGER IF NOT EXISTS trg_active_snapshot_member_insert
BEFORE INSERT ON serving_snapshot_members
WHEN NEW.snapshot_id = (SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1)
BEGIN SELECT RAISE(ABORT, 'active snapshot members are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_active_snapshot_member_update
BEFORE UPDATE ON serving_snapshot_members
WHEN OLD.snapshot_id = (SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1)
BEGIN SELECT RAISE(ABORT, 'active snapshot members are immutable'); END;
CREATE TRIGGER IF NOT EXISTS trg_active_snapshot_member_delete
BEFORE DELETE ON serving_snapshot_members
WHEN OLD.snapshot_id = (SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1)
BEGIN SELECT RAISE(ABORT, 'active snapshot members are immutable'); END;
"""


def _foreign_key_target(
    con: sqlite3.Connection, table: str, column: str
) -> str:
    for row in con.execute(f'PRAGMA foreign_key_list("{table}")'):
        if row[3] == column:
            return str(row[2])
    return ""


def inspect_inventory_registry(db_path: Path = UNIFIED_DB) -> dict:
    """Inspect the full/delta inventory parent model without writing."""
    if not db_path.exists():
        return {"db_exists": False, "db_path": str(db_path)}
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        tables = {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {
            "knowledge_inventory",
            "knowledge_delta_inventories",
            "knowledge_run_items",
            "knowledge_extraction_gates",
        }
        missing_tables = sorted(required - tables)
        registry_exists = "knowledge_inventory_registry" in tables
        run_target = (
            _foreign_key_target(con, "knowledge_run_items", "inventory_id")
            if "knowledge_run_items" in tables
            else ""
        )
        gate_target = (
            _foreign_key_target(con, "knowledge_extraction_gates", "inventory_id")
            if "knowledge_extraction_gates" in tables
            else ""
        )
        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        by_table: dict[str, int] = {}
        for row in violations:
            by_table[str(row[0])] = by_table.get(str(row[0]), 0) + 1
        counts = {
            "full": con.execute(
                "SELECT COUNT(*) FROM knowledge_inventory"
            ).fetchone()[0]
            if "knowledge_inventory" in tables
            else 0,
            "delta": con.execute(
                "SELECT COUNT(*) FROM knowledge_delta_inventories"
            ).fetchone()[0]
            if "knowledge_delta_inventories" in tables
            else 0,
            "registry": con.execute(
                "SELECT COUNT(*) FROM knowledge_inventory_registry"
            ).fetchone()[0]
            if registry_exists
            else 0,
            "run_items": con.execute(
                "SELECT COUNT(*) FROM knowledge_run_items"
            ).fetchone()[0]
            if "knowledge_run_items" in tables
            else 0,
            "gates": con.execute(
                "SELECT COUNT(*) FROM knowledge_extraction_gates"
            ).fetchone()[0]
            if "knowledge_extraction_gates" in tables
            else 0,
        }
        target = "knowledge_inventory_registry"
        healthy = (
            not missing_tables
            and registry_exists
            and run_target == target
            and gate_target == target
            and not violations
            and counts["registry"] == counts["full"] + counts["delta"]
        )
        return {
            "db_exists": True,
            "db_path": str(db_path),
            "missing_tables": missing_tables,
            "registry_exists": registry_exists,
            "run_items_inventory_fk_target": run_target,
            "gates_inventory_fk_target": gate_target,
            "counts": counts,
            "foreign_key_violations_total": len(violations),
            "foreign_key_violations_by_table": by_table,
            "healthy": healthy,
        }
    finally:
        con.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_sqlite(source: Path, backup_path: Path) -> dict:
    if backup_path.exists():
        raise FileExistsError(f"backup target already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise sqlite3.DatabaseError(f"backup integrity_check: {integrity}")
    finally:
        dst.close()
        src.close()
    return {
        "path": str(backup_path),
        "bytes": backup_path.stat().st_size,
        "sha256": _sha256_file(backup_path),
        "integrity_check": "ok",
    }


def _rebuild_inventory_fk_table(
    con: sqlite3.Connection,
    *,
    table: str,
    create_sql: str,
    columns: tuple[str, ...],
    indexes: tuple[str, ...],
) -> tuple[int, int]:
    legacy = f"{table}_legacy_inventory_fk"
    if con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (legacy,)
    ).fetchone():
        raise RuntimeError(f"stale migration table exists: {legacy}")
    before = int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    con.execute(f'ALTER TABLE "{table}" RENAME TO "{legacy}"')
    con.execute(create_sql)
    column_sql = ", ".join(f'"{name}"' for name in columns)
    con.execute(
        f'INSERT INTO "{table}" ({column_sql}) '
        f'SELECT {column_sql} FROM "{legacy}"'
    )
    after = int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    if after != before:
        raise RuntimeError(f"row count mismatch rebuilding {table}: {before} != {after}")
    con.execute(f'DROP TABLE "{legacy}"')
    for index_sql in indexes:
        con.execute(index_sql)
    return before, after


def migrate_inventory_registry(
    db_path: Path = UNIFIED_DB,
    *,
    write: bool = False,
    backup_path: Path | None = None,
) -> dict:
    """Repair polymorphic inventory FKs using a unified parent registry."""
    before = inspect_inventory_registry(db_path)
    if not before.get("db_exists"):
        return {"error": f"DB does not exist: {db_path}"}
    if before.get("missing_tables"):
        return {"error": f"required tables missing: {before['missing_tables']}"}
    if before.get("healthy"):
        return {"no_op": True, "before": before, "after": before}
    if not write:
        return {
            "dry_run": True,
            "would_backup": str(backup_path) if backup_path else None,
            "would_create_registry": not before.get("registry_exists"),
            "would_rebuild": ["knowledge_run_items", "knowledge_extraction_gates"],
            "before": before,
        }
    if backup_path is None:
        return {"error": "--backup is required for --write"}

    backup = _backup_sqlite(db_path, backup_path)
    con = sqlite3.connect(str(db_path), timeout=60)
    rebuilt: dict[str, dict[str, int]] = {}
    try:
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("BEGIN IMMEDIATE")
        con.execute(INVENTORY_REGISTRY_TABLE_SQL)
        con.execute(
            "INSERT OR IGNORE INTO knowledge_inventory_registry "
            "(inventory_id, inventory_kind, created_at) "
            "SELECT inventory_id, 'full', generated_at FROM knowledge_inventory"
        )
        con.execute(
            "INSERT OR IGNORE INTO knowledge_inventory_registry "
            "(inventory_id, inventory_kind, created_at) "
            "SELECT delta_inventory_id, 'delta', created_at "
            "FROM knowledge_delta_inventories"
        )
        con.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_knowledge_inventory_registry "
            "AFTER INSERT ON knowledge_inventory BEGIN "
            "INSERT OR IGNORE INTO knowledge_inventory_registry "
            "(inventory_id, inventory_kind, created_at) "
            "VALUES (NEW.inventory_id, 'full', NEW.generated_at); END"
        )
        con.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_knowledge_delta_inventory_registry "
            "AFTER INSERT ON knowledge_delta_inventories BEGIN "
            "INSERT OR IGNORE INTO knowledge_inventory_registry "
            "(inventory_id, inventory_kind, created_at) "
            "VALUES (NEW.delta_inventory_id, 'delta', NEW.created_at); END"
        )

        if _foreign_key_target(
            con, "knowledge_run_items", "inventory_id"
        ) != "knowledge_inventory_registry":
            old, new = _rebuild_inventory_fk_table(
                con,
                table="knowledge_run_items",
                create_sql=RUN_ITEMS_TABLE_SQL,
                columns=(
                    "id", "run_id", "inventory_id", "position", "evidence_ref",
                    "status", "attempt_count", "lease_started_at",
                    "last_error_class", "cache_key", "response_hash",
                    "unit_count", "updated_at",
                ),
                indexes=(
                    "CREATE INDEX idx_kri_run ON knowledge_run_items(run_id)",
                    "CREATE INDEX idx_kri_status ON knowledge_run_items(status)",
                ),
            )
            rebuilt["knowledge_run_items"] = {"before": old, "after": new}

        if _foreign_key_target(
            con, "knowledge_extraction_gates", "inventory_id"
        ) != "knowledge_inventory_registry":
            old, new = _rebuild_inventory_fk_table(
                con,
                table="knowledge_extraction_gates",
                create_sql=EXTRACTION_GATES_TABLE_SQL,
                columns=(
                    "gate_id", "run_id", "inventory_id", "gate_status",
                    "gate_json", "evaluated_at",
                ),
                indexes=(
                    "CREATE INDEX idx_keg_run ON knowledge_extraction_gates(run_id)",
                ),
            )
            rebuilt["knowledge_extraction_gates"] = {"before": old, "after": new}

        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            counts: dict[str, int] = {}
            for row in violations:
                counts[str(row[0])] = counts.get(str(row[0]), 0) + 1
            raise sqlite3.IntegrityError(
                f"foreign_key_check still reports {len(violations)}: {counts}"
            )
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("integrity_check failed before commit")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    after = inspect_inventory_registry(db_path)
    if not after.get("healthy"):
        raise RuntimeError(f"post-migration verification failed: {after}")
    return {
        "migrated": True,
        "backup": backup,
        "rebuilt": rebuilt,
        "before": before,
        "after": after,
    }


def inspect(db_path: Path = UNIFIED_DB) -> dict:
    """检查现有表状态。"""
    if not db_path.exists():
        return {"db_exists": False, "tables": []}
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    existing = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()

    new_tables = [
        "knowledge_build_runs", "knowledge_units", "knowledge_unit_evidence",
        "canonical_knowledge_units", "canonical_unit_members", "knowledge_index_versions",
        # Plan 02
        "knowledge_inventory", "knowledge_inventory_items",
        "knowledge_inventory_registry",
        "knowledge_run_items", "knowledge_response_cache", "knowledge_extraction_gates",
        # Plan 05
        "rag_runs", "rag_retrieval_items", "rag_feedback",
        # Plan 07
        "knowledge_delta_inventories", "knowledge_delta_items", "knowledge_source_watermark",
        # Phase 23 composite serving authority
        "artifact_registry_entries", "artifact_versions", "source_watermarks",
        "serving_snapshots", "serving_snapshot_members", "serving_authority",
        "serving_snapshot_events",
    ]
    return {
        "db_exists": True,
        "db_path": str(db_path),
        "existing_tables": sorted(existing & set(new_tables)),
        "missing_tables": sorted(set(new_tables) - existing),
    }


def plan_serving_bootstrap(db_path: Path = UNIFIED_DB) -> dict:
    """Build a read-only draft description for the current KU serving state."""
    before = db_path.stat().st_mtime_ns if db_path.exists() else None
    if not db_path.exists():
        return {"db_exists": False, "active": False, "missing_proofs": ["unified_db"]}
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "knowledge_index_versions" not in tables:
            return {"db_exists": True, "active": False, "missing_proofs": ["knowledge_index_versions"]}
        rows = con.execute(
            "SELECT version_id, build_id, collection_name, canonical_build_id, unit_count, checksum "
            "FROM knowledge_index_versions WHERE status='active' ORDER BY activated_at DESC"
        ).fetchall()
        missing: list[str] = []
        if len(rows) != 1:
            missing.append("exactly_one_active_knowledge_index")
        row = rows[0] if len(rows) == 1 else None
        if row and not row[5]:
            missing.append("active_collection_checksum")
        return {
            "db_exists": True,
            "active": False,
            "mode": "draft_only",
            "knowledge_index": dict(zip(
                ("version_id", "build_id", "collection_name", "canonical_build_id", "unit_count", "checksum"),
                row,
            )) if row else None,
            "missing_proofs": missing,
        }
    finally:
        con.close()
        after = db_path.stat().st_mtime_ns if db_path.exists() else None
        if before != after:
            raise RuntimeError("read-only bootstrap planning modified the database")


def migrate(db_path: Path = UNIFIED_DB, write: bool = False) -> dict:
    """执行迁移。"""
    info = inspect(db_path)
    if not info["db_exists"]:
        return {"error": f"DB 不存在: {db_path}"}
    if not info["missing_tables"] and write:
        return {"message": "所有表已存在，无需迁移", "tables": info["existing_tables"]}

    if write and {
        "knowledge_run_items",
        "knowledge_extraction_gates",
    }.issubset(set(info["existing_tables"])):
        registry_state = inspect_inventory_registry(db_path)
        if not registry_state.get("healthy"):
            return {
                "error": (
                    "existing inventory consumers require the guarded repair: "
                    "--repair-inventory-fks --write --backup <path>"
                ),
                "inventory_registry": registry_state,
            }

    if not write:
        return {"dry_run": True, "would_create": info["missing_tables"],
                "already_exist": info["existing_tables"]}

    con = connect_rw(db_path)
    try:
        con.executescript(SCHEMA_SQL)
        con.commit()
    finally:
        con.close()

    result = inspect(db_path)
    return {"migrated": True, "tables": result["existing_tables"]}


def main(argv: list[str] | None = None) -> int:
    import json

    p = argparse.ArgumentParser(description="Phase 14 Wave 1.1: knowledge_unit schema 迁移")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--inspect", action="store_true", help="检查现有表状态")
    g.add_argument("--write", action="store_true", help="执行迁移")
    p.add_argument(
        "--repair-inventory-fks",
        action="store_true",
        help="Repair full/delta inventory parent FKs (guarded, backup required for write)",
    )
    p.add_argument(
        "--backup",
        type=Path,
        default=None,
        help="New backup path required with --repair-inventory-fks --write",
    )
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)

    if args.repair_inventory_fks:
        result = migrate_inventory_registry(
            args.db,
            write=args.write,
            backup_path=args.backup,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if "error" not in result else 1

    if args.inspect or not args.write:
        result = inspect(args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = migrate(args.db, write=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
