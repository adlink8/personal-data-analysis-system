# 清理候选清单 — 2026-08-29（只标记，不删除）

**来源:** `.planning/codebase/PIPELINE_MAP.md`（2026-08-29 测绘）§5/§6.1 归档候选
**本清单性质:** 审批前置材料。所有路径已逐项实测核验（存在性 / 字节大小 / mtime / 内容类型）。**本文档只标记，未执行任何删除、移动、覆盖。**
**核验方法:**
- 大小/mtime：`ls -la --time-style=long-iso`（Git Bash，2026-08-29 实测）
- 内容类型：Python `sqlite3` 以 `file:...?mode=ro` **只读**打开枚举表名与行数；DuckDB 看文件魔数；CSV 看 BOM+表头
- 依赖核查：`grep -rn` 覆盖 `src/ apps/ tools/ ops/ integration/ .github/ docs/ governance/ tests/ .planning/`（`scripts/` 不存在）

---

## 一、候选总表

图例：**可删** = 低风险、无功能依赖；**需决策** = 有引用或有唯一数据价值，删除前需人工拍板；**需先改引用** = 存在代码/治理 manifest 指向，须先改引用再删；**保留** = 依赖核查推翻了候选资格。

### A. 可删（合计 4,652,575 B ≈ 4.44 MB）

| # | 路径 | 大小 (B) | mtime | 类型（实测） | 引用情况 | 风险 | 建议 |
|---|---|---|---|---|---|---|---|
| A1 | `var/db/conversation_graph.duckdb` | 4,206,592 | 2026-06-28 20:49 | DuckDB storage（魔数 `DUCK`，storage v64）；Phase 07 图管线产物 | 代码引用存在但均为"可重建"性质：`core/project_paths.py:66` `CONV_GRAPH_DB = DB_DIR/"conversation_graph.duckdb"`（`DB_DIR` 优先 var/db，project_paths.py:44）；`build_conversation_graph.py`/`visualize_conversation_graph.py`/`query_conversation_graph.py` 硬编码旧路径 `integration/db/conversation_graph.duckdb`；`build_triple_store.py:27` 该路径已标注禁用 | 自 2026-06-28 未再构建（停摆 2 个月）；删除后如重启图管线可重建（重建路径现成） | **可删** |
| A2 | `var/db/candidate_review.sqlite` | 24,576 | 2026-08-10 09:55 | SQLite，2 表 `candidate_review_state` / `candidate_review_feedback` 均为 **0 行** | `application/conversation/harness_candidate_review.py:75`、`services/pi_domain_gateway.py:83` 以 DEFAULT 路径引用，建表均为 `CREATE TABLE IF NOT EXISTS`（:147,:153） | 0 行无数据损失；首次使用时代码自动重建空库 | **可删** |
| A3 | `var/personal_system.sqlite` | 0 | 2026-07-18 14:16 | 0 字节 stub | 无任何代码/文档引用（全库 grep 仅 PIPELINE_MAP 自身提及） | 无内容 | **可删** |
| A4 | `var/tmp_ku_*.py` + `.ps1`（15 个文件） | 24,095（合计） | 2026-07-16 08:50–09:44 | KU 提取排障一次性脚本（`tmp_ku_diag.py`…`diag10`、`cache`、`inspect`、`is_new`、`resume.ps1`、`verify_run.py`） | 仅历史审计记录：`.planning/cleanup/2026-07-16-full-gap-audit.md:137` 原文即 *"Optional cleanup (not product)"*；无功能依赖 | 审计文档已留档其用途（`tmp_ku_verify_run.py` 关联事件 probe `6f3da1ee…`，:109） | **可删** |
| A5 | `var/backups/decision_analysis_pre_phase60_20260812T005623Z.sqlite` | 139,264 | 2026-08-12 08:56 | SQLite 6 表（analysis_runs=1 等） | 无引用 | Phase 60 重跑已成功且 17 天无异常（在役库正常更新） | **可删** |
| A6 | `var/backups/project_pilot_pre_phase60_20260812T005623Z.sqlite` | 98,304 | 2026-08-12 08:56 | SQLite 4 表（pilot_cases=2 等） | 无引用 | 同上 | **可删** |
| A7 | `var/backups/recommendation_calibration_pre_phase60_20260812T005623Z.sqlite` | 159,744 | 2026-08-12 08:56 | SQLite 7 表（calibration_arms=6 等） | 无引用 | 同上 | **可删** |

### B. 需决策（合计 4,703,711,232 B ≈ 4.38 GiB — 占清理预算 99%+）

