# 工具层架构

> **一句话：** CLI / REST / MCP 都基于同一套检索后端，但入口行为和返回格式并不完全一样。stdio MCP 当前是进程内直接调用后端，不再 loopback 调 REST。

---

## 三种入口，一个后端

```
你（人类/程序）                               后端
                                               ┌─────────────────┐
CLI: rag-search semantic "查词" ──────────────────────→ │                 │
REST: curl POST /search/semantic {"query":..}→ │ search_knowledge│
MCP: search_semantic(query=..) ─→ 进程内调用 ─→ │ _units()        │
                                               └─────────────────┘
```

区别只在外层包装：

| 入口 | 返回格式 | 适合谁用 |
|------|---------|---------|
| CLI | 格式化文本（人类可读） | 终端直接操作 |
| REST | `{"ok":true,"data":...}` | 程序调用、前端 |
| MCP | stdio：人类可读文本 → TextContent；ChatGPT MCP：structuredContent + 短文本摘要 | AI 客户端（Claude、Cursor、ChatGPT） |

---

## 实际跑一次看看区别

### CLI 版

```powershell
rag-search semantic "Python 调试" --top-k 2
```

输出：
```
检索路由: <route> fallback_policy=<policy>
──────────────────────────────────────────────────────────

#1
[score=0.8732] [Agent] 解决 Python 导入循环依赖
    来源库: personal_events | 单元: event | 原因: non_dialogue_raw personal_events
    时间: 2026-03-15T10:30:00 | 分类: 调试
    内容: from a import b 导致循环引用，改为 from a import b inside function...

#2
[score=0.8211] [Agent] Python 虚拟环境配置
    来源库: knowledge_units_ir_xxx | 单元: knowledge_unit
    时间: 2026-03-14T15:20:00
    内容: 使用 venv 创建虚拟环境...
```

### REST 版

```powershell
curl -X POST http://127.0.0.1:8000/search/semantic -H "Content-Type: application/json" -d '{"query":"Python 调试","top_k":2}'
```

返回：
```json
{"ok":true,"data":{"route":"knowledge","results":[{"rank":1,"unit_id":"ku|...","answer":"from a import b ...","retrieval_unit":"knowledge_unit"},{"rank":2,"unit_id":"ev|...","retrieval_unit":"event"}],"telemetry":{"layers":[{"name":"knowledge_unit","hits":1},{"name":"non_dialogue_raw","hits":1}],"total_latency_ms":92.5}}}
```

### MCP 版

AI 客户端调 stdio MCP `search_semantic` 时，MCP Server 直接进程内调用 `search_knowledge_units()`，拿结果后格式化为人类可读文本再返回；不需要 REST API 在运行。

**关键：** 当前 stdio MCP 不走 REST loopback；只有 ChatGPT MCP（`apps/personal_data_chatgpt/server.mjs`）里的 `search` 工具走 REST loopback。

---

## 服务端口清单

| 服务 | 端口 | 进程 | 怎么启动 | 关了会怎样 |
|------|------|------|---------|-----------|
| REST API | 8000 | Python `personal_knowledge` | `rag-api` 或 `start-services.ps1` | stdio MCP 检索不受影响；ChatGPT MCP 的 `search` 不可用 |
| ChatGPT MCP | 8789 | Node.js `apps/personal_data_chatgpt/server.mjs` | `start-services.ps1` | ChatGPT App 连不上 |
| Tunnel | 8081 | `tunnel-client.exe` | `start-services.ps1` | ChatGPT 外网连不上 |
| Chroma | 8001 | Chroma 进程 | 需单独启动（`build_vector_store` 只构造客户端，不拉起进程） | 语义搜索降级走 fallback，不直接崩溃 |

### 健康检查

```powershell
curl http://127.0.0.1:8000/health
# → {"ok":true,"data":{"status":"ok","knowledge":{"available":true,"unit_count":32181}}}

curl http://127.0.0.1:8789/health
# → {"ok":true,"status":"ok"}
```

---

## REST API 快速导航

### 最常用的 6 个

