from pathlib import Path
import sqlite3

from personal_knowledge.application.knowledge.promote_units import promote_units


def _dbs(tmp_path: Path) -> tuple[Path, Path]:
    unified = tmp_path / "personal_system.sqlite"
    agent = tmp_path / "agent.sqlite"
    u = sqlite3.connect(unified)
    u.executescript(
        """
        CREATE TABLE knowledge_units (
          unit_id TEXT PRIMARY KEY, evidence_quote TEXT NOT NULL,
          source_message_ref TEXT, lifecycle TEXT NOT NULL, status TEXT NOT NULL
        );
        CREATE TABLE canonical_knowledge_units (
          canonical_unit_id TEXT PRIMARY KEY, lifecycle TEXT NOT NULL, status TEXT NOT NULL
        );
        INSERT INTO knowledge_units VALUES ('u1','important evidence quote','old-ref','candidate','staging');
        """
    )
    u.commit()
    u.close()
    a = sqlite3.connect(agent)
    a.execute("CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, content TEXT)")
    a.execute("INSERT INTO canonical_messages VALUES ('new-ref','prefix important evidence quote suffix')")
    a.commit()
    a.close()
    return unified, agent


def test_dry_run_rematches_and_does_not_mutate(tmp_path: Path):
    unified, agent = _dbs(tmp_path)
    before = sqlite3.connect(unified).execute(
        "SELECT lifecycle,status,source_message_ref FROM knowledge_units WHERE unit_id='u1'"
    ).fetchone()
    report = promote_units(
        unified,
        agent,
        ["u1"],
        eligible_refs={"new-ref"},
        write=False,
    )
    after = sqlite3.connect(unified).execute(
        "SELECT lifecycle,status,source_message_ref FROM knowledge_units WHERE unit_id='u1'"
    ).fetchone()
    assert report["promoted"] == 1
    assert report["ref_remap"]["u1"] == {"old": "old-ref", "new": "new-ref"}
    assert before == after


def test_write_requires_rematch_and_creates_backup(tmp_path: Path):
    unified, agent = _dbs(tmp_path)
    report = promote_units(unified, agent, ["u1"], eligible_refs={"new-ref"}, write=True)
    row = sqlite3.connect(unified).execute(
        "SELECT lifecycle,status,source_message_ref FROM knowledge_units WHERE unit_id='u1'"
    ).fetchone()
    assert row == ("current", "current", "new-ref")
    assert Path(report["backup"]).exists()


def test_rematch_failure_is_fail_closed(tmp_path: Path):
    unified, agent = _dbs(tmp_path)
    report = promote_units(unified, agent, ["u1"], eligible_refs={"not-new-ref"}, write=True)
    assert report["rematch_failed"] == 1
    row = sqlite3.connect(unified).execute(
        "SELECT lifecycle,status FROM knowledge_units WHERE unit_id='u1'"
    ).fetchone()
    assert row == ("candidate", "staging")
