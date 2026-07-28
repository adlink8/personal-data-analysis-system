"""Repair dependent FK clauses left by an early candidate migration attempt."""
from __future__ import annotations
import argparse, json, shutil, sqlite3
from datetime import datetime, timezone
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); a=p.parse_args()
    db=a.db.resolve(); backup_dir=db.parents[1]/'backups'; backup_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); backup=backup_dir/f'{db.stem}_pre_fk_repair_{stamp}.sqlite'; shutil.copy2(db,backup)
    con=sqlite3.connect(db); before=con.execute('select count(*) from knowledge_units').fetchone()[0]
    con.execute('PRAGMA foreign_keys=OFF'); con.execute('PRAGMA legacy_alter_table=ON'); con.execute('BEGIN IMMEDIATE')
    con.execute('ALTER TABLE knowledge_unit_evidence RENAME TO knowledge_unit_evidence_legacy')
    con.execute('ALTER TABLE canonical_unit_members RENAME TO canonical_unit_members_legacy')
    con.execute("""CREATE TABLE knowledge_unit_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_id TEXT NOT NULL REFERENCES knowledge_units(unit_id),
        evidence_ref TEXT NOT NULL,
        evidence_type TEXT NOT NULL DEFAULT 'message',
        UNIQUE(unit_id,evidence_ref)
    )""")
    con.execute("""CREATE TABLE canonical_unit_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        canonical_unit_id TEXT NOT NULL REFERENCES canonical_knowledge_units(canonical_unit_id),
        member_unit_id TEXT NOT NULL REFERENCES knowledge_units(unit_id),
        UNIQUE(canonical_unit_id,member_unit_id)
    )""")
    con.execute('INSERT INTO knowledge_unit_evidence SELECT * FROM knowledge_unit_evidence_legacy')
    con.execute('INSERT INTO canonical_unit_members SELECT * FROM canonical_unit_members_legacy')
    con.execute('DROP TABLE knowledge_unit_evidence_legacy'); con.execute('DROP TABLE canonical_unit_members_legacy')
    con.execute('CREATE INDEX idx_kue_unit ON knowledge_unit_evidence(unit_id)')
    con.execute('CREATE INDEX idx_cum_canonical ON canonical_unit_members(canonical_unit_id)')
    fk=con.execute('PRAGMA foreign_key_check').fetchall()
    if fk: con.rollback(); raise RuntimeError(f'foreign_key_check failed: {fk[:5]}')
    con.commit(); after=con.execute('select count(*) from knowledge_units').fetchone()[0]; con.close()
    print(json.dumps({'db':str(db),'backup':str(backup),'knowledge_units_before':before,'knowledge_units_after':after,'foreign_key_errors':0},ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
