# integration

integration对应架构图左侧的大模块：接收 Google、GPT、Agent 等数据模块已经清洗好的structured，建立跨模块实体连接，并生成面向个人系统的综合analysis。

## 角色

```text
Google / GPT / Agent 数据模块
  -> 结构化 SQLite
  -> integration
  -> 统一事件 / 实体 / 关系 / 综合分析
```

integration不保存各来源的原始导出文件。raw继续留在各数据模块中。

## 目录

```text
integration/
  raw_index/
  structured/
  analysis/
  db/
  scripts/
  README.md
```

## 输入

- `Google/structured/db/google_data.sqlite`
- `GPT/structured/db/chatgpt_data.db`
- `Agent/structured/db/agent_data.sqlite`

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

消费入口：

```powershell
python integration\scripts\unified_search.py memory --type tooling
python integration\scripts\unified_search.py memory --subject Codex --neighbors 2
python integration\scripts\build_profile_from_memory.py
python integration\scripts\evaluate_memory_depth.py
python integration\scripts\mine_deep_memory_graph.py --output-json
python integration\scripts\build_deep_memory_profile.py --evaluate
```
