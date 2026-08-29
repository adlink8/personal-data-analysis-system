# 语义层接线说明（SEMANTIC-WIRING）

> **状态：已接入（2026-08-29）。**
> - MCP stdio 工具：`search_semantic_cards`（CORE profile，只读检索；query + top_k）。
>   挂点：`src/personal_knowledge/mcp_tools/tool_definitions.py`（CORE_TOOL_NAMES + ALL_TOOLS schema）、
>   `src/personal_knowledge/mcp_tools/handlers/data.py`（TOOL_NAMES + render 分支，渲染在
>   `handlers/_format.py:_format_semantic_cards`）。server 层零改动，`handlers/__init__.py`
>   按 TOOL_NAMES 自动路由（已验证）。
> - REST：`POST /search/cards`（body 传 `query`+可选 `limit`/`top_k` 检索；传 `session_id`
>   返回单卡详情，未命中 404，缺参 400）。挂点：`src/personal_knowledge/services/api_server.py`
>   （do_POST 分支 + 文件头路由注释 + 启动横幅）、
>   `src/personal_knowledge/services/http/handlers/data.py:handle_search_cards`。
> - 契约测试：`tests/contract/test_semantic_cards_wiring.py`（夹具库，零 LLM/零网络）。
> - 向量层已接入（2026-08-29）：`search_cards` 升级为向量优先、失败回退关键词，
>   详见下方「向量层已接入」一节。
> - 管线脚本已出 tmp：`tools/semantic/mvp_semantic_compress.py`（报告/清单等运行数据仍在 tmp/）。
> - 未做：`get_card` 的 MCP 侧独立详情工具（按"保持最小"暂缓，REST 已覆盖详情）、
>   证据 refs 二次跳转（evidence.py 接口未确认）。以下为接线时的挂点勘察原文（行号以当时为准）。

**日期:** 2026-08-29  **范围:** 只描述挂点，不改在役代码。
MVP 语义层（`var/db/semantic_mvp_v3.sqlite`：173 会话卡 + 1,037 ku_facts）的检索适配器已落在
`src/personal_knowledge/retrieval/semantic_cards.py`（`open_cards_db` / `search_cards(query, limit=8)` /
`get_card(session_id)`，纯 sqlite 关键词打分，只读）。它目前是独立模块，尚未接入任何在役入口；
未来接入下面两个正式入口时按此接线。KU 升格导出器 `tools/semantic/export_ku_staging.py`
产出的 `var/db/semantic_ku_staging.sqlite` 同理属 staging，不接 canonical。

## (a) MCP stdio `rag-mcp` 加一个工具

- **工具 schema**：`src/personal_knowledge/mcp_tools/tool_definitions.py`
  — 在 `CORE_TOOL_NAMES`（:18 起的 frozenset，`search_semantic` 在 :19）加工具名，
  并在 `ALL_TOOLS` 里仿 `types.Tool(name="search_semantic", ...)`（:85）加一条
  `inputSchema={query: string, top_k: int}`。profile 过滤走现成的 `active_tools()`，无需新机制。
- **分派 handler**：`src/personal_knowledge/mcp_tools/handlers/data.py`
  — 把工具名加进本域 `TOOL_NAMES` frozenset（:29），再在 `render()` 里加
  `if name == "search_semantic_cards":` 分支（参照 :56 的 `search_semantic` 分支），
  进程内直调 `personal_knowledge.retrieval.semantic_cards.search_cards(query, limit=top_k)`，
  用同文件已有的 `_format_*` 风格渲染文本。
- **server 层零改动**：`services/mcp_server.py` 的 `handle_call_tool`（:120）只调
  `mcp_tools/handlers/__init__.py:render_tool`（:45），后者按各域 `TOOL_NAMES` 自动构建
  `TOOL_TO_HANDLER` 路由——只要上面两处注册了名字，server 自动可达；
  出口已有 `guard_mcp_payload` 隐私扫描兜底。

## (b) REST `/search` 面加路由

- **路由分支**：`src/personal_knowledge/services/api_server.py` 的 `do_POST`（:628 起）
  — 仿 ：670 的 `if path == "/search/semantic": data_handlers.handle_search_semantic(self, ctx)`
  加一条 `if path == "/search/cards": data_handlers.handle_search_cards(self, ctx)`。
