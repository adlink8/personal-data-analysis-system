<!-- generated-by: gsd-doc-writer -->
# 语义会话卡检索使用指南

本文描述"语义会话卡"检索面的使用方式：数据是什么、从哪些入口查、检索引擎如何工作、结果长什么样、常见问题怎么排查。

核心实现：[`src/personal_knowledge/retrieval/semantic_cards.py`](../../src/personal_knowledge/retrieval/semantic_cards.py)——对 MVP 语义压缩产物库 `var/db/semantic_mvp_v3.sqlite`（`session_cards` 会话卡 + `ku_facts` 事实，只读，绝不写库）的检索适配器。检索策略为**向量优先、失败无声回退关键词**，两个公开接口签名不变：

- `search_cards(query, limit=8)`：检索，返回按分排序的摘要行
- `get_card(session_id)`：单张完整会话卡 + active 事实

背景与挂点勘察见 [`.planning/codebase/SEMANTIC-WIRING.md`](../../.planning/codebase/SEMANTIC-WIRING.md)；运行配置（embedding 模型路径、Chroma 端点）见[配置参考](../configuration/overview.md)。

## 1. 两个消费入口

检索面有两个正式消费入口，均为**进程内直连** `semantic_cards`（不经 HTTP 回环），另有 CLI 供快速人工使用（见第 4 节）。

### 1.1 MCP stdio 工具 `search_semantic_cards`

- 注册于 [`src/personal_knowledge/mcp_tools/tool_definitions.py`](../../src/personal_knowledge/mcp_tools/tool_definitions.py) 的 `CORE_TOOL_NAMES`（core profile 默认暴露；`PERSONAL_DATA_MCP_PROFILE=full` 亦包含），`ALL_TOOLS` 中带完整 JSON Schema。
- 参数：`query`（必填，关键词查询，如 `AI-Memory`、`Dockerfile 代理`）、`top_k`（返回条数，默认 8，1–20）。
- 分派：[`src/personal_knowledge/mcp_tools/handlers/data.py`](../../src/personal_knowledge/mcp_tools/handlers/data.py) 的 `render()` 分支，进程内直调 `semantic_cards.search_cards(query, limit=top_k)`；渲染在 [`handlers/_format.py`](../../src/personal_knowledge/mcp_tools/handlers/_format.py) 的 `_format_semantic_cards`（AI 友好文本：编号 + score + 会话 id 缩写 + 目的 + 命中事实）。
- MCP 服务启动：`rag-mcp`（即 `python -m personal_knowledge.services.mcp_server`，stdio 传输）。

注意：MCP 面目前只暴露检索（`search_cards`）；`get_card` 单卡详情暂未做成独立 MCP 工具（按"保持最小"暂缓，REST 已覆盖详情，见 SEMANTIC-WIRING 的"未做"清单）。

### 1.2 REST `POST /search/cards`

- 路由分支：[`src/personal_knowledge/services/api_server.py`](../../src/personal_knowledge/services/api_server.py) `do_POST` 的 `if path == "/search/cards"`（文件头路由注释与启动横幅各有一行契约说明）。
- Handler：[`src/personal_knowledge/services/http/handlers/data.py`](../../src/personal_knowledge/services/http/handlers/data.py) 的 `handle_search_cards`。
- API 服务启动：`rag-api`（即 `python -m personal_knowledge.services.api_server`，默认监听 `127.0.0.1:8000`）。

请求体三种语义：

| body | 行为 |
|------|------|
| `{"query": "...", "limit": 8}`（或 `top_k`） | 检索模式，返回摘要行数组；limit/top_k 缺省 8 |
| `{"session_id": "v2\|cs\|<hex>"}` | 详情模式，返回单张完整会话卡 + active facts（含 evidence_refs） |
| 两者都缺 | 400，错误信息 `缺少 query 或 session_id 参数` |

响应经 `api_server._ok(...)` 封装为 `{"ok": true, "data": ...}`（数据过 privacy guard 封存扫描）；错误为 `{"ok": false, "error": "<safe msg>"}`。详情模式下单卡不存在返回 **404**（`未找到 session_id=...`）；缺参返回 **400**。

### 1.3 会话 id 格式与缩写

`session_id` 形如 `v2|cs|<32位hex>`。展示时常用缩写 `cs:<前12位hex>`（`semantic_cards.abbrev_sid`，MCP 渲染同规则）。

## 2. 检索引擎

### 2.1 向量路径（mode=vector）

`search_cards` 优先走 Chroma 向量检索，启用需同时满足：

1. **登记文件存在且含 active build**：`var/db/semantic_index_registry.json`（由构建脚本维护），结构 `{"builds": [{build_id, collection, docs, dim, model, embedding_policy, chroma_endpoint, created_at, status}]}`，`status ∈ candidate|active|superseded`，active 至多一个；
2. **Chroma 可达**：端点取自 active build 的 `chroma_endpoint`（当前为 `http://127.0.0.1:8001`；客户端默认端点硬编码在 [`core/chroma_client.py`](../../src/personal_knowledge/core/chroma_client.py)，REST API v2，会话禁用系统代理）；
3. **集合存在**：active build 声明的 collection 在 Chroma 中真实存在；
4. **本机 embedding 模型可用**：环境变量 `PERSONAL_DATA_EMBED_MODEL_PATH` 指向 `bge-small-zh-v1.5` 模型目录（512 维，本地计算不联网；见 [`core/local_embed.py`](../../src/personal_knowledge/core/local_embed.py)）。

