"""MCP handlers 包：按域拆分的 tool 调用逻辑。

每个子模块暴露：
- TOOL_NAMES: 本域负责的工具名集合
- render(name, arguments) -> str: 执行工具并返回 AI 友好文本
以及该域对应的 *tool_contract 适配器（供 services/mcp_server.py 与测试 import）。

顶层 _format / _json_contract / _event_contract_args 由 _format 提供，
services/mcp_server.py 会原样 re-export 以兼容旧 import 名。

注意：父包 personal_knowledge/mcp/ 刻意不带 __init__.py，作为 namespace
子包存在。原因：仓库内多个模块会 `sys.path.insert(0, src/personal_knowledge)`
做脚本路径 bootstrap；若 mcp/ 是常规包，顶层 `import mcp` 会命中它从而遮蔽
真正的 MCP SDK（site-packages/mcp），导致 `from mcp.server import Server`
报 ModuleNotFoundError。namespace 子包在 sys.path 优先命中时只是 namespace
portion，site-packages 里的常规包 mcp 仍会胜出，保证 SDK 导入不被破坏。
"""

from __future__ import annotations

import personal_knowledge.mcp.handlers.agent as agent
import personal_knowledge.mcp.handlers.data as data
import personal_knowledge.mcp.handlers.decision as decision
import personal_knowledge.mcp.handlers.intelligence as intelligence
import personal_knowledge.mcp.handlers.orchestration as orchestration
import personal_knowledge.mcp.handlers.proactive as proactive

# 统一分派表：工具名 -> 处理函数
HANDLERS = {
    "data": data,
    "intelligence": intelligence,
    "decision": decision,
    "proactive": proactive,
    "agent": agent,
    "orchestration": orchestration,
}

# 工具名 -> 所属域。分派按此路由到对应 handler.render。
TOOL_TO_HANDLER: dict[str, str] = {}
for _domain, _handler in HANDLERS.items():
    for _name in _handler.TOOL_NAMES:
        TOOL_TO_HANDLER[_name] = _domain

# 汇总所有工具名（供快速判断是否已知工具）
ALL_TOOL_NAMES = frozenset(TOOL_TO_HANDLER)


def render_tool(name: str, arguments: dict) -> str:
    """分派单个 MCP tool 调用到对应域 handler；未知名返回"未知工具"。"""
    domain = TOOL_TO_HANDLER.get(name)
    if domain is None:
        return f"未知工具: {name}"
    return HANDLERS[domain].render(name, arguments)


__all__ = [
    "agent",
    "data",
    "decision",
    "intelligence",
    "orchestration",
    "proactive",
    "HANDLERS",
    "TOOL_TO_HANDLER",
    "ALL_TOOL_NAMES",
    "render_tool",
]
