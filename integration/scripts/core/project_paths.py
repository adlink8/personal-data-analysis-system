"""统一项目路径常量。

从 __file__ 派生，不依赖运行目录 (Path.cwd())。
所有脚本应从这里 import，而不是各自用 parents[N] 魔法数字。
"""
from __future__ import annotations
from pathlib import Path

# 项目根（integration/scripts/core/project_paths.py → parents[3] 是项目根）
# parents[0]=core  parents[1]=scripts  parents[2]=integration  parents[3]=root
ROOT = Path(__file__).resolve().parents[3]

INTEGRATION_DIR = ROOT / "integration"
DB_DIR = INTEGRATION_DIR / "db"
SCRIPTS_DIR = INTEGRATION_DIR / "scripts"
ANALYSIS_DIR = INTEGRATION_DIR / "analysis"
AI_CONTEXT_DIR = ANALYSIS_DIR / "ai_context"

# 常用数据库路径
UNIFIED_DB = DB_DIR / "personal_system.sqlite"
CONV_GRAPH_DB = DB_DIR / "conversation_graph.duckdb"

# 可回收归档（历史模块软归档，不删除；见 _recycle/README.md）
RECYCLE_DIR = ROOT / "_recycle"
RECYCLE_CLEANUP_20260712 = RECYCLE_DIR / "2026-07-12_structure_cleanup"

# 源数据库
# - Google：主树仍保留 structured/raw（可选导入源）
# - GPT：整模块已归档到 _recycle（路径指向归档，兼容旧脚本）
# - Agent：仅保留 structured/db（会话/知识证据主库）；raw/analysis 已归档
GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
GPT_DB = (
    RECYCLE_CLEANUP_20260712 / "GPT" / "structured" / "db" / "chatgpt_data.db"
)
AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"

SOURCE_DBS = {
    "Google": GOOGLE_DB,
    "GPT": GPT_DB,
    "Agent": AGENT_DB,
}

# Phase 13.5：AgentView 会话源（只读 live WAL，位于用户主目录）
# 这是 AgentView daemon 正在写入的库，任何连接都必须 mode=ro + query_only。
AGENTSVIEW_DB = Path.home() / ".agentsview" / "sessions.db"

# Phase 13.5：AgentView 规范化产物（安全快照，由 adapter 原子发布）
AGENT_STRUCTURED_DB_DIR = ROOT / "Agent" / "structured" / "db"
AGENTSVIEW_NORMALIZED_DB = AGENT_STRUCTURED_DB_DIR / "agentsview_normalized.sqlite"
AGENT_CONVERSATIONS_DB = AGENT_STRUCTURED_DB_DIR / "agent_conversations.sqlite"
