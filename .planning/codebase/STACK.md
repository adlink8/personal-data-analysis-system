# 技术栈总览 (STACK.md)

> 生成时间: 2026-06-17
> 项目路径: C:\Users\li\Desktop\数据分析

---

## 核心语言和运行时

| 项目 | 版本 / 说明 |
|------|------------|
| 语言 | Python 3.14（cp314 wheel 已验证） |
| 运行平台 | Windows（本地桌面环境） |
| 包管理 | pip + requirements.txt |

---

## 主要依赖库

| 库 | 最低版本 | 用途 |
|----|---------|------|
| pandas | ≥ 3.0 | 表格数据处理与分析 |
| numpy | ≥ 2.4 | 数值计算 |
| matplotlib | ≥ 3.10 | 静态图表绘制 |
| scikit-learn | ≥ 1.8 | 机器学习 / 数据挖掘 |
| streamlit | ≥ 1.58 | 交互式 Web 可视化 Dashboard |
| plotly | ≥ 6.8 | 动态/交互式图表 |
| sentence-transformers | 由本机环境提供 | 本地模型推理，生成文本向量 |
| torch | 由本机环境提供 | GPU 加速推理后端（CUDA） |
| requests | 标准库级别 | ChromaDB REST 自定义客户端 |
| mcp | ≥ 1.0 | Model Context Protocol 官方 SDK，MCP Server 支持 |

> `torch` 与 `sentence-transformers` 未写入 requirements.txt，需在新机器上单独安装。

---

## 本地模型

| 模型 | 维度 | 存放路径 | 用途 |
|------|------|---------|------|
| BAAI/bge-small-zh-v1.5 | 512 维 | `D:\models\bge-small-zh-v1.5` | 中文文本向量化（语义检索） |

**加载方式：** `sentence_transformers.SentenceTransformer`，懒加载单例，优先 CUDA GPU，失败自动回退 CPU。
**离线模式：** 启动时设置 `TRANSFORMERS_OFFLINE=1` 和 `HF_HUB_OFFLINE=1`，完全本地运行，数据不出机器。
**性能：** 7 723 条数据约 53 秒（GPU），模型加载约 0.6 秒。

---

## 数据库

### SQLite — 结构化事件库

| 项目 | 说明 |
|------|------|
| 文件 | `统合模块/SQLite数据库/personal_system.sqlite` |
| 驱动 | Python 标准库 `sqlite3` |
| 表数量 | 12+ 张 |
| 核心表 | `unified_events`（16 列）、`unified_events_rich`、`event_categories_v2`、`entities`、`entity_links_v2`、`cross_module_insights`、`module_summaries`、`merge_clusters`、`merge_members`、`memory_items` 等 |
| 主要字段 | `event_id`, `source`, `event_type`, `service`, `event_time`, `month`, `title`, `content`, `category`, `url`, `domain`, `weight` 等 |

### ChromaDB — 向量库

| 项目 | 说明 |
|------|------|
| 部署方式 | 本地独立进程，REST API v2 |
| 默认地址 | `http://127.0.0.1:8001` |
| 客户端 | 自研轻量客户端 `chroma_client.py`（基于 `requests`，不依赖 chromadb 包） |
| Collection | `personal_events`（cosine 空间，512 维） |
| 原因 | 官方 `chromadb` 包的 `httpx` 存在 502 兼容性问题，改用 `requests` 直连 |

---

## 模块结构概览

```
统合模块/脚本/
├── local_embed.py      # 本地模型向量化接口
├── chroma_client.py    # ChromaDB REST 自定义客户端
├── unified_search.py   # 统一检索后端（CLI / MCP / API 共用）
├── mcp_server.py       # MCP Server（stdio 协议）
└── api_server.py       # REST API Server（标准库 http.server）
```
