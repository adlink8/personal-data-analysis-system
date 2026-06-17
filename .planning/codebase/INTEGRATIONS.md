# 外部集成总览 (INTEGRATIONS.md)

> 生成时间: 2026-06-17
> 项目路径: C:\Users\li\Desktop\数据分析

---

## MCP Server 接入

### 概述

`mcp_server.py` 通过 **stdio 传输** 实现 MCP 标准协议，任何支持 MCP 的 AI 客户端均可直接接入。语义检索转发到本地 REST API（`127.0.0.1:8000`），避免多 MCP 子进程重复加载 CUDA 模型。

### 启动方式

```powershell
python "C:/Users/li/Desktop/数据分析/统合模块/脚本/mcp_server.py"
```

### 客户端配置（Claude Desktop / Cursor / ZCode 等）

```json
{
  "mcpServers": {
    "personal-data": {
      "command": "python",
      "args": ["C:/Users/li/Desktop/数据分析/统合模块/脚本/mcp_server.py"]
    }
  }
}
```

### 暴露的 MCP Tools

| Tool 名 | 描述 | 必填参数 | 可选参数 |
|---------|------|---------|---------|
| `search_semantic` | 自然语言 → 向量库模糊召回 | `query` (string) | `top_k` (1-20, 默认 5)、`source` (Google/GPT/Agent) |
| `query_events` | 结构化条件过滤 SQLite | 无 | `source`、`month`、`category`、`keyword`、`limit` (默认 50，上限 200) |
| `get_event_detail` | 按 event_id 取单条全字段详情 | `event_id` (string) | 无 |
| `stats` | 数据库 + 向量库统计概览 | 无 | 无 |
| `list_categories` | 列出所有 category_v2 分类及事件数 | 无 | `source` |

> MCP Server 语义检索不直接加载模型，而是转发到本地 REST API（`http://127.0.0.1:8000/search/semantic`）。MCP 子进程强制使用 CPU 模式（`PERSONAL_DATA_EMBED_DEVICE=cpu`）。

---

## REST API 接口列表

**服务文件：** `统合模块/脚本/api_server.py`
**启动命令：** `python api_server.py [--host 127.0.0.1] [--port 8000]`
**默认地址：** `http://127.0.0.1:8000`
**响应格式：** 统一 `{"ok": bool, "data": ..., "error": ...}`
**CORS：** 已开启（`Access-Control-Allow-Origin: *`，仅本地监听，风险可控）

| 方法 | 路径 | 描述 | 参数 |
|------|------|------|------|
| GET | `/health` | 健康检查 | 无 |
| GET | `/stats` | 数据库 + 向量库统计概览 | 无 |
| GET | `/categories` | 所有 category_v2 分布 | `?source=Google/GPT/Agent`（可选） |
| POST | `/search/semantic` | 语义检索（向量库召回） | JSON body: `query`(必填), `top_k`(默认 5), `source`(可选) |
| POST | `/search/query` | 精确查询（SQLite 过滤） | JSON body: `source`, `month`, `category`, `keyword`, `limit`（均可选） |
| GET | `/event/<event_id>` | 单条事件全字段详情 | 路径参数 `event_id` |
| GET | `/profile` | AI 长期上下文文档（RAG 注入） | 无，读取 `person_profile.md` |

### 示例

```powershell
# 健康检查
curl http://127.0.0.1:8000/health

# 语义检索
curl -X POST http://127.0.0.1:8000/search/semantic `
     -H "Content-Type: application/json" `
     -d '{"query": "PPT 排版", "top_k": 3}'

# 精确查询
curl -X POST http://127.0.0.1:8000/search/query `
     -H "Content-Type: application/json" `
     -d '{"source": "Agent", "month": "2025-03"}'
```

---

## 外部服务依赖

| 服务 | 地址 | 说明 | 是否必须 |
|------|------|------|---------|
| ChromaDB | `http://127.0.0.1:8001` | 向量数据库，本地独立进程，REST API v2 | 语义检索必须；精确查询/统计不依赖 |
| 本地 REST API | `http://127.0.0.1:8000` | api_server.py 常驻进程，MCP Server 转发语义检索到此 | MCP 语义检索必须 |
| Ollama | — | 已被 `local_embed.py` 替代（批量 hang 死问题），当前不再使用 | 已废弃 |
| HuggingFace Hub | — | 完全离线（`HF_HUB_OFFLINE=1`），模型从本地 `D:\models\` 加载 | 不依赖 |

---

## 接入示例 (examples/)

| 示例文件 | 接入方式 | 适用场景 | 依赖 |
|---------|---------|---------|------|
| `openai_function_calling.py` | OpenAI 函数调用 | GPT/DeepSeek/千问 等按需检索历史 | `openai` |
| `langchain_tool.py` | LangChain Tool | 已用 LangChain/LangGraph 的项目 | `langchain` 全家桶 |
| `rag_inject.py` | RAG 上下文注入 | Dify/FastGPT/自建 RAG 静默增强 | 仅标准库（调 HTTP API） |

---

## 接入方式总览

| 接入场景 | 方式 | 入口文件 | 传输协议 |
|---------|------|---------|---------|
| AI 客户端（Claude Desktop / Cursor / ZCode） | MCP Tools | `mcp_server.py` | stdio（MCP 标准） |
| RAG 平台（Dify / FastGPT / Coze） | HTTP 工具/自定义 API | `api_server.py` | HTTP REST |
| 前端 / curl / Postman | HTTP | `api_server.py` | HTTP REST |
| 命令行 CLI | 脚本直调 | `unified_search.py` | 无网络，纯本地 |
| 其他 Python 脚本 | import | `unified_search.py` | 无网络，纯本地 |