打分：Chroma cosine 距离 `d` → 相似度 `max(0, 1-d)`，**同一会话取最大相似度聚合**；每条查询取回 `limit × 4` 个邻居；`kind=fact` 的命中计入 `fact_hits` 并把事实文本放进 `matched_facts`（摘要行只留前 2 条）；`purpose` 不在向量 metadata 里，统一从 sqlite 会话卡回填。

任一步失败都**无声回退**关键词路径，不抛错、不中断调用方。

### 2.2 关键词路径（mode=keyword）

纯标准库 sqlite（只读 `mode=ro` 打开，无 FTS）：

- **分词**：ASCII 标识符复用管线同款正则 `[A-Za-z_][A-Za-z0-9_\-.\\/]{3,}`（最短 4 字符，取全词）；中文取连续 CJK 段的 2-gram（单字段落为单字）。
- **打分**：SQL LIKE 预筛候选，Python 精确计命中数后按字段权重加权：

  | 字段 | 权重 | 说明 |
  |------|------|------|
  | `ku_facts.fact` | 4 | 人工最凝练的可长期成立事实 |
  | `session_cards.purpose` | 3 | 80 字内的会话目的 |
  | `session_cards.summary_md` | 2 | 300 字内纪要 |
  | `session_cards.card_json` | 1 | 原始卡全文，仅兜底 |

- 事实命中按 `session_id` 归并到所属会话卡；只统计 `status='active'` 的事实（`superseded` 是历史版本，不进检索面）。仅事实命中的会话（卡字段零命中）也会进入结果，`purpose` 为 `null`。

### 2.3 mode 标注与测试确定性

摘要行统一附 `meta={"mode": "vector"|"keyword"}`，标注本次实际走的路径；调用方（MCP/REST）零改动。测试侧，[`tests/conftest.py`](../../tests/conftest.py) 的 autouse 夹具把登记路径 monkeypatch 到不存在位置，**所有测试强制走 keyword**，不依赖真实 Chroma 与模型；向量路径的真实环境冒烟在 `tests/unit/test_semantic_cards_vector.py`（skipif + live 标记），接线契约在 `tests/contract/test_semantic_cards_wiring.py`（夹具库，零 LLM 零网络）。

## 3. 数据契约

### 3.1 `search_cards` 摘要行

```json
{
  "session_id": "v2|cs|00086e9ac8b99fcc4fe46a6daceffa7c",
  "purpose": "会话目的文本（仅事实命中时为 null）",
  "score": 0.735,
  "fact_hits": 2,
  "matched_facts": ["命中事实原文（最多 2 条）"],
  "meta": {"mode": "vector"}
}
```

`score` 的量纲随 mode 变化（见第 6 节已知限制）：vector 模式为 0–1 的余弦相似度（CLI 显示 3 位小数），keyword 模式为加权命中数（CLI 显示 1 位小数）。

### 3.2 `get_card` 详情

`session_id, purpose, summary_md, card（card_json 解析后的原始卡对象）, n_messages, truncated, model, input_tokens, output_tokens, created_at, chunk_count`，外加 `facts` 数组——每条 `{fact_key, fact, evidence_refs, confidence, valid_from, supersedes, status}`（仅 active，按 `valid_from, fact_key` 排序；`evidence_refs` 已从 JSON 字符串解析为列表）。无卡返回 `null`（REST 转为 404）。

### 3.3 `evidence_refs` 与原文下钻

每条事实的 `evidence_refs` 是形如 `["v2|cm|748a534a0f7525fa4f0938d3497f4672"]` 的引用列表，前缀 `v2|cm|` + hex 即 **canonical_message_id**，可直接 join 会话库下钻原文：

```sql
-- 库：data/canonical/agent/structured/db/agent_conversations.sqlite
select role, timestamp, content from canonical_messages
where canonical_message_id = 'v2|cm|748a534a0f7525fa4f0938d3497f4672';
```

`canonical_messages` 表含 `canonical_message_id, canonical_session_id, source, ordinal, role, content, timestamp` 等列。管线在压缩时已校验 refs 指向真实送入模型的消息 id（并修复模型丢失 `v2|cm|` 前缀的裸 hex，见 `tools/semantic/mvp_semantic_compress.py` 的 `normalize_refs`）。注：检索模块本身暂未封装"refs 二次跳转"接口，需自行 join（SEMANTIC-WIRING 遗留项）。

## 4. CLI 快速用法

