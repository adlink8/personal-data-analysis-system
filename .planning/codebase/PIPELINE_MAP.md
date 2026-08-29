# 离线数据/知识流水线全景图（PIPELINE_MAP）

**Analysis Date:** 2026-08-29
**方法:** 全部 sqlite 以 `file:...?mode=ro` 只读打开核对表与行数；代码只读。未做任何写操作（本文档除外）。
**根目录:** `D:\ADLINK\数据分析`

---

## 0. 对背景假设的两处修正（有 SQL 证据）

1. **"graph/build_merge_layer.py 的 L1/L2/L3 从未运行、var/db 无产物" —— 不成立。**
   `var/db/personal_system.sqlite` 中 `merge_clusters = 470 行`、`merge_members = 1,628 行`、`merge_build_meta = 21 行`（含 `threshold_l2_cos=0.88`、`l2_max_size=50`、`elapsed_sec=4.9` 等 key-value），与 `src/personal_knowledge/application/graph/build_merge_layer.py` 文档头声明的产出表完全一致。该合并层构建器实际运行过（merge_build_meta 记录了 21 项构建参数/统计）。
2. **"canonical 库可见投影 1,267 会话/73,939 消息"** —— canonical 全量表计数是 `canonical_sessions=2,426 / canonical_messages=174,269`（多代事件累积）；1,267/78,841 与 staging 影子库 `data/staging/v2/agent_conversations_v2.sqlite` 的计数一致。可见性不是 DB 表/视图（canonical 库 sqlite_master 中无 `canonical_visibility`），而是代码谓词 `canonical_projection_predicate`（`src/personal_knowledge/core/canonical_visibility.py`），被 `application/knowledge/eligibility.py:107,110,193`、`application/knowledge/delta_build.py:28`、`tmp/mvp_semantic_compress.py:37` 引用。谓词过滤后的精确计数：未验证（需运行代码）。

---

## 1. 数据层与 schema 全量分类

### 1.1 数据库文件地图（有数据的核心库）

| 库 | 角色 | 关键表 × 行数 |
|---|---|---|
| `data/canonical/agent/structured/db/agent_conversations.sqlite` | 正式 canonical（事件权威） | `ce_events` 3,026,243；`ce_event_relations` 1,132,415；`canonical_messages` 174,269；`canonical_tool_events` 323,050；`canonical_sessions` 2,426；`ce_sessions` 6,296；`ce_field_dispositions` 104,003；`ce_source_artifacts` 804；`ce_adapter_runs` 60；`ce_event_generations` 5；`ce_generation_authority` 5；`crosswalk_review` 0 |
| `data/staging/v2/agent_conversations_v2.sqlite` | Phase 62 shadow/staging（D-15/D-31 零付费） | `canonical_messages` 78,841；`canonical_sessions` 1,267；`ce_events` 1,194,471；`ce_generation_authority` 1 |
| `data/canonical/agent/structured/db/agentsview_normalized.sqlite` | AgentView 快照规范化（遗留隔离对象） | `messages` 94,958；`sessions` 1,159；`tool_events` 110,456；`usage_events` 8,732；`source_tombstones` 10 |
| `data/canonical/agent/structured/db/agent_data.sqlite` | agent 域结构化库（v1 统合管线一代） | `agent_messages` 37,884；`sessions` 846；`skills` 590；`memories` 363；`source_files` 4,160；`database_tables` 126 |
| `data/canonical/google/structured/db/google_data.sqlite` | Google 域（在役） | `normalized_events` 1,696（+FTS）；`google_light_assertions` 96；`google_structure_runs` 2 |
| `var/db/personal_system.sqlite`（294 MB） | A 层权威库（~80 表） | 见 1.2 |
| `var/db/semantic_mvp_v3.sqlite` | MVP 轨道在产 | `session_cards` 173；`ku_facts` 1,037；`chunk_summaries` 216 |

### 1.2 `src/personal_knowledge/core/schema_ddl.py` 全部 CREATE TABLE × 行数 × 状态
（实际数据在 `var/db/personal_system.sqlite`；行数为 2026-08-29 只读实测）

