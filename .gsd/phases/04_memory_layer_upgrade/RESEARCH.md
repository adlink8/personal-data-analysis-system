# Phase 04 Research: Memory Layer Reference Projects

Status: Done
Date: 2026-06-17
Scope: HPI, mem0, LangMem, mcp-memory-service, Microsoft GraphRAG

## Research Question

Phase 04 已经完成本地记忆层的采集、图谱化和消费入口。这个研究回答三个问题：

1. 这些成熟项目里哪些模式值得借鉴或复用？
2. 哪些能力不应该现在引入，避免把个人数据系统过早平台化？
3. 当前仓库下一步应该先补哪三处？

## Standard Stack

当前仓库应继续保持轻量本地栈：

- Storage: SQLite 作为事实源和结构化记忆库。
- Vector: Chroma 作为语义检索层。
- Access: CLI + REST + MCP 三入口。
- Graph: SQLite relation table + NetworkX/可视化scripts，暂不引入图数据库。
- Extraction: 先规则化、可追溯抽取，再逐步增加 LLM 辅助归纳。

外部项目的可复用方向：

| Project | 可借鉴模式 | 不建议现在复用 |
| --- | --- | --- |
| HPI | 数据源 adapter 化；每类个人数据暴露稳定 Python 对象；把解析、缓存、错误隔离封装在 source module 内 | 不直接照搬其全量个人数据模块体系；当前仓库已有 Google/GPT/Agent 目录和统合管道 |
| mem0 | 用户/会话/agent 多层记忆；简单 API/CLI；记忆写入、搜索、召回分离 | 不迁移到外部托管/完整 mem0 服务；会削弱本地可控性 |
| LangMem | hot path 工具写入 + background memory manager；长期记忆与 LangGraph-style store 解耦 | 不把当前系统强绑定 LangGraph；先抽象接口 |
| mcp-memory-service | 单一 memory backend 暴露 REST/MCP/CLI/dashboard；多 agent 共享记忆；实体关系图 | 不开放远程 MCP/HTTPS/OAuth，除非先做认证、权限和脱敏 |
| GraphRAG | 从非结构文本抽取实体/关系，再用图记忆增强检索和回答；索引前先做 prompt tuning 和小样本验证 | 不直接引入完整 GraphRAG pipeline；索引成本和复杂度对当前阶段过高 |

## Architecture Patterns

### 1. HPI-style source modules

目标不是增加更多导入scripts，而是把现有scripts收敛成统一 adapter contract：

- `list_items()`: 返回稳定字段的原始事件或文档对象。
- `normalize()`: 转成 canonical event/entity。
- `provenance`: 每个输出必须带 source path、source type、timestamp/hash。
- `errors`: 单个 source 失败不阻断全局 pipeline。

这能降低当前 `run_pipeline.py` 中scripts顺序强耦合的问题。

### 2. mem0/LangMem-style memory tiers

当前 `memory_items` 已经初步区分 preference/context/capability/tooling 等类型。下一步应把语义层级明确成：

- Raw layer: 原始文件、聊天、代码、导入记录。
- Event/entity layer: 标准化事实、实体、时间线。
- Memory layer: 可被 agent 使用的长期偏好、能力、项目状态、工具经验。
- Profile layer: 面向消费的压缩画像，例如 `person_profile_v2.md`。

记忆写入也应分两条路径：

- Hot path: 用户显式触发、CLI/API/MCP 写入或查询。
- Background path: pipeline 批处理提取、去重、打分、归并。

### 3. mcp-memory-service-style service boundary

当前已经有 CLI/REST/MCP 三入口。后续不要让每个入口各自实现业务逻辑，应保持：

- `unified_search.py` 负责纯函数和核心查询。
- `api_server.py` 只做 HTTP 参数解析和 JSON 响应。
- `mcp_server.py` 只做 MCP tool schema 和结果包装。
- 所有入口共享同一套 memory query contract。

### 4. GraphRAG-style graph consumption

当前 `memory_relations` 适合做轻量 GraphRAG 前置层。下一步重点不是上复杂框架，而是补齐：

- entity/relation schema 稳定性。
- relation evidence 和 confidence。
- neighborhood query 的可解释输出。
- 对 profile 生成和 agent prompt 的可控上下文裁剪。

## Don't Hand-Roll

- 不手写 MCP 协议细节；继续使用现有 SDK/封装层。
- 不自建图数据库或复杂 graph engine；当前规模先用 SQLite relation table + NetworkX 足够。
- 不把 Chroma、SQLite、MCP、REST 全部抽象成可替换平台；先稳定当前本地系统。
- 不在没有 provenance/confidence 的情况下让 LLM 自动改写长期记忆。
- 不在本地个人数据系统上默认开放远程访问；如需远程 MCP，必须先补 auth、CORS、脱敏和审计。

## Common Pitfalls

- Adapter 膨胀：HPI 的强项是 source module 边界清晰，不是无限增加scripts。当前仓库应先统一接口，再扩数据源。
- Memory pollution：mem0/LangMem 类系统的关键风险是错误记忆长期污染。每条 memory 需要 evidence、confidence、last_seen、source。
- Transport drift：mcp-memory-service 的价值在于多入口共享同一 backend。当前 REST/MCP/CLI 需要契约测试防止漂移。
- Graph cost：GraphRAG 官方也提示索引可能昂贵。当前应先小样本验证抽取质量，再考虑完整图检索 pipeline。

## Recommended Reuse Backlog

### First 3 Changes

1. Define a memory adapter contract.
   - Add a small adapter interface/spec for source modules.
   - Acceptance: at least Google/GPT/Agent one类 source 能按统一字段导出 canonical records。

2. Add memory governance fields and tests.
   - Extend memory outputs with evidence/confidence/last_seen/source_hash where missing.
   - Acceptance: profile and neighbor query can explain why a memory exists。

3. Add CLI/REST/MCP contract tests.
   - Test the same subject/type query through all three transports.
   - Acceptance: output shape and count semantics remain aligned。

### Later

- Add background memory consolidation with explicit merge rules.
- Add graph neighborhood ranking for agent context packing.
- Add optional dashboard/HTML graph explorer.
- Evaluate GraphRAG only after relation extraction quality is measured.

## Source Notes

- HPI: https://github.com/karlicoss/HPI
- mem0: https://github.com/mem0ai/mem0
- LangMem: https://github.com/langchain-ai/langmem
- mcp-memory-service: https://github.com/doobidoo/mcp-memory-service
- Microsoft GraphRAG: https://github.com/microsoft/graphrag

