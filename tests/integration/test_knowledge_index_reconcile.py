"""P0: reconcile_knowledge_index 契约（mock Chroma，不连真服务）。"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.domains.knowledge.reconcile_knowledge_index import ReconcileReport, reconcile  # noqa: E402


def _ids_checksum(ids: list[str] | set[str]) -> str:
    return hashlib.sha256("".join(sorted(ids)).encode()).hexdigest()


def _setup_db(db: Path, *, canonical: list[tuple[str, str]], checksum: str | None, build_id: str = "run1") -> None:
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'current',NULL,NULL)"
    )
    for cuid, status in canonical:
        con.execute(
            "INSERT INTO canonical_knowledge_units "
            "(canonical_unit_id, subject, unit_type, question, answer, confidence, "
            "lifecycle, status, version, run_id, created_at) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?)",
            (cuid, "s", "preference", "q", "a", 0.9, "current", status, 1, "run1", "2026-01-01"),
        )
    if checksum is not None:
        con.execute(
            "INSERT INTO knowledge_index_versions VALUES "
            "(?,?,?,?,?,?,?,?,?)",
            ("v1", build_id, "ku_test", build_id, len(canonical), "active", "2026-01-01", "2026-01-01", checksum),
        )
    else:
        con.execute(
            "INSERT INTO knowledge_index_versions VALUES "
            "(?,?,?,?,?,?,?,?,?)",
            ("v1", build_id, "ku_test", build_id, len(canonical), "active", "2026-01-01", "2026-01-01", None),
        )
    con.commit()
    con.close()


class _FakeColl:
    def __init__(self, ids: list[str], count: int | None = None) -> None:
        self._ids = list(ids)
        self._count = len(ids) if count is None else count

    def count(self) -> int:
        return self._count

    def get(self, limit: int = 2000, offset: int = 0, include: Any = None) -> dict:
        batch = self._ids[offset : offset + limit]
        return {"ids": batch}


class _FakeClient:
    def __init__(self, coll: _FakeColl, collection_name: str = "ku_test") -> None:
        self._coll = coll
        self._name = collection_name

    def list_collections(self) -> list[dict]:
        return [{"name": self._name, "id": "cid-1"}]

    def get_or_create_collection(self, name: str) -> _FakeColl:
        return self._coll


def test_reconcile_checksum_match_passes(tmp_path: Path) -> None:
    ids = ["cu1", "cu2", "cu3"]
    ck = _ids_checksum(ids)
    db = tmp_path / "db.sqlite"
    _setup_db(db, canonical=[(i, "current") for i in ids], checksum=ck)

    client = _FakeClient(_FakeColl(ids))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert isinstance(report, ReconcileReport)
    assert report.passed is True
    assert report.checksum_match is True
    assert report.missing == 0
    assert report.orphan == 0
    assert report.deprecated_residue == 0
    assert report.actual_count == 3
    assert report.eligible_count == 3


def test_reconcile_checksum_mismatch_fails(tmp_path: Path) -> None:
    ids = ["cu1", "cu2"]
    db = tmp_path / "db.sqlite"
    _setup_db(db, canonical=[(i, "current") for i in ids], checksum="deadbeef" * 8)

    client = _FakeClient(_FakeColl(ids))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert report.passed is False
    assert report.checksum_match is False
    assert report.missing == -1
    assert report.orphan == -1


def test_reconcile_missing_collection_fails(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _setup_db(db, canonical=[("cu1", "current")], checksum="x")

    class EmptyClient:
        def list_collections(self):
            return []

        def get_or_create_collection(self, name):
            raise AssertionError("should not create")

    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=EmptyClient()):
        report = reconcile(db, "ku_missing")

    assert report.passed is False
    assert report.actual_count == 0


def test_reconcile_no_checksum_uses_eligible_set(tmp_path: Path) -> None:
    """无 stored checksum 时用 eligible ID-set 做 orphan/missing。"""
    ids = ["cu1", "cu2"]
    db = tmp_path / "db.sqlite"
    _setup_db(db, canonical=[(i, "current") for i in ids], checksum=None)

    client = _FakeClient(_FakeColl(ids))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert report.orphan == 0
    assert report.missing == 0
    assert report.passed is True
    # fallback 路径在 count 对齐时可标记 checksum_match
    assert report.checksum_match is True


def test_reconcile_orphan_without_checksum(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _setup_db(db, canonical=[("cu1", "current")], checksum=None)

    client = _FakeClient(_FakeColl(["cu1", "orphan_x"]))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert report.orphan == 1
    assert report.passed is False


def test_reconcile_deprecated_residue(tmp_path: Path) -> None:
    ids = ["cu_cur", "cu_old"]
    ck = _ids_checksum(ids)
    db = tmp_path / "db.sqlite"
    _setup_db(
        db,
        canonical=[("cu_cur", "current"), ("cu_old", "rejected")],
        checksum=ck,
    )

    client = _FakeClient(_FakeColl(ids))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert report.deprecated_residue >= 1
    assert report.passed is False


def test_reconcile_pages_large_id_set(tmp_path: Path) -> None:
    """分页 get 能拼出完整 ID 集。"""
    ids = [f"cu{i:04d}" for i in range(4500)]
    ck = _ids_checksum(ids)
    db = tmp_path / "db.sqlite"
    # 只写少量 canonical 行以控制 setup 成本；checksum 路径不依赖全量 eligible 行
    _setup_db(db, canonical=[("cu0000", "current")], checksum=ck)

    client = _FakeClient(_FakeColl(ids))
    with patch("personal_knowledge.core.chroma_client.ChromaClient", return_value=client):
        report = reconcile(db, "ku_test")

    assert report.actual_count == 4500
    assert report.checksum_match is True
    assert report.passed is True
