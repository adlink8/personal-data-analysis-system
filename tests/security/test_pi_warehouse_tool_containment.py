from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from personal_knowledge.services.warehouse_tools import WarehouseToolError, WarehouseTools


def _fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_forbidden_fixtures_do_not_touch_fixture_authority(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.fixture"
    watermark = tmp_path / "watermark.fixture"
    pointer = tmp_path / "active-pointer.fixture"
    for path, text in ((canonical, "canonical"), (watermark, "watermark"), (pointer, "active")):
        path.write_text(text, encoding="utf-8")
    before = {path: _fingerprint(path) for path in (canonical, watermark, pointer)}
    opened: list[str] = []
    tools = WarehouseTools(db_open=opened.append)

    forbidden = [
        {"authority_id": "knowledge", "cursor": "file.txt"},
        {"authority_id": "knowledge", "filters": {"status": "DELETE"}},
        {"authority_id": "knowledge", "snapshot_id": "x; PRAGMA journal_mode=off"},
        {"authority_id": "unknown", "limit": 1},
        {"authority_id": "knowledge", "limit": 1000},
        {"authority_id": "knowledge", "filters": {"status": lambda: None}},
        {"authority_id": "knowledge", "query": "TRUNCATE"},
    ]
    for params in forbidden:
        with pytest.raises(WarehouseToolError):
            tools.invoke("warehouse.inspect", params)

    assert opened == []
    assert before == {path: _fingerprint(path) for path in (canonical, watermark, pointer)}


def test_successful_read_still_exposes_no_raw_or_credential_shaped_values() -> None:
    tools = WarehouseTools(metadata={"knowledge": {"records": 2, "raw": "secret-token"}})
    result = tools.invoke("warehouse.integrity", {"authority_id": "knowledge", "limit": 2})
    assert result["ok"] is True
    assert "secret-token" not in str(result)
    assert "credentials" not in str(result).lower()
    assert "sql" not in str(result).lower()

