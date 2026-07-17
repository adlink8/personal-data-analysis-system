from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.serving.versions import publication_status, record_publication
from personal_knowledge.application.sync import build_parser, main as sync_main


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "unified.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    con.close()
    return path


def test_publication_is_atomic_idempotent_and_watermark_bound(tmp_path: Path) -> None:
    db = _db(tmp_path)
    kwargs = dict(
        registry_id="d.canonical_conversation",
        version="v1",
        checksum="checksum-1",
        location_kind="sqlite_store",
        location_ref="canonical.sqlite",
        source_key="agentsview",
        watermark_value="source-1",
    )
    first = record_publication(db, **kwargs)
    second = record_publication(db, **kwargs)
    assert first["created"] is True and first["watermark_created"] is True
    assert second["created"] is False and second["watermark_created"] is False
    assert first["artifact_version_id"] == second["artifact_version_id"]

    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM artifact_versions WHERE registry_id='d.canonical_conversation'").fetchone()[0] == 1
    row = con.execute("SELECT artifact_version_id FROM source_watermarks WHERE watermark_id=?", (first["watermark_id"],)).fetchone()
    assert row == (first["artifact_version_id"],)
    con.close()


def test_failed_publication_rolls_back_version_and_watermark(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        record_publication(
            db,
            registry_id="missing.artifact",
            version="v1",
            checksum="checksum",
            location_kind="sqlite_store",
            location_ref="x",
            source_key="source",
            watermark_value="wm",
        )
    except ValueError as exc:
        assert "unknown registry id" in str(exc)
    else:
        raise AssertionError("unknown artifact must fail")
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM artifact_versions").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM source_watermarks").fetchone()[0] == 0
    con.close()


def test_status_is_read_only_and_json_capable(tmp_path: Path, monkeypatch, capsys) -> None:
    db = _db(tmp_path)
    before = db.read_bytes()
    report = publication_status(db)
    assert report["ok"] is True and report["artifacts"] == {}
    assert db.read_bytes() == before

    monkeypatch.setattr("personal_knowledge.application.sync.UNIFIED_DB", db)
    code = sync_main(["status", "--json"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["schema_ready"] is True
    assert db.read_bytes() == before


def test_new_commands_are_dry_run_by_default() -> None:
    parser = build_parser()
    turns = parser.parse_args(["turns"])
    google = parser.parse_args(["google"])
    conversations = parser.parse_args(["conversations"])
    assert not turns.write and not google.write and not conversations.write
