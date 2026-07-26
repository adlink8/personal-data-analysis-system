"""Phase 41 Plan 01：eligible 口径唯一化（D-05）等价性与 role 解耦测试。

Nyquist 用例：
1. inspect 的 current_refs 集合 == prepare 的 after_hashes key 集合（Gate B 回归锁）
2. role 解耦：roles 参数只影响返回哪些行，不影响单条 eligible 判定
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.eligibility import (
    ASSISTANT_TOOL_PREFIX_PATTERNS,
    compute_eligible_messages,
)
from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import (
    SCHEMA_SQL,
)
from personal_knowledge.application.knowledge.refresh_knowledge_units import (
    _current_eligible_ref_hashes,
    find_affected_evidence,
)

_LONG_USER = "user prefers PowerShell for all local automation tasks daily"
_LONG_USER_DUP = _LONG_USER  # 与 cm_u1 内容完全相同 → excluded_dup
_LONG_ASSISTANT = "assistant solution: use sqlite WAL mode for concurrent reads and writes"
_LONG_TOOL = "[Bash] ls -la /var/log && tail -f system.log output here"
_LONG_GEMINI_USER = "gemini user asks about deployment topology for staging environment"
_SHORT = "x" * 25  # 原文 >20 但清洗后 <=30 → excluded_short
_INJECTION_ONLY = (
    "<system-reminder>junk</system-reminder>" + "<" + "a" * 29 + ">"
)  # 清洗后 31 字但去括号 <=30 → excluded_injection_only


def _make_canonical_db(dest: Path) -> Path:
    """fixture canonical DB：2 source、user+assistant 混合、各类排除路径各一条、
    1 个 evidence_eligible=0 会话。"""
    con = sqlite3.connect(str(dest))
    con.execute(
        "CREATE TABLE canonical_sessions ("
        "canonical_session_id TEXT PRIMARY KEY, agent TEXT, started_at TEXT, "
        "evidence_eligible INTEGER DEFAULT 1)"
    )
    con.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, "
        "source TEXT, role TEXT, content TEXT)"
    )
    con.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs1','codex','2026-01-01',1),('cs2','gemini','2026-02-01',1),"
        "('cs3','codex','2026-03-01',0)"
    )
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        f"('cm_u1','cs1','zcode','user',?),"          # eligible user
        f"('cm_a1','cs1','zcode','assistant',?),"     # eligible assistant
        f"('cm_a2','cs1','zcode','assistant',?),"     # [Bash] 前缀 → excluded_tool
        f"('cm_u2','cs1','zcode','user',?),"          # 内容重复 → excluded_dup
        f"('cm_u3','cs1','zcode','user',?),"          # 清洗后过短 → excluded_short
        f"('cm_g1','cs2','gemini','user',?),"         # eligible（第二 source）
        f"('cm_g2','cs2','gemini','assistant',?),"    # 仅注入残骸 → excluded_injection_only
        "('cm_x1','cs3','zcode','user','ineligible session 里的长用户消息内容超过三十字也不应出现')",
        (
            _LONG_USER,
            _LONG_ASSISTANT,
            _LONG_TOOL,
            _LONG_USER_DUP,
            _SHORT,
            _LONG_GEMINI_USER,
            _INJECTION_ONLY,
        ),
    )
    con.commit()
    con.close()
    return dest


def _make_unified_db(dest: Path) -> Path:
    con = sqlite3.connect(str(dest))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()
    return dest


def test_inspect_prepare_eligible_set_equal(tmp_path: Path) -> None:
    """Nyquist 用例 1：inspect current_refs == prepare after_hashes keys。"""
    canon = _make_canonical_db(tmp_path / "canon.db")
    unified = _make_unified_db(tmp_path / "unified.db")

    # inspect 路径（空 inventory baseline → new_refs 即 inspect 的当前 eligible 集合）
    inspect_result = find_affected_evidence(unified, canon, last_source_checksum="")
    inspect_refs = set(inspect_result["new_refs"])
    assert not inspect_result["deleted_refs"]

    # prepare 路径
    after_hashes, _meta = _current_eligible_ref_hashes(canon)
    prepare_refs = set(after_hashes)

    assert inspect_refs == prepare_refs
    assert inspect_refs == {"cm_u1", "cm_a1", "cm_g1"}
    # 红线：evidence_eligible=0 会话的消息永不出现
    assert "cm_x1" not in inspect_refs
    assert "cm_x1" not in prepare_refs


def test_role_decoupling(tmp_path: Path) -> None:
    """Nyquist 用例 2：roles 只决定返回哪些行，不影响单条 eligible 判定。"""
    canon = _make_canonical_db(tmp_path / "canon.db")

    full_items, _ = compute_eligible_messages(canon)
    user_items, _ = compute_eligible_messages(canon, roles=("user",))
    asst_items, _ = compute_eligible_messages(canon, roles=("assistant",))

    full_by_ref = {m.evidence_ref: m for m in full_items}
    # 并集 == 全量结果
    assert {m.evidence_ref for m in user_items} | {m.evidence_ref for m in asst_items} == set(full_by_ref)
    # roles=('user',) 只含 user 行
    assert all(m.role == "user" for m in user_items)
    assert all(m.role == "assistant" for m in asst_items)
    # 单条判定（content_hash / has_injection）不随 roles 参数改变
    for m in user_items:
        assert m == full_by_ref[m.evidence_ref]
    for m in asst_items:
        assert m == full_by_ref[m.evidence_ref]
    # ineligible session 在任何 roles 组合下都不出现
    assert "cm_x1" not in full_by_ref


def test_excluded_counts_present(tmp_path: Path) -> None:
    """stats 含 coarse_count + 四个排除计数键，数值与 fixture 构造相符。"""
    canon = _make_canonical_db(tmp_path / "canon.db")
    items, stats = compute_eligible_messages(canon)

    assert len(ASSISTANT_TOOL_PREFIX_PATTERNS) == 13
    for key in (
        "coarse_count",
        "excluded_short",
        "excluded_dup",
        "excluded_tool",
        "excluded_injection_only",
    ):
        assert key in stats, f"missing stats key: {key}"

    assert stats["coarse_count"] == 7  # ineligible session 在 SQL 层即被排除
    assert stats["excluded_short"] == 1
    assert stats["excluded_dup"] == 1
    assert stats["excluded_tool"] == 1  # assistant [Bash] 前缀行
    assert stats["excluded_injection_only"] == 1
    assert len(items) == 3
    assert all(m.role in ("user", "assistant") for m in items)


def test_alias_compat() -> None:
    """旧 import 路径（build_knowledge_units / build_knowledge_inventory）与
    eligibility 实现同一对象 / 同一输出。"""
    from personal_knowledge.application.knowledge import build_knowledge_inventory
    from personal_knowledge.application.knowledge import build_knowledge_units
    from personal_knowledge.application.knowledge import eligibility

    assert build_knowledge_units.strip_system_injections is eligibility.strip_system_injections
    assert build_knowledge_units.is_meaningful is eligibility.is_meaningful
    assert build_knowledge_units.SYSTEM_INJECTION_PATTERNS is eligibility.SYSTEM_INJECTION_PATTERNS
    assert build_knowledge_inventory.SYSTEM_INJECTION_PATTERNS is eligibility.SYSTEM_INJECTION_PATTERNS
    assert build_knowledge_inventory._strip_injections is eligibility.strip_system_injections
    assert build_knowledge_inventory._content_hash is eligibility.compute_content_hash

    sample = "<system-reminder>sr</system-reminder>真实内容超过三十个字的实际用户指令部分啊啊"
    assert build_knowledge_units.strip_system_injections(sample) == eligibility.strip_system_injections(sample)
    assert build_knowledge_inventory._strip_injections(sample) == eligibility.strip_system_injections(sample)
    assert build_knowledge_units.is_meaningful(sample) == eligibility.is_meaningful(sample)
