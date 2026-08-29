"""tools/semantic/materialize_wiki.py：会话卡实体主题键控 + 物化幂等。

覆盖:
- 实体归一化（去路径前缀取主干、lowercase、非法主题键丢弃）
- KU 经 source_session_id -> 卡 -> 实体 的主题绑定与 --min-claims 噪声阈值
- 页面正文符合 wiki_page_body_v1 契约（确定性、无时间戳、无原始对话文本）
- 物化幂等：同内容重跑不新增版本/行；内容变化才追加新版本（pv_N 递增），
  每个版本恰好一行页面正文，无同主键重复行
- 页面可被 page-first 读路径（TopicProjectionService + WikiPageReader）读取
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[2] / "tools" / "semantic"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import materialize_wiki as mw  # noqa: E402

from personal_knowledge.services.topic_projection import TopicProjectionService  # noqa: E402
from personal_knowledge.wiki.derived_store import latest_page  # noqa: E402
from personal_knowledge.wiki.page_reader import (  # noqa: E402
    WikiPageReader,
    parse_page_body,
    subject_topic_id,
)

SESSION_A = "v2|cs|" + "a" * 32
SESSION_B = "v2|cs|" + "b" * 32


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _ku(unit_id, session, answer="ans", unit_type="personal_fact", confidence=0.9):
    return (unit_id, unit_type, "subj", "", answer, confidence, "current", "current", 1, session)


def _make_dbs(tmp_path, units, cards):
    """units: [(unit_id, ...)]；cards: [(session_id, entities)]。"""
    ku_db = tmp_path / "ku.sqlite"
    con = sqlite3.connect(ku_db)
    con.execute(
        "CREATE TABLE knowledge_units (unit_id TEXT, unit_type TEXT, subject TEXT, question TEXT,"
        " answer TEXT, confidence REAL, lifecycle TEXT, status TEXT, version INTEGER, source_session_id TEXT)"
    )
    con.execute(
        "CREATE TABLE knowledge_unit_evidence (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " unit_id TEXT, evidence_ref TEXT, evidence_type TEXT)"
    )
    con.executemany("INSERT INTO knowledge_units VALUES (?,?,?,?,?,?,?,?,?,?)", units)
    for i, unit in enumerate(units):
        con.execute(
            "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref, evidence_type) VALUES (?,?,'message')",
            (unit[0], f"v2|cm|{i:032x}"),
        )
    con.commit()
    con.close()

    cards_db = tmp_path / "cards.sqlite"
    con = sqlite3.connect(cards_db)
    con.execute(
        "CREATE TABLE session_cards (session_id TEXT, purpose TEXT, summary_md TEXT,"
        " card_json TEXT, n_messages INTEGER)"
    )
    for session_id, entities in cards:
        con.execute(
            "INSERT INTO session_cards VALUES (?,?,?,?,?)",
            (session_id, "p", "s", json.dumps({"purpose": "p", "entities": entities}, ensure_ascii=False), 1),
        )
    con.commit()
    con.close()
    return ku_db, cards_db


def _codex_fixture(tmp_path):
    """codex：5 条 current KU（会话 A）；数据分析：2 条（会话 B，卡实体为同一路径的两种写法）→ 低于阈值。"""
    units = [
        _ku(f"v1|{i:032x}", SESSION_A, answer=f"answer-{i}") for i in range(3)
    ] + [
        _ku(f"v1|{(i + 10):032x}", SESSION_A, answer=f"answer-a{i}") for i in range(2)
    ] + [
        _ku("v1|" + "c" * 32, SESSION_B, answer="tiny-1"),
        _ku("v1|" + "d" * 32, SESSION_B, answer="tiny-2"),
    ]
    cards = [
        (SESSION_A, ["Codex"]),
        (SESSION_B, [r"C:\Users\li\Desktop\数据分析", r"D:/ADLINK/数据分析/"]),
    ]
    return _make_dbs(tmp_path, units, cards)


# ---------------------------------------------------------------------------
# 主题键控
# ---------------------------------------------------------------------------

def test_normalize_entity_strips_path_prefix_and_lowercases():
    assert mw.normalize_entity(r"C:\Users\li\Desktop\数据分析") == "数据分析"
    assert mw.normalize_entity("D:/ADLINK/数据分析/") == "数据分析"
    assert mw.normalize_entity("  Codex ") == "codex"
    assert mw.normalize_entity("AGENTS.md") == "agents.md"
    assert mw.normalize_entity("") is None
    assert mw.normalize_entity(None) is None


def test_invalid_entity_never_becomes_topic():
    assert mw.valid_topic_name("codex") is True
    # 含冒号/分隔符的实体无法构成合法 subject TopicKey，绑定阶段必须丢弃
    assert mw.valid_topic_name("a:b") is False
    assert mw.valid_topic_name("a/b") is False
    assert mw.valid_topic_name(r"a\b") is False


def test_bind_topics_links_ku_via_card_entities():
    units = [dict(
        unit_id=f"v1|{i:032x}", unit_type="personal_fact", subject="s", question="",
        answer=f"a{i}", confidence=0.9, lifecycle="current", version=1,
        source_session_id=SESSION_A,
    ) for i in range(2)]
    entities = {SESSION_A: ["codex", "gsd"]}
    topics, unbound = mw.bind_topics(units, entities)
    assert sorted(topics) == ["codex", "gsd"]
    assert len(topics["codex"]) == 2
    assert unbound == {"no_session_id": 0, "session_without_card": 0, "card_without_entities": 0}


def test_bind_topics_counts_unbound_kus():
    units = [
        {"unit_id": "u1", "source_session_id": SESSION_A},   # 卡存在但无实体
        {"unit_id": "u2", "source_session_id": "v2|cs|zz"},  # 无卡
        {"unit_id": "u3", "source_session_id": ""},          # 无 session id
    ]
    entities = {SESSION_A: []}
    topics, unbound = mw.bind_topics(units, entities)
    assert topics == {}
    assert unbound == {"no_session_id": 1, "session_without_card": 1, "card_without_entities": 1}


def test_select_topics_threshold_and_ranking():
    topics = {"tiny": [{}] * 2, "mid": [{}] * 5, "big": [{}] * 9, "bigger": [{}] * 9}
    selected = mw.select_topics(topics, min_claims=5)
    assert sorted(selected) == ["big", "bigger", "mid"]
    limited = mw.select_topics(topics, min_claims=5, limit_topics=2)
    # 同分（都是 9 条）按主题名升序稳定排序
    assert sorted(limited) == ["big", "bigger"]
    single = mw.select_topics({"a": [{}] * 5, "b": [{}] * 8}, min_claims=5, limit_topics=1)
    assert list(single) == ["b"]


# ---------------------------------------------------------------------------
# 页面正文契约
# ---------------------------------------------------------------------------

def test_page_body_is_deterministic_and_contract_shaped(tmp_path):
    ku_db, cards_db = _codex_fixture(tmp_path)
    units = mw.load_current_units(ku_db)
    evidence = mw.load_evidence_refs(ku_db)
    topics, _ = mw.bind_topics(units, mw.load_card_entities(cards_db))
    assert sorted(topics) == ["codex", "数据分析"]  # 卡内两个路径写法归一并去重
    assert len(topics["codex"]) == 5 and len(topics["数据分析"]) == 2
    body = mw.build_page_body("codex", topics["codex"], evidence)
    assert body["schema"] == "wiki_page_body_v1"
    assert body["subject"] == "codex"
    assert body["topic"]["topic_type"] == "subject"
    assert body["topic"]["canonical_key"] == "subject:codex"
    assert body["topic"]["topic_id"] == subject_topic_id("codex")
    assert body["aggregation"]["unit_count"] == 5
    assert set(body["aggregation"]["unit_type_counts"]) == {"personal_fact"}
    assert set(body["claims"][0]) >= {"unit_id", "unit_type", "answer", "confidence", "lifecycle", "evidence_refs", "authority_ref"}
    assert body["claims"][0]["evidence_refs"] == [{"ref": "v2|cm|" + "0" * 32}]
    # 确定性：无时间戳，同输入同 checksum；不含原始对话文本
    dumped = json.dumps(body, ensure_ascii=False)
    assert "2026" not in dumped and "对话" not in dumped and "summary_md" not in dumped
    assert mw.build_page_body("codex", topics["codex"], evidence) == body


def test_confidence_text_value_is_normalized():
    claim = mw._claim_from_unit({"unit_id": "u", "confidence": "0.9", "lifecycle": "current", "unit_type": "fact", "subject": "s", "question": "", "answer": "a"}, [])
    assert claim["confidence"] == 0.9
    assert mw._claim_from_unit({"unit_id": "u", "confidence": "n/a"}, [])["confidence"] is None


# ---------------------------------------------------------------------------
# 物化幂等
# ---------------------------------------------------------------------------

def _store_counts(store):
    con = sqlite3.connect(f"file:{Path(store).as_posix()}?mode=ro", uri=True)
    try:
        return {
            "versions": con.execute("SELECT COUNT(*) FROM wiki_projection_versions").fetchone()[0],
            "pages": con.execute("SELECT COUNT(*) FROM wiki_projection_pages").fetchone()[0],
            "dup_page_pk": con.execute(
                "SELECT COUNT(*) FROM (SELECT topic_id, projection_version FROM wiki_projection_pages GROUP BY 1,2 HAVING COUNT(*)>1)"
            ).fetchone()[0],
            "subject_versions": con.execute(
                "SELECT COUNT(*) FROM wiki_projection_versions WHERE topic_type='subject'"
            ).fetchone()[0],
        }
    finally:
        con.close()


def test_materialize_threshold_write_and_idempotent_rerun(tmp_path):
    ku_db, cards_db = _codex_fixture(tmp_path)
    store = tmp_path / "wiki.sqlite"

    # run 1: 只有 codex（5 条）过阈值，tiny（2 条）被噪声阈值挡住
    stats = mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=True)
    assert stats["topics_selected"] == 1 and stats["pages_written"] == 1 and stats["errors"] == []
    assert _store_counts(store) == {"versions": 1, "pages": 1, "dup_page_pk": 0, "subject_versions": 1}

    # run 2（内容不变）：全部跳过——不新增版本、行数不翻倍
    stats2 = mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=True)
    assert stats2["pages_written"] == 0 and stats2["pages_skipped"] == 1
    assert _store_counts(store) == {"versions": 1, "pages": 1, "dup_page_pk": 0, "subject_versions": 1}

    # run 3（源内容变化）：追加新版本 pv_2，页面行每个版本恰好一行
    con = sqlite3.connect(ku_db)
    con.execute("UPDATE knowledge_units SET answer='changed-answer' WHERE unit_id=?", ("v1|" + "0" * 32,))
    con.commit()
    con.close()
    stats3 = mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=True)
    assert stats3["pages_written"] == 1
    counts = _store_counts(store)
    assert counts == {"versions": 2, "pages": 2, "dup_page_pk": 0, "subject_versions": 2}
    page = latest_page(store, subject_topic_id("codex"))
    assert page.projection_version == "pv_2"
    assert "changed-answer" in page.page_body
    assert parse_page_body(page) is not None  # checksum 一致、schema 合法


def test_materialize_respects_limit_topics(tmp_path):
    units = [_ku(f"v1|{i:032x}", SESSION_A) for i in range(4)]
    units += [_ku("v1|" + "e" * 32, SESSION_B)]
    ku_db, cards_db = _make_dbs(
        tmp_path, units,
        [(SESSION_A, ["zeta"]), (SESSION_B, ["alpha", "zeta"])],
    )
    store = tmp_path / "wiki.sqlite"
    stats = mw.materialize(
        db_path=ku_db, cards_path=cards_db, store_path=store,
        write=True, min_claims=1, limit_topics=1,
    )
    # zeta 5 条 > alpha 1 条，limit 取 claims 最多的主题
    assert stats["topics_selected"] == 1 and stats["pages_written"] == 1
    page = latest_page(store, subject_topic_id("zeta"))
    assert page is not None and page.topic_type == "subject"


def test_dry_run_writes_nothing(tmp_path):
    ku_db, cards_db = _codex_fixture(tmp_path)
    store = tmp_path / "wiki.sqlite"
    stats = mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=False)
    assert stats["topics_selected"] == 1 and stats["pages_written"] == 1
    assert not store.exists()  # 派生库完全未被创建


# ---------------------------------------------------------------------------
# page-first 读路径（端到端）
# ---------------------------------------------------------------------------

class _Reader:
    def invoke(self, operation, **params):
        return {"ok": True, "data": {}}


def test_materialized_page_served_by_topic_get(tmp_path):
    ku_db, cards_db = _codex_fixture(tmp_path)
    store = tmp_path / "wiki.sqlite"
    assert mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=True)["pages_written"] == 1

    service = TopicProjectionService(
        personal_reader=_Reader(), decision_reader=_Reader(), external_reader=_Reader(),
        materializer=mw.WikiMaterializer(store), page_reader=WikiPageReader(store),
    )
    env = service.invoke("topic.get", topic_key="subject:codex")
    assert env["ok"] is True and env["status"] == "fresh"
    assert env["data"]["subject"] == "codex"
    assert env["data"]["topic"]["canonical_key"] == "subject:codex"
    assert env["data"]["aggregation"]["unit_count"] == 5
    assert env["data"]["claims"][0]["unit_id"] == "v1|" + "0" * 32
    assert env["authorities"] == {"wiki": "ok"}
    # 页面出现在 topic.list 目录里
    listing = service.invoke("topic.list", limit=50)
    assert "subject:codex" in [item["canonical_key"] for item in listing["data"]["items"]]


@pytest.mark.parametrize("bad_key", ["project:codex", "goal:a:b:c", "bogus"])
def test_non_subject_keys_do_not_serve_ku_pages(tmp_path, bad_key):
    """非 subject 键不吃统合页面：project 等必须走 authority 背书（契约）。"""
    ku_db, cards_db = _codex_fixture(tmp_path)
    store = tmp_path / "wiki.sqlite"
    mw.materialize(db_path=ku_db, cards_path=cards_db, store_path=store, write=True)
    service = TopicProjectionService(
        personal_reader=_Reader(), decision_reader=_Reader(), external_reader=_Reader(),
        materializer=mw.WikiMaterializer(store), page_reader=WikiPageReader(store),
    )
    env = service.invoke("topic.get", topic_key=bad_key)
    assert env["ok"] is False
