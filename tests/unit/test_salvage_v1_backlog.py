"""tools/migrations/salvage_v1_backlog.py 的最小单测（临时库）。

覆盖：①同 session 他消息命中 → ref 修复 + scope 按 role 改；②全局兜底命中；
③不可修复 → rejected；④已链接 unit 置 current → 影子行愈合；
⑤未链接 unit attach 到相似 canonical vs 新建（中文近重复句子接通 find_match）。
另验证 dry-run 不落库、Phase 3 清理不可救影子行。
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "migrations" / "salvage_v1_backlog.py"
sys.path.insert(0, str(ROOT / "src"))

spec = importlib.util.spec_from_file_location("salvage_v1_backlog", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import (  # noqa: E402
    SCHEMA_SQL,
)

SIM_ANSWER = "配置数据分析环境需要先安装Python，然后设置环境变量，最后验证路径是否正确。"


def _make_canonical_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, agent TEXT)"
    )
    con.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, "
        "role TEXT, content TEXT)"
    )
    con.executemany(
        "INSERT INTO canonical_sessions VALUES (?,?)",
        [("cs1", "codex"), ("cs2", "claude")],
    )
    con.executemany(
        "INSERT INTO canonical_messages VALUES (?,?,?,?)",
        [
            ("cm|wrong1", "cs1", "user", "这是一条无关的消息内容，不包含任何证据。"),
            ("cm|right1", "cs1", "assistant", "好的，我来帮你配置数据分析的环境变量，先确认路径。"),
            ("cm|glob1", "cs2", "user", "我的生日是1990年5月20日，请记住这个重要的日子。"),
            ("cm|ok1", "cs1", "user", "我偏好使用中文回答所有技术问题。"),
        ],
    )
    con.commit()
    con.close()


def _unit(uid, quote, ref="cm|wrong1", sid="cs1", subject="主题", answer="答案"):
    return (
        uid, "run_test", "preference", subject, "问题", answer, 0.8,
        quote, "current", sid, ref, "codex", "user", "staging", 1, "2026-01-01T00:00:00Z", None,
    )


def _make_unified_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs (run_id, run_type, generated_at, input_hash, status) "
        "VALUES ('run_test','extraction','2026-01-01T00:00:00Z','h','current')"
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            # ① quote 在同 session 的 assistant 消息里，原 ref 指错
            _unit("v1|sess", "我来帮你配置数据分析的环境变量",
                  subject="环境变量配置帮助", answer="用户需要协助配置数据分析的环境变量。"),
            # ② 同 session 搜不到，全局兜底命中 cs2
            _unit("v1|glob", "我的生日是1990年5月20日",
                  subject="生日", answer="用户的生日是1990年5月20日。"),
            # ③ 全库搜不到 → unrepairable
            _unit("v1|bad", "这段话在全库任何消息里都不存在xyz",
                  subject="幻觉内容", answer="一条无法找到证据的内容。"),
            # ④ 原 ref 本就支持 quote，且已是影子 canonical 成员
            _unit("v1|linked", "我偏好使用中文回答所有技术问题", ref="cm|ok1",
                  subject="回答语言偏好", answer="用户偏好中文回答。"),
            # ⑤a 未链接，与现有 current canonical 中文近重复 → attach
            _unit("v1|attach", "我来帮你配置数据分析的环境变量",
                  subject="数据分析环境配置", answer=SIM_ANSWER + "！"),
            # ⑤b 未链接，无相似 canonical → 新建
            _unit("v1|novel", "我来帮你配置数据分析的环境变量",
                  subject="独一无二的摄影器材清单", answer="相机机身选用全画幅，镜头搭配大光圈定焦。"),
            # 影子行（不可救）：成员 quote 全库搜不到
            _unit("v1|dead", "另一段彻底找不到出处的文字abc",
                  subject="不可救内容", answer="没有证据的内容。"),
        ],
    )
    con.executemany(
        "INSERT INTO canonical_knowledge_units "
        "(canonical_unit_id, subject, unit_type, question, answer, confidence, "
        "lifecycle, status, version, run_id, merge_reason, supersedes_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("cu|sim", "数据分析环境配置", "preference", "如何配置", SIM_ANSWER,
             0.9, "current", "current", 1, "run_test", "l2_session_window_import", None,
             "2026-01-01T00:00:00Z"),
            ("cu|shadow", "回答语言偏好", "preference", "语言", "用户偏好中文回答。",
             0.9, "current", "current", 1, "run_test", "l2_session_window_import", None,
             "2026-01-01T00:00:00Z"),
            ("cu|dead", "不可救内容", "preference", "无", "没有证据的内容。",
             0.9, "current", "current", 1, "run_test", "l2_session_window_import", None,
             "2026-01-01T00:00:00Z"),
        ],
    )
    con.executemany(
        "INSERT INTO canonical_unit_members (canonical_unit_id, member_unit_id) VALUES (?,?)",
        [("cu|shadow", "v1|linked"), ("cu|dead", "v1|dead")],
    )
    con.commit()
    con.close()


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    unified = tmp_path / "unified.sqlite"
    canonical = tmp_path / "canonical.sqlite"
    _make_unified_db(unified)
    _make_canonical_db(canonical)
    monkeypatch.setattr(mod, "BACKUP_DIR", tmp_path / "backups")
    return unified, canonical


def _row(db, uid):
    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT status, source_message_ref, source_session_id, source_agent, evidence_scope "
        "FROM knowledge_units WHERE unit_id=?",
        (uid,),
    ).fetchone()
    con.close()
    return row


def _canonical_status(db, cid):
    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT status FROM canonical_knowledge_units WHERE canonical_unit_id=?", (cid,)
    ).fetchone()
    con.close()
    return row[0] if row else None


@pytest.fixture()
def written(dbs):
    unified, canonical = dbs
    report = mod.run(unified, canonical, write=True, verbose=False)
    return unified, report


def test_dry_run_does_not_modify(dbs):
    unified, canonical = dbs
    report = mod.run(unified, canonical, write=False, verbose=False)
    assert report["mode"] == "dry-run"
    assert report["phase1"]["repaired_session"] >= 1
    assert report["phase1"]["repaired_global"] == 1
    assert report["phase1"]["unrepairable"] == 2
    assert report["phase2"]["heal_linked_current"] == 1
    assert report["phase2"]["unlinked_attach_or_create"] == 4
    assert report["phase3"]["est_healed"] == 1
    assert report["phase3"]["est_rejected"] == 1
    # 库未被改动
    assert _row(unified, "v1|sess") == ("staging", "cm|wrong1", "cs1", "codex", "user")
    assert _canonical_status(unified, "cu|dead") == "current"


def test_same_session_repair_and_scope(written):
    unified, _ = written
    status, ref, sid, agent, scope = _row(unified, "v1|sess")
    assert ref == "cm|right1"
    assert sid == "cs1"
    assert agent == "codex"
    assert scope == "assistant"  # role=assistant → scope=assistant
    assert status == "current"  # repairable 且未链接 → attach-or-create 后置 current


def test_global_fallback(written):
    unified, _ = written
    status, ref, sid, agent, scope = _row(unified, "v1|glob")
    assert ref == "cm|glob1"
    assert sid == "cs2"
    assert agent == "claude"
    assert scope == "user"
    assert status == "current"


def test_repair_writes_evidence_link(written):
    unified, report = written
    con = sqlite3.connect(str(unified))
    rows = set(con.execute("SELECT unit_id, evidence_ref FROM knowledge_unit_evidence"))
    con.close()
    # 修复后的新 message_id 同步写入 evidence 表（OR IGNORE 去重）
    assert ("v1|sess", "cm|right1") in rows
    assert ("v1|glob", "cm|glob1") in rows
    assert ("v1|attach", "cm|right1") in rows
    # already_ok / unrepairable 不写
    assert ("v1|linked", "cm|ok1") not in rows
    assert not any(uid == "v1|bad" for uid, _ in rows)
    assert report["applied"]["evidence_links_added"] == len(rows) == 4


def test_unrepairable_rejected(written):
    unified, _ = written
    status, ref, sid, _, _ = _row(unified, "v1|bad")
    assert status == "rejected"
    assert ref == "cm|wrong1"  # 未命中不改 ref
    assert sid == "cs1"


def test_heal_shadow_canonical(written):
    unified, _ = written
    assert _row(unified, "v1|linked")[0] == "current"
    # 影子行愈合：有 current 成员，Phase 3 不动它
    assert _canonical_status(unified, "cu|shadow") == "current"


def test_attach_vs_create(written):
    unified, report = written
    con = sqlite3.connect(str(unified))
    # ⑤a 中文近重复 → attach 到 cu|sim，不新建
    assert con.execute(
        "SELECT COUNT(*) FROM canonical_unit_members "
        "WHERE canonical_unit_id='cu|sim' AND member_unit_id='v1|attach'"
    ).fetchone()[0] == 1
    assert _row(unified, "v1|attach")[0] == "current"
    # ⑤b 无相似 → 新建 canonical，run_id/merge_reason 符合约定
    row = con.execute(
        "SELECT c.run_id, c.merge_reason, c.status FROM canonical_knowledge_units c "
        "JOIN canonical_unit_members m ON m.canonical_unit_id=c.canonical_unit_id "
        "WHERE m.member_unit_id='v1|novel'"
    ).fetchone()
    con.close()
    assert row == ("salvage_v1_backlog", "salvage_import", "current")
    assert _row(unified, "v1|novel")[0] == "current"
    assert report["applied"]["canonical_created"] >= 1


def test_phase3_rejects_unsavable_shadow(written):
    unified, _ = written
    assert _row(unified, "v1|dead")[0] == "rejected"
    assert _canonical_status(unified, "cu|dead") == "rejected"
