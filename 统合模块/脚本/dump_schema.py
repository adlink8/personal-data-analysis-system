# -*- coding: utf-8 -*-
"""打印统合库 schema，输出到 分析数据/_schema.json。

运行: python 统合模块\\脚本\\dump_schema.py
"""
import sqlite3, json
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent          # 统合模块/脚本/
UNIFIED = SCRIPT_DIR.parent / "SQLite数据库" / "personal_system.sqlite"
OUT = SCRIPT_DIR.parent / "分析数据" / "_schema.json"
con = sqlite3.connect(UNIFIED)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
cols = {t: [c[1] for c in con.execute(f"PRAGMA table_info({t})")] for t in tables}
out = {"tables": tables, "count": len(tables), "unified_events_cols": cols.get("unified_events", [])}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK -> {OUT}", flush=True)
