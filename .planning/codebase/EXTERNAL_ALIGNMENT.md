# External Project Alignment

Status: Current as of 2026-06-17
Scope: Phase 04 memory layer implementation vs HPI, mem0, LangMem, mcp-memory-service, GraphRAG

## Current Local Baseline

当前仓库已经具备一个本地优先的个人数据和记忆层：

- `integration/scripts/run_pipeline.py`: 12-step pipeline，包含 integrated system、vector index、memory store、memory graph、profile v2 生成。
- `integration/scripts/unified_search.py`: 统一搜索、记忆画像、subject 关系、neighbor 查询。
- `integration/scripts/api_server.py`: REST 查询入口，包含 `/memory` 和 `/memory/<subject>`。
- `integration/scripts/mcp_server.py`: MCP 查询入口，包含 `get_memory_profile` 和 `get_memory_by_subject`。
- `integration/scripts/build_profile_from_memory.py`: 从 `memory_items` 与 `memory_relations` 生成 agent 可消费画像。
- `integration/analysis/personal_system.sqlite`: 本地事实源，当前已有 `memory_items`、`memory_links`、`memory_relations` 等表。

## Alignment Matrix

| Reference | External pattern | Current implementation | Gap | Recommendation |
| --- | --- | --- | --- | --- |
| HPI | 每类个人数据通过 Python module 暴露稳定对象；隐藏路径、解析、缓存、错误处理 | 当前按 Google/GPT/Agent/integration分目录，pipeline 串联多个scripts | 缺少统一 source adapter contract；scripts间字段约定隐含在实现中 | 先定义 adapter spec，再逐步改造 1-2 个高价值数据源 |
| mem0 | 通用 agent memory layer；User/Session/Agent 多层记忆；API/SDK/CLI 搜索与写入 | 已有 preference/context/capability/tooling 等 memory 类型，CLI/REST/MCP 可查 | 缺少明确的层级语义、写入准入、冲突合并和污染控制 | 增加 memory governance 字段和合并规则，不迁移到外部服务 |
| LangMem | hot path memory tools + background manager；长期记忆与 agent runtime 解耦 | 当前偏 batch pipeline，消费入口已补齐 | 缺少 hot path 写入/更新工具；background consolidation 规则还不显式 | 先增加只读契约测试，再设计可审计的写入/更新工具 |
| mcp-memory-service | 单 memory backend 同时服务 REST/MCP/CLI/dashboard；支持多 agent 共享与图关系 | 当前已有同一 SQLite backend + CLI/REST/MCP；已有 relation 查询 | 入口契约缺少自动测试；无 dashboard；远程安全边界未定义 | 保持 localhost 默认；补 CLI/REST/MCP contract tests；dashboard 放后续 |
| GraphRAG | 从非结构文本抽取实体关系，用知识图谱增强检索和回答 | 当前已有 `memory_relations` 和 neighbor query，可作为轻量 graph memory | 没有完整图索引、社区摘要、prompt tuning、图检索评估 | 不引入完整 GraphRAG；先评估现有 relation 质量和上下文裁剪效果 |

## What To Borrow

### Borrow Now

- HPI 的 source module 边界：每个数据源单独解析、单独失败、统一输出。
- mem0 的 memory levels：区分 user/session/project/tooling/capability，而不是只按表名堆数据。
- LangMem 的 hot/background split：批处理生成长期记忆，交互路径只做可审计的查询或显式写入。
- mcp-memory-service 的 one-backend-many-transports：CLI/REST/MCP 不重复业务逻辑。

### Borrow Later

- mcp-memory-service 风格 dashboard。
- GraphRAG 风格社区摘要、全局/局部图检索。
- mem0/LangMem 风格自动记忆更新，但必须先有 evidence/confidence/merge policy。

### Do Not Borrow Yet

- 外部托管记忆服务。
- 远程开放 MCP server。
- 完整 GraphRAG indexing pipeline。
- 强绑定 LangGraph runtime。

## First 3 Codebase Changes

### 1. Adapter Contract

Problem: 当前导入/统合scripts可以工作，但边界靠约定维持。继续增加数据源会提高漂移风险。

Change:

- 新增 `integration/scripts/source_adapters/` 或等价轻量目录。
- 定义最小 canonical record 字段：`source_type`、`source_id`、`title`、`content`、`created_at`、`updated_at`、`metadata`、`source_path`、`source_hash`。
- 先迁移一个最稳定 source 作为样例，不做全量重构。

Acceptance:

- pipeline 仍能 dry-run。
- 样例 adapter 有最小单元测试或scripts级 smoke test。

### 2. Memory Governance

Problem: 当前记忆可查询，但长期记忆需要解释来源和置信度，否则会污染 agent 上下文。

Change:

- 标准化 memory item metadata：`evidence_ids`、`confidence`、`last_seen`、`source_hash`、`merge_key`。
- profile 生成时展示关键 evidence，而不是只输出结论。
- relation 查询返回 relation confidence 和 evidence 摘要。

Acceptance:

- `python integration\scripts\unified_search.py memory --subject Codex --neighbors 1` 能解释关键关系来源。
- `person_profile_v2.md` 中关键偏好/能力有来源字段。

### 3. Transport Contract Tests

Problem: Phase 04 新增 CLI/REST/MCP 消费入口后，最容易出现入口漂移。

Change:

- 增加一个轻量测试scripts或 pytest：同一查询分别走核心函数、CLI、REST、MCP schema 层。
- 至少覆盖 `memory type` 和 `subject neighbors` 两类查询。

Acceptance:

- 本地一条命令可验证三入口返回 shape 一致。
- 后续修改 `unified_search.py`、`api_server.py`、`mcp_server.py` 时能及时发现漂移。

## Documentation Drift To Fix

`.planning/codebase` 里已有基础地图，但部分数字会随 Phase 04 Wave 5 变化：

- REST endpoint 数量已经增加。
- MCP tool 数量已经增加。
- pipeline 已从 11 步变为 12 步。

建议后续单独刷新 `ARCHITECTURE.md`、`INTEGRATIONS.md`、`TESTING.md`，不要在本对齐文档里静默覆盖旧审计口径。

## Source References

- HPI: https://github.com/karlicoss/HPI
- mem0: https://github.com/mem0ai/mem0
- LangMem: https://github.com/langchain-ai/langmem
- mcp-memory-service: https://github.com/doobidoo/mcp-memory-service
- Microsoft GraphRAG: https://github.com/microsoft/graphrag