**Phase 14 知识核心段（`SCHEMA_SQL`）**

| 表 | 行数 | 状态判定 |
|---|---|---|
| `knowledge_build_runs` | 3 | 有数据：1 条 `run_type='index', status='current'`（kg_20260812T025401Z_live，即空索引构建）；2 条 `run_type='incremental', status='pending'`（ir_b0099928a0ad7f5e / ir_6d1c610127139045，model=gemini-3.5-flash-lite，2026-08-12T02:56Z） |
| `knowledge_units` | 0 | 空表（知识抽取从未产出） |
| `knowledge_unit_evidence` | 0 | 空表 |
| `canonical_knowledge_units` | 0 | 空表（merge 从未产出） |
| `canonical_unit_members` | 0 | 空表 |
| `knowledge_index_versions` | 1 | 有数据：`kiv_kg_20260812T025401Z_live` → collection `knowledge_units_empty_kg_20260812T025401Z_live`，`unit_count=0, status='active'`（**active 指针指向显式空索引**） |

**Phase 14 Plan 02 backfill 段**

| 表 | 行数 | 状态 |
|---|---|---|
| `knowledge_inventory` | 0 | 空表 |
| `knowledge_inventory_registry` | 1 | 有数据（delta 注册） |
| `knowledge_inventory_items` | 0 | 空表 |
| `knowledge_run_items` | 24,487 | 有数据：**D-30 封存的消息级 pending 队列**（与 62-CONTEXT.md 数字 3,224 user + 21,263 assistant 完全吻合） |
| `knowledge_response_cache` | 0 | 空表（无 LLM 响应缓存 → 付费提取从未发生） |
| `knowledge_extraction_gates` | 0 | 空表 |
| `knowledge_source_watermark` | 0 | 空表 |

**Phase 14 Plan 05 RAG 段**：`rag_runs` 0 / `rag_retrieval_items` 0 / `rag_feedback` 0 —— 全空。
**Plan 07 delta 段**：`knowledge_delta_inventories` 1；`knowledge_delta_items` 24,487 —— delta 冻结运行过一次（与 run_items 同源）。

**Phase 23 artifact/serving 段（在役）**：`artifact_registry_entries` 17；`artifact_versions` 46；`source_watermarks` 43；`serving_snapshots` 19；`serving_snapshot_members` 181；`serving_authority` 1（active=`ss_37041cc36becd1013056e9db`，2026-08-17T00:03Z 激活）；`serving_snapshot_events` 60。

**Phase 25 personal state 段（试点 1 次）**：`personal_state_runs` 1；`personal_state_publications` 1；`personal_state_assertions` 3；`personal_state_evidence` 3；`personal_state_changes` 0；`personal_state_risks` 0。

**Phase 26 decision feedback 段（试点 1 次）**：`decision_runs` 1；`decision_recommendations` 1；`decision_support_refs` 1；`decision_confirmations` 1；`decision_actions` 3；`decision_outcomes` 1；`decision_effectiveness` 1；`decision_events` 7。

**Phase 27 proactive 段（试点 1 次）**：`proactive_runs` 1；`proactive_coordination_items` 1；`proactive_candidates` 1；`proactive_candidate_support` 2；`proactive_evaluations` 1；`proactive_control_events` 2；`proactive_surface_events` 1。

**非 schema_ddl 的同库表（v1 管线所建，有数据）**：`unified_events` 11,370；`unified_events_rich` 11,370；`event_entities` 63,819；`entities` 5,149；`entity_links_v2` 7,220；`event_categories_v2` 11,370；`merge_clusters` 470；`merge_members` 1,628；`merge_build_meta` 21；memory 族（`memory_items` 291、`memory_links` 1,771、`memory_relations` 67、`memory_promotion_candidates` 1,370、`memory_evidence_bundles` 11,310、`memory_candidate_extraction_progress` 2,503 等）。

**结论：正式知识层（KU）内容表 100% 为空；有数据的只有"台账/冻结/队列"与 v1 memory 层。系统当前知识事实 = v1 memory_* 表 + MVP v3 sqlite（旁路），而不是 schema_ddl 定义的 KU 权威层。**

