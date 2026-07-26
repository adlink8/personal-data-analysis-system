"""schema_invalid 重排队:配合 _tolerant_parse 抢救层零成本回收已付费响应。

背景(2026-07-26 实测):run ir_13486f30c029db49 的 164 条 schema_invalid
全部有缓存响应;离线重放新抢救解析器可救回 109 条(127 个 unit)。
本脚本把指定 run 的 terminal_failed/schema_invalid 且**有 cache_key** 的
item 翻回 retryable(attempt_count 归零),之后 `pk-ku extract --run <run>`
续跑时命中内容寻址缓存,不产生任何 LLM 调用,由新解析器重新裁决:
救得回 → succeeded/abstained;救不回 → 重新落 terminal_failed(维持判死)。

默认 dry-run;--write 落库。幂等(重复执行时无匹配行 → no_op)。
前置:确认无 extract 进程正在跑同一 run(避免旧代码进程消费重排队项)。

用法::

    python tools/migrations/requeue_schema_invalid.py --run ir_13486f30c029db49          # dry-run
    python tools/migrations/requeue_schema_invalid.py --run ir_13486f30c029db49 --write  # 落库
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", required=True, help="run_id")
    p.add_argument("--write", action="store_true", help="落库（默认 dry-run）")
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)

    if not args.db.exists():
        print(f"[error] DB 不存在: {args.db}", file=sys.stderr)
        return 2

    con = sqlite3.connect(str(args.db))
    con.execute("PRAGMA busy_timeout=30000")
    try:
        n_cached, n_nocache = con.execute(
            "SELECT SUM(CASE WHEN cache_key != '' THEN 1 ELSE 0 END), "
            "       SUM(CASE WHEN cache_key = '' THEN 1 ELSE 0 END) "
            "FROM knowledge_run_items "
            "WHERE run_id=? AND status='terminal_failed' "
            "  AND last_error_class='schema_invalid'",
            (args.run,),
        ).fetchone()
        n_cached, n_nocache = n_cached or 0, n_nocache or 0
        print(f"run {args.run}: schema_invalid 有缓存 {n_cached} 条"
              f"(可零成本重裁), 无缓存 {n_nocache} 条(保持不动)")
        if not n_cached:
            print("[no_op] 无可重排队项。")
            return 0
        if not args.write:
            print("[dry_run] 未落库;加 --write 执行。")
            return 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with con:
            n = con.execute(
                "UPDATE knowledge_run_items "
                "SET status='retryable', attempt_count=0, updated_at=? "
                "WHERE run_id=? AND status='terminal_failed' "
                "  AND last_error_class='schema_invalid' AND cache_key != ''",
                (now, args.run),
            ).rowcount
        print(f"[write] {n} 条 → retryable(attempt_count=0)。"
              f"续跑 `pk-ku extract --run {args.run}` 即从缓存重裁,无 LLM 成本。")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
