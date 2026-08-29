"""semantic_cards 向量优先路径测试。

跟随 tests/unit/test_semantic_cards.py 的夹具风格：夹具库用几行假数据自建，
向量路径用假登记文件 + monkeypatch 假 chroma 客户端 / 假 embedding，零网络、
零真实模型；回退路径验证任一环节失败时无声回退且结果与关键词路径一致；
真实环境（登记 active + chroma 存活）只做 skipif 冒烟。
"""

from __future__ import annotations

import json
import sqlite3
from functools import partial
from pathlib import Path

import pytest

import personal_knowledge.retrieval.semantic_cards as semantic_cards
from personal_knowledge.core.chroma_client import ChromaError
from personal_knowledge.retrieval.semantic_cards import (
    _keyword_search,
    _split_endpoint,
    open_cards_db,
    search_cards,
)

# 与 tests/unit/test_semantic_cards.py 一致的 DDL（仅夹具用）
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
            ("v2|cs|aaaa1111aaaa", "配置 Dockerfile 代理构建环境", "普通纪要", "{}",
             10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1),
            ("v2|cs|bbbb2222bbbb", "普通会话乙", "普通纪要乙", "{}",
             10, 0, "test", 1, 1, "2026-08-01T00:00:00Z", 1),
        ],
    )
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


# === 假 chroma / 假 embedding ===

class _FakeCollection:
    """query 返回构造时给定的固定邻居（按距离升序）。"""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.last_n_results: int | None = None

    def query(self, query_embeddings=None, n_results=10, **kw) -> dict:
        self.last_n_results = n_results
        rows = self._rows[:n_results]
        return {
            "ids": [[r["id"] for r in rows]],
            "distances": [[r["distance"] for r in rows]],
            "metadatas": [[r["meta"] for r in rows]],
            "documents": [[r["doc"] for r in rows]],
        }


class _FakeClient:
    """可配置行为的假 chroma 客户端（只实现 _vector_search 用到的面）。"""

    def __init__(self, host="127.0.0.1", port=8001, fail: bool = False,
                 names: tuple[str, ...] = ("semantic_mvp_v1_test",),
                 coll: _FakeCollection | None = None):
        self.host, self.port = host, port
        self._fail = fail
        self._names = names
        self._coll = coll

    def list_collections(self):
        if self._fail:
            raise ChromaError("list_collections unavailable")
        return [{"name": n, "id": n} for n in self._names]

    def get_or_create_collection(self, name, metadata=None):
        if self._fail:
            raise ChromaError("get_or_create failed")
        return self._coll


