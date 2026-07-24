# 目录结构

> **阅读建议：** 不需要记所有目录。先看根目录 9 个区域的作用，然后看 `src/personal_knowledge/` 的分层，其余用到再查。

---

## 根目录：9 个区域

```
D:\ADLINK\数据分析/
│
├── src/                    ← 产品源码（核心，git track，R2）
├── apps/                   ← 外部应用（ChatGPT MCP + Decision Cockpit）
├── data/                   ← 私有数据（git ignore，R4，不能提交）
├── var/                    ← DB/运行时/日志（git ignore，R4）
├── governance/             ← 治理策略（git track，R2，fail-closed）
├── docs/                   ← 文档（git track，R1）
├── tests/                  ← 测试（git track，R1）
├── assets/                 ← 版本化资源（git track，R2）
├── archive/                ← 隔离区（git ignore，R4）
├── .planning/              ← GSD 规划（git track，R2）
└── integration/            ← 遗留脚本位置（迁移过渡）
```

**窍门：** 处理个人数据时（`data/`、`var/`）永远记得它们是 R4 级隐私，不能提交、不能打包、不能公开报告。治理脚本 `preflight.py` 会检查你有没有不小心把密钥提交上去。

### 各区域详细

#### `data/` — 个人数据层

```
data/
├── raw/                    # 原始数据（AgentsView 导出、Google Takeout 原始文件）
├── staging/                # 暂存区
├── canonical/              # 规范化权威数据
│   └── agent/structured/db/
│       ├── agentsview_normalized.sqlite
│       └── agent_conversations.sqlite    ← 对话 SSOT
│   └── google/structured/db/
│       └── google_data.sqlite
└── imports/                # 导入缓存
```

**规则：** 只读，修改要通过 `pk-sync` 命令。

#### `var/` — 运行时层

```
var/
├── db/                     # SQLite 数据库
│   ├── personal_system.sqlite            ← 统一库（核心）
│   ├── knowledge_index_active.txt        ← 知识索引指针
│   ├── decision_orchestration.sqlite     ← 决策编排
│   ├── decision_analysis.sqlite          ← 决策分析
│   ├── project_pilot.sqlite              ← Pilot
│   ├── recommendation_calibration.sqlite ← 校准
│   └── external_context.sqlite           ← 外部上下文
├── reports/analysis/       # 分析报告
│   └── ai_context/         # AI 上下文文档
├── logs/                   # 运行日志
├── runtime/                # 运行时锁/状态
└── cache/                  # 缓存
```

**规则：** 随时可变，不备份也可重建。

#### `governance/` — 治理策略

```
governance/
├── policies/               # YAML 策略文件（9 个）
│   ├── architecture.yaml   # 源码分层 + 区域定义
│   ├── artifact_layers.yaml # D/S/R/A 制品分层
│   ├── privacy.yaml        # R1-R4 隐私等级
│   ├── retention.yaml      # 保留与处置策略
│   ├── paths.yaml          # 路径规则（gitignore 配置）
│   ├── external_sources.yaml
│   ├── decision_analysis.yaml
│   ├── dependencies.yaml
│   └── planning.yaml
├── manifests/              # 迁移清单
├── baselines/              # 基准快照
├── reports/                # 审计报告
└── schema/                 # schema 定义
```

**规则：** 这目录 fail-closed，任何修改要慎重。

---

## 源码分层 `src/personal_knowledge/`

```
src/personal_knowledge/
│
├── core/                   ← 地基（任何模块都可能引用）
│   ├── llm.py              # LLM 调用封装（OpenAI/Vertex 兼容）
│   ├── local_embed.py      # 嵌入模型(bge-small-zh-v1.5, 512维)
│   ├── chroma_client.py    # Chroma REST 客户端
│   ├── project_paths.py    # 所有路径的真相源
│   ├── privacy_guard.py    # 出站数据隐私封存
│   └── sqlite.py           # SQLite 工具
│
├── retrieval/              ← 检索层（搜索入口）
│   ├── unified_search.py   # 统一检索 facade（只重新导出）
│   ├── semantic_search.py  # 混合语义检索（核心逻辑）
│   ├── events_query.py     # 精确查询 + data contract
│   ├── memory.py           # 记忆层查询
│   ├── search_vectors.py   # Chroma 向量查询底层
│   ├── merge_cluster.py    # 合并层折叠
│   ├── evidence.py         # 证据解析
│   ├── relevance.py        # 证据门禁
│   └── serving.py          # 服务快照
│
├── services/               ← 对外服务
│   ├── api_server.py       # REST API（端口 8000）
│   ├── mcp_server.py       # MCP Server
│   └── dashboard.py        # Streamlit 仪表盘
│
├── application/            ← Canonical 构建
│   ├── sync.py             # 对话同步
│   ├── ku.py               # 知识单元 CLI 入口
│   ├── conversation/       # 对话处理
│   ├── knowledge/          # 知识单元构建/提取
│   ├── memory/             # 记忆构建
│   └── serving/            # 服务快照
│
├── intelligence/           ← 智能分析
│   ├── service.py          # 个人状态
│   ├── decision/           # 决策推荐
│   ├── proactive/          # 主动情报
│   └── orchestration/      # 受控编排
│
├── governance/             ← 治理执行
│   ├── preflight.py        # 合规检查入口
│   └── artifact_registry.py # 制品注册表验证
│
├── evaluation/             ← 评测套件
│   └── knowledge/
│       ├── evaluate_knowledge_canary.py
│       └── evaluate_knowledge_unit_rag.py
│
└── cli.py                  # CLI 入口（6 个命令注册）
```

### 分层依赖规则（记这 3 条就够了）

```
- core     可以引用谁？→ 只能引用自己（地基）
- retrieval/application/services 可以引用谁？→ core + 同级
- governance    呢？→ 只能引用自己（独立控制面）

违反规则 → preflight --ci 会报 P1 违规
```

---

## 外部 App

```
apps/
├── personal_data_chatgpt/       # ChatGPT MCP App
│   ├── server.mjs               # MCP HTTP Server（端口 8789）
│   ├── public/                  # 前端 Widget
│   │   ├── data-browser-widget.html
│   │   ├── memory-graph-widget.html
│   │   └── relation-review-widget.html
│   ├── scripts/
│   │   ├── start-services.ps1   # 一键启动脚本
│   │   └── 启动服务.bat
│   └── contracts/               # MCP 工具定义
│
└── personal_decision_cockpit/   # Decision Cockpit 前端
    └── src/                     # React/TypeScript/Vite
```

---

## 数据库文件对照

| 文件 | 内容 | 产生方式 | 隐私级 |
|------|------|----------|--------|
| `var/db/personal_system.sqlite` | 统一库（核心） | 由 build pipeline 生成 | R4 |
| `data/canonical/.../agent_conversations.sqlite` | 规范对话库（对话 SSOT） | `pk-sync conversations --write` | R4 |
| `data/canonical/.../agentsview_normalized.sqlite` | 归一化对话 | `pk-sync conversations --write` | R4 |
| `data/canonical/.../google_data.sqlite` | 规范 Google 数据 | `pk-sync google --write` | R4 |
| `var/db/decision_orchestration.sqlite` | 决策编排 | intelligence 流程 | R4 |
| `var/db/decision_analysis.sqlite` | 决策分析 | intelligence 流程 | R4 |
| `var/db/knowledge_index_active.txt` | 知识索引文本指针 | promote 时写入 | R2 |
