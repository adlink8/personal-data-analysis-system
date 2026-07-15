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
import sqlite3
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402

SCHEMA_SQL = """
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
CREATE TABLE IF NOT EXISTS knowledge_run_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    inventory_id    TEXT NOT NULL REFERENCES knowledge_inventory(inventory_id),
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
CREATE TABLE IF NOT EXISTS knowledge_extraction_gates (
    gate_id         TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES knowledge_build_runs(run_id),
    inventory_id    TEXT NOT NULL REFERENCES knowledge_inventory(inventory_id),
    gate_status     TEXT NOT NULL CHECK(gate_status IN ('passed','failed','awaiting_pilot_threshold')),
    gate_json       TEXT NOT NULL,     -- 完整 gate 报告
    evaluated_at    TEXT NOT NULL
);

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
"""


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
        "knowledge_run_items", "knowledge_response_cache", "knowledge_extraction_gates",
        # Plan 05
        "rag_runs", "rag_retrieval_items", "rag_feedback",
        # Plan 07
        "knowledge_delta_inventories", "knowledge_delta_items", "knowledge_source_watermark",
    ]
    return {
        "db_exists": True,
        "db_path": str(db_path),
        "existing_tables": sorted(existing & set(new_tables)),
        "missing_tables": sorted(set(new_tables) - existing),
    }


def migrate(db_path: Path = UNIFIED_DB, write: bool = False) -> dict:
    """执行迁移。"""
    info = inspect(db_path)
    if not info["db_exists"]:
        return {"error": f"DB 不存在: {db_path}"}
    if not info["missing_tables"] and write:
        return {"message": "所有表已存在，无需迁移", "tables": info["existing_tables"]}

    if not write:
        return {"dry_run": True, "would_create": info["missing_tables"],
                "already_exist": info["existing_tables"]}

    con = sqlite3.connect(str(db_path))
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
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)

    if args.inspect or not args.write:
        result = inspect(args.db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = migrate(args.db, write=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
