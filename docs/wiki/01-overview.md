# 项目总览

> **一句话：** 把你的对话记录自动变成可搜索的知识库，再基于这些知识做决策辅助。
>
> 全本地运行，数据不出机器。

---

## 场景速览

你每天会在多个地方产生记录——Claude Code 里的调试对话、Chrome 上网记录、GPT 问答。这些记录分散在不同的地方，想回头看"上次那个 Python 报错是怎么解决的"时找起来很痛苦。

这个系统的做法：

**① 把分散的数据拉到本地 → ② 归一化成统一格式 → ③ 用 LLM 提取成知识单元(Q&A) → ④ 建成向量索引 → ⑤ 每次搜索先查知识库，不够再回退到原始记录**

这样搜"Python 报错"时，优先返回之前 LLM 提取的结构化解答；如果知识库里没有，才回落到你原始的对话片段里去搜。

---

## 一个完整的工作日是什么样的

```powershell
# 早上：同步昨晚的对话
pk-sync conversations --write

# 检查有没有新内容需要提取知识
pk-ku inspect

# 如果有新内容（source_changed=true），提取知识单元
pk-ku prepare --model gemini-3.5-flash --provider vertex_google --endpoint "https://aiplatform.googleapis.com" --auth-mode gcloud
pk-ku extract --run ir_xxxx --max-items 50
pk-ku canonical --run ir_xxxx --write
pk-ku publish --run ir_xxxx --write
pk-ku vector --write
pk-ku canary --candidate-override knowledge_units_ir_xxxx --report canary.json
pk-ku canary --report canary.json --label-with-llm
pk-ku canary --report canary.json --strict
pk-ku promote --collection knowledge_units_ir_xxxx --require-eval-pass --eval-summary ... --eval-gate ...
pk-ku watermark --advance --from-canonical --write

# 搜一下看看有没有效果
rag-search "Python 报错处理"

# 想看统计数据
rag-search stats
```

---

## 三个核心设计原则

### 1. 增量，不全量

知识提取只处理"上次同步之后新增的对话"，不每天把全部历史重新跑一遍。这样既不浪费 LLM 费用，也快。

对应命令：`pk-ku inspect` 检测增量 → `pk-ku prepare` 冻结增量清单 → `pk-ku extract` 只提取增量。

### 2. 有证据才回答（fail-closed）

每次搜索匹配到的知识单元，要经过 6 道门禁检查。证据链断裂、生命周期已过期、隐私标记为敏感——这些情况直接丢弃，不返回给用户。

对应代码：`relevance.py` 的 `decide_evidence_support()`。

### 3. 叠加不删除

合并重复事件时，原始数据不动，只在叠加表里记"哪些事件属于同一簇"。任何时候都能 JOIN 回去拿到原始事件。

对应数据表：`merge_clusters` + `merge_members`。

---

## 技术栈速览

| 组件 | 选型 | 为什么 |
|------|------|--------|
| 嵌入模型 | bge-small-zh-v1.5（512 维） | 中文优化、95MB、CPU/GPU 都能跑 |
| 向量库 | Chroma（REST API v2） | 轻量、本机、零运维 |
| 数据库 | SQLite（多库分治） | 不需要 PostgreSQL，纯本地 |
| REST API | Python 标准库 http.server | 零依赖，装了 Python 就能跑 |
| MCP | Python mcp 包 / stdio | AI 客户端(Claude/Cursor)直接调用 |
| LLM | Vertex AI Gemini / OpenAI 兼容 | 灵活切换 |
| 前端 | React/TS/Vite | Decision Cockpit 看板 |

**文件布局：** 彻底搞清目录结构在 [02-目录结构](02-directory-structure.md)。

---

## 关键入口

| 入口 | 做什么 | 什么时候用 |
|------|--------|-----------|
| `pk-sync` | 同步外部对话到本地 | 每天一次，有新对话时 |
| `pk-ku` | 知识单元提取全流程 | 对话同步后 |
| `rag-search` | 语义搜索 CLI | 随时 |
| `rag-api` | 启动 REST 服务 | 需要 HTTP 查询时 |
| `rag-mcp` | 启动 MCP 服务 | AI 客户端需要调用时 |
| `pk-ku doctor` | 系统健康检查 | 排查问题时 |
