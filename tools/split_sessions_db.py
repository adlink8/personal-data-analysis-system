"""
拆分 sessions.db (887MB) 为两个 <512MB 的数据库。
按 session 对半拆分，保持数据完整性（含 FTS 索引）。
"""
import sqlite3
import os
import time

SRC = os.path.expanduser(r"~/.agentsview/sessions - 副本.db")
OUT1 = os.path.expanduser(r"~/.agentsview/sessions_part1.db")
OUT2 = os.path.expanduser(r"~/.agentsview/sessions_part2.db")

# ── 表分类 ──────────────────────────────────────────
# A) 会话级：按 session_id 过滤
SESSION_TABLES = {
    "sessions":              "id",
    "messages":              "session_id",
    "tool_calls":            "session_id",
    "tool_result_events":    "session_id",
    "usage_events":          "session_id",
    "secret_findings":       "session_id",
    "session_project_identity_snapshots": "session_id",
    "session_project_identity_snapshot_changes": "session_id",
    "pinned_messages":       "session_id",
    "starred_sessions":      "session_id",
}

# B) 引用 sessions.id 但列名不同
SESSION_TABLES_ALT = {
    "recall_entries":        "source_session_id",
    "recall_evidence":       "session_id",
}

# C) FTS 表（重建，不做行拷贝）
FTS_TABLES = {
    "messages_fts":          "messages",
    "recall_entries_fts":    "recall_entries",
    "recall_evidence_fts":   "recall_evidence",
}

# D) 全局表（两边都复制完整）
GLOBAL_TABLES = [
    "model_pricing",
    "stats",
    "background_migrations",
    "archive_metadata",
    "pg_sync_state",
    "cursor_usage_events",
    "insights",
    "project_identity_observations",
    "project_identity_observation_changes",
    "git_cache",
    "excluded_sessions",
    "remote_skipped_files",
    "skipped_files",
    "worktree_project_mappings",
    "recall_query_events",
    "recall_query_exposures",
]


def get_session_split(source):
    """按 started_at 排序，将 session_id 对半分为两组。"""
    con = sqlite3.connect(source)
    cur = con.execute(
        "SELECT id FROM sessions ORDER BY started_at NULLS LAST, id"
    )
    ids = [r[0] for r in cur.fetchall()]
    con.close()
    n = len(ids)
    mid = n // 2
    print(f"  总 sessions: {n} → 前半 {mid} 个, 后半 {n - mid} 个")
    return set(ids[:mid]), set(ids[mid:])


def create_db(target, source, session_set, label):
    """创建拆分后的数据库。"""
    t0 = time.perf_counter()
    print(f"\n{'='*60}")
    print(f"创建: {label} → {target}")
    print(f"{'='*60}")

    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)

    # ── 1. 复制全局表 ──
    print("  复制全局表...")
    for tbl in GLOBAL_TABLES:
        schema = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        ).fetchone()
        if schema and schema[0]:
            dst.execute(schema[0])
        rows = src.execute(f"SELECT * FROM \"{tbl}\"").fetchall()
        if rows:
            cols = [d[1] for d in src.execute(f"PRAGMA table_info(\"{tbl}\")").fetchall()]
            placeholders = ",".join("?" * len(cols))
            col_names = ",".join(f"\"{c}\"" for c in cols)
            dst.executemany(
                f"INSERT INTO \"{tbl}\" ({col_names}) VALUES ({placeholders})", rows
            )
        # 复制索引
        for idx in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL", (tbl,)
        ).fetchall():
            if idx[0]:
                try:
                    dst.execute(idx[0])
                except Exception as e:
                    print(f"    索引跳过 {tbl}: {e}")
        dst.commit()

    # ── 2. 复制会话级表 ──
    all_session_tables = dict(SESSION_TABLES)
    all_session_tables.update(SESSION_TABLES_ALT)

    for tbl, fk_col in all_session_tables.items():
        schema = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        ).fetchone()
        if schema and schema[0]:
            dst.execute(schema[0])
        
        # 过滤属于该分组的 session
        placeholders = ",".join("?" for _ in session_set)
        rows = src.execute(
            f"SELECT * FROM \"{tbl}\" WHERE \"{fk_col}\" IN ({placeholders})",
            list(session_set)
        ).fetchall()
        if rows:
            cols = [d[1] for d in src.execute(f"PRAGMA table_info(\"{tbl}\")").fetchall()]
            col_placeholders = ",".join("?" * len(cols))
            col_names = ",".join(f"\"{c}\"" for c in cols)
            dst.executemany(
                f"INSERT INTO \"{tbl}\" ({col_names}) VALUES ({col_placeholders})", rows
            )
        # 复制索引
        for idx in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL", (tbl,)
        ).fetchall():
            if idx[0]:
                try:
                    dst.execute(idx[0])
                except Exception as e:
                    print(f"    索引跳过 {tbl}: {e}")
        dst.commit()
        print(f"  {tbl}: {len(rows)} 行")

    # ── 3. FTS 表重建 ──
    print("  FTS 虚拟表...")
    for fts_tbl, content_tbl in FTS_TABLES.items():
        fts_schema = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (fts_tbl,)
        ).fetchone()
        if fts_schema and fts_schema[0]:
            try:
                dst.execute(fts_schema[0])
            except Exception as e:
                print(f"    FTS 创建跳过 {fts_tbl}: {e}")
        # 尝试重建
        try:
            dst.execute(f"INSERT INTO \"{fts_tbl}\"(\"{fts_tbl}\") VALUES('rebuild')")
            print(f"    {fts_tbl}: 重建完成")
        except Exception as e:
            print(f"    {fts_tbl}: 重建失败（可后续手动执行）: {e}")
        dst.commit()

    # ── 4. 分析优化 ──
    print("  执行 ANALYZE...")
    dst.execute("ANALYZE")
    dst.commit()

    # ── 统计 ──
    dst.execute("VACUUM")
    dst.commit()

    src.close()
    dst.close()

    size_mb = os.path.getsize(target) / (1024 * 1024)
    elapsed = time.perf_counter() - t0
    print(f"  完成: {size_mb:.1f} MB, 耗时 {elapsed:.1f}s")
    return size_mb


def main():
    if not os.path.exists(SRC):
        print(f"错误: 找不到源文件 {SRC}")
        return

    size_gb = os.path.getsize(SRC) / (1024**3)
    print(f"源文件: {SRC} ({size_gb:.2f} GB)")

    # 获取 session 分组
    set_a, set_b = get_session_split(SRC)

    # 创建两个数据库
    s1 = create_db(OUT1, SRC, set_a, "Part 1 (前半 sessions)")
    s2 = create_db(OUT2, SRC, set_b, "Part 2 (后半 sessions)")

    print(f"\n{'='*60}")
    print(f"拆分完成:")
    print(f"  {OUT1}: {s1:.1f} MB")
    print(f"  {OUT2}: {s2:.1f} MB")
    print(f"{'='*60}")

    # 验证
    for db_path, label in [(OUT1, "Part1"), (OUT2, "Part2")]:
        con = sqlite3.connect(db_path)
        cnt = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        msg_cnt = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        con.close()
        print(f"  {label}: sessions={cnt}, messages={msg_cnt}")


if __name__ == "__main__":
    main()