---

## 2. 流水线代际

### 代际 A —— v1/遗留统合管线（~2026-06，被封存/部分在役）
- 编排器：`src/personal_knowledge/application/run_pipeline.py`。文件头自述 **deprecated**："Product day-to-day sync is `pk-sync conversations [--write]`. This module retains steps 1–12 for forensics only and requires `--legacy-integrated`"，需环境开关 `PK_ALLOW_LEGACY_PIPELINE=1`。13 步：build_integrated_system → enrich_unified_events → **build_merge_layer（L1/L2/L3）** → build_deep_profiles → memory 4 件套 → build_memory_graph → build_vector_store（Chroma personal_events）→ build_context_doc → build_profile_from_memory → build_conversation_vector_store（步骤 13，Wave 7）。
- `application/graph/build_merge_layer.py`：L1 真重复/L2 同主题/L3 保留，余弦+Jaccard+骨架去重三重门槛；**已运行**（见 §0 修正 1）。
- `application/memory/`（16 个 py）：`build_memory_store/capability/context/preference_memory.py`、`build_memory_graph.py`、`build_memory_promotion_candidates.py`、`mine_deep_memory_graph.py` 等 → A 层 memory_* 表（有数据，仍被 `retrieval/memory.py` 服务）。**在役**。
- `build_deep_profiles.py`、`build_context_doc.py`（application 根）：v1 上下文文档生成。产物在 `var/reports/analysis/ai_context/`。
- `build_conversation_summary.py`：**文件已不存在于工作树**（全仓 find 无果；仅 `run_pipeline.py:21-23` 注释仍引用）。其历史产物 `var/reports/analysis/ai_context/conversation_summaries.json` 仍在。`archive/README.md`："Tracked legacy-pipeline source was retired from the cleanup branch on 2026-08-23"，pre-cleanup 状态在分支 `codex/archive-pre-cleanup-20260823`。
- 状态：**编排封存（fail-closed 门禁），memory 派生层在役**。

### 代际 B —— 正式 view-policy/KU 轨道（Phase 14–21 + Phase 62，代码完成、成本门锁定）
- CLI：`src/personal_knowledge/application/ku.py`（pk-ku inspect/prepare/extract/canonical/publish/vector/extract-gate/canary/promote/watermark/reconcile/history/doctor）。头注释即产品操作手册。
- 候选台账：`application/knowledge/view_candidate_prepare.py` 定义 `ce_candidate_runs` / `ce_candidate_estimates` / `ce_candidate_audit`（:78/:102/:115）——**这三张表在 canonical 库与 staging 库的 sqlite_master 中均不存在 → 该 prepare 从未跑到建表步骤**（未验证 ≠ 永不，但与 D-30/D-31 锁定一致）。
- 提取硬门：`application/ku.py:613-637` —— view-policy run 一律拒绝 extract；:618 "Phase 62-06 D-31: view-policy runs are never extractable in this phase."
- D-30 / D-31 决策原文（`.planning/phases/PDA-62-multi-format-conversation-adapters-unified-event-authority-a/62-CONTEXT.md:67-68`）：
  > **D-30:** The two existing message-level prepare runs—3,224 user items and 21,263 assistant items, 24,487 calls / 48,974,000 estimated tokens / USD 24.487 total—must not be extracted. Phase 62 may supersede or invalidate their queue semantics without deleting their audit history.
  > **D-31:** No `pk-ku extract`, provider generation, paid semantic labeling, or full rebuild is authorized by this phase plan. Planning and deterministic/replay testing must remain zero-paid-call; any later representative LLM pilot requires a separate explicit user cost approval checkpoint.
- 状态：**封存（零执行）**。实际发生过的是：inventory/delta 冻结 1 次 + 24,487 条 pending 队列 + 空知识索引 promoted 为 active（2026-08-12，配合 `application/knowledge/legacy_isolation.py` + `isolate_legacy_knowledge.py` 的"遗留隔离"fail-closed 状态机：隔离 derived knowledge 表、切换 serving snapshot、promote 空 KU collection）。