- **handler**：`src/personal_knowledge/services/http/handlers/data.py`
  — 仿 `handle_search_semantic`（:221，进程内调 `api_server.backend.search_knowledge_units`）
  加 `handle_search_cards`，进程内直调 `semantic_cards.search_cards/get_card`，
  响应经 `api_server._ok(...)` 封装（错误走 `_err`）。
- **契约注释同步**：`api_server.py` 文件头路由注释（:19-20）与启动横幅（:721 附近）
  各补一行，保持文档与路由一致。

## 顺带说明

- 检索层惯例是进程内直连（MCP `search_semantic` 已从 HTTP 回环改为直调 backend），
  `semantic_cards` 的三个公开函数即为此设计的接口；向量检索（Chroma）接入后只换内部实现，
  挂点与调用方不变。
- `get_card` 返回的证据 refs（`v2|cm|<hex>` = canonical_message_id）可用现有
  `retrieval/evidence.py` 的证据解析能力做二次跳转（未验证接口名，接线时确认）。

## 向量层已接入（2026-08-29）

`search_cards` 已从纯关键词升级为**向量优先、失败无声回退关键词**；`get_card`
不动，两个公开接口的签名与返回形状不变，摘要行在原字段外附
`meta={"mode": "vector"|"keyword"}` 标注实际路径（调用方零改动）。

- **构建脚本**：`tools/semantic/build_semantic_vector_store.py`
  （`--dry-run` 默认 / `--write` 真建 / `--activate` 建后即激活）。
  文档集 = active ku_facts（id `f|<fact_key>`）+ 全部 session_cards
  （id `c|<session_id>`），文本经 `guard_text`，本次共 1,182 文档、512 维。
- **collection**：`semantic_mvp_v1_<UTC时间戳>`（版本化，每次构建新版本，旧版本
  保留不删；当前 active：`semantic_mvp_v1_20260829103652`）。
- **登记文件**：`var/db/semantic_index_registry.json`
  （`{"builds":[{build_id, collection, docs, dim, model, embedding_policy,
  chroma_endpoint, status, created_at}]}`；status ∈ candidate|active|superseded，
  active 至多一个）。检索层据此发现 active build。**不写** canonical 的
  `knowledge_index_versions`——该表外键依赖正式 build_runs，语义 MVP 产物尚未走
  KU 程序转正；转正后由正式管线登记 canonical 版本表。
- **embed 模型与路径约定**：本机模型 bge-small-zh-v1.5（512 维，
  `personal_knowledge.core.local_embed`），不联网。运行构建脚本与向量检索都要求
  环境变量 `PERSONAL_DATA_EMBED_MODEL_PATH` 指向模型目录（本机约定
  `D:\models\bge-small-zh-v1.5`）；构建脚本内部已 `setdefault` 该值，检索侧由
  调用环境提供（未设置时模型不可用 → 自动回退关键词）。
- **向量打分**：cosine 距离 d → 相似度 max(0, 1-d)，同会话取最大相似度聚合；
  取回邻居数 = limit×4；fact 类命中计入 `fact_hits`/`matched_facts`，
  `purpose` 由 sqlite 会话卡回填。
- **回退行为**：无登记/无 active build、chroma 不可达、集合缺失、模型缺失等
  任何一步失败 → 无声回退关键词路径（行为与升级前完全一致），meta 标
  `mode: 'keyword'`。测试默认通过 `tests/conftest.py` 的 autouse 夹具把登记
  指向不存在路径，保证离线测试确定性；真实环境冒烟见
  `tests/unit/test_semantic_cards_vector.py`（skipif + live 标记）。
- **遗留一**：chroma 容器（novel-mind-chroma-1，127.0.0.1:8001）目前借用
  novel-mind 的 docker compose，正式栈应有自己的 compose 条目。
- **遗留二**：`core/runtime_config.py` 的默认 embedding 模型候选路径指向残缺的
  C 盘缓存，导致不设 `PERSONAL_DATA_EMBED_MODEL_PATH` 时向量路径必然回退；
  修复默认路径后可消除该环境变量要求。
