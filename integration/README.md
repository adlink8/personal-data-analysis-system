# integration

integration对应架构图左侧的大模块：接收 Google、GPT、Agent 等数据模块已经清洗好的structured，建立跨模块实体连接，并生成面向个人系统的综合analysis。

## 角色

```text
Google / GPT / Agent 数据模块
  -> 结构化 SQLite
  -> integration
  -> 统一事件 / 实体 / 关系 / 综合分析
  -> 知识单元索引 (Chroma active) + 分发接口
```

integration不保存各来源的原始导出文件。raw继续留在各数据模块中。

## 数据分发接口(CLI / REST / MCP)

统一后端：`scripts/vector/unified_search.py`（根目录 shim 仍可用）。

| 能力 | CLI | REST | MCP |
|------|-----|------|-----|
| 语义检索(knowledge-first) | `unified_search.py semantic` | `POST /search/semantic` | `search_semantic` |
| 知识索引状态 | `unified_search.py knowledge` | `GET /knowledge` | `knowledge_status` |
| 统计(含 knowledge) | `stats` | `GET /stats` | `stats` |
| 事件/记忆分页导出 | — | `/data/*` | `data_*` |
| 精确查询 | `query` | `POST /search/query` | `query_events` |

Active 指针：`integration/db/knowledge_index_active.txt`。  
promote/rollback **不**经分发接口，使用 `promote_knowledge_index.py` / `rollback_knowledge_checkpoint.py`。

## 目录

```text
integration/
  raw_index/
  structured/
  analysis/          # 系统级报告 + ai_context（含 test_coverage_gaps）
  db/                # personal_system.sqlite、active knowledge pointer
  scripts/           # 实现分包 + 根目录兼容 shim（见 scripts/README.md）
    core/ knowledge/ memory/ conversation/
    graph/ vector/ services/ pipeline/
    source_adapters/ examples/ _tools/
  evals/             # 冻结评测集
  apps/              # ChatGPT App 等
  prompts/           # LLM prompt 版本
  README.md
```

## 输入

- `Google/structured/db/google_data.sqlite`（可选；Google analysis 已归档）
- `Agent/structured/db/`（会话证据主源：`agent_conversations` / `agentsview_normalized` / `agent_data`）
- 历史 GPT 源库若需要可从 `_recycle/2026-07-12_structure_cleanup/GPT/` 恢复

## 输出

- `db/personal_system.sqlite`
- `structured/unified_events.csv`
- `structured/entities.csv`
- `structured/event_entities.csv`
- `structured/entity_links.csv`
- `analysis/module_summary.csv`
- `analysis/cross_module_insights.csv`
- `analysis/integrated_system_report.html`
- `analysis/profile.md`
- `analysis/profile.html`
- `analysis/profile.json`
- `analysis/profile_data_flow.csv`
- `analysis/profile_growth_monthly.csv`
- `analysis/profile_growth_chart.png`
- `analysis/profile_focus.csv`
- `analysis/profile_thinking_mode.csv`
- `analysis/memory_report.md`
- `analysis/capability_report.md`
- `analysis/context_report.md`
- `analysis/preference_report.md`
- `analysis/graph_report.md`
- `analysis/memory_graph.html`
- `analysis/ai_context/person_profile.md`
- `analysis/ai_context/person_profile_v2.md`
- `analysis/ai_context/memory_depth_readiness.md`
- `analysis/ai_context/deep_memory_mining.json`
- `analysis/ai_context/deep_memory_insights.json`
- `analysis/ai_context/deep_memory_insights.md`
- `analysis/ai_context/deep_memory_profile.md`
- `analysis/ai_context/deep_profile_evaluation.md`
- `analysis/ai_context/vector_collection_health.md`
- `analysis/ai_context/vector_retrieval_eval_report.md`
- `analysis/ai_context/graph_relation_eval_report.md`
- `analysis/ai_context/graph_relation_candidate_proposals_report.md`
- `analysis/ai_context/memory_evidence_bundles_preview.md`
- `analysis/ai_context/memory_candidate_extraction_report.md`
- `analysis/ai_context/memory_promotion_report.md`
- `analysis/ai_context/memory_gate_repair_report.md`
- `db/conversation_graph.duckdb`

## 重建

从数据分析根目录运行：

```powershell
python integration\scripts\build_integrated_system.py
```

生成深度画像：

```powershell
python integration\scripts\build_deep_profiles.py
```

## 核心表

- `source_modules`：来源模块清单。
- `unified_events`：统一事件表。
- `entities`：主题、工具、域名、文件、会话、技能等实体。
- `event_entities`：事件和实体的关系。
- `entity_links`：跨模块实体连接。
- `memory_items`：长期记忆对象(tooling / preference / capability / fact / project / habit)。
- `memory_links`：记忆对象到原始事件的证据链。
- `memory_relations`：记忆对象之间的图谱关系。
- `memory_items.metadata`：Phase 05 起统一含 `evidence_ids` / `confidence` / `last_seen` / `source_hash` / `merge_key`。
- `module_summaries`：模块级摘要。
- `cross_module_insights`：综合分析结果。
- `memory_evidence_bundles`：Phase 09 结构化证据 bundle 审计表，只承接事件/turn/accepted graph edge，不直接承接长期记忆写入。

## 深度画像

深度画像基于 `personal_system.sqlite` 生成，不改变raw和structured库。