### 代际 C —— MVP 语义压缩（唯一在产出的知识线）
- `tmp/mvp_semantic_compress.py`：只读打开 canonical（`file:...?mode=ro`）→ 调 pi kernel（purpose=conversation_summary）→ 写 `var/db/semantic_mvp_v3.sqlite`。pilot 12 会话；scale 模式压缩全部可见会话（>=200 strip 字符，3 并发，成本硬顶 `PK_MVP_COST_CAP` 默认 ¥8）。v1/v2 库作为对照证据永不重写。产出 `session_cards` 173 / `ku_facts` 1,037 / `chunk_summaries` 216；报告 `tmp/mvp_recall_report_v3.json`（2026-08-29 15:25）、`tmp/mvp_compression_report_v3.md`。
- 状态：**在役**（v3 库 mtime 2026-08-29 15:39，本测绘当日仍在迭代）。

### 外围在役线（非知识生产，但流水线上下游）
- **D 层同步**：`application/sync.py`（`pk-sync conversations`）+ `application/conversation/v2_sync.py`（Phase 62-04 dry-run/shadow/activation 编排，"never touches the live canonical stores (D-15/D-31); staging goes to a caller-supplied shadow db"）+ `adapters/conversation_sources/` + `conversation/event_generations.py`/`event_repository.py`/`extraction_views.py`/`extraction_policy.py`（ce_* 事件权威，300 万级 ce_events）。
- **检索/服务**：`retrieval/*`（§3 组 2）、`mcp_tools/tool_definitions.py`、`services/`（harness/serving）。
- **决策/内核侧台账**：`var/db/pi_kernel_*`（events 2,050 / tasks 556 / sessions 552，2026-08-29 当日仍写）、`decision_analysis.sqlite`、`decision_orchestration.sqlite`、`recommendation_calibration.sqlite`、`project_pilot.sqlite`、`evaluation_registry.sqlite`（eval_runs 40 / eval_metrics 145）。

---

## 3. 重复实现全集（核实后的判定）

**组 1：向量库构建器 —— 名义 3 套，实为 3 个不同 collection 的 builder + 2 层历史兼容副本**
| 实现 | 路径 | 目标 collection | 状态 |
|---|---|---|---|
| 事件向量库（v1） | `src/personal_knowledge/retrieval/build_vector_store.py` | `personal_events` | 曾运行（Chroma 服务端数据，仓内无 chroma.sqlite3） |
| 会话 turn 向量库（Wave 7） | `src/personal_knowledge/application/conversation/build_conversation_vector_store.py` | `conversation_turns`（输入 `conversation_summaries.json`） | 依赖的 summary 生成器已被撤 → 事实停摆 |
| KU 向量库（Phase 14 Wave 4.1） | `src/personal_knowledge/application/knowledge/build_knowledge_unit_vector_store.py` | `knowledge_units_<build_id>` 版本化 | 建过（promote_log 有 2026-07-10 两次 promote/rollback），现为空索引 active |
| domains facade 镜像 | `src/personal_knowledge/domains/conversation|knowledge/build_*.py` | — | 66 个 domains 文件中 62 个是 "Re-export facade"（2026-08-13 cleanup 窗口），canonical 在 `application/` |
| v1_1 兼容副本 | `tools/compat/v1_1/`（84 文件） | — | 旧路径兼容副本层 |
**判定：该留 `application/` 三个 builder（职责不同，非同职责三份拷贝）；真正的冗余是 domains/ facade 层与 tools/compat/v1_1 副本层，待兼容窗口结束后删除。**