| 方法 | 路径 | 做什么 |
|------|------|--------|
| GET | `/health` | 健康检查 + 知识索引摘要 |
| GET | `/stats` | 总事件数、按源分布、向量库状态 |
| POST | `/search/semantic` | **语义检索**（knowledge-first + fallback） |
| POST | `/search/query` | **精确查询**（按条件过滤） |
| GET | `/knowledge` | 知识索引状态 |
| GET | `/categories` | 分类分布 |

### 数据浏览（data contract）

| 方法 | 路径 | 做什么 |
|------|------|--------|
| GET | `/data/events?source=Agent&limit=50` | 分页浏览事件 |
| GET | `/data/event/{id}` | 单条事件详情 |
| GET | `/data/memories` | 分页浏览记忆 |
| GET | `/data/aggregate?group_by=source,service` | 聚合统计 |
| GET | `/data/timeline?interval=month` | 时间线统计 |
| GET | `/data/export?format=jsonl` | 导出数据 |
| GET | `/data/quality` | 数据质量报告 |

### 决策智能

| 方法 | 路径 | 做什么 |
|------|------|--------|
| GET | `/intelligence/state/current` | 当前个人状态 |
| GET | `/intelligence/changes/recent` | 近期变化 |
| GET | `/decision/recommendations` | 推荐列表 |
| GET | `/proactive/inbox` | 主动情报收件箱 |
| POST | `/agent/session/prepare` | 准备决策会话 |

### Decision Cockpit UI

> **状态提醒：** Decision Cockpit（v1.4，Phase 36–40）在 `.planning/ROADMAP.md` 中已标记完成（UAT 已于 2026-07-28 接受）。但当前 REST dispatcher 中 `/ui/*` 与 `/app/*` 的投影/SPA 分发块被注释掉，实际请求会 404；下列表格仅记录设计/规划中的接口，不代表当前可用。

| 方法 | 路径 | 做什么 |
|------|------|--------|
| GET | `/ui/overview` | Cockpit 总览投影（规划，当前 404） |
| GET | `/ui/system/status` | 系统状态（规划，当前 404） |
| GET | `/ui/personal-state` | 个人状态投影（规划，当前 404） |
| GET | `/ui/external/delta` | 外部数据增量投影（规划，当前 404） |
| GET | `/ui/decision-queue` | 决策队列投影（规划，当前 404） |
| GET | `/ui/decision/workspace` | 决策工作区投影（规划，当前 404） |
| GET | `/ui/actions/recent` | 近期行动投影（规划，当前 404） |
| GET | `/ui/proactive/summary` | 主动情报摘要（规划，当前 404） |
| GET | `/ui/calibration/overview` | 校准总览（规划，当前 404） |
| GET | `/ui/evidence/resolve` | 只读证据解析（规划，当前 404） |
| GET | `/app/` 或 `/app/<path>` | 前端 SPA 静态托管（规划，当前 404） |

接口清单注释位于 `src/personal_knowledge/services/api_server.py` 顶部，但它仍把已注释的 Cockpit 路由列为可用，实际以 dispatcher 中未注释的路由为准。

---

## CLI 命令一览

详细参数和示例在 [09-CLI 命令速查](09-cli-reference.md)，这里列出 7 个入口（含已退役的 rag-pipeline）：

```
pk-sync      对话同步（AgentsView → 本地）
pk-ku        知识单元全流程（inspect → extract → promote；付费 extract 当前受治理门禁拦截，需先走审批/试点路径）
rag-search   搜索（语义 + 精确）
rag-api      启动 REST API（端口 8000）
rag-mcp      启动 MCP Server（stdio）
rag-dashboard 启动 Streamlit 仪表盘
rag-pipeline [已退役] → 用 pk-sync + pk-ku 替代
```

---

## 典型使用场景的入口选择

| 场景 | 推荐入口 | 为什么 |
|------|---------|--------|
| 日常检查增量 | CLI `pk-ku inspect` | 最快，不需要启动服务 |
| 写脚本批量查询 | REST API | JSON 好解析 |
| AI 客户端接入 | MCP | AI 原生支持 |
| 人肉查一次历史 | CLI `rag-search semantic "关键词"` | 不需要配 curl |
| 查数据质量 | REST `/data/quality` | 结构化的质量报告 |
| 看系统概览 | REST `/stats` | 一次拿全统计数据 |
