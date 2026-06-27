# 目录结构 (STRUCTURE.md)

> 生成时间: 2026-06-17
> 项目路径: C:\Users\li\Desktop\数据分析

---

## 顶层目录总览

```
数据分析/
├── Google/                    # Google 数字足迹数据
├── GPT/                       # GPT 对话数据
├── Agent/                     # AI Agent 会话/记忆/技能数据
├── 统合模块/                   # 核心：整合三源数据的脚本与产出
├── lib/                       # [未纳入 git] 依赖库或临时库
├── imports/                   # 导入批次管理（含 batches/ incoming/）
├── new_import/                # [未纳入 git] 新导入管道（含 duplicate_audit/）
├── %DB%/                      # [未纳入 git] 含义不明，目录名含 % 符号（风险）
├── .planning/                 # 项目规划文档（codebase map、phases 等）
├── .gsd/                      # GSD 工作流状态（phases、milestones）
├── README.md                  # 项目总说明，含完整重跑链路
├── requirements.txt           # pip 依赖清单
├── _schema.py                 # 数据结构定义
├── _schema.json               # 数据结构 JSON 描述
├── classification_summary.json # 分类汇总产物（顶层散落文件）
└── 架构图.drawio               # 系统架构可视化图
```

---

## 三源数据目录（对称结构）

```
Google/                     GPT/                        Agent/
├── 原始数据/               ├── 原始数据/               ├── 原始数据/
├── 结构化数据/             ├── 结构化数据/             ├── 结构化数据/
│   └── SQLite数据库/       │   └── SQLite数据库/       │   └── SQLite数据库/
└── 分析数据/               └── 分析数据/               └── 分析数据/
```

三个模块完全对称，各自存放：
- `原始数据/`：平台导出文件（Google Takeout JSON、GPT 导出、Agent jsonl/memory）
- `结构化数据/`：清洗后的 CSV 和模块 SQLite
- `分析数据/`：`模块画像.md` 等分析产出

---

## 统合模块详细结构

```
统合模块/
├── 原始输入索引/
├── 结构化数据/
├── 分析数据/
│   ├── 模块画像 (各模块).md
│   ├── 统合画像.md
│   ├── 统合画像_数据增长图.png
│   ├── 统合画像_数据流向.csv
│   ├── 统合画像_个人思考模式.csv
│   └── ai_context/
│       └── person_profile.md      # AI 长期上下文文档（注入 system prompt 用）
├── SQLite数据库/
│   └── personal_system.sqlite     # 核心统合数据库（12+张表）
└── 脚本/
    ├── 核心管道脚本
    ├── 共享模块
    ├── 服务层
    └── examples/                  # 接入示例
```

---

## 脚本清单

### 数据构建管道（按执行顺序）

| 脚本 | 职责 | 产出 |
|------|------|------|
| `build_integrated_system.py` | 三源原始数据解析，重建统合库 | `personal_system.sqlite`（9张原始表） |
| `enrich_unified_events.py` | 语义增强：补真实文本/修复分类/建跨模块链接 | `unified_events_rich`, `event_categories_v2`, `entity_links_v2` |
| `build_merge_layer.py` | 三层去重折叠，叠加在原始表之上 | `merge_clusters`, `merge_members`, `merge_build_meta` |
| `build_deep_profiles.py` | 基于统合库生成各模块+统合画像 | `模块画像.md`, `统合画像*.md/csv/png` |
| `build_vector_store.py` | 批量向量化 content_rich，写入 Chroma | ChromaDB `personal_events` collection |
| `build_context_doc.py` | 生成 AI 长期上下文文档 | `ai_context/person_profile.md` |

### 记忆层脚本（Phase 04，未提交 git）

| 脚本 | 职责 |
|------|------|
| `build_memory_store.py` | 初始化 `memory_items` 等记忆表，建表基础结构 |
| `build_capability_memory.py` | 抽取能力类记忆（技能、工具使用模式） |
| `build_context_memory.py` | 抽取上下文类记忆（项目/任务上下文） |
| `build_preference_memory.py` | 抽取偏好类记忆（行为偏好、习惯） |
| `build_memory_graph.py` | 构建记忆关系图（节点+边） |
| `query_graph.py` | 图查询接口 |

### 共享模块

| 脚本 | 职责 |
|------|------|
| `common.py` | 纯工具函数（hash/norm/ID生成/CSV写入等），无副作用 |
| `rules.py` | 分类规则常量（TOPIC_RULES v1 对照 + PURE_TOPIC_RULES v2 纯净版） |
| `local_embed.py` | bge-small-zh-v1.5 懒加载单例，CUDA 优先，CPU 回退 |
| `chroma_client.py` | 轻量 ChromaDB REST 客户端（绕开 httpx 兼容性问题） |

### 服务层

| 脚本 | 职责 | 端口 |
|------|------|------|
| `unified_search.py` | 统一检索后端（CLI+模块双用途） | 无（本地函数） |
| `api_server.py` | REST API 服务（标准库 http.server） | 8000 |
| `mcp_server.py` | MCP Server（stdio 协议） | stdio |
| `dashboard.py` | Streamlit 交互可视化（5页面） | 8501（Streamlit 默认） |
| `search_vectors.py` | 简化版语义检索脚本（早期遗留） | 无 |

### 接入示例（examples/）

| 脚本 | 接入方式 |
|------|---------|
| `openai_function_calling.py` | OpenAI 函数调用 |
| `langchain_tool.py` | LangChain Tool |
| `rag_inject.py` | RAG 上下文注入（两种策略：长期画像+动态事件） |
| `README.md` | 示例使用说明 |

---

## 规划文档目录

```
.planning/
└── codebase/
    ├── STACK.md           # 技术栈
    ├── INTEGRATIONS.md    # 外部集成
    ├── ARCHITECTURE.md    # 系统架构
    ├── STRUCTURE.md       # 目录结构（本文件）
    ├── CONVENTIONS.md     # 代码规范
    ├── TESTING.md         # 测试覆盖
    └── CONCERNS.md        # 技术债与风险

.gsd/
└── phases/
    ├── 01_*/              # Phase 01: 数据摄入与统合
    ├── 02_*/              # Phase 02: 向量化与语义检索
    ├── 03_*/              # Phase 03: 统一检索层 + 四类接入
    └── 04_memory_layer_upgrade/
        ├── CONTEXT.md     # Phase 04 规划背景
        └── PLAN.md        # Phase 04 执行计划
```