**组 2：检索入口 —— facade + 拆分，非平行双实现**
- `retrieval/unified_search.py` = 门面（自述"原 3,221 行已拆分为 _constants/_db_utils/semantic_search/google_assertions/events_query/memory/merge_cluster"），保留 backend API 兼容。
- `retrieval/search_vectors.py` = Chroma 底层查询（personal_events / conversation_turns，本地 bge-small-zh-v1.5 embedding，`core/local_embed.py`；Chroma 为 localhost:8001 REST 服务，`core/chroma_client.py`）。
- `retrieval/semantic_search.py` = hybrid 分层检索（KU → dialogue → Google → pad，Phase 15/22 contract，见 `retrieval/_constants.py`），包装 search_vectors。
- 文档层重复：`docs/legacy/retrieval-ssot.duplicate.md` vs `docs/architecture/retrieval-ssot.md`。
**判定：该留现结构；删除 legacy 文档副本。**

**组 3：聚类器 —— 构建/读取分离，非重复**
- 构建器：`application/graph/build_merge_layer.py`（写 merge_clusters/merge_members，运行过）。
- 读取器：`retrieval/merge_cluster.py`（`merge_stats()`/`cluster()`/`_merge_layer_ready()`，供 unified_search facade 与 api/mcp 使用）。
**判定：保留两者；风险仅在"同语义、双包"的命名混淆。**

**组 4：canonical 迁移/同步 —— v2_sync 为在役权威**
- `application/conversation/build_canonical_agent_conversations.py`（初建期构建器）、`import_agentsview_sessions.py`、`build_agentsview_normalized.py`（AgentView 快照路径，已被隔离）、`rollback_agent_conversation_source.py`、`conversation_source_rollback_log.jsonl`（var/db）。
- 在役：`v2_sync.py`（shadow→activation，经 `event_generations.py` 写 canonical）。
- 一次性迁移集中在 `tools/migrations/`（18 文件：`add_inventory_items_role_column.py`、`abandon_orphan_runs.py`、`repair_candidate_migration_fk.py` 等）。
**判定：保留 v2_sync + event_generations 权威路径；build_canonical_* 与 migrations 归档待审。**

**组 5：图管线（Phase 07"真关系流水线"）—— 构建一次后停摆**
- 权威顺序记录在 `var/db/DEPRECATED.md`（2026-06-28）：build_conversation_vector_store → evaluate_vector_collections → evaluate_vector_retrieval → graph/build_graph_relation_candidates → judge_graph_relations → evaluate_graph_relation_judgments → build_conversation_graph → query_conversation_graph；`build_triple_store.py --only duckdb` 已硬禁用。
- 产物 `var/db/conversation_graph.duckdb`（4.2 MB，mtime 2026-06-28，此后未再构建）。
**判定：代码保留，事实停摆；duckdb 为归档候选。**

---

## 4. 外围目录

**tools/（141 文件）**：`tools/compat/v1_1/` 84（旧路径兼容副本）；`tools/forensics/` 20（`_inspect_*`/`_probe_*` 取证脚本）；`tools/migrations/` 18（一次性 DDL/数据修复）；`tools/supported/` 12（在役：`pi_runtime.py`、`evaluate_pi_kernel.py`、`compare_l1_l2_retrieval.py`、`configure_pi_aliyun.ps1` 等）；`tools/analysis/` 2；散件若干。

**integration/（47 文件）**：`integration/evals/knowledge_units/` 私有冻结评测集（dev/frozen/hard_negative/merge_positive *.private.jsonl）；`integration/db/personal_system.sqlite` **0 字节 stub**（2026-07-17）；`*.bak-phase20` 旧日志；`integration/runtime/governance/` 审计快照；`integration/scripts/`（含 `vector/`、`governance/apply_repository_migration.py`）。

**archive/（7.9 GB / 7,301 文件，已是封存区）**：`archive/phase62/` **7.5 GB**（diagnostic-replays + pre-activation 快照）；`archive/quarantine/` 286 MB（desktop-strays-20260713、knowledge_generations、pre-main-cleanup-20260823）；`archive/planning/.gsd/` 504 KB；`archive/vendor-reference/` 66 MB。治理：`archive/README.md`（恢复需 exact manifest + retention review + approval）。**结论：整体已封存，可保持现状；清理预算大头是 phase62 diagnostic-replays（7.5 GB）。**