def _write_registry(path: Path, build: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = build if build is not None else {
        "build_id": "sem_test",
        "collection": "semantic_mvp_v1_test",
        "docs": 3,
        "dim": 512,
        "model": "bge-small-zh-v1.5",
        "embedding_policy": "semantic-mvp-cards-facts-v1",
        "chroma_endpoint": "http://127.0.0.1:9999",
        "status": "active",
        "created_at": "2026-08-29T00:00:00+00:00",
    }
    path.write_text(json.dumps({"builds": [entry]}, ensure_ascii=False), encoding="utf-8")
    return path


def _patch_vector(monkeypatch: pytest.MonkeyPatch, registry: Path,
                  client_factory, embed=None) -> None:
    """client_factory 是可调用对象，接受 (host=..., port=...) 返回假客户端
    （仿 ChromaClient(host, port) 的构造方式）。"""
    monkeypatch.setattr(semantic_cards, "SEMANTIC_INDEX_REGISTRY", registry)
    monkeypatch.setattr(semantic_cards, "ChromaClient", client_factory)
    monkeypatch.setattr(
        semantic_cards.local_embed, "embed",
        embed or (lambda q: [0.1, 0.2, 0.3]),
    )


# === 向量路径：打分与聚合 ===

def test_vector_scoring_and_session_aggregation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _make_db(tmp_path / "cards.sqlite")
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    # 会话 A 两条事实（0.1 -> 0.9 / 0.3 -> 0.7），会话 B 一张卡（0.2 -> 0.8）
    coll = _FakeCollection([
        {"id": "f|k1", "distance": 0.1, "meta": {"kind": "fact", "session_id": "v2|cs|aaaa1111aaaa"},
         "doc": "事实一"},
        {"id": "f|k2", "distance": 0.3, "meta": {"kind": "fact", "session_id": "v2|cs|aaaa1111aaaa"},
         "doc": "事实二"},
        {"id": "c|b", "distance": 0.2, "meta": {"kind": "card", "session_id": "v2|cs|bbbb2222bbbb"},
         "doc": "普通会话乙"},
    ])
    _patch_vector(monkeypatch, registry, partial(_FakeClient, coll=coll))

    con = open_cards_db(db)
    try:
        rows = search_cards("任意查询", limit=5, con=con)
    finally:
        con.close()
    assert rows[0]["meta"]["mode"] == "vector"
    # 同会话聚合取最大相似度：A(0.9) > B(0.8)
    assert [r["session_id"] for r in rows] == ["v2|cs|aaaa1111aaaa", "v2|cs|bbbb2222bbbb"]
    assert rows[0]["score"] == pytest.approx(0.9)
    assert rows[1]["score"] == pytest.approx(0.8)
    assert rows[0]["fact_hits"] == 2
    assert rows[0]["matched_facts"] == ["事实一", "事实二"]
    assert rows[1]["fact_hits"] == 0
    # purpose 由 sqlite 会话卡回填
    assert rows[0]["purpose"] == "配置 Dockerfile 代理构建环境"
    assert rows[1]["purpose"] == "普通会话乙"
    # n_results = limit * VECTOR_TOP_MULTIPLIER
    assert coll.last_n_results == 5 * semantic_cards.VECTOR_TOP_MULTIPLIER


def test_vector_distance_clamped_and_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _make_db(tmp_path / "cards.sqlite")
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    coll = _FakeCollection([
        # 距离 >= 1 相似度钳到 0，应被过滤
        {"id": "f|far", "distance": 1.5, "meta": {"kind": "fact", "session_id": "v2|cs|aaaa1111aaaa"}, "doc": "远"},
        {"id": "f|near", "distance": 0.05, "meta": {"kind": "fact", "session_id": "v2|cs|bbbb2222bbbb"}, "doc": "近"},
        {"id": "f|near2", "distance": 0.2, "meta": {"kind": "fact", "session_id": "v2|cs|bbbb2222bbbb"}, "doc": "近二"},
        {"id": "c|extra", "distance": 0.3, "meta": {"kind": "card", "session_id": "v2|cs|cccc3333cccc"}, "doc": "多余"},
    ])
    _patch_vector(monkeypatch, registry, partial(_FakeClient, coll=coll))

    con = open_cards_db(db)
    try:
        rows = search_cards("任意查询", limit=1, con=con)
    finally:
        con.close()
    # 只有 score>0 的会话保留；limit=1 只留最相关的 B
    assert len(rows) == 1
    assert rows[0]["session_id"] == "v2|cs|bbbb2222bbbb"
    assert rows[0]["score"] == pytest.approx(0.95)
    assert rows[0]["meta"]["mode"] == "vector"


def test_vector_endpoint_parsed_from_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _make_db(tmp_path / "cards.sqlite")
    registry = _write_registry(tmp_path / "reg" / "registry.json", build={
        "build_id": "sem_test", "collection": "semantic_mvp_v1_test", "status": "active",
        "chroma_endpoint": "http://10.0.0.9:9100",
    })
    captured: dict = {}

    class _RecordingClient(_FakeClient):
        def __init__(self, host="127.0.0.1", port=8001, **kw):
            captured["endpoint"] = (host, port)
            super().__init__(host=host, port=port,
                             coll=_FakeCollection([
                                 {"id": "c|b", "distance": 0.2,
                                  "meta": {"kind": "card", "session_id": "v2|cs|bbbb2222bbbb"},
                                  "doc": "x"},
                             ]), **kw)

    _patch_vector(monkeypatch, registry, _RecordingClient)
    con = open_cards_db(db)
    try:
        rows = search_cards("查询", con=con)
    finally:
        con.close()
    assert captured["endpoint"] == ("10.0.0.9", 9100)
    assert rows and rows[0]["meta"]["mode"] == "vector"


def test_split_endpoint() -> None:
    assert _split_endpoint("http://127.0.0.1:8001") == ("127.0.0.1", 8001)
    assert _split_endpoint("http://host.example:9100") == ("host.example", 9100)
    assert _split_endpoint("") == ("127.0.0.1", 8001)
    assert _split_endpoint("garbage") == ("127.0.0.1", 8001)


# === 回退路径：任何一步失败 → keyword，且结果与关键词路径一致 ===

def test_fallback_no_registry(db_path: Path, con) -> None:
    # conftest autouse 已把登记指到不存在的路径：应走 keyword
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"
    assert rows == _with_mode_shape(_keyword_search("Dockerfile", con=con))


def _with_mode_shape(rows: list[dict]) -> list[dict]:
    out = [{**r, "meta": {"mode": "keyword"}} for r in rows]
    return out


def test_fallback_chroma_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, con) -> None:
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    _patch_vector(monkeypatch, registry, partial(_FakeClient, fail=True))
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"
    assert rows[0]["session_id"] == "v2|cs|aaaa1111aaaa"


