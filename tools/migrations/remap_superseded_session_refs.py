"""Phase 42 存量消息引用迁移（默认 dry-run）。

语义：
1. 只更新 unified DB 中的引用，不删除行；canonical 数据库全程只读。
2. superseded 副本按 content_hash 映射到 active 副本，映射不了的 ref 保持原值并计数。
3. 与本次改键无关的历史悬空 ref 单独计数，不混入迁移孤儿。
4. ``--write`` 先备份 unified DB，三张表在一个事务中更新；重复执行应 no_op。

用法：
    python tools/migrations/remap_superseded_session_refs.py \
        --old-canonical-db var/backups/agent_conversations_pre42_<ts>.sqlite
    python tools/migrations/remap_superseded_session_refs.py --write \
        --old-canonical-db var/backups/agent_conversations_pre42_<ts>.sqlite
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_CONVERSATIONS_DB,
    UNIFIED_DB,
    VAR_DIR,
)

BACKUP_DIR = VAR_DIR / "backups"
BASELINE_PATH = VAR_DIR / "reports" / "phase42_baseline.json"
TABLES = (
    ("knowledge_unit_evidence", "id", "evidence_ref", "remapped_evidence"),
    ("knowledge_units", "unit_id", "source_message_ref", "remapped_source_ref"),
    ("knowledge_inventory_items", "id", "evidence_ref", "remapped_inventory"),
)


def _ro_connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _cleaned_hash(content: str | None, stored: str | None) -> str | None:
    if stored:
        return stored
    if not content:
        return None
    return hashlib.sha256(" ".join(content.split()).encode("utf-8")).hexdigest()[:32]


def _startup_assert(old_db: Path, baseline_path: Path) -> tuple[bool, str]:
    if not old_db.exists():
        return False, f"old canonical DB 不存在: {old_db}"
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        minimum = int(baseline["dup_groups_legacy_av"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return False, f"baseline JSON 无法读取或缺少 dup_groups_legacy_av: {exc}"
    try:
        with _ro_connect(old_db) as con:
            count = con.execute(
                "SELECT COUNT(DISTINCT canonical_session_id) "
                "FROM canonical_messages WHERE source='legacy'"
            ).fetchone()[0]
    except sqlite3.Error as exc:
        return False, f"old canonical DB 前置查询失败: {exc}"
    if count < minimum:
        return False, (
            "old canonical DB 前置校验失败：legacy 会话行数 "
            f"{count} < 基线双份组数 {minimum}，疑似指错或已被换代"
        )
    return True, f"old canonical DB 前置校验通过：legacy_sessions={count}, minimum={minimum}"


def _load_canonical_index(con: sqlite3.Connection) -> dict:
    messages: dict[str, dict] = {}
    by_session_hash: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in con.execute(
        "SELECT canonical_message_id, canonical_session_id, source, source_message_ref, "
        "ordinal, content, content_hash FROM canonical_messages"
    ):
        mid, sid, source, source_ref, ordinal, content, content_hash = row
        item = {
            "id": mid,
            "session_id": sid,
            "source": source,
            "source_ref": source_ref,
            "ordinal": ordinal,
            "hash": _cleaned_hash(content, content_hash),
        }
        messages[mid] = item
        if item["hash"]:
            by_session_hash[(sid, item["hash"])].append(item)

    columns = {row[1] for row in con.execute("PRAGMA table_info(canonical_sessions)")}
    lifecycle_expr = "lifecycle" if "lifecycle" in columns else "NULL"
    eligible_expr = "evidence_eligible" if "evidence_eligible" in columns else "1"
    superseded_expr = "superseded_by_canonical_id" if "superseded_by_canonical_id" in columns else "NULL"
    sessions = {
        row[0]: {
            "lifecycle": row[1],
            "eligible": bool(row[2]),
            "superseded_by": row[3],
        }
        for row in con.execute(
            f"SELECT canonical_session_id, {lifecycle_expr}, {eligible_expr}, "
            f"{superseded_expr} FROM canonical_sessions"
        )
    }
    legacy_links: dict[str, set[str]] = defaultdict(set)
    for sid, source, source_session_id, method in con.execute(
        "SELECT canonical_session_id, source, source_session_id, match_method "
        "FROM session_source_links WHERE source='legacy'"
    ):
        legacy_links[source_session_id].add(sid)
    return {
        "messages": messages,
        "by_session_hash": by_session_hash,
        "sessions": sessions,
        "legacy_links": legacy_links,
    }


def _pick_target(index: dict, session_id: str | None, content_hash: str | None, ordinal: int | None) -> str | None:
    if not session_id or not content_hash:
        return None
    candidates = index["by_session_hash"].get((session_id, content_hash), [])
    if not candidates:
        return None
    return min(candidates, key=lambda item: (abs((item["ordinal"] or 0) - (ordinal or 0)), item["id"]))["id"]


def _active_mapping(index: dict, old_session_id: str) -> str | None:
    targets = set()
    for source_session_id, canonical_ids in index["legacy_links"].items():
        if source_session_id != old_session_id:
            continue
        for sid in canonical_ids:
            session = index["sessions"].get(sid, {})
            if session.get("lifecycle") in (None, "active") and session.get("eligible"):
                targets.add(sid)
    return sorted(targets)[0] if len(targets) == 1 else None


def _old_legacy_target(old_index: dict, new_index: dict, old_ref: str) -> str | None:
    old_message = old_index["messages"].get(old_ref)
    if not old_message:
        return None
    if old_message["source"] != "legacy" and not str(old_message["source_ref"] or "").startswith("legacy:"):
        return None
    old_links = [
        source_session_id
        for source_session_id, session_ids in old_index["legacy_links"].items()
        if old_message["session_id"] in session_ids
    ]
    targets = {_active_mapping(new_index, source_session_id) for source_session_id in old_links}
    targets.discard(None)
    if len(targets) != 1:
        return None
    return _pick_target(new_index, next(iter(targets)), old_message["hash"], old_message["ordinal"])


def _all_refs(unified_con: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    refs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for table, key_col, ref_col, _counter in TABLES:
        for key, ref in unified_con.execute(
            f"SELECT {key_col}, {ref_col} FROM {table} "
            f"WHERE {ref_col} LIKE 'cm|%'"
        ):
            if ref:
                refs[ref].append((table, str(key)))
    return refs


def plan_remap(
    unified_con: sqlite3.Connection,
    canonical_con: sqlite3.Connection,
    old_canonical_con: sqlite3.Connection,
) -> dict:
    """返回三表更新计划和分类统计，不写任何数据库。"""
    new_index = _load_canonical_index(canonical_con)
    old_index = _load_canonical_index(old_canonical_con)
    plans: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    counts = Counter()
    by_table = {counter: 0 for _table, _key, _ref, counter in TABLES}
    orphan_by_table = Counter()
    preexisting_by_table = Counter()

    for old_ref, locations in sorted(_all_refs(unified_con).items()):
        new_message = new_index["messages"].get(old_ref)
        target = None
        category = "resolved_active"
        if new_message:
            session = new_index["sessions"].get(new_message["session_id"], {})
            if session.get("lifecycle") == "superseded":
                target_session = session.get("superseded_by")
                target = _pick_target(new_index, target_session, new_message["hash"], new_message["ordinal"])
                category = "resolved_superseded"
                if target is None:
                    category = "remap_orphan"
            elif session.get("lifecycle") in (None, "active") and session.get("eligible"):
                category = "resolved_active"
            else:
                category = "remap_orphan"
        else:
            target = _old_legacy_target(old_index, new_index, old_ref)
            if target:
                category = "unresolved_dup_member"
            elif old_ref in old_index["messages"] and (
                old_index["messages"][old_ref]["source"] == "legacy"
                or str(old_index["messages"][old_ref]["source_ref"] or "").startswith("legacy:")
            ):
                category = "remap_orphan"
            else:
                category = "preexisting_orphan"

        counts[category] += 1
        locations_by_table: dict[str, list[str]] = defaultdict(list)
        for table, key in locations:
            locations_by_table[table].append(key)
        for table, keys in locations_by_table.items():
            if target and target != old_ref:
                plans[table].extend((key, old_ref, target) for key in keys)
                by_table[next(counter for t, _k, _r, counter in TABLES if t == table)] += 1
            elif category == "remap_orphan":
                orphan_by_table[table] += 1
            elif category == "preexisting_orphan":
                preexisting_by_table[table] += 1

    return {
        "plans": {table: rows for table, rows in plans.items()},
        "counts": dict(counts),
        "by_table": by_table,
        "remap_orphans_by_table": dict(orphan_by_table),
        "preexisting_orphans_by_table": dict(preexisting_by_table),
        "remap_orphans": counts["remap_orphan"],
        # 基线的 809 是 knowledge_unit_evidence distinct ref 口径。
        "preexisting_orphans": preexisting_by_table["knowledge_unit_evidence"],
    }


def _backup_unified_db(path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"personal_system_{stamp}.sqlite"
    shutil.copy2(path, dest)
    return dest


def apply_remap(unified_con: sqlite3.Connection, plan: dict) -> dict[str, int]:
    changed = Counter()
    for table, key_col, ref_col, counter_name in TABLES:
        for key, old_ref, new_ref in plan["plans"].get(table, []):
            changed[counter_name] += unified_con.execute(
                f"UPDATE {table} SET {ref_col}=? WHERE {key_col}=? AND {ref_col}=?",
                (new_ref, key, old_ref),
            ).rowcount
    return dict(changed)


def _summary(plan: dict, write: bool, changed: dict[str, int] | None = None) -> dict:
    planned = plan["by_table"]
    return {
        "write": write,
        "remapped_evidence": (changed or {}).get("remapped_evidence", planned["remapped_evidence"]),
        "remapped_source_ref": (changed or {}).get("remapped_source_ref", planned["remapped_source_ref"]),
        "remapped_inventory": (changed or {}).get("remapped_inventory", planned["remapped_inventory"]),
        "remap_orphans": plan["remap_orphans"],
        "preexisting_orphans": plan["preexisting_orphans"],
        "no_op": not any(planned.values()),
        "remap_orphans_by_table": plan["remap_orphans_by_table"],
        "preexisting_orphans_by_table": plan["preexisting_orphans_by_table"],
    }


def _print_report(plan: dict, write: bool, changed: dict[str, int] | None = None) -> None:
    print(f"[report] categories={plan['counts']}")
    print(f"[report] remap_orphans_by_table={plan['remap_orphans_by_table']}")
    print(f"[report] preexisting_orphans_by_table={plan['preexisting_orphans_by_table']}")
    result = _summary(plan, write, changed)
    if result["no_op"]:
        print("[no_op] 没有待迁移引用。")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只出报告，不写（默认）")
    mode.add_argument("--write", action="store_true", help="备份后写入 unified DB")
    parser.add_argument("--unified-db", type=Path, default=UNIFIED_DB)
    parser.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    parser.add_argument("--old-canonical-db", type=Path, required=True)
    parser.add_argument("--baseline-json", type=Path, default=BASELINE_PATH)
    args = parser.parse_args(argv)

    ok, message = _startup_assert(args.old_canonical_db, args.baseline_json)
    if not ok:
        print(f"[error] {message}", file=sys.stderr)
        return 2
    print(f"[ok] {message}")
    if not args.unified_db.exists() or not args.canonical_db.exists():
        print("[error] unified 或 current canonical DB 不存在", file=sys.stderr)
        return 2

    unified = sqlite3.connect(str(args.unified_db))
    unified.execute("PRAGMA busy_timeout=30000")
    canonical = old = None
    try:
        canonical = _ro_connect(args.canonical_db)
        old = _ro_connect(args.old_canonical_db)
        plan = plan_remap(unified, canonical, old)
        changed = None
        if args.write and any(plan["by_table"].values()):
            backup = _backup_unified_db(args.unified_db)
            print(f"[backup] {backup}")
            try:
                unified.execute("BEGIN")
                changed = apply_remap(unified, plan)
                unified.commit()
            except Exception:
                unified.rollback()
                raise
        _print_report(plan, args.write, changed)
        return 0
    finally:
        if old is not None:
            old.close()
        if canonical is not None:
            canonical.close()
        unified.close()


if __name__ == "__main__":
    raise SystemExit(main())
