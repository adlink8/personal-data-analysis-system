---
phase: 43
slug: l2-scope-redefinition-cross-turn-state-ownership-and-increme
status: active
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-27
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest（pytest.ini：testpaths=tests、pythonpath=src、addopts=-q、cache_dir=var/cache/pytest） |
| **Config file** | pytest.ini（已存在） |
| **Quick run command** | `PYTHONIOENCODING=utf-8 python -m pytest tests/unit/test_knowledge_l2_session_extract.py tests/unit/test_history_knowledge_units.py tests/unit/test_knowledge_eligibility.py -q` |
| **Full suite command** | `PYTHONIOENCODING=utf-8 python -m pytest tests/unit tests/integration tests/contract -q` |
| **Estimated runtime** | quick ~秒级（实测 11 passed）；full 分钟级 |

---

## Sampling Rate

- **After every task commit:** Run quick run command（或该任务相关的定向测试文件）
- **After every plan wave:** Run full suite command
- **Before `$gsd-verify-work`:** Full suite must be green + `pk-ku doctor --skip-ports` exit=0
- **Max feedback latency:** 60 秒（quick subset）

---

## Per-Task Verification Map

> Task ID 待 planner 产出 PLAN.md 后回填；下表为 Req → 测试设计映射（来自 43-RESEARCH.md Validation Architecture），每个 plan 的任务必须落到其中一行或多行。

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 43-02-T1/T2 | 43-02 | 2 | L2G-01 | T-43-01（prompt 注入：注入清单被当指令） | 注入清单以数据段呈现；`duplicate_of` 仅接受注入清单内 id，非法引用拒绝并计数 | unit：归一化/注入段组装/duplicate_of 白名单/supersedes_id 落 staging | `python -m pytest tests/unit/test_l2_injection_dedup.py tests/unit/test_knowledge_unit_extraction.py tests/unit/test_extraction_salvage_parse.py -q` | ❌ W0（43-02 创建） | ⬜ pending |
| 43-04-T2, 43-05-T2 | 43-04, 43-05 | 3 | L2G-01 | T-43-01 | 同上（L1/L2 提交处接线 + 计数） | unit：接线行为（stub LLM 捕获 llm_input/window_text + 落库断言） | `python -m pytest tests/unit/test_l2_injection_dedup.py tests/unit/test_knowledge_l2_session_extract.py tests/unit/test_knowledge_unit_prod_assistant_track.py -q` | ❌ W0（43-02 创建，43-04/05 扩展） | ⬜ pending |
| 43-07-T1 | 43-07 | 4 | L2G-01 | — | N/A | integration：同事实两会话双 run 对照，平行 current 新增下降（tmp 实验库，stub LLM） | `python -m pytest tests/integration/test_l2g01_dedup_gate.py -q` | ❌ W0（43-07 创建） | ⬜ pending |
| 43-01-T1 | 43-01 | 1 | L2G-02 | — | N/A | unit：清单 yaml 加载/匹配（精确+前缀）/归一化 | `python -m pytest tests/unit/test_state_subjects.py -q` | ❌ W0（43-01 创建） | ⬜ pending |
| 43-03-T2/T3, 43-04-T2 | 43-03, 43-04 | 1, 3 | L2G-02 | T-43-02（误转正/误删） | publish 排除 candidate；promote dry-run 默认 + 快照 + 单事务 + D-09 re-match 门 | unit：publish 排除 / promote 行为 / candidate 路由 | `python -m pytest tests/unit/test_publish_candidate_exclusion.py tests/unit/test_promote_units.py tests/unit/test_l2_injection_dedup.py -q` | ❌ W0（43-03 创建） | ⬜ pending |
| 43-07-T2 | 43-07 | 4 | L2G-02 | — | N/A | 实验库实跑：双轨 run 清单内 subject 的 L1 current 新增=0（计数断言 + 证据文档） | `python tools/analysis/run_l2g_experiment.py`（dry-run）→ --write 实跑 + 43-EXPERIMENT-EVIDENCE.md 判据 | ❌ W0（43-07 创建） | ⬜ pending |
| 43-06-T1 | 43-06 | 1 | L2G-03 | — | N/A | unit：history 当前值标注唯一 + 零 schema 新字段（PRAGMA table_info 断言） | `python -m pytest tests/unit/test_history_knowledge_units.py -q`（扩展） | ✅ | ⬜ pending |
| 43-06-T2 | 43-06 | 1 | L2G-03 | — | N/A | contract：`rag-search --current-only` 行为与默认一致性（最小路线：排除即极限降权） | `python -m pytest tests/contract/test_knowledge_search_contracts.py -q`（扩展） | ✅ | ⬜ pending |
| 43-08-T1/T2/T3, 43-09-T1/T2/T3 | 43-08, 43-09 | 2, 3 | L2G-04 | T-43-02（SQL 注入/误删） | 参数化查询；改库前 var/backups/ 快照；dry-run 默认；≤50/批逐对人工检视；deprecate 走 unit 自引 evidence 通道 | 脚本级：分级报告落盘 + 抽样人工检视 + 治理批 manifest 链 + 执行笔记 | `python tools/migrations/triage_legacy_staging_units.py`（dry-run）；`pk-ku doctor --skip-ports`；`pk-ku inspect`（推进后 delta 复算） | ❌ W0（43-08/43-09 创建脚本与笔记） | ⬜ pending |
| all | all | — | 全部 | — | N/A | 回归：现有 KU 套件全绿 | `PYTHONIOENCODING=utf-8 python -m pytest tests/unit tests/integration tests/contract -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_state_subjects.py` — covers L2G-02（清单加载/匹配/归一化）→ **plan 43-01 Task 1 创建**（owned-by-plan，Task ID 已核对）
- [x] `tests/unit/test_l2_injection_dedup.py` — covers L2G-01（注入段/白名单/supersedes_id）→ **plan 43-02 Task 1 创建，43-04/43-05 扩展**（owned-by-plan，Task ID 已核对）
- [x] `tests/unit/test_publish_candidate_exclusion.py` + `tests/unit/test_promote_units.py` — covers L2G-02 candidate 落库/排除/转正 → **plan 43-03 Task 2/3 创建**（owned-by-plan，Task ID 已核对）
- [x] `tests/integration/test_l2g01_dedup_gate.py` — covers L2G-01 验收（双 run 对照，tmp 实验库 + stub LLM）→ **plan 43-07 Task 1 创建**（owned-by-plan，Task ID 已核对）

