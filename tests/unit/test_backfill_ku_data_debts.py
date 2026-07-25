"""tools/migrations/backfill_ku_data_debts.py 的最小单测。

① provenance 回填（可解析/不可解析）、④ 只重标 assistant、
⑥ GC 清单的排除规则（fake client）。
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "migrations" / "backfill_ku_data_debts.py"

spec = importlib.util.spec_from_file_location("backfill_ku_data_debts", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _make_unified(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE knowledge_units ("
        "unit_id TEXT PRIMARY KEY, source_session_id TEXT, "
        "source_message_ref TEXT, source_agent TEXT, "
        "evidence_scope TEXT NOT NULL DEFAULT 'user', "
        "status TEXT NOT NULL DEFAULT 'staging')"
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?)",
        [
            # ① 候选：可解析 / 不可解析 / 已有 provenance（不动）
            ("v1|aaa", "", "cm|ok1", "", "user", "current"),
            ("ku_bbb", None, "cm|missing", None, "user", "current"),
            ("v1|ccc", "cs_keep", "cm|ok1", "codex", "user", "current"),
            # ④ 候选：assistant 重标 / user 不动 / 非 user scope 不动
            ("ku_ddd", "", "cm|asst", "", "user", "staging"),
            ("l2|eee", "", "cm|user1", "", "user", "current"),
            ("v1|fff", "", "cm|asst", "", "assistant", "current"),
        ],
    )
    con.commit()
    return con


def _make_canonical(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, agent TEXT)"
    )
    con.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, role TEXT)"
    )
    con.execute("INSERT INTO canonical_sessions VALUES ('cs1','codex')")
    con.executemany(
        "INSERT INTO canonical_messages VALUES (?,?,?)",
        [
            ("cm|ok1", "cs1", "user"),
            ("cm|asst", "cs1", "assistant"),
            ("cm|user1", "cs1", "user"),
        ],
    )
    con.commit()
    return con


def test_provenance_plan_and_apply(tmp_path: Path) -> None:
    unified = _make_unified(tmp_path / "u.sqlite")
    canonical = _make_canonical(tmp_path / "c.sqlite")

    plan = mod.plan_provenance(unified, canonical)
    # 候选：v1|aaa、ku_ddd、l2|eee、v1|fff（可解析）、ku_bbb（ref 查不到）
    assert len(plan["rows"]) == 5
    assert plan["resolved"] == 4
    assert plan["unresolved"] == 1
    assert plan["by_prefix"] == {"v1|": 2, "ku_": 2, "l2|": 1}

    changed = mod.apply_provenance(unified, plan)
    unified.commit()
    assert changed == 4
    row = unified.execute(
        "SELECT source_session_id, source_agent FROM knowledge_units WHERE unit_id='v1|aaa'"
    ).fetchone()
    assert row == ("cs1", "codex")
    # 不可解析保持空串
    row = unified.execute(
        "SELECT source_session_id, source_agent FROM knowledge_units WHERE unit_id='ku_bbb'"
    ).fetchone()
    assert row in ((None, None), ("", ""))
    # 已有 provenance 的行不动
    row = unified.execute(
        "SELECT source_session_id, source_agent FROM knowledge_units WHERE unit_id='v1|ccc'"
    ).fetchone()
    assert row == ("cs_keep", "codex")


def test_scope_relabels_only_assistant(tmp_path: Path) -> None:
    unified = _make_unified(tmp_path / "u.sqlite")
    canonical = _make_canonical(tmp_path / "c.sqlite")

    plan = mod.plan_scope(unified, canonical)
    # evidence_scope='user' 的 5 行中：v1|aaa/ku_ddd 指向 assistant，
    # v1|ccc 也指向 cm|ok1(user)… 只有指向 cm|asst 的 v1|aaa? 否——
    # v1|aaa→cm|ok1(user)、ku_ddd→cm|asst(assistant)、v1|ccc→cm|ok1(user)、
    # l2|eee→cm|user1(user)、ku_bbb→cm|missing(查不到)
    assert plan["rows"] == [("ku_ddd",)]
    assert plan["by_status"] == {"staging": 1}
    assert plan["by_prefix"] == {"ku_": 1}
    assert plan["other_roles"] == {"user": 3}
    assert plan["unresolved"] == 1

    changed = mod.apply_scope(unified, plan)
    unified.commit()
    assert changed == 1
    scopes = dict(
        unified.execute("SELECT unit_id, evidence_scope FROM knowledge_units").fetchall()
    )
    assert scopes["ku_ddd"] == "assistant"
    assert scopes["l2|eee"] == "user"
    assert scopes["v1|fff"] == "assistant"  # 原本就是，未被误改计数


class _FakeCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class _FakeChromaClient:
    def __init__(self, collections: dict[str, int]) -> None:
        self._collections = collections

    def list_collections(self) -> list[dict]:
        return [{"name": n, "id": n} for n in self._collections]

    def get_or_create_collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections[name])


def test_chroma_gc_exclusion_rules() -> None:
    client = _FakeChromaClient(
        {
            "ku_test": 0,
            "ku_x": 0,
            "ku_old": 0,
            "ku_new": 0,
            "knowledge_units_20260101": 1200,
            "knowledge_units_20260201": 800,
            "knowledge_units_active_gen": 5000,  # active 指针指向 → 排除
            "knowledge_units_eval_l2_frozen": 100,  # eval 前缀 → 排除
            "novel_foo": 10,
            "personal_events": 20,
            "conversation_turns": 30,
        }
    )
    plan = mod.plan_chroma_gc(client, "knowledge_units_active_gen")
    names = [item["name"] for item in plan]
    assert names == [
        "knowledge_units_20260101",
        "knowledge_units_20260201",
        "ku_new",
        "ku_old",
        "ku_test",
        "ku_x",
    ]
    counts = {item["name"]: item["count"] for item in plan}
    assert counts["knowledge_units_20260101"] == 1200
    assert counts["ku_test"] == 0
