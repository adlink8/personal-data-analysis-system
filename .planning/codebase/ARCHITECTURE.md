# 系统架构 (ARCHITECTURE.md)

> 生成时间: 2026-06-17
> 项目路径: C:\Users\li\Desktop\数据分析

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        原始数据层 (Layer 0)                       │
│  Google/原始数据/    GPT/原始数据/    Agent/原始数据/               │
│  (Takeout JSON)    (导出对话文件)   (session jsonl/memory/skills) │
└────────────────────────┬────────────────────────────────────────┘
                         │ build_integrated_system.py
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    统合层 (Layer 1 · SQLite)                      │
│  personal_system.sqlite                                          │
│  ├─ unified_events        (9张原始统合表, 约8000条)                │
│  ├─ entities / entity_links                                      │
│  ├─ cross_module_insights / module_summaries                     │
│  └─ agent_data.sqlite (Agent 子库)                               │
└────────────────────────┬────────────────────────────────────────┘
                         │ enrich_unified_events.py
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  语义增强层 (Layer 2 · 叠加表)                     │
│  ├─ unified_events_rich   (补真实文本 content_rich)               │
│  ├─ event_categories_v2   (纯净分类，去元数据污染)                  │
│  └─ entity_links_v2       (7182 条真实跨模块链接)                  │
└──────────────┬─────────────────────────┬───────────────────────┘
               │ build_merge_layer.py    │ build_memory_store.py 等
               ▼                         ▼
┌──────────────────────┐   ┌─────────────────────────────────────┐
│   合并去重层 (L1.5)   │   │         记忆层 (Layer 4 · Phase 04) │
│  merge_clusters      │   │  memory_items / memory_links        │
│  merge_members       │   │  memory_relations                   │
│  merge_build_meta    │   │  (能力/上下文/偏好记忆)               │
└──────────────┬───────┘   └─────────────────────────────────────┘
               │ build_vector_store.py
               ▼
┌─────────────────────────────────────────────────────────────────┐
│                     向量库 (Layer 3 · ChromaDB)                  │
│  personal_events collection                                      │
│  ├─ documents: content_rich                                      │
│  ├─ embeddings: bge-small-zh-v1.5 512维                         │
│  ├─ ids: event_id (与 SQLite 对齐)                               │
│  └─ metadatas: source/category_v2/event_time/month/service      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              统一检索后端 (unified_search.py)                     │
│  search_semantic() ← 语义 → Chroma REST                         │
│  query_events()    ← 精确 → SQLite                               │
│  get_event_detail() / stats() / cluster()                        │
└───────┬──────────────┬──────────────┬──────────────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌───────────┐ ┌───────────────────────────────┐
│ Streamlit    │ │ REST API  │ │ MCP Server                    │
│ Dashboard    │ │ :8000     │ │ (stdio → AI客户端)             │
│ (5个页面)    │ │ 7个接口   │ │ 5个 MCP Tools                 │
└──────────────┘ └───────────┘ └───────────────────────────────┘
```

---

## 数据流说明

### 写入链路（重跑管道）

```
原始导出文件
  → build_integrated_system.py   (解析 → unified_events 等9张表)
  → enrich_unified_events.py     (补文本 + 修分类 + 建跨模块链接)
  → build_merge_layer.py         (去重折叠 → merge_* 叠加表)
  → build_deep_profiles.py       (生成模块画像 + 统合画像 Markdown)
  → build_memory_store.py 等     (抽取记忆对象 → memory_items)
  → build_vector_store.py        (bge-small-zh → Chroma personal_events)
  → build_context_doc.py         (生成 person_profile.md AI上下文文档)
```

**关键约束：** 步骤1重建整个 SQLite，步骤2必须紧跟步骤1，否则增强表丢失。

### 读取链路（查询接入）

```
用户/AI 发起查询
  → unified_search.py (统一入口)
      ├─ 语义查询 → chroma_client.py → ChromaDB :8001
      └─ 精确查询 → sqlite3 → personal_system.sqlite
  → 返回事件列表 + content_rich 真实文本
```

---

## 核心模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 数据摄入 | `build_integrated_system.py` | 三源原始数据解析，建立9张统合表 |
| 语义增强 | `enrich_unified_events.py` | 补真实文本、修复分类污染、建跨模块连接 |
| 去重合并 | `build_merge_layer.py` | 三层去重（L1真重复/L2同主题/L3保留），叠加表不破坏原数据 |
| 画像生成 | `build_deep_profiles.py` | 基于统合库生成模块画像和统合画像 |
| 向量化 | `build_vector_store.py` | 批量向量化，写入 Chroma |
| 检索后端 | `unified_search.py` | CLI/MCP/API 共用的纯函数检索接口 |
| 工具函数 | `common.py` | 纯函数工具（hash/norm/CSV写入等） |
| 分类规则 | `rules.py` | 集中维护分类规则（v1 对照 + v2 纯净版） |
| 向量客户端 | `chroma_client.py` | 轻量 ChromaDB REST 客户端（绕开 httpx 兼容问题） |
| 嵌入模型 | `local_embed.py` | bge-small-zh-v1.5 懒加载单例，CUDA 优先 |
| 仪表盘 | `dashboard.py` | Streamlit 五页面交互可视化 |
| REST API | `api_server.py` | 标准库 http.server，7个HTTP接口 |
| MCP Server | `mcp_server.py` | stdio MCP协议，5个Tool暴露给AI客户端 |

---

## 关键数据库表结构概述

### unified_events（核心原始表，16列）

| 字段 | 含义 |
|------|------|
| `event_id` | 全局唯一 ID（sha256 派生） |
| `source` | 来源（Google/GPT/Agent） |
| `event_type` | 事件类型 |
| `service` | 子服务名 |
| `event_time` | 事件时间 |
| `month` | 年月（YYYY-MM，索引加速） |
| `title` | 标题 |
| `content` | 原始内容（Agent 为 uuid，需 content_rich 补全） |
| `category` | v1 分类（含元数据污染，已弃用） |
| `domain` / `url` / `weight` | 域名/链接/权重 |

### unified_events_rich（增强层，扩展 content_rich）

在 `unified_events` 基础上增加 `content_rich`：Agent 补入真实对话，GPT/Google 直接透传。

### merge_clusters / merge_members（合并层）

```
merge_clusters: cluster_id, level(L1/L2/L3), representative_id, member_count, summary
merge_members:  cluster_id, event_id, is_representative, role
```

所有原始 event_id 通过 JOIN 可完整追溯，零数据损失。

### memory_items（记忆层，Phase 04）

```
memory_items: id, type(capability/context/preference/...), content, source_event_id, created_at
```
