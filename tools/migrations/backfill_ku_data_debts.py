"""一次性数据迁移：knowledge_units 三笔数据债（dry-run 优先）。

① provenance backfill（--provenance）
   knowledge_units 中 source_agent/source_session_id 为空串或 NULL 的行，
   经 source_message_ref → canonical_messages.canonical_session_id
   → canonical_sessions.agent 回填两列。查不到的保持空串并计数 unresolved。

④ scope relabel（--scope）
   evidence_scope='user' 但 source_message_ref 指向 canonical role='assistant'
   的行，evidence_scope 改 'assistant'。其他 role 只计数报告，不动。

⑥ chroma GC（--gc-chroma）
   列出并（--write 时）删除垃圾集合：
   - 空集合（count=0）中名字为 ku_test/ku_x/ku_old/ku_new 的；
   - knowledge_units_* 历代集合，排除 active 指针指向的与
     knowledge_units_eval_l2_* 前缀。
   绝不触碰：novel_*、personal_events、conversation_turns、eval、active。

用法:
    python tools/migrations/backfill_ku_data_debts.py                 # 全部 dry-run
    python tools/migrations/backfill_ku_data_debts.py --provenance    # 只跑 ①
    python tools/migrations/backfill_ku_data_debts.py --write --scope # 只写 ④

--write 安全：写库前先把 UNIFIED_DB 复制备份到
var/backups/personal_system_<UTC时间戳>.sqlite；①② 的 UPDATE 在同一事务。
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_CONVERSATIONS_DB,
    KNOWLEDGE_ACTIVE_POINTER,
    UNIFIED_DB,
    VAR_DIR,
)

BACKUP_DIR = VAR_DIR / "backups"
GC_EMPTY_NAMES = ("ku_test", "ku_x", "ku_old", "ku_new")
GC_PREFIX = "knowledge_units_"
GC_EVAL_PREFIX = "knowledge_units_eval_l2_"


def _prefix(unit_id: str) -> str:
    """unit_id 前缀标签：v1|/l2|/ku| 归一类，ku_xxx 归 'ku_'。"""
    if "|" in unit_id:
        return unit_id.split("|", 1)[0] + "|"
    return unit_id[:3]


def _ref_index(canonical_con: sqlite3.Connection, refs: list[str]) -> dict[str, tuple[str | None, str | None, str | None]]:
    """canonical_message_id → (canonical_session_id, agent, role)。"""
    index: dict[str, tuple[str | None, str | None, str | None]] = {}
    for i in range(0, len(refs), 500):
        chunk = refs[i : i + 500]
        marks = ",".join("?" * len(chunk))
        rows = canonical_con.execute(
            "SELECT m.canonical_message_id, m.canonical_session_id, s.agent, m.role "
            "FROM canonical_messages m "
            "LEFT JOIN canonical_sessions s ON s.canonical_session_id = m.canonical_session_id "
            f"WHERE m.canonical_message_id IN ({marks})",
            chunk,
        )
        for mid, sid, agent, role in rows:
            index[mid] = (sid, agent, role)
    return index


# ---------------------------------------------------------------- ① provenance

def plan_provenance(
    unified_con: sqlite3.Connection,
    canonical_con: sqlite3.Connection,
) -> dict:
    """计算 ① 的回填计划。返回 {rows, resolved, unresolved, by_prefix}。"""
    candidates = unified_con.execute(
        "SELECT unit_id, source_message_ref FROM knowledge_units "
        "WHERE source_agent = '' OR source_agent IS NULL "
        "OR source_session_id = '' OR source_session_id IS NULL"
    ).fetchall()
    refs = sorted({ref for _, ref in candidates if ref})
    index = _ref_index(canonical_con, refs)

    rows = []  # (unit_id, session_id, agent, resolved)
    for unit_id, ref in candidates:
        sid, agent, _role = index.get(ref, (None, None, None))
        resolved = sid is not None
        rows.append((unit_id, sid if resolved else None, agent or "", resolved))

    by_prefix = Counter(_prefix(r[0]) for r in rows)
    return {
        "rows": rows,
        "resolved": sum(1 for r in rows if r[3]),
        "unresolved": sum(1 for r in rows if not r[3]),
        "by_prefix": dict(by_prefix),
    }


def apply_provenance(unified_con: sqlite3.Connection, plan: dict) -> int:
    """在调用方的事务里执行 ① 的 UPDATE，返回变更行数。"""
    changed = 0
    for unit_id, sid, agent, resolved in plan["rows"]:
        if not resolved:
            continue
        changed += unified_con.execute(
            "UPDATE knowledge_units SET source_session_id = ?, source_agent = ? "
            "WHERE unit_id = ?",
            (sid, agent, unit_id),
        ).rowcount
    return changed


# ---------------------------------------------------------------- ④ scope

def plan_scope(
    unified_con: sqlite3.Connection,
    canonical_con: sqlite3.Connection,
) -> dict:
    """计算 ④ 的重标计划。返回 {rows, by_status, by_prefix, other_roles, unresolved}。"""
    candidates = unified_con.execute(
        "SELECT unit_id, status, source_message_ref FROM knowledge_units "
        "WHERE evidence_scope = 'user'"
    ).fetchall()
    refs = sorted({ref for _, _, ref in candidates if ref})
    index = _ref_index(canonical_con, refs)

    rows = []  # (unit_id,) 仅 role='assistant' 的
    by_status: Counter = Counter()
    by_prefix: Counter = Counter()
    other_roles: Counter = Counter()
    unresolved = 0
    for unit_id, status, ref in candidates:
        _sid, _agent, role = index.get(ref, (None, None, None))
        if role == "assistant":
            rows.append((unit_id,))
            by_status[status] += 1
            by_prefix[_prefix(unit_id)] += 1
        elif role is None:
            unresolved += 1
        else:
            other_roles[role] += 1
    return {
        "rows": rows,
        "by_status": dict(by_status),
        "by_prefix": dict(by_prefix),
        "other_roles": dict(other_roles),
        "unresolved": unresolved,
    }


def apply_scope(unified_con: sqlite3.Connection, plan: dict) -> int:
    """在调用方的事务里执行 ④ 的 UPDATE，返回变更行数。"""
    changed = 0
    for (unit_id,) in plan["rows"]:
        changed += unified_con.execute(
            "UPDATE knowledge_units SET evidence_scope = 'assistant' "
            "WHERE unit_id = ? AND evidence_scope = 'user'",
            (unit_id,),
        ).rowcount
    return changed


# ---------------------------------------------------------------- ⑥ chroma GC

def read_active_name(pointer_path: Path) -> str:
    return pointer_path.read_text(encoding="utf-8").strip()


def plan_chroma_gc(client, active_name: str) -> list[dict]:
    """计算 ⑥ 的删除清单：[{name, count, reason}]，按名字排序。

    client 需有 list_collections() / get_or_create_collection(name)。
    """
    plan: list[dict] = []
    for coll in client.list_collections():
        name = coll.get("name", "")
        if name in GC_EMPTY_NAMES:
            count = client.get_or_create_collection(name).count()
            if count == 0:
                plan.append({"name": name, "count": 0, "reason": "empty junk collection"})
        elif name.startswith(GC_PREFIX):
            if name == active_name or name.startswith(GC_EVAL_PREFIX):
                continue  # active 与 eval 集合绝不触碰
            count = client.get_or_create_collection(name).count()
            plan.append({"name": name, "count": count, "reason": "stale knowledge_units_* generation"})
    plan.sort(key=lambda item: item["name"])
    return plan


# ---------------------------------------------------------------- 报告与写库

def _print_provenance_report(plan: dict) -> None:
    print("== ① provenance backfill ==")
    print(f"  待回填行数: {len(plan['rows'])}")
    print(f"  可解析: {plan['resolved']}  不可解析(unresolved): {plan['unresolved']}")
    print(f"  按 unit_id 前缀分布: {plan['by_prefix']}")
    print("  抽样 5 条 (unit_id -> agent):")
    for unit_id, _sid, agent, resolved in plan["rows"][:5]:
        print(f"    {unit_id} -> {agent if resolved else '<unresolved>'}")


def _print_scope_report(plan: dict) -> None:
    print("== ④ scope relabel ==")
    print(f"  待重标行数 (role=assistant): {len(plan['rows'])}")
    print(f"  按 status 分布: {plan['by_status']}")
    print(f"  按 unit_id 前缀分布: {plan['by_prefix']}")
    print(f"  role 为其他值的行数（不动）: {plan['other_roles']}")
    print(f"  source_message_ref 查不到的行数（不动）: {plan['unresolved']}")


def _print_gc_report(plan: list[dict]) -> None:
    print("== ⑥ chroma GC ==")
    if not plan:
        print("  无待删除集合")
        return
    print(f"  待删除集合 {len(plan)} 个:")
    for item in plan:
        print(f"    {item['name']}  count={item['count']}  ({item['reason']})")


def _backup_unified_db(unified_db: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"personal_system_{stamp}.sqlite"
    shutil.copy2(unified_db, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="只出报告，不写（默认）")
    mode.add_argument("--write", action="store_true", help="实际写入（先备份 UNIFIED_DB）")
    parser.add_argument("--provenance", action="store_true", help="只跑 ① provenance backfill")
    parser.add_argument("--scope", action="store_true", help="只跑 ④ scope relabel")
    parser.add_argument("--gc-chroma", action="store_true", help="只跑 ⑥ chroma GC")
    args = parser.parse_args(argv)

    run_all = not (args.provenance or args.scope or args.gc_chroma)
    do_prov = run_all or args.provenance
    do_scope = run_all or args.scope
    do_gc = run_all or args.gc_chroma
    write = args.write

    prov_plan = scope_plan = None
    if do_prov or do_scope:
        unified_con = sqlite3.connect(str(UNIFIED_DB))
        canonical_con = sqlite3.connect(str(AGENT_CONVERSATIONS_DB))
        try:
            if do_prov:
                prov_plan = plan_provenance(unified_con, canonical_con)
                _print_provenance_report(prov_plan)
            if do_scope:
                scope_plan = plan_scope(unified_con, canonical_con)
                _print_scope_report(scope_plan)

            if write and (do_prov or do_scope):
                backup = _backup_unified_db(UNIFIED_DB)
                print(f"备份: {backup}")
                try:
                    unified_con.execute("BEGIN")
                    prov_changed = apply_provenance(unified_con, prov_plan) if prov_plan else 0
                    scope_changed = apply_scope(unified_con, scope_plan) if scope_plan else 0
                    unified_con.commit()
                except Exception:
                    unified_con.rollback()
                    raise
                print(f"① provenance 变更行数: {prov_changed}")
                print(f"④ scope 变更行数: {scope_changed}")
        finally:
            unified_con.close()
            canonical_con.close()

    if do_gc:
        from personal_knowledge.core.chroma_client import ChromaClient

        client = ChromaClient(port=8001)
        active_name = read_active_name(KNOWLEDGE_ACTIVE_POINTER)
        gc_plan = plan_chroma_gc(client, active_name)
        _print_gc_report(gc_plan)
        if write:
            for item in gc_plan:
                ok = client.delete_collection_by_name(item["name"])
                print(f"  delete {item['name']}: {'ok' if ok else 'not found (skipped)'}")

    if not write:
        print("\n(dry-run：未做任何修改；加 --write 执行)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
