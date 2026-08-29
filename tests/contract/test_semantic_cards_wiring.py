"""MVP 会话卡检索接线契约：MCP render 分支 + REST /search/cards handler。

夹具库复用 tests/unit/test_semantic_cards.py 的 DDL 与数据思路（零 LLM、零网络），
通过 monkeypatch semantic_cards.CARDS_DB_PATH 把检索指向夹具库，不依赖真实
var/db/semantic_mvp_v3.sqlite。REST handler 用桩 handler 直接调函数（不启服务）。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import personal_knowledge.retrieval.semantic_cards as semantic_cards
from personal_knowledge.mcp_tools import tool_definitions as td
from personal_knowledge.mcp_tools.handlers import ALL_TOOL_NAMES
from personal_knowledge.mcp_tools.handlers import data as data_handlers
from personal_knowledge.services.http.handlers import data as rest_data_handlers

TOOL_NAME = "search_semantic_cards"

# 与 tests/unit/test_semantic_cards.py 一致的 DDL（仅夹具用，复刻管线 init_db）
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
    con = sqlite3.connect(str(db_path))
    con.executescript(_FIXTURE_DDL)
    con.executemany(
        "insert into session_cards values (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("v2|cs|aaaa1111aaaa", "配置 Dockerfile 代理构建环境", "普通纪要",
             json.dumps({"conclusions": ["走本地代理构建"]}, ensure_ascii=False),
             10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1),
            ("v2|cs|bbbb2222bbbb", "普通会话乙", "普通纪要乙", "{}",
             10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1),
            ("v2|cs|dddd4444dddd", "普通会话丁", "纪要里有 onlysumm 一个词", "{}",
             10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1),
        ],
    )
    con.executemany(
        "insert into ku_facts values (?,?,?,?,?,?,?,?,?)",
        [
            ("kc|f1", "v2|cs|aaaa1111aaaa", "Dockerfile 的代理地址改为 http://127.0.0.1:7890",
             '["v2|cm|e1", "v2|cm|e2"]', "high", "2026-08-01T00:00:00Z", None,
             "active", "dockerfile的代理地址改为http1270017890"),
            ("kc|onlyfact", "v2|cs|bbbb2222bbbb", "关键事实包含 onlyfact 标记",
             '["v2|cm|e3"]', "high", "2026-08-02T00:00:00Z", None, "active", "x"),
        ],
    )
    con.commit()
    con.close()
    return db_path


@pytest.fixture
def cards_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = _make_db(tmp_path / "cards.sqlite")
    monkeypatch.setattr(semantic_cards, "CARDS_DB_PATH", db)
    return db


class _FakeHandler:
    """记录 _send 调用的桩 handler（handle_search_cards 只用到 _send）。"""

    def __init__(self) -> None:
        self.sent: tuple[bytes, int] | None = None

    def _send(self, body: bytes, code: int = 200) -> None:
        self.sent = (body, code)


def _rest(body: dict) -> tuple[dict, int]:
    handler = _FakeHandler()
    rest_data_handlers.handle_search_cards(handler, {"path": "/search/cards", "body": body})
    assert handler.sent is not None, "handler 未发送响应"
    payload, code = handler.sent
    return json.loads(payload.decode("utf-8")), code


# === 工具定义与 handler 一致性 ===

def test_tool_registered_in_core_and_all_tools() -> None:
    assert TOOL_NAME in td.CORE_TOOL_NAMES
    assert TOOL_NAME in data_handlers.TOOL_NAMES
    tool = next(t for t in td.ALL_TOOLS if t.name == TOOL_NAME)
    assert tool.description
    schema = tool.inputSchema
    assert schema["type"] == "object"
    assert "query" in schema["properties"]
    assert "top_k" in schema["properties"]
    assert "query" in schema.get("required", [])


def test_every_tool_schema_has_handler_route() -> None:
    # schema 面（ALL_TOOLS）与分派表（TOOL_TO_HANDLER）双向一致性：
    # 有 schema 必有 handler；反向多出的只能是文档化的 call 兼容别名。
    schema_names = {t.name for t in td.ALL_TOOLS}
    aliases = {"data_export_all", "data_export_query"}
    assert schema_names <= ALL_TOOL_NAMES
    assert set(ALL_TOOL_NAMES) - schema_names == aliases


# === MCP render 分支 ===

def test_mcp_render_search_cards_hit(cards_db: Path) -> None:
    out = data_handlers.render(TOOL_NAME, {"query": "Dockerfile"})
    assert "v2|cs|aaaa1111aaaa" in out
    assert "score=" in out
    assert "Dockerfile" in out  # 命中事实行回显


def test_mcp_render_search_cards_empty(cards_db: Path) -> None:
    out = data_handlers.render(TOOL_NAME, {"query": "zzzznohit"})
    assert "无匹配结果" in out
    # 空查询不成词，同样走空结果文案
    assert "无匹配结果" in data_handlers.render(TOOL_NAME, {"query": ""})


def test_mcp_render_search_cards_respects_top_k(cards_db: Path) -> None:
    # "会话" 命中乙/丁两张卡的 purpose；top_k=1 应只返回 1 条
    out = data_handlers.render(TOOL_NAME, {"query": "会话", "top_k": 1})
    assert "共召回 1 条" in out


# === REST /search/cards handler ===

def test_rest_search_cards_hit(cards_db: Path) -> None:
    payload, code = _rest({"query": "Dockerfile"})
    assert code == 200
    assert payload["ok"] is True
    rows = payload["data"]
    assert isinstance(rows, list) and rows
    assert rows[0]["session_id"] == "v2|cs|aaaa1111aaaa"
    assert rows[0]["fact_hits"] >= 1
    assert rows[0]["matched_facts"]


def test_rest_search_cards_accepts_top_k_alias(cards_db: Path) -> None:
    payload, code = _rest({"query": "会话", "top_k": 1})
    assert code == 200
    assert len(payload["data"]) == 1


def test_rest_search_cards_empty_result(cards_db: Path) -> None:
    payload, code = _rest({"query": "zzzznohit"})
    assert code == 200
    assert payload["ok"] is True
    assert payload["data"] == []


def test_rest_search_cards_missing_params(cards_db: Path) -> None:
    payload, code = _rest({})
    assert code == 400
    assert payload["ok"] is False
    # 空 query 同样 400
    payload, code = _rest({"query": "   "})
    assert code == 400


def test_rest_search_cards_detail_by_session_id(cards_db: Path) -> None:
    payload, code = _rest({"session_id": "v2|cs|aaaa1111aaaa"})
    assert code == 200
    card = payload["data"]
    assert card["purpose"] == "配置 Dockerfile 代理构建环境"
    assert card["card"] == {"conclusions": ["走本地代理构建"]}
    assert [f["fact_key"] for f in card["facts"]] == ["kc|f1"]
    assert card["facts"][0]["evidence_refs"] == ["v2|cm|e1", "v2|cm|e2"]


def test_rest_search_cards_detail_not_found(cards_db: Path) -> None:
    payload, code = _rest({"session_id": "v2|cs|nope"})
    assert code == 404
    assert payload["ok"] is False
