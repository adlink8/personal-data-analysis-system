"""Phase 41-04 Nyquist 用例 10：EvidenceResolver scope 放宽的 4 象限锁。

放行边界严格限定在 evidence_scope in ('user','assistant')：
- user scope + eligible session      -> ok
- assistant scope + eligible session -> ok（本 phase 的放行面）
- assistant scope + ineligible session -> ineligible（红线 1：session veto 不动）
- is_system=1                        -> ineligible（红线 2：is_system veto 不动）
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.retrieval.evidence import EvidenceResolver


def _fixture(tmp_path: Path) -> EvidenceResolver:
    conv = tmp_path / "c.sqlite"
    con = sqlite3.connect(conv)
    con.execute("CREATE TABLE canonical_sessions(canonical_session_id TEXT PRIMARY KEY,evidence_eligible INTEGER)")
    con.execute(
        "CREATE TABLE canonical_messages("
        "canonical_message_id TEXT PRIMARY KEY,"
        "canonical_session_id TEXT,role TEXT,content TEXT,"
        "evidence_scope TEXT,is_system INTEGER)"
    )
    con.execute("INSERT INTO canonical_sessions VALUES ('s-ok',1),('s-no',0)")
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cm|user-ok','s-ok','user','用户提问','user',0),"
        "('cm|assistant-ok','s-ok','assistant','模型回答正文','assistant',0),"
        "('cm|assistant-ineligible-session','s-no','assistant','ineligible session 的回答','assistant',0),"
        "('cm|system','s-ok','assistant','系统注入内容','assistant',1)"
    )
    con.commit()
    con.close()
    return EvidenceResolver(
        unified_db=tmp_path / "missing-u.sqlite",
        conversation_db=conv,
        google_db=tmp_path / "missing-g.sqlite",
        turns_artifact=tmp_path / "missing-turns.json",
    )


def test_user_scope_eligible_session_resolves_ok(tmp_path: Path) -> None:
    r = _fixture(tmp_path)
    result = r.resolve("cm|user-ok", artifact_type="canonical_message")
    assert result["status"] == "ok"
    assert result["eligible"] is True


def test_assistant_scope_eligible_session_resolves_ok(tmp_path: Path) -> None:
    r = _fixture(tmp_path)
    result = r.resolve("cm|assistant-ok", artifact_type="canonical_message", include_content=True)
    assert result["status"] == "ok"
    assert result["eligible"] is True
    assert result["content"] == "模型回答正文"


def test_assistant_scope_ineligible_session_still_vetoed(tmp_path: Path) -> None:
    r = _fixture(tmp_path)
    result = r.resolve("cm|assistant-ineligible-session", artifact_type="canonical_message", include_content=True)
    assert result["status"] == "ineligible"
    assert result["eligible"] is False
    assert "content" not in result


def test_is_system_still_vetoed(tmp_path: Path) -> None:
    r = _fixture(tmp_path)
    result = r.resolve("cm|system", artifact_type="canonical_message", include_content=True)
    assert result["status"] == "ineligible"
    assert result["eligible"] is False
    assert "content" not in result
