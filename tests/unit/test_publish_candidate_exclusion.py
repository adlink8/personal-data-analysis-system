import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.knowledge.publish_incremental_run import publish_incremental_run


def test_publish_excludes_candidate_and_reports_count(tmp_path: Path):
    db = tmp_path / "publish.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        SCHEMA_SQL.replace(
            "CHECK(lifecycle IN ('current','deprecated','superseded','conflict'))",
            "CHECK(lifecycle IN ('current','deprecated','superseded','conflict','candidate'))",
        )
    )
    con.execute(
        "INSERT INTO knowledge_build_runs "
        "(run_id,run_type,generated_at,input_hash,schema_version,status) "
        "VALUES ('ir_test','incremental','now','hash','v1','staging')"
    )
    values = [
        ("candidate", "staging", "u_candidate"),
        ("current", "staging", "u_current"),
    ]
    for lifecycle, status, unit_id in values:
        con.execute(
            "INSERT INTO knowledge_units "
            "(unit_id,run_id,unit_type,subject,question,answer,confidence,evidence_quote,lifecycle,status,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (unit_id, "ir_test", "solution", "subject", "q", "a", 0.9, "evidence quote", lifecycle, status, "now"),
        )
    con.commit()
    con.close()

    report = publish_incremental_run("ir_test", db, write=True)
    assert report["candidate_excluded"] == 1
    con = sqlite3.connect(db)
    assert con.execute("SELECT status FROM knowledge_units WHERE unit_id='u_candidate'").fetchone()[0] == "staging"
    assert con.execute("SELECT status FROM knowledge_units WHERE unit_id='u_current'").fetchone()[0] == "current"
    con.close()
