# -*- coding: utf-8 -*-
import sqlite3, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
con = sqlite3.connect(ROOT / "统合模块" / "SQLite数据库" / "personal_system.sqlite")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
cols = {t: [c[1] for c in con.execute(f"PRAGMA table_info({t})")] for t in tables}
out = {"tables": tables, "count": len(tables), "unified_events_cols": cols.get("unified_events", [])}
(ROOT / "_schema.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("OK", flush=True)