| # | 路径 | 大小 (B) | mtime | 类型（实测） | 引用情况 | 风险 | 建议 |
|---|---|---|---|---|---|---|---|
| B1 | `var/backup/agent_conversations.pre-cleanup-20260816.sqlite` | 4,069,511,168 | 2026-08-16 18:56 | SQLite 17 对象；canonical 全量快照：`ce_events` 2,946,088 / `canonical_messages` 178,508 / `canonical_sessions` 2,837 | 无代码引用。对比在役库（ce_events 3,026,243 / messages 174,269 / sessions 2,426）：备份含被 2026-08-16 canonical 清理掉的约 **411 会话** | **08-16 清理所删数据的唯一恢复源**；删除后不可恢复 | **需决策**（决策点：是否还需恢复被清理会话；若否可删或按 `archive/README.md` 治理流程移入 archive） |
| B2 | `var/backups/personal_system_pre_conflict_resolution_20260811T063247Z.sqlite` | 294,256,640 | 2026-08-11 14:32 | SQLite 78 表；**关键差异**：`knowledge_units` 44,880 / `canonical_knowledge_units` 40,417 / `knowledge_unit_evidence` 59,705 / `knowledge_run_items` 76,353 / `knowledge_response_cache` 35,539 —— 在役库这些表现全为 0（2026-08-12 legacy isolation 后） | `.planning/phases/PDA-5-quality-close/CONFLICT-RESOLUTION.md:6` 记录为该次冲突解决恢复点；`.planning/codebase/MVP_PROMOTION_PLAN.md:131` 引用其文件名作为命名先例 | **可能是 v1 知识层（隔离前）唯一存活完整快照**（与 B3 同态，二选一保留） | **需决策**（倾向保留至 v1 KU 数据去向定案） |
| B3 | `var/backups/personal_system_pre_fk_repair_20260728T014630Z.sqlite` | 294,256,640 | 2026-07-28 09:45 | SQLite 78 表；逐表行数与 B2 完全一致（同样含 44,880 KU） | 无引用 | 与 B2 互为冗余副本（同数据状态）；FK 修复前快照的历史使命已完成 | **需决策**（若 B2 保留，此份冗余度最高，可删） |
| B4 | `var/db/backups/personal_system_before_import_20260704_133717.sqlite` | 45,613,056 | 2026-07-02 15:23 | SQLite 30 表；v1 早期快照（`unified_events` 8,136 / `merge_clusters` 516 / `graph_relation_candidates` 4,653） | `governance/manifests/data/var.json:288-297` 迁移 manifest 记录（含 `.bak-phase20`/`.stage-phase20` 条目） | 早期导入前快照；manifest 记录在案 | **需决策**（manifest 同步更新后可删） |
| B5 | `var/db/decision_orchestration.sqlite` | 73,728 | 2026-07-19 21:34 | SQLite 4 表共 9 行试点数据（`orchestration_sessions` 3 / `orchestration_events` 3 / `orchestration_confirmations` 3 / `orchestration_invocations` 0） | **ops 启动栈在役引用**：`ops/runtime/start-agent-stack.ps1:265` 启动时 `apply_schema`；`ops/runtime/live-agent-acceptance.py:21`；`services/orchestration_service.py:25` DEFAULT 路径 | 删除丢 9 行试点数据；重启 agent-stack 会自动重建空 schema | **需决策**（报告标"停摆"，但 ops 侧把它当启动前置；删除仅损失试点台账） |
| B6 | `integration/db/personal_system.sqlite` | 0 | 2026-07-17 15:49 | 0 字节 stub（Phase 20 迁移产物） | `governance/manifests/data/var.json:240-246` manifest 条目；`services/dashboard.py:12`、`application/build_deep_profiles.py:331`、`evaluation/vector/compare_sqlite_generations.py:1058` 为 docstring/字符串残留（旧路径叙事，非运行时依赖）；`governance/policies/paths.yaml:16` 已将其目录标 `rolled-back-legacy` | 0 字节无数据；manifest/docstring 需同步 | **需决策**（低风险；改 docstring + manifest 后可删） |

### C. 需先改引用（合计 19,412,123 B ≈ 18.5 MB）