**docs/（设计文档清单）**：architecture/：`overview.md`、`repository-zones.md`、`conversation-event-authority.md`、`retrieval-ssot.md`、`domains-slimming.md`、`engineering-and-testing-contract.md`、`conversation-data-quality-audit.md`；runbooks/：`product-sync.md`（含 D-31 dry-run/shadow 章节）、`ku-incremental.md`、`personal-state-intelligence.md`、`proactive-intelligence.md`、`decision-cockpit.md`、`decision-feedback.md`、`pi-aliyun-provider.md`、`dependency-governance.md`、`tooling/tools.md`；wiki/：`04-data-pipeline.md`（D/S/R/A 四层加工叙事）、`06-merge-compression.md`、`11-architecture-roadmap.md` 等 14 篇 + `AUDIT-2026-07-27.md`；legacy/：`retrieval-ssot.duplicate.md`（标记重复）。

**scripts/ 不存在**；另有 `ops/`（agent-stack 启停/状态）、`governance/`（policies/baselines/manifests，含 `storage_budgets.yaml`、`data_disposition.json`——数据处置的既有治理入口）。

---

## 5. var/db 全量盘点（标记，不删除）

| 文件 | 大小 | 最后修改 | 所属系统 | 状态/处置标记 |
|---|---|---|---|---|
| `personal_system.sqlite` | 294,256,640 | 2026-08-17 16:09 | A 层权威库 | **在役** |
| `semantic_mvp_v3.sqlite` | 1,974,272 | 2026-08-29 15:39 | MVP 轨道 v3 | **在役（当日活跃）** |
| `semantic_mvp_v2.sqlite` | 204,800 | 2026-08-29 13:56 | MVP v2（对照证据，"never rewritten"） | 保留（对照） |
| `semantic_mvp.sqlite` | 69,632 | 2026-08-29 12:06 | MVP v1（对照证据） | 保留（对照） |
| `pi_kernel_events.sqlite` | 2,551,808 | 2026-08-29 15:40 | pi kernel 事件 | **在役** |
| `pi_kernel_sessions.sqlite` | 622,592 | 2026-08-29 15:40 | pi kernel 会话 | **在役** |
| `pi_kernel_tasks.sqlite` | 446,464 | 2026-08-29 15:40 | pi kernel 任务 | **在役** |
| `pi_kernel_candidates.sqlite` | 20,480 | 2026-08-04 | pi kernel 候选 | 空表（0 行）→ 闲置 |
| `pi_runtime_activation.sqlite` + `.pointer.json` | 20,480 / 362 | 2026-08-12 | pi 运行时激活 | 在役 |
| `evaluation_registry.sqlite` | 253,952 | 2026-08-23 | 评测台账（40 runs） | **在役** |
| `decision_analysis.sqlite` | 159,744 | 2026-08-12 | 决策分析（intelligence/analysis） | 试点在役 |
| `recommendation_calibration.sqlite` | 196,608 | 2026-08-12 | 校准（intelligence/calibration） | 试点在役 |
| `project_pilot.sqlite` | 114,688 | 2026-08-12 | 试点协议（intelligence/pilot） | 试点在役 |
| `external_context.sqlite` | 204,800 | 2026-07-18 | 外部上下文（external_context/） | 低频在役 |
| `personal_wiki_projection.sqlite` | 45,056 | 2026-07-28 | wiki 投影（application/wiki/consolidate_wiki.py） | 低频在役 |
| `decision_orchestration.sqlite` | 73,728 | 2026-07-19 | 决策编排 | **停摆 → 归档候选** |
| `candidate_review.sqlite` | 24,576 | 2026-08-10 | 候选评审 | 两表均 0 行 → 闲置 |
| `conversation_graph.duckdb` | 4,206,592 | 2026-06-28 | Phase 07 图管线 | **停摆 → 归档候选** |
| `knowledge_index_active.txt` | 46 | 2026-08-17 | KU 索引 active 指针（指向 `knowledge_units_empty_kg_20260812T025401Z_live`） | **在役** |
| `knowledge_index_promote_log.jsonl` | 42,258（167 行） | 2026-08-17 | promote/rollback/promote_refused 审计（含 3 次 fail-closed 拒绝记录） | 在役（审计） |
| `conversation_source.txt` / `conversation_source_rollback_log.jsonl` | 6 / 2,683 | 2026-07-15 | canonical source 切换/回滚审计 | 审计保留 |
| `raw_index/input_tables.csv` | 879 | 2026-07-04 | 早期 CSV 导出 | **归档候选** |
| `structured/*.csv`（entities/entity_links/event_entities/unified_events） | ~18 MB | 2026-07-04 | 早期 CSV 导出 | **归档候选** |
| `backups/personal_system_before_import_20260704.sqlite` | 45,613,056 | 2026-07-02 | 导入前备份 | **归档候选** |
| `backups/recommendation_calibration_before_phase53_rerun_20260812.sqlite` | 126,976 | 2026-08-12 | 校准重跑前备份 | 保留（近期） |
| `DEPRECATED.md` / `README.md` | 1,381 / 481 | 2026-06-28 / 2026-07-13 | 图管线状态说明 / 目录职责 | 在役（文档） |