def test_fallback_collection_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, con) -> None:
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    # 服务可达但登记的 collection 不在列表里
    _patch_vector(monkeypatch, registry, partial(_FakeClient, names=("other_collection",)))
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"


def test_fallback_embed_model_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, con) -> None:
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    coll = _FakeCollection([])

    def _boom(query: str) -> list[float]:
        raise RuntimeError("Local embedding model not configured")

    _patch_vector(monkeypatch, registry, partial(_FakeClient, coll=coll), embed=_boom)
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"


def test_fallback_registry_without_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, con) -> None:
    registry = _write_registry(tmp_path / "reg" / "registry.json", build={
        "build_id": "sem_test", "collection": "semantic_mvp_v1_test",
        "status": "candidate", "chroma_endpoint": "http://127.0.0.1:9999",
    })
    _patch_vector(monkeypatch, registry, _FakeClient)
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"


def test_fallback_corrupt_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, con) -> None:
    registry = tmp_path / "reg" / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("{not json", encoding="utf-8")
    _patch_vector(monkeypatch, registry, _FakeClient)
    rows = search_cards("Dockerfile", con=con)
    assert rows and rows[0]["meta"]["mode"] == "keyword"


def test_empty_query_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = _write_registry(tmp_path / "reg" / "registry.json")
    _patch_vector(monkeypatch, registry, partial(_FakeClient, coll=_FakeCollection([])))
    assert search_cards("") == []
    assert search_cards("   ") == []


# === 真实环境冒烟（登记不存在或无 active build 则跳过）===

_REAL_REGISTRY = semantic_cards.SEMANTIC_INDEX_REGISTRY


def _real_has_active_build() -> bool:
    try:
        data = json.loads(_REAL_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(
        b.get("status") == "active" and b.get("collection")
        for b in data.get("builds", []) if isinstance(b, dict)
    )


@pytest.mark.live
@pytest.mark.skipif(
    not (_REAL_REGISTRY.exists() and _real_has_active_build()),
    reason="var/db/semantic_index_registry.json 不存在或无 active build（本机未构建向量层）",
)
def test_real_vector_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest autouse 默认屏蔽登记；真实冒烟需还原为真实登记路径
    monkeypatch.setattr(semantic_cards, "SEMANTIC_INDEX_REGISTRY", _REAL_REGISTRY)
    rows = search_cards("Dockerfile", limit=3)
    assert rows, "真实向量层（或其关键词回退）应有 'Dockerfile' 命中"
    assert rows[0]["meta"]["mode"] in ("vector", "keyword")
    first = rows[0]
    assert first["session_id"].startswith("v2|cs|")
    assert first["score"] > 0
    # 向量模式下 purpose 应已由 sqlite 回填（有卡会话）
    if first["meta"]["mode"] == "vector":
        assert first["purpose"]