| # | 路径 | 大小 (B) | mtime | 类型（实测） | 引用情况 | 建议 |
|---|---|---|---|---|---|---|
| C1 | `var/db/raw_index/input_tables.csv` | 879 | 2026-07-04 13:37 | CSV（BOM-UTF8；`source,database_path,table_name,row_count` 台账，指向旧 `Google/structured/sqlite/...` 路径） | `src/personal_knowledge/governance/data_disposition.py:83`（`integration/raw_index/` → `var/db/raw_index/` 处置映射）；`governance/manifests/data/var.json` / `var.apply.json`；`governance/reconcile_phase19.py:37`、`governance/build_approved_apply_manifests.py:153`（指向源路径 `integration/raw_index`） | **先改** data_disposition.py 映射 + governance manifests，再删 |
| C2 | `var/db/structured/entities.csv` | 1,290,155 | 2026-07-04 13:37 | CSV BOM-UTF8 实体导出（早期 8,136 事件时代） | `data_disposition.py:84`；`governance/manifests/data/var.json:39-45`、`var.apply.json:69-75` | 同上，整组 C2–C5 一起处置 |
| C3 | `var/db/structured/entity_links.csv` | 4,944 | 2026-07-04 13:37 | 同上 | 同上 | 同上 |
| C4 | `var/db/structured/event_entities.csv` | 9,761,561 | 2026-07-04 13:37 | 同上 | 同上 | 同上 |
| C5 | `var/db/structured/unified_events.csv` | 8,346,598 | 2026-07-04 13:37 | 同上（内容已被在役库 `unified_events` 11,370 行取代） | 同上 | 同上 |
| C6 | `docs/legacy/retrieval-ssot.duplicate.md` | 7,986 | 2026-08-16 12:53 | 标记重复的 legacy 文档副本 | **治理代码强引用**：`src/personal_knowledge/governance/source_manifest.py:81-82` 专门分支返回 `"duplicate-doc-preserved"`；`governance/manifests/asset_classification.json:143`、`asset_classification_recovery.json:143`、`manifests/source/apps-assets-docs-tests.json:264-266` | **先改** source_manifest.py 分支 + 3 个 manifest，再删（同时列入下方"关闭兼容窗口"清单） |

### D. 保留（依赖核查推翻候选资格，合计 147,456 B）

| # | 路径 | 大小 (B) | mtime | 理由 |
|---|---|---|---|---|
| D1 | `var/db/backups/recommendation_calibration_before_phase53_rerun_20260812.sqlite` | 126,976 | 2026-08-12 07:54 | SQLite 7 表；近期重跑前快照；PIPELINE_MAP §5 原判"保留（近期）"，无反证 |
| D2 | `var/db/pi_kernel_candidates.sqlite` | 20,480 | 2026-08-04 21:46 | SQLite 2 表当前 0 行，**但**：`apps/personal_intelligence_kernel/src/candidates/store.mjs:4` 硬编码 `PI_KERNEL_CANDIDATES_DB = "var/db/pi_kernel_candidates.sqlite"`；desktop UAT 验收项明确 *"only the four governed Kernel DBs exist"*（`apps/personal_intelligence_desktop/test/desktop-uat-record.md:422`）——它是 kernel 治理四库之一，删除将违反治理验收 |

**伴生文件（随主文件处置，不单列）:** `var/backups/personal_system_pre_conflict_resolution_20260811T063247Z.sqlite-shm`（32,768 B）/ `-wal`（0 B）、`personal_system_pre_fk_repair_20260728T014630Z.sqlite-shm`（32,768 B）/ `-wal`（0 B）。⚠️ 观察：4 个伴生文件 mtime 均为 **2026-08-29 17:01**（本清单编写当日）——说明当日有进程以 WAL 模式打开过这两份备份（-wal 为 0 B，无未落盘数据）。处置 B2/B3 时必须连同伴生文件一起处理；建议先排查当日打开来源。

---

## 二、合计

| 类别 | 行数 | 文件数 | 字节 | 约合 |
|---|---|---|---|---|
| A 可删 | 7 | 21（tmp_ku 15 + pre-phase60 3 + 3 单文件） | 4,652,575 | ≈ 4.44 MB |
| B 需决策 | 6 | 6 | 4,703,711,232 | ≈ 4.38 GiB |
| C 需先改引用 | 6 | 6 | 19,412,123 | ≈ 18.5 MB |
| D 保留 | 2 | 2 | 147,456 | ≈ 144 KB |
| **候选总计（A+B+C）** | **19** | **33** | **4,727,775,930** | **≈ 4.40 GiB（4.73 GB）** |

与 PIPELINE_MAP 估计的"约 4.7 GB"吻合。差异说明：structured CSV 实测 19,403,258 B（≈18.5 MB），报告 "~18 MB" 成立；`var/db/backups` 实际文件名带 `_133717` 后缀（报告表内省略）；`var/tmp_ku_*` 实测 15 个（报告 "~20"）。

---

## 三、关闭兼容窗口清单（单列；只描述，本清单不动）

