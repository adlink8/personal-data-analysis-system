"""Phase 41 Plan 02 Task 5：assistant watermark bootstrap（R4 防全量队列）。

语义（D-04 豁免的 operational 落地）：存量 assistant 消息视为 ku|/v1| 世代
已覆盖，assistant 轨只抽增量。首次 `prepare --track assistant` 前必须把
`knowledge_source_watermark` 的 `committed_assistant` key .bootstrap 到当前
`committed` 值——否则首次 prepare 会把 ~73k 条存量 assistant 全部判为 new，
直接撞成全量付费队列。

幂等：`committed_assistant` 已存在 → 打印 no_op 退出 0。
默认 dry-run（打印将写入的 key/value 与跳过本步骤的存量入队估算计数）；
--write 调 advance_watermark(..., key='committed_assistant') 落库。

用法::

    python tools/migrations/bootstrap_assistant_watermark.py            # dry-run
    python tools/migrations/bootstrap_assistant_watermark.py --write    # 落库
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_CONVERSATIONS_DB,
    UNIFIED_DB,
)
from personal_knowledge.application.knowledge.eligibility import (  # noqa: E402
    compute_eligible_messages,
)
from personal_knowledge.application.knowledge.refresh_knowledge_units import (  # noqa: E402
    advance_watermark,
    get_committed_watermark,
)

ASSISTANT_KEY = "committed_assistant"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true", help="落库（默认 dry-run）")
    p.add_argument("--db", type=Path, default=UNIFIED_DB, help="unified DB 路径")
    p.add_argument(
        "--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB,
        help="canonical DB 路径（估算计数用）",
    )
    args = p.parse_args(argv)

    if not args.db.exists():
        print(f"[error] DB 不存在: {args.db}", file=sys.stderr)
        return 2

    existing = get_committed_watermark(args.db, key=ASSISTANT_KEY)
    if existing:
        print(f"[no_op] {ASSISTANT_KEY} 已存在（value={existing}），无需 bootstrap。")
        return 0

    committed = get_committed_watermark(args.db, key="committed")
    if not committed:
        print(
            "[error] committed watermark 为空，无法 bootstrap（先完成一轮 user 轨提交）",
            file=sys.stderr,
        )
        return 2

    # 估算：若跳过 bootstrap，首次 prepare --track assistant 将入队的存量
    # assistant 消息数（41-01 唯一 eligible 口径；只输出 count，不含原文）
    estimate = -1
    if args.canonical_db.exists():
        items, _stats = compute_eligible_messages(
            args.canonical_db, roles=("assistant",)
        )
        estimate = len(items)

    print(f"key:   {ASSISTANT_KEY}")
    print(f"value: {committed}  (= 当前 committed)")
    print(
        f"estimate: 跳过本步骤时首次 prepare --track assistant "
        f"将入队的存量 assistant 消息 ≈ {estimate} 条"
    )

    if not args.write:
        print("[dry_run] 未落库；加 --write 写入 watermark。")
        return 0

    result = advance_watermark(args.db, committed, key=ASSISTANT_KEY)
    print(f"[write] before={result['before']!r} after={result['after']}")
    print(
        "[ok] bootstrap 完成：存量 assistant 视为 ku|/v1| 世代已覆盖（D-04），"
        "assistant 轨只抽增量。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