**var/ 其它**（盘点）：
- `var/backup/agent_conversations.pre-cleanup-20260816.sqlite` = **4,069,511,168 B（4.07 GB）**，canonical 清理前全量备份 → **最大单文件归档候选**。
- `var/backups/`：`personal_system_pre_conflict_resolution_20260811` 与 `personal_system_pre_fk_repair_20260728` 各 **294,256,640 B**（+ 3 个小的 pre-phase60 备份）→ 较旧副本 **归档候选**。
- `var/personal_system.sqlite` = **0 字节**（2026-07-18 stub）→ 可清理候选；`integration/db/personal_system.sqlite` 同为 0 字节 stub。
- `var/tmp_ku_*.py` 约 20 个调试脚本（`tmp_ku_diag.py`…`tmp_ku_diag10.py`、`tmp_ku_cache.py`、`tmp_ku_resume.ps1` 等）→ KU 提取排障遗留，**清理候选**。
- `var/config/pi-provider.json`（含 provider 配置；**未读取内容**——凭据红线）。
- Chroma 向量库本体不在仓内：`core/chroma_client.py` 连 localhost:8001 REST 服务，仓内无 `chroma.sqlite3`。各 collection 实际内容：**未验证**（服务不一定在运行）。

---

## 6. 结论

### 6.1 设计代际 × 组件 × 状态 × 处置建议总表