报告 §6.2-4："2026-08-13 与 2026-08-23 两次 cleanup 各留一层兼容窗，窗口尚未关闭。" 实测痕迹与关闭动作如下。

### W1. domains facade 层（2026-08-13 窗口）
- **痕迹（实测 66 个 py，其中 62 个 facade）**：`src/personal_knowledge/domains/{conversation,graph,knowledge,memory}/*.py` 文件头均为 *"Re-export facade — retained for backward compatibility during the 2026-08-13 cleanup window."*；另 4 个为各子包 `__init__.py`。整层 128,880 B。
- **状态**：`application → domains` 真实 import = 0（`docs/architecture/domains-slimming.md:50`，由 `pk-ku doctor` 验证）；tests 中 3 处 `domains` import 是 `tests/unit/test_doctor_ku.py:300-306` 的扫描器测试字符串，非真实依赖；**外部消费者遥测未知**（domains-slimming.md:73，这是窗口未关闭的唯一理由）。
- **关闭要动什么**：
  1. 确认外部消费者为 0（跑 `pk-ku doctor` facade 计数 + 检查包外调用方）；
  2. 删除整个 `src/personal_knowledge/domains/` 包（62 facade + 4 `__init__.py`）；
  3. 更新 `application/knowledge/doctor_ku.py:747` 的 `"retire_window": "2026-08-13"` 字段（改为窗口已关闭或移除该报告项）；
  4. 更新 `docs/architecture/domains-slimming.md`（Import rules 表的 "Legacy path" 行 :46、"Deferred" 行 :73-75）；
  5. 全量 `pytest` 回归（含 `test_doctor_ku.py`）。

### W2. tools/compat/v1_1 副本层（独立 compat 预算，约 08-23 前后）
- **痕迹（实测 84 文件，67,385 B）**：每个文件头为 *"Compatibility shim -> …; Legacy CLI: python integration/scripts/xxx.py"*；`tools/compat/` 下仅此一层。
- **状态**：全库 grep `compat[/\]v1_1|compat\.v1_1|tools[/\]compat` 除自身目录外 **0 引用**；`.github/` 无引用；`domains-slimming.md:76` 标 *"Separate compat budget (not application facade debt)"*。
- **关闭要动什么**：删除 `tools/compat/v1_1/` 整目录 + 更新 domains-slimming.md:76 提法。前置核实：`integration/scripts/` 历史入口是否还有文档残留引用。

### W3. legacy 文档副本 + 治理代码残留
- `docs/legacy/retrieval-ssot.duplicate.md`（7,986 B）：见 C6，删除前必须先改 `governance/source_manifest.py:81-82` 与 3 个 manifest。
- `run_pipeline.py:21-23` 仍引用已撤销的 `build_conversation_summary.py`（报告 §6.1 "run_pipeline 注释待清"）；同类 docstring 残留：`application/conversation/build_conversation_vector_store.py:14-15`、`core/llm.py:3`、`evaluation/conversation/evaluate_conversation_prompt.py:161`。
- 关闭要动什么：改 4 处注释/docstring + 按 C6 改治理代码后删文档副本。`docs/architecture/retrieval-ssot.md` 为唯一 SSOT 保留。

### 关联事实（不改，仅记录）
- 2026-08-23 cleanup 的另一痕迹：`archive/README.md:37-40` — *"Tracked legacy-pipeline source was retired from the cleanup branch on 2026-08-23. Its exact pre-cleanup state remains available on `codex/archive-pre-cleanup-20260823`"*（分支级备份，非工作树文件，不在本清单范围）。

---

## 四、执行配套

- 干跑/审批脚本草稿：`tmp/cleanup-draft-2026-08-29.ps1`（**未执行**，连 -WhatIf 都未跑）。默认干跑；真删需显式 `-Confirm`，且"需决策"项需另加 `-IncludeNeedsDecision`；"需先改引用"项（C 类）不在脚本删除流程内。
- 脚本在真删前会把逐项清单（路径/大小/mtime/SHA256，SHA256 仅对 <50 MB 文件计算）写入 `.planning/cleanup/cleanup-manifest-<时间戳>.json`。
- 4.07 GB 的 B1 若批准删除，建议走 `archive/README.md` 治理流程（exact manifest + retention review + approval）或直接删除二选一，均需人工拍板。
- 本清单未覆盖：`archive/phase62/` 7.5 GB（已封存区，PIPELINE_MAP §4 建议保持现状，清理需走 governance 处置流程，超出本次窗口）。

---

*CANDIDATES-2026-08-29：编制于 2026-08-29。编制过程零删除、零移动、零覆盖；仅新增本文件与 `tmp/cleanup-draft-2026-08-29.ps1`。*
