---
phase: 14
slug: knowledge-unit-layer
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-10
---

# Phase 14 — Validation Strategy

> Phase 14 的执行期验证契约。每个实现任务必须就近交付自动测试；真实模型调用、生产 promote 与 lifecycle 写入使用显式 checkpoint。

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` / existing repository test infrastructure |
| **Quick run command** | `python -m pytest -q <task-specific test files>` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | task tests < 60 seconds；full suite按当前约 210 tests |

---

## Sampling Rate

- **After every task commit:** 运行该任务 `<automated>` 中列出的定向 pytest。
- **After every plan wave:** 运行本 wave 涉及的全部 Phase 14 测试。
- **Before `$gsd-verify-work`:** `python -m pytest -q` 必须全绿，并核对 pilot/full/canary 的机器可读 gate report。
- **Max feedback latency:** 普通任务 60 秒；真实 pilot/full/canary 通过 checkpoint 单独记录。

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-* | 01 | PoC | KU-01..KU-04 | T-14-01/02/03/05 | frozen eval、schema/manifest、small-sample extraction、33-unit candidate A/B 与 pointer promotion PoC；不代表 canonicalization/canary/lifecycle 完成 | unit/component | `python -m pytest -q tests/test_knowledge_unit_eval_dataset.py tests/test_knowledge_unit_contracts.py tests/test_knowledge_unit_checkpoint.py tests/test_knowledge_unit_extraction.py tests/test_knowledge_index_promotion.py` | ✅ | ✅ historical green（上述 5 个文件合计 40 tests；210 为当时全量 suite 记录） |
| 14-02-* | 02 | 1 | KU-05 | T-14-01/02/03 | inventory 冻结；resume/cache/retry；错误或低产出不能 PASS | unit/component/crash | `python -m pytest -q tests/test_knowledge_unit_backfill.py tests/test_knowledge_unit_retry_cache.py tests/test_knowledge_unit_checkpoint.py` | ❌ W0 | ⬜ pending |
| 14-03-* | 03 | 2 | KU-05, KU-06 | T-14-02/04/05 | 300–500 分层 pilot；evidence/privacy 人审；hard-negative false merge=0 | component/offline eval | `python -m pytest -q tests/test_knowledge_unit_backfill.py tests/test_canonical_knowledge_units.py` | partial | ⬜ pending |
| 14-04-* | 04 | 3 | KU-05, KU-06 | T-14-01/03/05 | full run 与旧 current 隔离；实际 collection IDs 精确 reconcile；不自动 promote | production/offline eval | `python -m pytest -q tests/test_knowledge_unit_backfill.py tests/test_canonical_knowledge_units.py tests/test_knowledge_unit_vector_store.py tests/test_knowledge_index_promotion.py` | partial | ⬜ pending |
| 14-05-* | 05 | 4 | KU-07 | T-14-05/06/07 | 未通过 candidate 拒绝 promote；knowledge-first/raw fallback；反馈不保存原 query | contract/canary | `python -m pytest -q tests/test_knowledge_index_promotion.py tests/test_knowledge_search_contracts.py tests/test_rag_feedback_privacy.py` | partial | ⬜ pending |
| 14-06-* | 06 | 5 | KU-08 | T-14-05/08 | 增量仅改变受影响 subject；deleted/deprecated 零索引残留；联合 rollback | component/regression | `python -m pytest -q tests/test_knowledge_incremental_refresh.py tests/test_memory_lifecycle_sync.py tests/test_knowledge_index_promotion.py` | partial | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] 现有 pytest、临时 SQLite、fake LLM 与 Phase 14 测试基础设施可用。
- [ ] `tests/test_knowledge_unit_backfill.py` — inventory、恢复、隔离与严格 gate。
- [ ] `tests/test_knowledge_unit_retry_cache.py` — retry 分类、Retry-After/jitter 与 cache key/revalidation。
- [ ] 其余表中标记 partial 的测试在对应实现任务内先补失败用例，再实现功能。

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pilot evidence 审核 | KU-05, KU-06 | 语义忠实度与隐私泄漏不能只由同一模型自评 | 对 300–500 分层 pilot 至少抽查 20 个 evidence links，记录 pass/fail 与原因；任何 critical privacy/evidence failure 阻断 full run。 |
| Full extraction checkpoint | KU-05 | 涉及长时间、可能计费的真实模型调用 | 审核 frozen inventory count/hash、模型/提示词/schema/config hash、预计成本与 pilot gate 后，用户明确批准再运行；完成后核对 processed+failed=inventory。 |
| Candidate canary/promote | KU-07 | 最终 promote 会改变 active pointer 与用户可见检索路径 | 先审核 frozen A/B gate；通过 candidate override/独立 canary route 运行并人工标注 30 条真实 query，默认 active 不变；canary PASS 后再单独批准 journal promote。 |
| Memory lifecycle `--write` 与 incremental promote | KU-08 | 两者分别修改 memory 状态和 active index | 先批准 exact lifecycle preview 并写入；再构建 incremental candidate，完成 actual-ID reconcile、eval/smoke，使用第二个独立 checkpoint 批准 journal promote。 |

---

## Validation Sign-Off

- [x] 所有规划能力都有 task-local 自动验证或明确的 Wave 0 测试依赖。
- [x] Sampling continuity：不存在连续 3 个无自动验证的实现任务。
- [x] Wave 0 明确列出缺失测试，且由对应计划先写测试。
- [x] 命令不使用 watch mode。
- [x] 普通自动反馈目标 < 60 秒；长运行由 checkpoint 和 manifest 单独验证。
- [x] `nyquist_compliant: true` 已设置。

**Approval:** planning contract approved 2026-07-10；execution evidence pending
