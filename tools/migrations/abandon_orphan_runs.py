"""孤儿 run 处置：把已放弃 run 的未闭合队列项作废并登记死信。

背景：F-13 之后 `pk-ku watermark --advance` fail-closed，前置检查扫描
**所有** run 的 pending/in_flight/retryable 项（`refresh_knowledge_units.py::
check_watermark_advance_preconditions`）。2026-07-16 遗留的两个被放弃 run
（全量误启动 `6f3da1eec…` 与被 sibling 顶替的 `ir_ab6d20f78da2038d`）共约
4 万条 pending，会永久阻塞水位推进。`acknowledge_dead_refs()` 只覆盖
terminal_failed，pending 没有内置作废通道——本脚本补上这一步。

语义（不删行，全程可审计）：对每个显式指定的 run：
1. pending / in_flight / retryable 项 → `terminal_failed`，
   `last_error_class='run_abandoned'`
2. 该 run 全部 terminal_failed 项登记进 `knowledge_dead_refs`
   （error_class 保留原值，缺省补 'run_abandoned'；INSERT OR IGNORE 幂等）
3. `knowledge_build_runs.status` → `'aborted'`

安全护栏：run 必须显式用 --run 指定（可重复）；若该 run 有 24 小时内
更新过的队列项则拒绝处理（防止误传还在跑的 run）。

幂等：重复执行时无未闭合项 → 该 run 报 no_op。
默认 dry-run；--write 才落库。写完后重跑 watermark 前置检查并打印剩余阻塞。

用法::

    python tools/migrations/abandon_orphan_runs.py \
        --run 6f3da1eec10c4fee6fb1509c83cfb85b --run ir_ab6d20f78da2038d          # dry-run
    python tools/migrations/abandon_orphan_runs.py \
        --run 6f3da1eec10c4fee6fb1509c83cfb85b --run ir_ab6d20f78da2038d --write  # 落库
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402
from personal_knowledge.application.knowledge.refresh_knowledge_units import (  # noqa: E402
    check_watermark_advance_preconditions,
)

ERROR_CLASS = "run_abandoned"
OPEN_STATUSES = ("pending", "in_flight", "retryable")
RECENT_GUARD = timedelta(hours=24)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _inspect_run(con: sqlite3.Connection, run_id: str) -> dict | None:
    row = con.execute(
        "SELECT run_id, run_type, generated_at, status FROM knowledge_build_runs "
        "WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    by_status = {
        status: count
        for status, count in con.execute(
            "SELECT status, COUNT(*) FROM knowledge_run_items WHERE run_id=? "
            "GROUP BY status",
            (run_id,),
        )
    }
    last_touch = con.execute(
        "SELECT MAX(COALESCE(updated_at, lease_started_at, '')) "
        "FROM knowledge_run_items WHERE run_id=?",
        (run_id,),
    ).fetchone()[0]
    return {
        "run_id": row[0],
        "run_type": row[1],
        "generated_at": row[2],
        "run_status": row[3],
        "items_by_status": by_status,
        "open_items": sum(by_status.get(s, 0) for s in OPEN_STATUSES),
        "terminal_failed": by_status.get("terminal_failed", 0),
        "last_item_touch": last_touch or "",
    }


def _is_recent(last_touch: str) -> bool:
    if not last_touch:
        return False
    try:
        touched = datetime.strptime(last_touch, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        # 无法解析的时间戳按"最近"处理，宁可拒绝也不误废活跃 run
        return True
    return datetime.now(timezone.utc) - touched < RECENT_GUARD


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--run", action="append", dest="runs", required=True,
        help="要作废的 run_id（可重复指定）",
    )
    p.add_argument("--write", action="store_true", help="落库（默认 dry-run）")
    p.add_argument("--db", type=Path, default=UNIFIED_DB, help="unified DB 路径")
    args = p.parse_args(argv)

    if not args.db.exists():
        print(f"[error] DB 不存在: {args.db}", file=sys.stderr)
        return 2

    con = sqlite3.connect(str(args.db))
    con.execute("PRAGMA busy_timeout=30000")
    summary: list[dict] = []
    try:
        plans: list[dict] = []
        for run_id in args.runs:
            info = _inspect_run(con, run_id)
            if info is None:
                print(f"[error] run 不存在于 knowledge_build_runs: {run_id}",
                      file=sys.stderr)
                return 2
            if _is_recent(info["last_item_touch"]):
                print(
                    f"[error] run {run_id} 有 24 小时内更新的队列项"
                    f"（last_touch={info['last_item_touch']}），疑似仍在运行，拒绝处理。",
                    file=sys.stderr,
                )
                return 2
            plans.append(info)

        for info in plans:
            run_id = info["run_id"]
            print(f"run {run_id}")
            print(f"  run_type={info['run_type']} generated_at={info['generated_at']} "
                  f"run_status={info['run_status']}")
            print(f"  items: {info['items_by_status']}")
            if info["open_items"] == 0 and info["run_status"] == "aborted":
                print("  [no_op] 无未闭合项且已 aborted。")
                summary.append({"run_id": run_id, "action": "no_op"})
                continue
            print(f"  计划: {info['open_items']} 条 open → terminal_failed"
                  f"({ERROR_CLASS})；"
                  f"{info['open_items'] + info['terminal_failed']} 条登记 dead_refs；"
                  f"run status → aborted")

            if not args.write:
                summary.append({"run_id": run_id, "action": "dry_run",
                                "would_fail": info["open_items"]})
                continue

            now = _utc_now()
            with con:
                failed = con.execute(
                    "UPDATE knowledge_run_items SET status='terminal_failed', "
                    "last_error_class=?, updated_at=? "
                    "WHERE run_id=? AND status IN ('pending','in_flight','retryable')",
                    (ERROR_CLASS, now, run_id),
                ).rowcount
                acked = con.execute(
                    "INSERT OR IGNORE INTO knowledge_dead_refs "
                    "(evidence_ref, run_id, error_class, acknowledged_at) "
                    "SELECT evidence_ref, run_id, "
                    "COALESCE(NULLIF(last_error_class,''), ?), ? "
                    "FROM knowledge_run_items "
                    "WHERE run_id=? AND status='terminal_failed'",
                    (ERROR_CLASS, now, run_id),
                ).rowcount
                con.execute(
                    "UPDATE knowledge_build_runs SET status='aborted' WHERE run_id=?",
                    (run_id,),
                )
            print(f"  [write] failed={failed} dead_refs_new={acked} status=aborted")
            summary.append({"run_id": run_id, "action": "written",
                            "items_failed": failed, "dead_refs_new": acked})
    finally:
        con.close()

    print()
    print(json.dumps({"write": args.write, "runs": summary}, ensure_ascii=False))

    pre = check_watermark_advance_preconditions(args.db)
    if pre["unfinished"] or pre["failed"]:
        print("[info] watermark 前置检查仍有阻塞项（活跃 run 属正常）:")
        for u in pre["unfinished"]:
            print(f"  unfinished {u['run_id']} {u['status']} x{u['count']}")
        for f in pre["failed"]:
            print(f"  failed(未 ack) {f['run_id']} x{f['count']}")
    else:
        print("[info] watermark 前置检查全部通过，可以 --advance。")

    if not args.write:
        print("[dry_run] 未落库；加 --write 执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
