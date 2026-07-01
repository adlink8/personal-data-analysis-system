# Phase 04: 记忆层升级与服务收口 - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning
**Source:** Codex repo audit + GSD planning

<domain>
## Phase Boundary

本阶段聚焦三件事：

1. 把统合层的大scripts拆成可扩展的源适配器与规范对象层。
2. 把 CLI / MCP / REST 的重复逻辑收口到统一服务契约。
3. 在现有事件检索之上补一层“长期记忆对象”，让系统不仅能搜历史，还能沉淀稳定偏好、项目关系和工作模式。

本阶段不是“重写全仓库”，而是在保留当前可运行链路的前提下，对integration做可演进化改造。

</domain>

<decisions>
## Implementation Decisions

### 目录与建模
- integration后续应从“大scripts直出 SQLite”演进为“源适配器 -> 规范对象 -> 统合入库”的结构。
- `Google` / `GPT` / `Agent` 三个来源必须先映射为统一 `CanonicalEvent` / `CanonicalEntity`，再做跨源链接。
- 路径解析一律基于scripts文件位置，不再依赖 `Path.cwd()` 作为核心定位方式。

### 服务边界
- `unified_search.py` 继续作为唯一检索领域层，CLI / MCP / REST 不得各自复制查询、分类分布、参数规则和错误处理。
- MCP 与 HTTP 层只做 transport adapter，不再承载领域逻辑。
- 对外接口需要统一的请求/响应结构、分页与错误语义，避免不同入口行为漂移。

### 记忆层
- 当前“事件全文向量检索”不足以表达长期偏好和跨会话稳定事实，需要新增记忆对象层。
- 记忆对象至少区分：`event`、`preference`、`project`、`tooling`、`habit`、`fact`。
- 记忆关系至少支持：`same_project`、`uses_tool`、`prefers`、`caused_by`、`repeats_pattern`。
- 向量索引需要从“只索引 event 文本”升级为“event + memory object 双索引”或等价能力。

### 兼容性与迁移
- 现有 `personal_system.sqlite`、`personal_events` collection、`mcp_server.py`、`api_server.py` 不能被破坏式替换。
- 当前 README 中承诺的交互方式必须保持可用：CLI、MCP、REST API、dashboard。
- 本阶段允许新增表、模块、构建scripts和测试，但不允许要求用户先重做已有数据目录结构。

### the agent's Discretion
- 规范对象层用 dataclass、TypedDict 还是 pydantic，由实现时按依赖成本决定。
- 统一契约层用纯函数模块还是轻量 service class，由实现时按测试便利性决定。
- 记忆对象抽取规则先走规则/启发式还是先引入 LLM 抽取，由实现复杂度与可验证性决定。

</decisions>

<canonical_refs>
## Canonical References

### 当前统合入口
- `integration/scripts/build_integrated_system.py` - 现有统合构建入口，后续要拆出适配器与 integrator。
- `integration/scripts/build_vector_store.py` - 当前事件向量化构建入口，后续要支持记忆对象索引。

### 当前检索与服务层
- `integration/scripts/unified_search.py` - 当前统一检索后端，后续继续作为领域层核心。
- `integration/scripts/mcp_server.py` - 当前 MCP transport，后续应瘦身为契约适配层。
- `integration/scripts/api_server.py` - 当前 HTTP transport，后续应瘦身为契约适配层。

### 当前向量与 embedding 基础设施
- `integration/scripts/chroma_client.py` - 当前 Chroma REST 客户端。
- `integration/scripts/local_embed.py` - 当前本地 embedding 实现。

### 产品与架构说明
- `README.md` - 当前项目能力、接入方式、向量层与 MCP/REST 承诺。
- `integration/README.md` - 当前integration输入输出边界说明。

</canonical_refs>

<specifics>
## Specific Ideas

- 适配器重构优先拆 `rows_from_google`、`rows_from_gpt`、`rows_from_agent`，不要一开始就大规模改 SQL 语义。
- 统一契约层至少沉淀：`search_semantic`、`query_events`、`get_event_detail`、`stats`、`list_categories` 五类能力。
- 记忆层第一版优先做“规则生成 + 可回溯到原始事件”，暂不追求过度智能抽取。
- 评估是否新增 `memory_search` 能力，避免把稳定偏好和原始事件混在同一召回列表里。

</specifics>

<deferred>
## Deferred Ideas

- 暂不引入外部云向量库或远程记忆服务。
- 暂不把 dashboard 全量重写为新的信息架构，只做必要接入。
- 暂不做跨设备同步、OAuth、多用户隔离。
- 暂不把图推理升级成完整 GraphRAG 工作流，先把关系层和索引打稳。

</deferred>

---

*Phase: 04-memory-layer-upgrade*
*Context gathered: 2026-06-15 via repo audit and GSD planning*
