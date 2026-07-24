# 工具层架构

> **一句话：** 三个入口（CLI / REST / MCP）调用同一个后端，行为完全一样。MCP 内部实际是 loopback 调 REST API。

---

## 三种入口，一个后端

```
你（人类/程序）                               后端
                                               ┌─────────────────┐
CLI: rag-search "查词" ──────────────────────→ │                 │
REST: curl POST /search/semantic {"query":..}→ │ search_knowledge│
MCP: search_semantic(query=..) ─→ REST API ─→ │ _units()        │
                                               └─────────────────┘
```

区别只在外层包装：

| 入口 | 返回格式 | 适合谁用 |
|------|---------|---------|
| CLI | 格式化文本（人类可读） | 终端直接操作 |
| REST | `{"ok":true,"data":...}` | 程序调用、前端 |
| MCP | JSON 字符串 → TextContent | AI 客户端（Claude、Cursor） |

---

## 实际跑一次看看区别

### CLI 版

```powershell
rag-search "Python 调试" --top-k 2
```

输出：
```
检索: "Python 调试" (top_k=2)
──────────────────────────────────────────────────────────

#1
[0.8732] [Agent] 解决 Python 导入循环依赖
    来源库: personal_events | 单元: event | 原因: non_dialogue_raw personal_events
    时间: 2026-03-15T10:30:00 | 分类: 调试 | 服务: claude-code
    内容: from a import b 导致循环引用，改为 from a import b inside function...

#2
[0.8211] [Agent] Python 虚拟环境配置
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

AI 客户端调 MCP `search_semantic` 时，MCP Server 内部发 HTTP POST 到 `http://127.0.0.1:8000/search/semantic`，拿到结果后格式化再返回。

**关键：** MCP 不直接调 `search_knowledge_units()`，而是通过本机 REST API 做 loopback。这意味着 REST API 必须在运行中。

---

## 服务端口清单

| 服务 | 端口 | 进程 | 怎么启动 | 关了会怎样 |
|------|------|------|---------|-----------|
| REST API | 8000 | Python `personal_knowledge` | `rag-api` 或 `start-services.ps1` | MCP 搜索不可用 |
| ChatGPT MCP | 8789 | Node.js `server.mjs` | `start-services.ps1` | ChatGPT App 连不上 |
| Tunnel | 8081 | `tunnel-client.exe` | `start-services.ps1` | ChatGPT 外网连不上 |
| Chroma | 8001 | Chroma 进程 | 随 `build_vector_store` 自动启动 | 搜索崩溃 |

### 健康检查

```powershell
curl http://127.0.0.1:8000/health
# → {"ok":true,"status":"ok","knowledge":{"available":true,"unit_count":32181}}

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

| 方法 | 路径 | 做什么 |
|------|------|--------|
| GET | `/ui/overview` | Cockpit 总览 |
| GET | `/ui/system/status` | 系统状态 |
| GET | `/app/` | 前端 SPA |

---

## CLI 命令一览

详细参数和示例在 [09-CLI 命令速查](09-cli-reference.md)，这里只列 6 个顶层命令：

```
pk-sync      对话同步（AgentsView → 本地）
pk-ku        知识单元全流程（inspect → extract → promote）
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
| 人肉查一次历史 | CLI `rag-search "关键词"` | 不需要配 curl |
| 查数据质量 | REST `/data/quality` | 结构化的质量报告 |
| 看系统概览 | REST `/stats` | 一次拿全统计数据 |
