"""Phase 13.5 Wave 4.1：统一会话查询 repository。

把下游（conversation summary、integrated system、evidence bundle）的 agent
会话查询收口到一个 repository，支持 ``legacy|canonical`` 显式模式。

契约（PLAN Task 4.1）：
  - 首轮默认 ``legacy``，``--source canonical`` 做 shadow run；禁止静默双计数。
  - summary/source_ref 携带 canonical session/message ID 和原 source refs。
  - tool output 默认只显示 ``[tool output omitted]``，不拼入 LLM prompt。

两种数据源的统一查询接口：

  - ``legacy`` 模式：读 ``agent_data.sqlite`` 的 ``agent_messages`` /
    ``agent_tool_calls`` / ``agent_tool_outputs``
  - ``canonical`` 模式：读 ``agent_conversations.sqlite`` 的
    ``canonical_messages`` / ``canonical_tool_events``

用法::

    repo = ConversationRepository(source="canonical")
    for session in repo.iter_sessions():
        turns = list(repo.iter_turns(session["session_id"]))
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_DB,
    AGENT_CONVERSATIONS_DB,
)

SOURCE_LEGACY = "legacy"
SOURCE_CANONICAL = "canonical"
VALID_SOURCES = (SOURCE_LEGACY, SOURCE_CANONICAL)

TOOL_OUTPUT_OMITTED = "[tool output omitted]"


@dataclass(frozen=True)
class ConversationTurn:
    """统一会话 turn/message 表示。"""
    session_id: str        # canonical session ID 或 legacy session_id
    source: str            # 'legacy' | 'canonical'
    ordinal: int           # 消息顺序
    role: str              # user / assistant / developer / system / tool
    content: str           # 消息正文（eligible + 脱敏后）
    timestamp: str
    source_ref: str        # 原 source 的 message ref（回查用）
    source_session_ref: str  # 原 source 的 session ref
    is_system: bool = False
    is_sidechain: bool = False
    evidence_scope: str = "user"


@dataclass(frozen=True)
class ToolEvent:
    """统一工具事件表示（不含 input_json/result 全文）。"""
    session_id: str
    source: str
    tool_name: str
    category: str
    status: str
    call_index: int | None
    output_display: str  # 默认 [tool output omitted]
    timestamp: str
    source_ref: str


class ConversationRepository:
    """统一会话查询，显式 legacy|canonical 模式。

    不允许静默双计数：同一时刻只读一个 source。
    """

    def __init__(
        self,
        source: str = SOURCE_LEGACY,
        legacy_db: Path = AGENT_DB,
        canonical_db: Path = AGENT_CONVERSATIONS_DB,
    ) -> None:
        if source not in VALID_SOURCES:
            raise ValueError(f"source 必须是 {VALID_SOURCES}，得到 {source!r}")
        self.source = source
        self.legacy_db = legacy_db
        self.canonical_db = canonical_db

    @property
    def active_db(self) -> Path:
        return self.canonical_db if self.source == SOURCE_CANONICAL else self.legacy_db

    def _connect(self) -> sqlite3.Connection:
        db = self.active_db
        if not db.exists():
            raise FileNotFoundError(f"{self.source} 数据库不存在: {db}")
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    # --- legacy 模式查询 ---

    def _iter_legacy_sessions(self) -> Iterable[dict]:
        con = self._connect()
        try:
            for r in con.execute(
                "SELECT DISTINCT session_id, source, family, raw_file, "
                "timestamp, cwd, model FROM agent_sessions_meta "
                "ORDER BY session_id"
            ):
                yield dict(r)
        finally:
            con.close()

    def _iter_legacy_turns(self, session_id: str) -> Iterable[ConversationTurn]:
        con = self._connect()
        try:
            ordinal = 0
            for r in con.execute(
                "SELECT event_index, timestamp, role, text, raw_file, line_no "
                "FROM agent_messages WHERE session_id=? "
                "ORDER BY event_index",
                (session_id,),
            ):
                ordinal += 1
                role = (r["role"] or "assistant").lower()
                if role not in ("user", "assistant", "developer", "system", "tool"):
                    role = "assistant"
                yield ConversationTurn(
                    session_id=session_id,
                    source=SOURCE_LEGACY,
                    ordinal=ordinal,
                    role=role,
                    content=r["text"] or "",
                    timestamp=r["timestamp"] or "",
                    source_ref=f"legacy:{session_id}:{r['event_index']}",
                    source_session_ref=f"legacy:{session_id}",
                )
        finally:
            con.close()

    def _iter_legacy_tools(self, session_id: str) -> Iterable[ToolEvent]:
        con = self._connect()
        try:
            for r in con.execute(
                "SELECT call_id, tool_name, status, arguments FROM agent_tool_calls "
                "WHERE session_id=? ORDER BY call_id",
                (session_id,),
            ):
                yield ToolEvent(
                    session_id=session_id,
                    source=SOURCE_LEGACY,
                    tool_name=r["tool_name"] or "",
                    category="",
                    status=r["status"] or "",
                    call_index=None,
                    output_display=TOOL_OUTPUT_OMITTED,
                    timestamp="",
                    source_ref=f"legacy:{session_id}:{r['call_id']}",
                )
        finally:
            con.close()

    # --- canonical 模式查询 ---

    def _iter_canonical_sessions(self) -> Iterable[dict]:
        con = self._connect()
        try:
            for r in con.execute(
                "SELECT canonical_session_id, primary_source, agent, started_at, "
                "ended_at, message_count, evidence_eligible, evidence_scope "
                "FROM canonical_sessions ORDER BY started_at"
            ):
                yield dict(r)
        finally:
            con.close()

    def _iter_canonical_turns(self, canonical_session_id: str) -> Iterable[ConversationTurn]:
        con = self._connect()
        try:
            for r in con.execute(
                "SELECT canonical_message_id, source, source_message_ref, ordinal, "
                "role, content, timestamp, is_system, is_sidechain, evidence_scope "
                "FROM canonical_messages WHERE canonical_session_id=? "
                "ORDER BY ordinal",
                (canonical_session_id,),
            ):
                yield ConversationTurn(
                    session_id=canonical_session_id,
                    source=SOURCE_CANONICAL,
                    ordinal=r["ordinal"],
                    role=r["role"],
                    content=r["content"] or "",
                    timestamp=r["timestamp"] or "",
                    source_ref=r["source_message_ref"] or "",
                    source_session_ref=f"canonical:{canonical_session_id}",
                    is_system=bool(r["is_system"]),
                    is_sidechain=bool(r["is_sidechain"]),
                    evidence_scope=r["evidence_scope"],
                )
        finally:
            con.close()

    def _iter_canonical_tools(self, canonical_session_id: str) -> Iterable[ToolEvent]:
        con = self._connect()
        try:
            for r in con.execute(
                "SELECT canonical_tool_id, source, source_kind, tool_name, category, "
                "status, call_index, timestamp FROM canonical_tool_events "
                "WHERE canonical_session_id=? ORDER BY call_index",
                (canonical_session_id,),
            ):
                yield ToolEvent(
                    session_id=canonical_session_id,
                    source=SOURCE_CANONICAL,
                    tool_name=r["tool_name"] or "",
                    category=r["category"] or "",
                    status=r["status"] or "",
                    call_index=r["call_index"],
                    output_display=TOOL_OUTPUT_OMITTED,
                    timestamp=r["timestamp"] or "",
                    source_ref=r["canonical_tool_id"],
                )
        finally:
            con.close()

    # --- 统一公共接口 ---

    def iter_sessions(self) -> Iterable[dict]:
        """迭代所有 session（不含正文）。"""
        if self.source == SOURCE_LEGACY:
            yield from self._iter_legacy_sessions()
        else:
            yield from self._iter_canonical_sessions()

    def iter_turns(self, session_id: str) -> Iterable[ConversationTurn]:
        """迭代单个 session 的 turn/message（按 ordinal 排序）。"""
        if self.source == SOURCE_LEGACY:
            yield from self._iter_legacy_turns(session_id)
        else:
            yield from self._iter_canonical_turns(session_id)

    def iter_tools(self, session_id: str) -> Iterable[ToolEvent]:
        """迭代单个 session 的工具事件（output 默认 omitted）。"""
        if self.source == SOURCE_LEGACY:
            yield from self._iter_legacy_tools(session_id)
        else:
            yield from self._iter_canonical_tools(session_id)

    def session_count(self) -> int:
        """session 总数。"""
        con = self._connect()
        try:
            if self.source == SOURCE_LEGACY:
                return con.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM agent_sessions_meta"
                ).fetchone()[0]
            else:
                return con.execute(
                    "SELECT COUNT(*) FROM canonical_sessions"
                ).fetchone()[0]
        finally:
            con.close()

    def user_turn_count(self) -> int:
        """role=user 的 turn 数（用于 parity 比对）。"""
        con = self._connect()
        try:
            if self.source == SOURCE_LEGACY:
                return con.execute(
                    "SELECT COUNT(*) FROM agent_messages WHERE role='user'"
                ).fetchone()[0]
            else:
                return con.execute(
                    "SELECT COUNT(*) FROM canonical_messages WHERE role='user'"
                ).fetchone()[0]
        finally:
            con.close()

    def session_source_refs(self, session_id: str) -> list[dict]:
        """canonical 模式：返回该 canonical session 的所有 source lineage link。

        legacy 模式返回空（legacy 无 lineage）。
        """
        if self.source != SOURCE_CANONICAL:
            return []
        con = self._connect()
        try:
            return [
                dict(r) for r in con.execute(
                    "SELECT source, source_session_id, source_raw_file, "
                    "match_method FROM session_source_links "
                    "WHERE canonical_session_id=?",
                    (session_id,),
                )
            ]
        finally:
            con.close()
