---
phase: 43-l2-scope-redefinition-cross-turn-state-ownership-and-increme
plan: 03
subsystem: candidate-lifecycle
tags: [candidate, promote-units, rematch, publish, l2g-02, l2g-04]
requirements-completed: [L2G-02]
completed: 2026-07-28
---

# 43-03 执行摘要

## 结果

已落地 candidate 生命周期基础设施：`knowledge_units.lifecycle` 的迁移脚本默认只读、publish 不再把 candidate staging 行翻转为 current，并新增 `pk-ku promote-units` 人工转正通道。转正前必须对 evidence quote 做 eligible re-match；失败则保留原状态，不硬转正。

## 安全边界

- `add_candidate_lifecycle.py` 的默认执行为 dry-run；真实迁移需要显式 `--write`，并在改库前创建 `var/backups/` 快照。
- `promote-units` 默认 dry-run；`--write` 使用快照、`BEGIN IMMEDIATE` 单事务和 evidence re-match。
- publish 报告新增 `candidate_excluded` 计数；candidate 不会静默进入库存。
- 本次没有执行 schema migration 或任何 candidate/promote 真实写库。

## 验证

- `tests/unit/test_promote_units.py`、`tests/unit/test_publish_candidate_exclusion.py`：通过。
- `python -m personal_knowledge.application.ku promote-units --unit-id nonexistent`：dry-run 通过，报告为 not_found，零写入。
- `python tools/migrations/add_candidate_lifecycle.py`：识别当前 44,880 行、candidate 支持尚未启用，输出 `would_rebuild`，未写库。
- `python -m personal_knowledge.application.ku doctor --skip-ports`：`status: OK`，exit=0。
