"""semantic_cards 检索适配器测试。

夹具库用几行假数据自建（复刻 tools/semantic/mvp_semantic_compress.py init_db 的 DDL），
不依赖真实 173 卡库；真实库只做一条 skip-if-missing 的冒烟测试。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.core.project_paths import VAR_DB
from personal_knowledge.retrieval.semantic_cards import (
    abbrev_sid,
    get_card,
    main,
    open_cards_db,
    search_cards,
)

# 与 tools/semantic/mvp_semantic_compress.py init_db 一致的 DDL（仅夹具用）
_FIXTURE_DDL = """
CREATE TABLE IF NOT EXISTS session_cards(
  session_id TEXT PRIMARY KEY, purpose TEXT, summary_md TEXT,
  card_json TEXT, n_messages INTEGER, truncated INTEGER,
  model TEXT, input_tokens INTEGER, output_tokens INTEGER, created_at TEXT,
  chunk_count INTEGER);
CREATE TABLE IF NOT EXISTS ku_facts(
  fact_key TEXT PRIMARY KEY, session_id TEXT, fact TEXT,
  evidence_refs TEXT, confidence TEXT, valid_from TEXT,
  supersedes TEXT, status TEXT DEFAULT 'active', norm_prefix TEXT);
"""


def _make_db(db_path: Path) -> Path:
    """4 张卡 + 5 条事实的确定性夹具库（打分用例见 test_field_weights）。"""
    con = sqlite3.connect(str(db_path))
    con.executescript(_FIXTURE_DDL)
    cards = [
        # A: purpose 命中 "dockerfile"
        ("v2|cs|aaaa1111aaaa", "配置 Dockerfile 代理构建环境", "普通纪要",
         json.dumps({"conclusions": ["走本地代理构建"]}, ensure_ascii=False)),
        # B: 只有 fact 命中 "onlyfact"
        ("v2|cs|bbbb2222bbbb", "普通会话乙", "普通纪要乙", "{}"),
        # C: 只有 purpose 命中 "onlypurp"
        ("v2|cs|cccc3333cccc", "onlypurp 专题讨论", "普通纪要丙", "{}"),
        # D: 只有 summary_md 命中 "onlysumm"
        ("v2|cs|dddd4444dddd", "普通会话丁", "纪要里有 onlysumm 一个词", "{}"),
    ]
    con.executemany(
        "insert into session_cards values (?,?,?,?,?,?,?,?,?,?,?)",
        [(sid, p, s, cj, 10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1)
         for sid, p, s, cj in cards],
    )
    facts = [
        # A 的两条事实：一条 active + 一条 superseded（get_card 应排除后者）
        ("kc|f1", "v2|cs|aaaa1111aaaa", "Dockerfile 的代理地址改为 http://127.0.0.1:7890",
         '["v2|cm|e1", "v2|cm|e2"]', "high", "2026-08-01T00:00:00Z", None, "active",
         "dockerfile的代理地址改为http1270017890"),
        ("kc|f0", "v2|cs|aaaa1111aaaa", "旧的代理设置是 http://127.0.0.1:1080",
         '["v2|cm|e1"]', "medium", "2026-07-01T00:00:00Z", "kc|f1", "superseded",
         "旧的代理设置是http1270011080"),
        # B：只有 fact 命中（权重 4 用例）
        ("kc|onlyfact", "v2|cs|bbbb2222bbbb", "关键事实包含 onlyfact 标记",
         '["v2|cm|e3"]', "high", "2026-08-02T00:00:00Z", None, "active", "x"),
        # C：fact 归并用（session 无卡，搜索应合成条目）
        ("kc|orphan", "v2|cs|nocard9999", "无卡记录的事实包含补充说明",
         "[]", "medium", "2026-08-03T00:00:00Z", None, "active", "y"),
    ]
    con.executemany("insert into ku_facts values (?,?,?,?,?,?,?,?,?)", facts)
    con.commit()
    con.close()
    return db_path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return _make_db(tmp_path / "cards.sqlite")


@pytest.fixture
def con(db_path: Path):
    c = open_cards_db(db_path)
    yield c
    c.close()


# === search_cards ===

def test_search_hits_purpose(con) -> None:
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["session_id"] == "v2|cs|aaaa1111aaaa"
    assert rows[0]["score"] > 0


def test_search_fact_join_and_case_insensitive(con) -> None:
    # "onlyfact" 只出现在 B 的 fact 里 -> 通过 session_id 归并到 B 的卡
    rows = search_cards("ONLYFACT", con=con)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "v2|cs|bbbb2222bbbb"
    assert rows[0]["fact_hits"] == 1
    assert rows[0]["matched_facts"] == ["关键事实包含 onlyfact 标记"]


def test_field_weights(con) -> None:
    """同一次命中：fact(4) > purpose(3) > summary_md(2)。"""
    fact_rows = search_cards("onlyfact", con=con)
    purp_rows = search_cards("onlypurp", con=con)
    summ_rows = search_cards("onlysumm", con=con)
    assert fact_rows[0]["score"] == pytest.approx(4.0)
    assert purp_rows[0]["score"] == pytest.approx(3.0)
    assert summ_rows[0]["score"] == pytest.approx(2.0)


def test_cjk_bigram_search(con) -> None:
    # 中文 2-gram："代理" 是 CJK run，子串命中 A 的 purpose 与 f1 的 fact
    rows = search_cards("代理", con=con)
    assert rows and rows[0]["session_id"] == "v2|cs|aaaa1111aaaa"
    assert rows[0]["fact_hits"] >= 1  # active fact f1 命中；superseded f0 不计


def test_orphan_fact_without_card(con) -> None:
    # 事实的 session 无卡 -> 合成条目（purpose 为 None）仍可检索
    rows = search_cards("补充", con=con)
    assert len(rows) == 1
    assert rows[0]["session_id"] == "v2|cs|nocard9999"
    assert rows[0]["purpose"] is None


def test_search_limit(con) -> None:
    rows = search_cards("会话", limit=1, con=con)
    assert len(rows) == 1


def test_search_empty_query(con) -> None:
    assert search_cards("", con=con) == []
    assert search_cards("ab", con=con) == []  # 短于 4 字符的 ASCII 串不成词


def test_search_empty_db(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite"
    c = sqlite3.connect(str(empty))
    c.executescript(_FIXTURE_DDL)
    c.commit()
    c.close()
    ro = open_cards_db(empty)
    try:
        assert search_cards("Dockerfile", con=ro) == []
        assert get_card("v2|cs|anything", con=ro) is None
    finally:
        ro.close()


# === get_card ===

def test_get_card_full(con) -> None:
    card = get_card("v2|cs|aaaa1111aaaa", con=con)
    assert card is not None
    assert card["purpose"] == "配置 Dockerfile 代理构建环境"
    assert card["card"] == {"conclusions": ["走本地代理构建"]}
    # 只返回 active facts，superseded 的 kc|f0 被排除
    keys = [f["fact_key"] for f in card["facts"]]
    assert keys == ["kc|f1"]
    assert card["facts"][0]["evidence_refs"] == ["v2|cm|e1", "v2|cm|e2"]
    assert card["facts"][0]["confidence"] == "high"


def test_get_card_missing(con) -> None:
    assert get_card("v2|cs|nope", con=con) is None


def test_abbrev_sid() -> None:
    assert abbrev_sid("v2|cs|034f94cecd4d3c5d") == "cs:034f94cecd4d"


# === CLI ===

def test_cli_prints_results(db_path: Path, capsys) -> None:
    rc = main(["Dockerfile", "--db", str(db_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "cs:aaaa1111aaaa" in out
    assert "score=" in out


# === 真实库冒烟（文件不存在则跳过，避免环境耦合）===

_REAL_DB = VAR_DB / "semantic_mvp_v3.sqlite"


@pytest.mark.live
@pytest.mark.skipif(not _REAL_DB.exists(), reason="var/db/semantic_mvp_v3.sqlite 不存在（本机无 MVP 产物）")
def test_real_db_smoke() -> None:
    con = open_cards_db()
    try:
        rows = search_cards("codex", con=con)
        assert rows, "真实 v3 库应有 'codex' 命中"
        first = rows[0]
        assert first["session_id"].startswith("v2|cs|")
        assert first["score"] > 0
        card = get_card(first["session_id"], con=con)
        assert card is not None
        assert isinstance(card["facts"], list)
        assert all(f["status"] == "active" for f in card["facts"])
    finally:
        con.close()
