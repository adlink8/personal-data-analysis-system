from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.build_knowledge_unit_vector_store import (
    EMBEDDING_POLICY,
    MAX_EVIDENCE_CHARS,
    candidate_version_id,
    canonical_document,
    embedding_text,
    load_eligible_units,
)


def _unified(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE canonical_knowledge_units(
          canonical_unit_id TEXT PRIMARY KEY, unit_type TEXT, subject TEXT,
          question TEXT, answer TEXT, confidence REAL, lifecycle TEXT,
          run_id TEXT, status TEXT
        );
        CREATE TABLE knowledge_units(
          unit_id TEXT PRIMARY KEY, source_message_ref TEXT
        );
        CREATE TABLE canonical_unit_members(
          id INTEGER PRIMARY KEY, canonical_unit_id TEXT, member_unit_id TEXT
        );
        INSERT INTO canonical_knowledge_units VALUES
          ('ku-a','fact','Target D','如何完成？','按门禁收口',0.9,'current','run-1','current'),
          ('ku-b','fact','Secret','安全答案','不得泄露',0.8,'current','run-1','current');
        INSERT INTO knowledge_units VALUES
          ('m1','cm|assistant-a'),('m2','cm|assistant-a2'),('m3','cm|assistant-b');
        INSERT INTO canonical_unit_members VALUES
          (1,'ku-a','m1'),(2,'ku-a','m2'),(3,'ku-b','m3');
        """
    )
    con.commit()
    con.close()


def _conversations(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE canonical_sessions(
          canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER,
          evidence_scope TEXT
        );
        CREATE TABLE canonical_messages(
          canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT,
          ordinal INTEGER, role TEXT, content TEXT, evidence_scope TEXT,
          is_system INTEGER
        );
        INSERT INTO canonical_sessions VALUES
          ('s1',1,'user'),('s2',0,'user');
        INSERT INTO canonical_messages VALUES
          ('cm|user-a','s1',1,'user','完成 Target D，token=raw-secret-value','user',0),
          ('cm|assistant-a','s1',2,'assistant','回答 A','assistant',0),
          ('cm|user-a2','s1',3,'user','第二个真实问题','user',0),
          ('cm|assistant-a2','s1',4,'assistant','回答 B','assistant',0),
          ('cm|user-b','s2',1,'user','不合规的私密上下文','user',0),
          ('cm|assistant-b','s2',2,'assistant','回答 C','assistant',0);
        """
    )
    con.commit()
    con.close()


def test_loads_preceding_eligible_user_context_and_excludes_ineligible(tmp_path: Path) -> None:
    unified = tmp_path / "unified.sqlite"
    conversations = tmp_path / "conversations.sqlite"
    _unified(unified)
    _conversations(conversations)

    units, sealed = load_eligible_units(unified, conversations)

    assert [unit["unit_id"] for unit in units] == ["ku-a", "ku-b"]
    assert len(units[0]["evidence_contexts"]) == 2
    assert "完成 Target D" in units[0]["evidence_contexts"][0]
    assert "第二个真实问题" in units[0]["evidence_contexts"][1]
    assert "raw-secret-value" not in units[0]["evidence_contexts"][0]
    assert sealed == 1
    assert units[1]["evidence_contexts"] == []


def test_embedding_input_is_enriched_but_document_is_canonical_only() -> None:
    unit = {
        "subject": "Target D",
        "question": "如何完成？",
        "answer": "按门禁收口",
        "evidence_contexts": ["用户要求用真实数据完成整体流程"],
    }

    private_input = embedding_text(unit)
    product_document = canonical_document(unit)

    assert EMBEDDING_POLICY == "eligible-user-context-v1"
    assert "用户要求用真实数据完成整体流程" in private_input
    assert product_document == "如何完成？ 按门禁收口"
    assert "真实数据" not in product_document


def test_context_is_bounded_and_deterministic(tmp_path: Path) -> None:
    unified = tmp_path / "unified.sqlite"
    conversations = tmp_path / "conversations.sqlite"
    _unified(unified)
    _conversations(conversations)
    con = sqlite3.connect(conversations)
    con.execute(
        "UPDATE canonical_messages SET content=? WHERE canonical_message_id='cm|user-a'",
        ("甲" * (MAX_EVIDENCE_CHARS + 100),),
    )
    con.commit()
    con.close()

    first, _ = load_eligible_units(unified, conversations)
    second, _ = load_eligible_units(unified, conversations)

    assert first == second
    assert len(first[0]["evidence_contexts"][0]) == MAX_EVIDENCE_CHARS


def test_candidate_version_is_unique_per_collection() -> None:
    active = candidate_version_id("ir_same_build", "knowledge_units_active")
    candidate = candidate_version_id("ir_same_build", "knowledge_units_candidate")

    assert active != candidate
    assert active == candidate_version_id("ir_same_build", "knowledge_units_active")