*其余需求复用现有测试文件扩展（test_history_knowledge_units.py / test_knowledge_search_contracts.py / test_knowledge_l2_session_extract.py），无需新框架或 fixtures。L2G-04 为脚本级验证（dry-run/抽样/治理链/doctor），见 43-08/43-09。*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 治理批逐对检视（supersede/deprecate 裁定） | L2G-01, L2G-04 | 41 ⑧ 铁律：全自动误并率高，每批 ≤50 必须人工逐对检视 | 每批 manifest dry-run 报告人工过一遍，异常对强制方向覆写或 skip（参照 var/tmp/conflict_apply_batch.py 的可审计覆写清单模式） |
| 11,008 分级报告的规则档抽样检视 | L2G-04 | 规则准确率需人工/LLM 抽样验证（每档 50 条） | 抽样清单落盘后逐条核对判档是否正确，准确率写入分级报告 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies（Task ID 已按 9 份 PLAN 回填并逐行复核——revision pass 2）
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references（4 项均 owned-by-plan：43-01/43-02/43-03/43-07）
- [x] No watch-mode flags
- [x] Feedback latency < 60s（quick subset 实测秒级）
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved（planner revision pass 2——Task ID 回填核对完成；Wave 0 项均归属具体 plan 任务；43-08/43-09 wave 随 B1 依赖修正更新为 2/3，Per-Task Map 已同步）
