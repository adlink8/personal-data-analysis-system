"""Phase 16: Google normalized_events + light assertions."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from pipeline.build_google_normalized_events import build as build_norm  # noqa: E402
from pipeline.build_google_light_assertions import (  # noqa: E402
    build as build_assert,
    _is_restricted,
)


def _seed_google_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.executescript(
        """
        CREATE TABLE activities (
            id INTEGER PRIMARY KEY,
            service TEXT,
            event_at TEXT,
            month TEXT,
            action TEXT,
            category TEXT,
            title_or_query TEXT,
            channel_or_source TEXT,
            domain TEXT,
            url TEXT,
            raw_excerpt TEXT,
            source_dataset TEXT
        );
        """
    )
    rows = [
        (1, "Search", "2026-01-01", "2026-01", "search", "AI / 编程 / 工具", "python fastapi", "", "example.com", "", "python fastapi", "t"),
        (2, "Search", "2026-01-02", "2026-01", "search", "AI / 编程 / 工具", "sqlite fts", "", "example.com", "", "sqlite fts", "t"),
        (3, "Search", "2026-01-03", "2026-01", "search", "AI / 编程 / 工具", "chroma vector", "", "docs.com", "", "chroma", "t"),
        (4, "Search", "2026-01-04", "2026-01", "search", "AI / 编程 / 工具", "rag pipeline", "", "docs.com", "", "rag", "t"),
        (5, "Search", "2026-01-05", "2026-01", "search", "AI / 编程 / 工具", "embedding model", "", "docs.com", "", "embed", "t"),
        (6, "YouTube", "2026-01-06", "2026-01", "watch", "娱乐 / 体育 / 生活内容", "video a", "ChannelX", "youtube.com", "", "vid", "t"),
        (7, "YouTube", "2026-01-07", "2026-01", "watch", "娱乐 / 体育 / 生活内容", "video b", "ChannelX", "youtube.com", "", "vid", "t"),
        (8, "YouTube", "2026-01-08", "2026-01", "watch", "娱乐 / 体育 / 生活内容", "video c", "ChannelX", "youtube.com", "", "vid", "t"),
        (9, "Maps", "2026-01-09", "2026-01", "view", "地图 / 地点 / 本地生活", "some place", "", "", "", "place", "t"),
        (10, "Search", "2026-01-10", "2026-01", "search", "支付 / 金融 / 卡", "bank stuff", "", "bank.com", "", "pay", "t"),
    ]
    con.executemany(
        "INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    con.close()


def test_is_restricted() -> None:
    assert _is_restricted("Maps", "anything")
    assert _is_restricted("Search", "支付 / 金融 / 卡")
    assert not _is_restricted("Search", "AI / 编程 / 工具")


def test_normalized_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "g.sqlite"
    _seed_google_db(db)
    s1 = build_norm(db, write=True)
    assert s1.written == 10
    assert s1.after_count == 10
    s2 = build_norm(db, write=True)
    assert s2.after_count == 10
    con = sqlite3.connect(str(db))
    eid = con.execute("SELECT event_id FROM normalized_events LIMIT 1").fetchone()[0]
    assert str(eid).startswith("g|")
    con.close()


def test_light_assertions_privacy(tmp_path: Path) -> None:
    db = tmp_path / "g.sqlite"
    _seed_google_db(db)
    build_norm(db, write=True)
    stats, assertions = build_assert(db, write=True)
    assert stats.assertions >= 1
    # Maps/payment not as interest subjects
    subjects = {a["subject"] for a in assertions}
    assert "Maps" not in subjects
    assert not any("支付" in s for s in subjects)
    # programming topic should appear
    types = {a["assertion_type"] for a in assertions}
    assert "interest_topic" in types or "frequent_service" in types
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT COUNT(*) FROM google_light_assertions").fetchone()[0]
    assert n == len(assertions)
    con.close()


def test_dry_run_no_write(tmp_path: Path) -> None:
    db = tmp_path / "g.sqlite"
    _seed_google_db(db)
    s = build_norm(db, write=False)
    assert s.written == 10
    con = sqlite3.connect(str(db))
    # table may exist after ensure but empty if dry-run without write path creating empty - build dry-run still runs ENSURE
    n = con.execute("SELECT COUNT(*) FROM normalized_events").fetchone()[0]
    assert n == 0
    con.close()
