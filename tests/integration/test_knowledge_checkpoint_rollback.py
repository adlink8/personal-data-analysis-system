"""P0: rollback_knowledge_checkpoint 入口与 dry-run 契约。"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
import personal_knowledge.domains.knowledge.promote_knowledge_index as pk  # noqa: E402
import personal_knowledge.domains.knowledge.rollback_knowledge_checkpoint as rkc  # noqa: E402


def _setup(tmp_path: Path) -> Path:
    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'current',NULL,NULL)"
    )
    con.executescript(
        "INSERT INTO knowledge_index_versions VALUES "
        "('v1','run1','ku_old','run1',1,'candidate','2026-01-01',NULL,NULL),"
        "('v2','run1','ku_new','run1',2,'candidate','2026-01-02',NULL,NULL)"
    )
    con.commit()
    con.close()
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"
    pk.PROMOTE_LOG = tmp_path / "knowledge_index_promote_log.jsonl"
    return db


def test_rollback_module_reexports_promote_entrypoint() -> None:
    assert rkc.rollback_main is pk.rollback_main


def test_rollback_main_dry_run_does_not_change_active(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = _setup(tmp_path)
    pk.promote("ku_old", db_path=db)
    pk.promote("ku_new", db_path=db)
    assert pk.read_active() == "ku_new"

    code = pk.rollback_main(["--to", "previous", "--dry-run"])
    assert code == 0
    assert pk.read_active() == "ku_new"
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "ku_old" in out


def test_rollback_main_applies(tmp_path: Path) -> None:
    db = _setup(tmp_path)
    pk.promote("ku_old", db_path=db)
    pk.promote("ku_new", db_path=db)

    # rollback_main 默认读 UNIFIED_DB / 全局 ACTIVE_POINTER；此处直接测实现函数
    result = pk.rollback_to_previous(db_path=db)
    assert result["rolled_back_to"] == "ku_old"
    assert pk.read_active() == "ku_old"

    lines = pk.PROMOTE_LOG.read_text(encoding="utf-8").strip().split("\n")
    actions = [json.loads(l)["action"] for l in lines]
    assert actions.count("promote") == 2
    assert actions[-1] == "rollback"
