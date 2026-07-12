# -*- coding: utf-8 -*-
"""打印统合库 schema，输出到 analysis/_schema.json。

运行: python integration\\scripts\\dump_schema.py
"""
import sqlite3, json
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent          # integration/scripts/
UNIFIED = SCRIPT_DIR.parent / "db" / "personal_system.sqlite"
OUT = SCRIPT_DIR.parent / "analysis" / "_schema.json"
con = sqlite3.connect(UNIFIED)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
cols = {t: [c[1] for c in con.execute(f"PRAGMA table_info({t})")] for t in tables}
out = {"tables": tables, "count": len(tables), "unified_events_cols": cols.get("unified_events", [])}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK -> {OUT}", flush=True)