| 代际 | 组件 | 路径 | 状态 | 处置建议 |
|---|---|---|---|---|
| A v1 | 统合管线编排器 | `application/run_pipeline.py` | deprecated+门禁封存 | 保留（取证用途），文档已声明 |
| A v1 | L1/L2/L3 合并层 | `application/graph/build_merge_layer.py` | **已运行**（470 簇在库） | 保留在役（A 层去重基础设施） |
| A v1 | memory 派生层 | `application/memory/*`（16） | **在役**（memory_* 有数据） | 保留在役（当前事实上的知识层） |
| A v1 | 事件向量库 | `retrieval/build_vector_store.py` | 曾运行 | 保留（personal_events collection 仍被检索） |
| A v1 | 会话摘要生成 | `build_conversation_summary.py` | **文件已撤**（2026-08-23 cleanup） | 归档（产物 json 保留）；run_pipeline 注释待清 |
| A v1 | 会话 turn 向量库 | `application/conversation/build_conversation_vector_store.py` | 停摆（上游已撤） | 封存待审 |
| A v1 | 图管线 | `application/graph/*`（6）+ `conversation/build_conversation_graph.py` | 构建一次后停摆（duckdb 2026-06-28） | 封存待审；duckdb 归档候选 |
| B 正式 | pk-ku CLI | `application/ku.py` | 在役（但 extract 被 D-31 锁死） | 保留在役（权威入口） |
| B 正式 | view-policy 候选台账 | `application/knowledge/view_candidate_prepare.py` | 代码完成、**从未执行到建表** | 封存待审（D-31 解锁成本门后再启用） |
| B 正式 | KU 权威层 | `schema_ddl.py` 知识段 40 表 | 表全建、**内容 0 行** | 保留（这是目标态权威层） |
| B 正式 | 遗留隔离 | `application/knowledge/legacy_isolation.py`、`isolate_legacy_knowledge.py` | 已执行（空索引 active 2026-08-12） | 保留（一次性治理工具） |
| C MVP | 语义压缩 | `tmp/mvp_semantic_compress.py` + `var/db/semantic_mvp_v3.sqlite` | **唯一知识产出线** | 保留在役；**注意它住在 tmp/（非正式代码区）——迁移转正决策待做** |
| 在役 | D 层同步/事件权威 | `application/sync.py`、`conversation/v2_sync.py`、`adapters/conversation_sources/`、`event_generations.py` | **在役**（ce_* 300 万事件） | 保留在役（产品每日路径） |
| 在役 | 检索层 | `retrieval/*`（unified_search facade + 7 子模块） | **在役** | 保留在役 |
| 在役 | serving/artifact 权威 | `application/serving/` + Phase 23–27 表 | 在役（active snapshot 2026-08-17） | 保留在役 |
| 兼容层 | domains facade | `src/personal_knowledge/domains/`（62/66 为 facade） | 兼容窗口 | 窗口期满后删除 |
| 兼容层 | v1_1 副本 | `tools/compat/v1_1/`（84 文件） | 兼容副本 | 归档候选 |
| 取证 | forensics/ku 调试 | `tools/forensics/`（20）、`var/tmp_ku_*.py`（~20） | 一次性 | 清理候选（var 侧） |
| 备份 | 大备份 | `var/backup/`（4.07 GB）、`var/backups/`（~590 MB）、`var/db/backups/`（45 MB） | 保留期满 | **归档候选（合计 ~4.7 GB）** |
| 封存区 | archive/ | 7.9 GB（phase62 replays 7.5 GB） | 已封存 | 保持；清理需走 governance 处置流程 |

### 6.2 观察到的设计分裂点（根因）

1. **三代知识生产并存且互不喂食。** A 层 `memory_*`（v1，291 items + 1,370 候选，有数据）、B 层 KU 权威表（40 表全建、0 行）、C 层 MVP v3（173 卡/1,037 facts，独立 sqlite）是三套互不相通的"知识"形态；检索层的 KU 槽（`retrieval/semantic_search.py`，`_KU_SLOTS=1`）常年落在空索引上，MVP 产出完全未接入检索。
2. **成本门把正式轨道冻结成"台账完备、零执行"，催生 tmp/ 旁路。** D-30（USD 24.487 估值队列封存）+ D-31（零付费强制）使 B 轨道只剩 freeze/audit 能力；MVP 因此绕开 pk-ku、直连 pi kernel、住进 `tmp/`。治理越严格，事实生产路径越偏离治理面。
3. **"叠加不破坏"惯例 + 按 Phase 累积 schema → 化石层。** `schema_ddl.py` 按 Phase 14/23/25/26/27 分段累积 40+ 表；旧轨道靠 fail-closed 门禁封存而非删除（ir_* 队列 24,487 行 pending、空 KU 索引 active），形成"只能加、不能删"的考古现场。
4. **兼容层复利。** 同一职责平均存在 2–3 个可达路径：`application/`（canonical）→ `domains/`（62 个 facade）→ `tools/compat/v1_1/`（84 个副本）→ `archive/`（retired source）。2026-08-13 与 2026-08-23 两次 cleanup 各留一层兼容窗，窗口尚未关闭。
5. **serving 权威已制度化"知识层为空"这一稳态。** active KU 索引 = `knowledge_units_empty_...`（unit_count=0，2026-08-12 起），active snapshot = `ss_37041cc36becd1013056e9db`（2026-08-17）——空知识层不是事故，而是 `legacy_isolation.py` 状态机的既定结果。任何"让知识层有数据"的下一步，本质都是一次 promote 事件，路径与门禁都是现成的。

---

*Pipeline map analysis: 2026-08-29（只读测绘；除本文件外无写操作）*
