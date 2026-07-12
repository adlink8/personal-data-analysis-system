"""Phase 14 Wave 4.2：knowledge index promote / rollback。

把通过 frozen-test A/B gate 的 candidate collection promote 为 active，
或回滚到上一个 active checkpoint。使用原子 active pointer。

用法::

    python promote_knowledge_index.py --promote knowledge_units_a89ebe470357
    python promote_knowledge_index.py --list
    python rollback_knowledge_checkpoint.py --to previous
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from core.project_paths import UNIFIED_DB, DB_DIR  # noqa: E402

ACTIVE_POINTER = DB_DIR / "knowledge_index_active.txt"
PROMOTE_LOG = DB_DIR / "knowledge_index_promote_log.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_active() -> str:
    """读当前 active collection 名。"""
    if ACTIVE_POINTER.exists():
        return ACTIVE_POINTER.read_text(encoding="utf-8").strip()
    return ""


def _write_active(collection: str) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVE_POINTER.with_suffix(".tmp")
    tmp.write_text(collection, encoding="utf-8")
    tmp.replace(ACTIVE_POINTER)


def _log(action: str, collection: str, details: dict | None = None) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": _utc_now(), "action": action, "collection": collection}
    if details:
        entry.update(details)
    with PROMOTE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _compute_collection_checksum(collection_name: str, port: int = 8001) -> str:
    """从 Chroma 实际 IDs 计算 ID-set checksum（sorted IDs 的 sha256）。"""
    try:
        from chroma_client import ChromaClient
        client = ChromaClient(port=port)
        coll = client.get_or_create_collection(collection_name)
        ids: list[str] = []
        page, offset = 2000, 0
        while True:
            batch = (coll.get(limit=page, offset=offset, include=[]) or {}).get("ids") or []
            if not batch:
                break
            ids.extend(batch)
            offset += len(batch)
            if len(batch) < page:
                break
            if offset > 500000:
                break
        return hashlib.sha256("".join(sorted(ids)).encode()).hexdigest()
    except Exception:
        return ""


def promote(collection: str, db_path: Path = UNIFIED_DB) -> dict:
    """把 candidate collection promote 为 active。

    同时更新 knowledge_index_versions 表的 status 和 checksum。
    """
    previous = read_active()

    # 计算 collection 的 ID-set checksum（用于精确 rollback reconcile）
    checksum = _compute_collection_checksum(collection)

    # 更新 DB
    con = sqlite3.connect(str(db_path))
    try:
        # 旧 active → rolled_back（保留其 checksum 供 rollback reconcile 用）
        if previous:
            # 如果旧 active 还没有 checksum，现在补算
            old_ck = con.execute(
                "SELECT checksum FROM knowledge_index_versions WHERE collection_name=? AND status='active'",
                (previous,),
            ).fetchone()
            if not old_ck or not old_ck[0]:
                old_checksum = _compute_collection_checksum(previous)
                con.execute(
                    "UPDATE knowledge_index_versions SET status='rolled_back', checksum=? "
                    "WHERE collection_name=? AND status='active'",
                    (old_checksum, previous),
                )
            else:
                con.execute(
                    "UPDATE knowledge_index_versions SET status='rolled_back' "
                    "WHERE collection_name=? AND status='active'",
                    (previous,),
                )
        # 新 collection → active + checksum
        con.execute(
            "UPDATE knowledge_index_versions SET status='active', "
            "activated_at=?, checksum=? WHERE collection_name=?",
            (_utc_now(), checksum, collection),
        )
        con.commit()
    finally:
        con.close()

    _write_active(collection)
    _log("promote", collection, {"previous": previous, "checksum": checksum})

    return {"promoted": collection, "previous": previous, "checksum": checksum}


def rollback_to_previous(db_path: Path = UNIFIED_DB) -> dict:
    """回滚到上一个 active collection。"""
    current = read_active()
    if not current:
        return {"error": "no active collection to rollback from"}

    # 从 promote log 找上一个
    previous = ""
    if PROMOTE_LOG.exists():
        entries = [json.loads(l) for l in PROMOTE_LOG.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
        # 找最近的 promote，其 previous 非空
        for entry in reversed(entries):
            if entry.get("action") == "promote" and entry.get("previous"):
                previous = entry["previous"]
                break

    if not previous:
        return {"error": "no previous collection found in log"}

    # 更新 DB
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "UPDATE knowledge_index_versions SET status='rolled_back' "
            "WHERE collection_name=? AND status='active'",
            (current,),
        )
        con.execute(
            "UPDATE knowledge_index_versions SET status='active', "
            "activated_at=? WHERE collection_name=?",
            (_utc_now(), previous),
        )
        con.commit()
    finally:
        con.close()

    _write_active(previous)
    _log("rollback", previous, {"rolled_back_from": current})

    return {"rolled_back_to": previous, "rolled_back_from": current}


def list_versions(db_path: Path = UNIFIED_DB) -> list[dict]:
    """列出所有 index version。"""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT version_id, build_id, collection_name, unit_count, status, "
        "created_at, activated_at FROM knowledge_index_versions ORDER BY created_at DESC"
    ).fetchall()
    con.close()
    active = read_active()
    result = []
    for r in rows:
        d = dict(r)
        d["is_active_pointer"] = (d["collection_name"] == active)
        result.append(d)
    return result


def promote_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Wave 4.2: promote knowledge index")
    p.add_argument("--promote", metavar="COLLECTION", help="promote collection 为 active")
    p.add_argument("--list", action="store_true", help="列出所有 index version")
    args = p.parse_args(argv)

    if args.list:
        versions = list_versions()
        active = read_active()
        print(f"active pointer: {active or '(none)'}")
        print(f"{'collection':<40} {'status':<12} {'units':>6} {'created'}")
        for v in versions:
            marker = " ← active" if v["collection_name"] == active else ""
            print(f"{v['collection_name']:<40} {v['status']:<12} {v['unit_count']:>6} {v['created_at'][:19]}{marker}")
        return 0

    if args.promote:
        result = promote(args.promote)
        if "error" in result:
            print(f"[error] {result['error']}")
            return 1
        print(f"[ok] promoted: {result['promoted']} (previous: {result['previous'] or 'none'})")
        return 0

    print("用法: --promote <collection> | --list")
    return 0


def rollback_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Wave 4.2: rollback knowledge checkpoint")
    p.add_argument("--to", choices=["previous"], default="previous")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.dry_run:
        current = read_active()
        print(f"[dry-run] current active: {current}")
        # 找上一个
        if PROMOTE_LOG.exists():
            entries = [json.loads(l) for l in PROMOTE_LOG.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
            for entry in reversed(entries):
                if entry.get("action") == "promote" and entry.get("previous"):
                    print(f"[dry-run] would rollback to: {entry['previous']}")
                    break
        return 0

    result = rollback_to_previous()
    if "error" in result:
        print(f"[error] {result['error']}")
        return 1
    print(f"[ok] rolled back to: {result['rolled_back_to']} (from: {result['rolled_back_from']})")
    return 0


if __name__ == "__main__":
    # 默认运行 promote（可通过第一个参数切换）
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        raise SystemExit(rollback_main(sys.argv[2:]))
    raise SystemExit(promote_main())