```powershell
# 默认：向量优先，失败回退关键词
python -m personal_knowledge.retrieval.semantic_cards "Dockerfile 代理"

# 强制关键词打分（不碰 Chroma/模型）
python -m personal_knowledge.retrieval.semantic_cards "AI-Memory" --mode keyword

# 其它参数
python -m personal_knowledge.retrieval.semantic_cards "查询词" --limit 8 --db var/db/semantic_mvp_v3.sqlite
```

输出首行标注实际路径（`mode=vector 共 N 条` / `mode=keyword 共 N 条`），随后每行 `编号. score=… f=<fact_hits> <会话id缩写> <purpose 前 60 字>`。`--mode` 取值 `auto`（默认，向量优先）| `keyword`（强制关键词）。

## 5. 常见问题

### 5.1 为什么结果里 `mode` 是 `keyword`？

向量路径任一环节失败都会无声回退。按代码（`semantic_cards._vector_search`）逐一排查：

1. **登记文件缺失/损坏/无 active build**：看 `var/db/semantic_index_registry.json` 是否存在、能否解析、`builds` 里是否有一条 `status=active` 且带 `collection`。测试环境走的就是这条路（conftest 夹具故意指空）。
2. **Chroma 不可达**：容器 `novel-mind-chroma-1`（宿主 8001 → 容器 8000，本机 Chroma 服务 `127.0.0.1:8001`）没启动。该容器借用 novel-mind 项目的 compose，**不在本仓库内**；用 `docker ps --filter name=chroma` 检查，未启动时去 novel-mind 项目拉起对应 compose 服务。
3. **集合缺失**：登记里 active build 声明的 collection 不在 Chroma 中（例如换过 Chroma 数据卷）。重建索引即可（见 5.2）。
4. **embedding 模型不可用**：`PERSONAL_DATA_EMBED_MODEL_PATH` 未设置、或指向坏路径。本机 C 盘 HF 缓存里的 `bge-small-zh-v1.5` 副本已损坏（加载必失败），推荐显式指向 `D:\models\bge-small-zh-v1.5`（详见[配置参考](../configuration/overview.md)）。

关键词路径不依赖任何常驻服务（不依赖 Kernel/API 进程，纯进程内只读 sqlite），无 Chroma 时检索功能仍然可用，只是失去语义相似度能力。

### 5.2 如何重建向量索引

```powershell
python tools/semantic/build_semantic_vector_store.py --write --activate
```

要点（详见脚本头注释）：

- 默认 `--dry-run` 只打印构建计划；`--write` 真建；`--activate` 建后即标 active（隐含 `--write`），其余 active build 降级为 `superseded`。
- 每次构建生成新版本化 collection `semantic_mvp_v1_<UTC时间戳>`，旧版本一律保留，脚本无任何删除路径；同名撞车会报错退出（重跑换时间戳即可）。
- 文档集 = active `ku_facts`（id `f|<fact_key>`）+ 全部 `session_cards`（id `c|<session_id>`），文本经 `guard_text` 隐私处理。
- 前置：Chroma 已启动、本机模型可用（脚本内部对 `PERSONAL_DATA_EMBED_MODEL_PATH` 做了 `setdefault D:\models\bge-small-zh-v1.5` 兜底）。
- 登记只写 `var/db/semantic_index_registry.json`，不写 canonical 的 `knowledge_index_versions`（语义 MVP 产物尚未走 KU 程序转正）。

### 5.3 数据规模是多少？

库内容随管线运行增长。本文撰写时实测（2026-08-29）：1,108 张会话卡、7,403 条 active 事实（另有 284 条 superseded 不进检索面）。部分历史文档（含 `search_semantic_cards` 的工具描述）写的"173 张卡 / 1,037 条事实"是接线时点的数字，仅供参考。

## 6. 已知限制

- **score 跨模式量纲不同**：vector 是 0–1 余弦相似度，keyword 是加权命中数，两者不可直接比较；混合对比结果时应以 `meta.mode` 为准分别解读。
- **类型过滤未暴露**：向量 collection 中 fact 文档的 metadata 带 `unit_type`（构建时从 `var/db/semantic_ku_staging.sqlite` 反查，缺失时为 `unclassified`），Chroma 的 `where` 过滤能力也已在客户端封装（`Collection.query(where=...)`），但 `search_cards`/`get_card` 尚未暴露过滤参数——按类型过滤属**计划中**，当前只能整面检索。
- **`matched_facts` 只带前 2 条**：摘要行截断，完整事实列表走 `get_card` 详情。
- **chroma 容器借用外部 compose**（SEMANTIC-WIRING 遗留一）：正式栈应有自己的 compose 条目；容器不在本仓库内，启停需到 novel-mind 项目操作。
- **默认模型路径待修**（遗留二）：`core/runtime_config.py` 的默认候选路径指向残缺的 C 盘缓存，不显式设置 `PERSONAL_DATA_EMBED_MODEL_PATH` 时向量路径必然回退；修复默认值后可消除该环境变量要求。
- **refs 二次跳转未封装**：`evidence_refs` 下钻原文目前需自行 join canonical 库（见 3.3）。
