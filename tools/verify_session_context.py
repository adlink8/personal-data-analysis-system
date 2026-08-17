"""Post-integration verification: session context fields in a fresh shadow run."""
import json
import sqlite3
import sys
from pathlib import Path

SHADOW = Path(r"data/staging/v2/agent_conversations_v2.sqlite")

def main() -> int:
    if not SHADOW.exists():
        print("shadow db missing; run --v2-native first")
        return 1
    con = sqlite3.connect(f"file:{SHADOW}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(ce_sessions)")]
        have_ctx = all(c in cols for c in ("cwd", "git_branch", "model", "title", "stop_reason"))
        print("ce_sessions context columns:", have_ctx)
        if not have_ctx:
            return 1
        rows = con.execute("""
            SELECT family,
                   SUM(cwd IS NOT NULL AND cwd != '') AS with_cwd,
                   SUM(model IS NOT NULL) AS with_model,
                   SUM(title IS NOT NULL) AS with_title,
                   COUNT(*) AS total
            FROM ce_sessions GROUP BY family ORDER BY total DESC
        """).fetchall()
        print(f"{"family":16s} total  cwd  model  title")
        for r in rows:
            print(f"{str(r[0]):16s} {r[4]:5d} {r[1]:4d} {r[2]:5d} {r[3]:5d}")
        # relations / events check
        rel = con.execute("""
            SELECT relation_kind, COUNT(*) n FROM ce_event_relations
            GROUP BY relation_kind ORDER BY n DESC
        """).fetchall()
        print("\nrelations:", {r[0]: r[1] for r in rel})
        kinds = con.execute("""
            SELECT kind, COUNT(*) n FROM ce_events
            WHERE kind IN ('subagent_boundary','usage') GROUP BY kind
        """).fetchall()
        print("event kinds:", {r[0]: r[1] for r in kinds})
    finally:
        con.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
