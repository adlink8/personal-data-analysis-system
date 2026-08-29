"""KU 升格导出器：ku_facts (MVP v3) -> knowledge_units_staging (staging 库)。

!!! staging 导出，非 canonical !!!
本脚本把 var/db/semantic_mvp_v3.sqlite 的 ku_facts 行映射为正式
knowledge_units（src/personal_knowledge/core/schema_ddl.py:72-124）的字段形状，
写入独立的 staging 库 var/db/semantic_ku_staging.sqlite。它不触碰
data/canonical 下任何库，也不写 var/db/personal_system.sqlite 的正式
knowledge_units 表。

分类与 Q-A 结构化待 schema 定稿后由 LLM 步骤补齐：
  - unit_type 暂填 'unclassified'（九类枚举的判类需要 LLM 结构化，此处不做）
  - question 置空串；answer = ku_facts.fact 原文
  - subject 用源会话 id 占位；evidence_quote 用 fact 原文占位
  - evidence_refs（v2|cm|<hex>）进伴生表 knowledge_unit_evidence_staging
映射规则：
  unit_id        = 'stg|' + sha256(fact_key)（确定性 -> 幂等）
  run_id         = 'stg_' + 源库文件名主干（无 FK，staging 不挂 knowledge_build_runs）
  lifecycle      = active -> current，superseded -> superseded
  supersedes_id  = ku_facts.supersedes（superseded 行指向前向替代者的 fact_key）
  confidence     = high 0.9 / medium 0.7 / low 0.5（其余 0.5）
  status/version = 'staging' / 1（staging 导出的既定初始态）
幂等：目标表 IF NOT EXISTS 建表后，单事务内 DELETE 全量 + 重新 INSERT
（等价"重建临时表再 rename"，重复运行收敛到同一状态）。

用法：
  python tools/semantic/export_ku_staging.py [--db SRC] [--out DST]
  （默认 --db var/db/semantic_mvp_v3.sqlite --out var/db/semantic_ku_staging.sqlite）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "var" / "db" / "semantic_mvp_v3.sqlite"
DEFAULT_OUT = ROOT / "var" / "db" / "semantic_ku_staging.sqlite"
CANONICAL_DIR = ROOT / "data" / "canonical"

# 字段名照抄 schema_ddl 的 knowledge_units；unit_type 的 CHECK 放宽到允许
# 'unclassified'，run_id 去 FK（staging 不依赖 knowledge_build_runs）。
STAGING_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_units_staging (
    unit_id         TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    unit_type       TEXT NOT NULL CHECK(unit_type IN ('unclassified','preference','habit','personal_fact','project_decision','capability','tool_usage','solution','decision_rationale','technical_conclusion')),
    subject         TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    confidence      REAL NOT NULL CHECK(confidence >= 0.0 AND confidence <= 1.0),
    evidence_quote  TEXT NOT NULL,
    lifecycle       TEXT NOT NULL DEFAULT 'current' CHECK(lifecycle IN ('current','deprecated','superseded','conflict','candidate')),
    source_session_id   TEXT,
    source_message_ref  TEXT,
    source_agent    TEXT,
    evidence_scope  TEXT NOT NULL DEFAULT 'user' CHECK(evidence_scope IN ('user','assistant','system','sidechain','subagent')),
    status          TEXT NOT NULL DEFAULT 'staging' CHECK(status IN ('staging','current','rejected')),
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    supersedes_id   TEXT
);
CREATE TABLE IF NOT EXISTS knowledge_unit_evidence_staging (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id         TEXT NOT NULL,
    evidence_ref    TEXT NOT NULL,
    evidence_type   TEXT NOT NULL DEFAULT 'message',
    UNIQUE(unit_id, evidence_ref)
);
CREATE INDEX IF NOT EXISTS idx_kus_lifecycle ON knowledge_units_staging(lifecycle);
CREATE INDEX IF NOT EXISTS idx_kus_type ON knowledge_units_staging(unit_type);
CREATE INDEX IF NOT EXISTS idx_kus_session ON knowledge_units_staging(source_session_id);
CREATE INDEX IF NOT EXISTS idx_kues_unit ON knowledge_unit_evidence_staging(unit_id);
"""

LIFECYCLE_MAP = {"active": "current", "superseded": "superseded"}
CONFIDENCE_MAP = {"high": 0.9, "medium": 0.7, "low": 0.5}


def unit_id_for(fact_key: str) -> str:
    return "stg|" + hashlib.sha256(fact_key.encode("utf-8")).hexdigest()


