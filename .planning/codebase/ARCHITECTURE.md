# 系统架构 (ARCHITECTURE.md)

> 生成时间: 2026-06-17
> 项目路径: C:\Users\li\Desktop\数据分析

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        raw层 (Layer 0)                       │
│  Google/raw/    GPT/raw/    Agent/raw/               │
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
│   合并去重层 (L1.5)   │   │      记忆层 (Layer 4 · Phase 04/05) │
│  merge_clusters      │   │  memory_items / memory_links        │
│  merge_members       │   │  memory_relations                   │
│  merge_build_meta    │   │  + governance metadata / readiness  │
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
│                                                                   │
│  conversation_turns collection (Phase 07 Wave 7 · 独立)           │
│  ├─ documents: turn 叙述(含因果链,非单条 message)                │
│  ├─ ids: session_id#turn_id (幂等)                               │
│  └─ metadatas: session_id/turn_id/turn_no/main_topic/source     │
│                                                                   │
│  跨 collection 检索: search_vectors.search_all()                  │
│  unified_search 默认 include_turns=True                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              统一检索后端 (unified_search.py)                     │
│  search_semantic() ← 语义 → Chroma REST                         │
│  query_events()    ← 精确 → SQLite                               │
│  get_event_detail() / stats() / memory queries / cluster()       │
└───────┬──────────────┬──────────────┬──────────────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌───────────┐ ┌───────────────────────────────┐
│ Streamlit    │ │ REST API  │ │ MCP Server                    │
│ Dashboard    │ │ :8000     │ │ (stdio → AI客户端)             │
│ (5个页面)    │ │ 9个接口   │ │ 7个 MCP Tools                 │
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
  → build_deep_profiles.py       (生成module_profile + profile Markdown)
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
| 数据摄入 | `build_integrated_system.py` | 三源raw解析，建立9张统合表 |
| 语义增强 | `enrich_unified_events.py` | 补真实文本、修复分类污染、建跨模块连接 |
| 去重合并 | `build_merge_layer.py` | 三层去重（L1真重复/L2同主题/L3保留），叠加表不破坏原数据 |
| 画像生成 | `build_deep_profiles.py` | 基于统合库生成module_profile和profile |
| 向量化 | `build_vector_store.py` | 批量向量化，写入 Chroma |
| 检索后端 | `unified_search.py` | CLI/MCP/API 共用的纯函数检索接口 |
| 工具函数 | `common.py` | 纯函数工具（hash/norm/CSV写入等） |
| 分类规则 | `rules.py` | 集中维护分类规则（v1 对照 + v2 纯净版） |
| 向量客户端 | `chroma_client.py` | 轻量 ChromaDB REST 客户端（绕开 httpx 兼容问题） |
| 嵌入模型 | `local_embed.py` | bge-small-zh-v1.5 懒加载单例，CUDA 优先 |
| 仪表盘 | `dashboard.py` | Streamlit 五页面交互可视化 |
| REST API | `api_server.py` | 标准库 http.server，9个HTTP接口（含 memory 入口） |
| MCP Server | `mcp_server.py` | stdio MCP协议，7个Tool暴露给AI客户端 |

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

### memory_items（记忆层，Phase 05）

```
memory_items: memory_id, memory_type, memory_subtype, subject, description,
              confidence, evidence_count, metadata, created_at
```

`metadata` 在 Phase 05 标准化为 `evidence_ids` / `confidence` / `last_seen` /
`source_hash` / `merge_key` + 来源特有字段。

### Phase 06 深层画像（旁路分析层）

Phase 06 不回写 `memory_items`，而是在 `integration/analysis/ai_context/` 旁路输出：

- `deep_memory_mining.json`：只包含 readiness gate 通过主题的深挖事实层结果
- `deep_memory_insights.md`：洞察清单，区分 include / review / exclude
- `deep_memory_profile.md`：适合 agent prompt 的深层模式画像
- `deep_profile_evaluation.md`：浅层 `person_profile_v2.md` 与深层 profile 的差异评估

这层的职责是把浅层标签升级成模式、演化、关系强度和反例约束，但不把推测写回长期记忆库。

### Phase 07 对话叙述层（Agent 对话规范化 + LLM 叙述压缩回流）

Phase 07 同样**不回写 `memory_items`**，定位是"更可靠的对话输入 + 可检索的 turn 叙述回流"：

**Agent 对话规范化**（`Agent/structured/db/agent_data.sqlite` v2 旁路表，不动旧表）：
- `agent_sessions_meta` / `agent_turns`：会话和 turn 边界（turn_id 前向填充，96.4% user 消息可串联）
- `agent_messages`：role 归一化为 user/assistant/developer 三值，提取可解释文本，带 `raw_file + line_no` 证据链
- `agent_tool_calls` / `agent_tool_outputs`：按 `call_id` 关联的工具调用与输出（长输出截断，原文回源文件）
- `agent_lifecycle_events` / `agent_usage_metrics`：生命周期事件与 token 指标
- 当前只深度解析 Codex rollout 格式；Claude/WorkBuddy/Hermes 仅发现计数（`unsupported`）

**用户想法片段**（`integration/analysis/ai_context/conversation_segments.json`）：
- 输入只来自 `agent_messages` 和 GPT `messages` 的 `role=user`
- 列表项/双换行/超长句确定性切分，丢弃过短噪声

**mem0 候选压缩**（⚠️ 已降级为可选实验）：
- 实测 mem0 压缩度太狠，把一次性操作指令误判为稳定偏好，且丢失因果链
- 保留scripts和候选文件作为实验记录，不进入主路径

**LLM 叙述压缩（★ Phase 07 主线）**：
- `build_conversation_summary.py`：对每个 Agent session 逐 turn 生成中文叙述摘要，保留主干+分支+细节因果，用 MiMo/OpenAI 兼容 API
- `conversation_summaries.json`：turn 级叙述段，非 mem0 风格离散 claim

**Prompt Lab 评测门（★ Wave 6）**：
- `build_conversation_eval_set.py`：7 类真实 Codex session turn 固定评测样本集
- `prompts/conversation_compression/`：版本化 prompt（v1_main/v1_schema/eval_rubric），7 维评分 + faithfulness 硬门槛 + 一次性任务误判为偏好专项检查
- `evaluate_conversation_prompt.py`：两轮 LLM（压缩轮 + LLM-as-judge 评分轮），gate 通过才允许回流
- 实测 7/7 样本 gate 通过（faithfulness 全 5，pass_rate=1.00）

**turn 叙述回流向量库（★ Wave 7）**：
- `build_conversation_vector_store.py`：turn 叙述向量化入库到独立 collection `conversation_turns`
- 检索单元 = turn 叙述（含 user+assistant+tool 因果链），不是单条 message
- 不碰 `personal_events` collection（用户拍板 B 方案，隔离风险）
- `search_vectors.py` 新增 `search_all`：跨 collection 合并检索（personal_events + conversation_turns）
- `unified_search.py` 的 `search_semantic` 默认 `include_turns=True`，CLI/MCP/Agent 全接入
- `run_pipeline.py` 新增步骤 13