- module_profile：输出到 `Google/GPT/Agent` 各自的 `analysis/module_profile.*`。
- profile：输出到 `integration/analysis/profile.*`。
- 数据流向：说明 `raw -> structured -> analysis -> integration` 的证据链。
- 数据增长：按月统计各来源进入统合层的事件增长。
- 关注点：按主题、服务/工具、原始分类聚合。
- 个人思考：基于行为文本的模式推断，用于复盘和 AI 上下文建设，不是心理诊断。

## 记忆层

记忆层基于统合事件和增强表生成，不删除原始事件。

- `memory_items` 把事件折叠成可消费的长期记忆对象。
- `memory_links` 保留每条记忆背后的原始事件证据。
- `memory_relations` 把工具、能力、偏好、项目、事实、习惯连成图谱。
- `person_profile_v2.md` 是面向 AI system prompt 的记忆图谱版用户画像。
- `memory_depth_readiness.md` 是进入 Phase 06 前的深挖准入门槛报告。
- `deep_memory_mining.json` 只保存通过 readiness gate 的深挖事实层结果。
- `deep_memory_profile.md` 面向 agent prompt，强调模式、演化和反例，而不是静态标签。
- Phase 06 不自动写回 `memory_items`，避免把推测污染长期记忆。

Phase 05 补强：

- `scripts/source_adapters/` 提供 source adapter contract 和 `google_activities.py` 样例。
- `scripts/memory_governance.py` 统一治理 metadata。
- `tests/test_memory_contracts.py` 验证 core / CLI / REST / MCP 记忆查询契约。

Phase 09 候选管道：

```text
script coarse recall
-> LLM candidate proposal
-> deterministic evidence gate
-> LLM judgment
-> deterministic evidence gate
-> memory_evidence_bundles
-> LLM memory candidate extraction
-> weighted promotion gate
-> human review / auto-approved apply(dry-run first)
```

- `build_graph_relation_candidates_v2.py` 只把 recall signal 打包给 LLM；没有 live LLM 时只写 blocked 审计，不把 recall pair 直接写成候选事实。
- `build_memory_evidence_bundles.py` 是结构化 evidence 的硬边界。`unified_events_rich`、`conversation_turns_summary`、accepted graph edges 必须先进入 `memory_evidence_bundles`，不能直接变成 promotion candidate。
- `extract_memory_candidates_from_bundles.py` 是唯一 active 的 structured-evidence -> `llm_memory_candidate` 入口；无 live LLM 时明确 blocked，不伪造候选。
- `evaluate_memory_promotion_candidates.py` 负责 weighted promotion gate；`repair_memory_promotion_candidates.py` 只根据 failure reasons 做 repair / downgrade / reject，不编造新证据。
- `apply_memory_promotions.py` 当前默认 dry-run，仅展示 `approved && human_review_required=false` 的潜在动作；长期三表 `memory_items` / `memory_links` / `memory_relations` 不在这一步被静默改写。

消费入口：

```powershell
python integration\scripts\unified_search.py memory --type tooling
python integration\scripts\unified_search.py memory --subject Codex --neighbors 2
python integration\scripts\build_profile_from_memory.py
python integration\scripts\evaluate_memory_depth.py
python integration\scripts\mine_deep_memory_graph.py --output-json
python integration\scripts\build_deep_memory_profile.py --evaluate
```

## 数据访问接口

Phase 12 在 `scripts/unified_search.py` 增加了只读数据访问 contract，供 REST、MCP Apps、离线分析和可视化复用。

核心能力：

- `list_events_contract()`：分页浏览 `unified_events`，支持 `limit/offset/source/service/category/start_time/end_time/keyword/fields`。
- `export_events_contract()` / `export_all_contract()` / `export_query_contract()`：有界导出 JSONL / CSV。
- `list_memories_contract()`：分页浏览 `memory_items`。
- `list_relations_contract()`：分页浏览 `memory_relations`；传 `status=review|accepted|rejected` 时浏览 LLM judgment 关系。
- `get_event_by_id_contract()` / `get_memory_by_id_contract()`：按精确 id 取记录。
- `aggregate_contract()`：按 `source/service/category/month/memory_type/relation_type` 统计。
- `timeline_contract()`：按时间桶统计主题趋势。
- `data_quality_report_contract()`：检查缺失字段、重复 id、断链和 LLM judgment 状态。

接入面：

- REST：`api_server.py` 暴露 `/data/*`。
- stdio MCP：`mcp_server.py` 暴露 `data_list_events`、`data_export_all`、`data_export_query`、`data_list_memories`、`data_list_relations`、`data_aggregate`、`data_timeline`、`data_get_event_by_id`、`data_get_memory_by_id`、`data_quality_report`。
- ChatGPT Apps：`personal_data_chatgpt/server.mjs` 暴露同名 `data_*` tools，并提供 `show_data_browser` widget 通过 bridge 调用这些 tools。

REST 路径：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/data/events` | 分页事件列表，默认不含完整正文 |
| GET | `/data/export` | 有界 JSONL/CSV 导出 |
| GET | `/data/memories` | 分页长期记忆 |
| GET | `/data/relations` | 分页长期记忆关系，支持 `relation_type/subject/status` |
| GET | `/data/aggregate` | 聚合统计 |
| GET | `/data/timeline` | 主题时间线 |
| GET | `/data/event/<id>` | 精确事件读取 |
| GET | `/data/memory/<id>` | 精确记忆读取 |
| GET | `/data/quality` | 数据质量报告 |

当前真实库验证基线：

- `unified_events`: 8136
- 来源聚合：Agent 4324、Google 2016、GPT 1796
- `memory_items`: 194
- `memory_relations`: 27
- 质量检查：重复 event_id 为 0；缺失 `event_time` 为 1060；缺失 `title` 为 1618。