def export(db_path: Path, out_path: Path) -> int:
    if db_path.resolve().is_relative_to(CANONICAL_DIR.resolve()):
        sys.exit(f"拒绝：源库在 canonical 区（只读铁律）: {db_path}")
    if out_path.resolve().is_relative_to(CANONICAL_DIR.resolve()):
        sys.exit(f"拒绝：目标库不允许落在 canonical 区: {out_path}")

    src = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    dst = sqlite3.connect(str(out_path))

    run_id = "stg_" + db_path.stem
    try:
        facts = src.execute(
            "select fact_key, session_id, fact, evidence_refs, confidence,"
            " valid_from, supersedes, status from ku_facts order by fact_key"
        ).fetchall()
        src_stats = {
            "total": len(facts),
            "active": sum(1 for r in facts if r[7] == "active"),
            "superseded": sum(1 for r in facts if r[7] == "superseded"),
        }

        dst.executescript(STAGING_DDL)
        # re-export keeps already-assigned classifications (unit_type is set by
        # classify_ku_staging.py; the source ku_facts table has no type column)
        try:
            existing_types = {r[0]: r[1] for r in dst.execute(
                "select unit_id, unit_type from knowledge_units_staging")}
        except sqlite3.OperationalError:
            existing_types = {}
        n_units = n_current = n_superseded = n_bad_status = 0
        n_evidence = n_bad_refs = 0
        supersedes_ids: set[str] = set()
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with dst:  # 单事务：全量重建，幂等
            dst.execute("DELETE FROM knowledge_unit_evidence_staging")
            dst.execute("DELETE FROM knowledge_units_staging")
            for (fk, sid, fact, refs, conf, valid_from, supersedes, status) in facts:
                lifecycle = LIFECYCLE_MAP.get(status)
                if lifecycle is None:
                    n_bad_status += 1
                    continue
                uid = unit_id_for(fk)
                if supersedes:
                    supersedes_ids.add(supersedes)
                dst.execute(
                    "insert into knowledge_units_staging"
                    " (unit_id, run_id, unit_type, subject, question, answer,"
                    "  confidence, evidence_quote, lifecycle, source_session_id,"
                    "  source_message_ref, source_agent, evidence_scope, status,"
                    "  version, created_at, supersedes_id)"
                    " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        uid, run_id, existing_types.get(uid, "unclassified"), sid or "", "", fact,
                        CONFIDENCE_MAP.get(conf or "", 0.5), fact, lifecycle,
                        sid, None, None, "user", "staging", 1, valid_from or now,
                        supersedes,
                    ),
                )
                n_units += 1
                if lifecycle == "current":
                    n_current += 1
                else:
                    n_superseded += 1
                try:
                    ref_list = json.loads(refs) if refs else []
                except (TypeError, ValueError):
                    ref_list = []
                    n_bad_refs += 1
                for ref in ref_list if isinstance(ref_list, list) else []:
                    if isinstance(ref, str) and ref:
                        dst.execute(
                            "insert or ignore into knowledge_unit_evidence_staging"
                            " (unit_id, evidence_ref, evidence_type) values (?,?, 'message')",
                            (uid, ref),
                        )
                        n_evidence += 1

        exported = dict(
            rows=n_units, current=n_current, superseded=n_superseded,
            bad_status_skipped=n_bad_status, evidence_rows=n_evidence,
            bad_refs_json=n_bad_refs,
        )
        dangling = 0
        fact_keys = {fk for fk, *_ in facts}
        for (fk, _sid, _fact, _refs, _conf, _vf, supersedes, _status) in facts:
            if supersedes and supersedes not in fact_keys:
                dangling += 1
        return report(src_stats, exported, dangling, run_id, out_path)
    finally:
        src.close()
        dst.close()


def report(src_stats: dict, exported: dict, dangling: int, run_id: str, out_path: Path) -> int:
    print(f"run_id: {run_id}")
    print(f"source ku_facts: total={src_stats['total']} active={src_stats['active']} "
          f"superseded={src_stats['superseded']}")
    print(f"exported knowledge_units_staging: rows={exported['rows']} "
          f"(current={exported['current']}, superseded={exported['superseded']}, "
          f"bad_status_skipped={exported['bad_status_skipped']})")
    print(f"knowledge_unit_evidence_staging rows: {exported['evidence_rows']} "
          f"(bad refs json: {exported['bad_refs_json']})")
    ok_current = exported["current"] == src_stats["active"]
    ok_superseded = exported["superseded"] == src_stats["superseded"]
    print(f"check current==active: {exported['current']}=={src_stats['active']} -> {'OK' if ok_current else 'MISMATCH'}")
    print(f"check superseded==superseded: {exported['superseded']}=={src_stats['superseded']} -> {'OK' if ok_superseded else 'MISMATCH'}")
    print(f"dangling supersedes_id (target 不在导出集): {dangling}")
    print(f"out: {out_path}")
    return 0 if (ok_current and ok_superseded and dangling == 0) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ku_facts -> knowledge_units_staging 导出（staging，非 canonical）")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="源库（只读，默认 var/db/semantic_mvp_v3.sqlite）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="目标 staging 库（默认 var/db/semantic_ku_staging.sqlite）")
    args = parser.parse_args(argv)
    return export(Path(args.db), Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
