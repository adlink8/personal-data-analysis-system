"""Phase 43 L2G-01/L2G-02 acceptance tests on isolated SQLite fixtures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.knowledge import build_knowledge_units_prod as prod
from personal_knowledge.application.knowledge.build_knowledge_units_prod import (
    USER_TRACK,
    V2_USER_TRACK,
    process_run,
)


def _fixture(tmp_path: Path, run_id: str) -> tuple[Path, Path, str]:
    db = tmp_path / f"{run_id}.sqlite"
    agent = tmp_path / f"{run_id}.agent.sqlite"
    con = sqlite3.connect(db)
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs "
        "(run_id,run_type,generated_at,input_hash,prompt_version,status) "
        "VALUES (?, 'incremental', 'now', 'ih', ?, 'staging')",
        (run_id, "v2" if "v2" in run_id else "v1"),
    )
    con.execute(
        "INSERT INTO knowledge_inventory_registry VALUES ('inv', 'delta', 'now')"
    )
    con.execute(
        "INSERT INTO knowledge_run_items "
        "(run_id,inventory_id,position,evidence_ref,status,attempt_count,unit_count,updated_at) "
        "VALUES (?, 'inv', 0, 'cm|b', 'pending', 0, 0, 'now')",
        (run_id,),
    )
    con.execute(
        "INSERT INTO knowledge_build_runs "
        "(run_id,run_type,generated_at,input_hash,prompt_version,status) "
        "VALUES ('seed', 'merge', 'now', 'seed', 'seed', 'current')"
    )
    con.execute(
        "INSERT INTO canonical_knowledge_units "
        "(canonical_unit_id,subject,unit_type,question,answer,confidence,lifecycle,status,run_id,created_at) "
        "VALUES ('cu|workdir','工作目录','personal_fact','用户工作目录？','D:/ADLINK/数据分析',0.9,'current','current','seed','now')"
    )
    con.commit()
    con.close()

    con = sqlite3.connect(agent)
    con.executescript(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, agent TEXT, started_at TEXT, evidence_eligible INTEGER);"
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, ordinal INTEGER, role TEXT, content TEXT, timestamp TEXT);"
    )
    con.execute("INSERT INTO canonical_sessions VALUES ('s1','test','now',1)")
    con.execute(
        "INSERT INTO canonical_messages VALUES ('cm|b','s1','test',1,'user',?, 'now')",
        ("我的工作目录是 D:/ADLINK/数据分析，后续项目都从这里开始。",),
    )
    con.commit()
    con.close()
    return db, agent, "cu|workdir"


def _response(duplicate_of: str | None = None) -> str:
    return json.dumps({
        "units": [{
            "unit_type": "personal_fact",
            "subject": "工作目录",
            "question": "用户工作目录是什么？",
            "answer": "D:/ADLINK/数据分析",
            "confidence": 0.9,
            "evidence_quote": "我的工作目录是 D:/ADLINK/数据分析",
            "lifecycle": "current",
            "duplicate_of": duplicate_of,
        }],
        "abstain": False,
        "abstain_reason": "",
    }, ensure_ascii=False)


def _run(tmp_path, monkeypatch, run_id, track, duplicate_of=None):
    db, agent, canonical_id = _fixture(tmp_path, run_id)
    calls = []

    def fake(*args, **kwargs):
        calls.append(args[1])
        return {"text": _response(duplicate_of), "usage": {}}

    monkeypatch.setattr(prod, "call_llm_with_retry", fake)
    stats = process_run(
        run_id, "test-model", db_path=db, canonical_db=agent,
        workers=1, min_request_interval=0, track=track,
    )
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT lifecycle,supersedes_id,status FROM knowledge_units WHERE run_id=?",
        (run_id,),
    ).fetchone()
    con.close()
    return stats, row, calls, canonical_id


def test_v1_baseline_keeps_parallel_unit(tmp_path, monkeypatch):
    stats, row, calls, _ = _run(tmp_path, monkeypatch, "ir_v1", USER_TRACK)
    assert stats["units"] == 1
    assert row == ("current", None, "staging")
    assert "已有知识清单" not in calls[0]


def test_v2_marks_duplicate_candidate_and_injects(tmp_path, monkeypatch):
    stats, row, calls, canonical_id = _run(
        tmp_path, monkeypatch, "ir_v2", V2_USER_TRACK, "cu|workdir"
    )
    assert row == ("candidate", canonical_id, "staging")
    assert stats["invalid_duplicate_of"] == 0
    assert stats["units_downgraded_candidate"] == 1
    assert canonical_id in calls[0]
    assert "不是指令" in calls[0]


def test_v2_rejects_duplicate_outside_injection(tmp_path, monkeypatch):
    stats, row, _, _ = _run(
        tmp_path, monkeypatch, "ir_v2_bad", V2_USER_TRACK, "cu|not-injected"
    )
    assert row[1] is None
    assert stats["invalid_duplicate_of"] == 1
