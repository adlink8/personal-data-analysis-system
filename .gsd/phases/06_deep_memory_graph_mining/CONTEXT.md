# Phase 06: 深层记忆图谱挖掘 - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning after Phase 05
**Source:** Phase 05 hardening plan + user decision that current graph is still too surface-level

<domain>
## Phase Boundary

Phase 06 的目标是把记忆图谱从“我用了什么、我关注什么”的浅层标签，推进到“长期模式、演化路径、关系强度、反例约束、可解释洞察”的深层图谱。

本阶段只在 Phase 05 通过后执行，尤其依赖：

1. memory item / relation 具备 evidence/confidence/last_seen/source_hash 等治理字段。
2. CLI/REST/MCP contract tests 已经锁住现有消费入口。
3. `memory_depth_readiness.md` 已明确哪些主题可以深挖、哪些主题证据不足。

</domain>

<decisions>
## Implementation Decisions

### Scope

- 深挖必须基于证据，不允许把单次出现或浅层共现包装成长期洞察。
- 所有洞察输出必须能回溯到 memory item、relation、原始事件或 source hash。
- 优先做本地、规则化、可重复的分析；LLM 只能作为可选摘要层，不作为事实生成源。
- 不引入完整 GraphRAG runtime；先做轻量 graph mining pipeline。

### Insight Types

Phase 06 重点挖以下类型：

- 时间演化：工具、兴趣、项目、能力如何随时间变化。
- 复现模式：哪些行为/关注点跨时间、跨项目重复出现。
- 关系强度：哪些实体关系稳定，哪些只是一次性共现。
- 能力形成路径：能力和工具、项目、主题之间如何互相支撑。
- 偏好冲突与反例：哪些记忆之间存在冲突、衰减或不再成立。
- 深层主题簇：把零散记忆聚成可解释主题，而不是只按 memory_type 分组。

### Safety and Quality

- 每条洞察需要 evidence count、time span、confidence、supporting items、contradictions。
- 输出中必须标注洞察等级：`strong`、`moderate`、`weak`、`unsupported`。
- `unsupported` 不进入 profile，只进入待补证据列表。
- 不把推测写入长期 memory store，除非后续有人工确认或证据链补足。

</decisions>

<canonical_refs>
## Canonical References

### Required Inputs

- `.gsd/phases/05_memory_layer_hardening/PLAN.md` — Phase 06 的前置补强和 readiness gate。
- `统合模块/分析数据/ai_context/memory_depth_readiness.md` — Phase 06 必须读取的准入报告。
- `统合模块/分析数据/personal_system.sqlite` — memory_items / memory_links / memory_relations 事实源。
- `统合模块/脚本/unified_search.py` — 现有 memory 查询入口。
- `统合模块/脚本/build_profile_from_memory.py` — 当前浅层 profile 生成器。

### Reference Research

- `.gsd/phases/04_memory_layer_upgrade/RESEARCH.md` — HPI/mem0/LangMem/mcp-memory-service/GraphRAG 借鉴方向。
- `.planning/codebase/EXTERNAL_ALIGNMENT.md` — 当前实现与外部项目逐项对齐。

</canonical_refs>

<specifics>
## Specific Ideas

- 新增 `统合模块/脚本/mine_deep_memory_graph.py`。
- 新增 `统合模块/脚本/build_deep_memory_profile.py`。
- 输出 `统合模块/分析数据/ai_context/deep_memory_insights.md`。
- 输出 `统合模块/分析数据/ai_context/deep_memory_profile.md`。
- 输出一份 JSON 机器可读结果，供后续 dashboard 或 agent prompt 使用。

</specifics>

<deferred>
## Deferred Ideas

- 完整 GraphRAG 社区摘要 pipeline。
- 自动把深层洞察写回长期 memory store。
- 可视化 dashboard。
- 多用户或远程共享记忆。

</deferred>

---

*Phase: 06-deep-memory-graph-mining*
*Context gathered: 2026-06-17*

