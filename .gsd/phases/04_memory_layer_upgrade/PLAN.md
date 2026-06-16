# Phase 04: 记忆层升级与服务收口

## 目标

在不破坏现有可运行链路的前提下，把统合模块从“能跑的脚本集合”提升为“可扩展的个人记忆平台底座”：

- 导入层可扩展
- 服务层行为一致
- 检索层从事件搜索升级为事件 + 记忆对象搜索

## 范围

- 重构统合构建入口，拆出来源适配器与规范对象层。
- 收口 CLI / MCP / REST 的公共契约与错误语义。
- 新增记忆对象层、关系层与索引层。
- 保持现有 README 承诺的入口继续可用。

## 不做

- 不重做 Google / GPT / Agent 的原始数据抓取逻辑。
- 不引入云端依赖或托管记忆服务。
- 不把 dashboard 整体重写成新产品。
- 不把 GraphRAG 做成独立大工程。

## Wave 1: 适配器化统合层

### 目标

把 `build_integrated_system.py` 从单文件统合脚本拆成可维护结构，为后续新增来源和记忆对象奠定底座。

### 任务

1. 新增 `统合模块/脚本/adapters/`，拆出 `google.py`、`gpt.py`、`agent.py`。
2. 新增规范对象定义模块，如 `schemas.py` 或 `models.py`，统一 `CanonicalEvent` / `CanonicalEntity` 字段。
3. 新增 `integrator.py`，负责合并事件、建实体、建连接、落库。
4. 把 `build_integrated_system.py` 改为 orchestrator，只负责编排与输出。
5. 去掉核心流程对 `Path.cwd()` 的依赖，统一使用基于 `__file__` 的路径解析。

### 验收

- `python 统合模块\脚本\build_integrated_system.py` 仍可生成 `personal_system.sqlite`。
- 原三源数据总量与关键核心表不发生明显回归。
- 新增第四来源时，不再需要修改单个超大脚本的主体结构。

## Wave 2: 统一服务契约

### 目标

让 `CLI / MCP / REST` 三个入口共用一套能力定义、参数规则和错误语义，避免入口间行为漂移。

### 任务

1. 抽出服务契约层，如 `service_contract.py` 或 `service_api.py`。
2. 抽出公共能力目录：`search_semantic`、`query_events`、`get_event_detail`、`stats`、`list_categories`。
3. 统一分页、limit 上限、source/category 参数校验、空结果和错误格式。
4. 让 `mcp_server.py` 与 `api_server.py` 只做 transport adapter。
5. 补最小 smoke tests，覆盖 MCP/HTTP 对核心能力的调用一致性。

### 验收

- 同一查询在 CLI / MCP / REST 的结果字段和过滤语义一致。
- `list_categories` 不再在多个入口重复实现。
- transport 层代码显著变薄，领域逻辑集中在后端模块。

## Wave 3: 记忆对象层与双索引

### 目标

把“检索历史事件”升级为“检索长期记忆”，让系统能表达偏好、项目、工具使用模式和稳定事实。

### 任务

1. 在 `personal_system.sqlite` 新增 `memory_items`、`memory_links`、`memory_profiles` 或等价结构。
2. 基于现有事件与实体，生成第一版记忆对象：
   - preference
   - project
   - tooling
   - habit
   - fact
3. 为记忆对象建立可追溯关系，确保每条记忆都能回到原始事件证据。
4. 扩展 `build_vector_store.py`，支持记忆对象索引。
5. 在 `unified_search.py` 增加记忆检索入口，或新增独立 `memory_search` 能力。

### 验收

- 系统不只返回原始事件，还能返回稳定记忆对象。
- 每条记忆对象可追溯到事件证据。
- 向量层可同时支持事件与记忆对象检索。

## Wave 4: 验证与文档收口

### 目标

把架构升级结果固化到文档与验证脚本，防止后续再次漂移。

### 任务

1. 为导入构建、服务契约、记忆对象索引分别补 smoke tests。
2. 更新 `README.md` 的统合构建、统一检索、MCP、REST、向量层说明。
3. 更新 `统合模块/README.md`，补新目录结构和新表结构。
4. 输出一份迁移说明，说明旧接口未破坏、哪些能力是新增的。

### 验收

- README 与代码边界一致。
- 新增验证可在本地复现核心路径。
- 用户能从文档看懂“事件层”和“记忆层”的差别。

## 风险

- 大脚本拆分时容易引入字段兼容性回归。
- 服务契约收口时，若不先定义边界，可能只是把重复代码换个地方堆。
- 记忆对象抽取如果过度依赖启发式，可能得到大量低价值噪声。

## 实施顺序

1. 先做 Wave 1，确保底层结构能承载后续改造。
2. 再做 Wave 2，压住服务层漂移。
3. 再做 Wave 3，把“个人数据仓库”推进到“个人记忆系统”。
4. 最后做 Wave 4，补验证与文档。

## 成功标准

- 统合模块从单脚本结构升级为可扩展模块结构。
- 三个服务入口共享同一套契约与行为。
- 系统具备第一版长期记忆对象与双索引能力。
- 文档、代码、验证三者口径一致。
