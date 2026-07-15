---
phase: 19
plan: "01"
subsystem: physical-source-migration
tags: [packaging, manifest, rollback, governance]
requires: [phase-18-governance]
provides: [stable-console-entry-skeleton, exact-source-manifest, reversible-source-executor]
affects: [phase-19-source-cohorts]
tech-stack:
  added: [setuptools-src-layout]
  patterns: [manifest-driven-migration, exact-byte-rollback, fail-closed-preflight]
key-files:
  created:
    - pyproject.toml
    - src/personal_knowledge/cli.py
    - src/personal_knowledge/governance/source_manifest.py
    - src/personal_knowledge/governance/apply_source_migration.py
    - governance/manifests/source_migration.json
    - tests/test_physical_source_layout.py
  modified:
    - integration/scripts/governance/apply_source_migration.py
key-decisions:
  - "Phase 19 source scope is the 206 git-tracked Python files under integration/scripts; private and binary zones are excluded."
  - "Dirty source overlap is frozen in the manifest and blocks apply until a cohort-specific approved manifest is produced."
  - "Console commands initially bridge to canonical legacy modules; later cohorts replace the bridge after physical relocation."
requirements-completed: [PHY-02, PHY-07]
duration: 32 min
completed: 2026-07-13
---

# Phase 19 Plan 01: Packaging and exact source migration manifest Summary

已建立五个稳定 console script、206 文件精确 source/target/inverse/consumer/dirty manifest，以及支持 dry-run、apply、rewrite、journal 和 exact-byte rollback 的 fail-closed executor；本计划没有移动任何现有源码或数据。

## Execution

- Start: 2026-07-13
- End: 2026-07-13
- Tasks: 2/2
- Source files represented: 206/206
- Physical moves performed: 0

## Task Results

### 19-01-01 — package and exact manifest

- `pyproject.toml` 注册 `rag-pipeline`、`rag-search`、`rag-api`、`rag-mcp`、`rag-dashboard`。
- `src/personal_knowledge/` 提供过渡期稳定入口。
- manifest 对 `git ls-files integration/scripts/*.py` 的 206 个文件逐项保存 source、target、inverse、SHA-256、consumer 与 dirty 状态。
- `Agent/`、`Google/`、`imports/`、数据库、runtime、analysis 和 `_recycle/` 不进入 source manifest。

Verification: `python -m pytest -q tests/test_physical_source_layout.py -k manifest` — 4 passed.

### 19-01-02 — reversible executor

- apply 前验证 workspace containment、private/binary scope、case-fold collision、reparse node、source hash、tracked status、dirty source/target 与 manifest checksum。
- apply 使用 staged copy、byte hash、backup rename、target rename；consumer rewrite 记录原始 bytes。
- rollback 从 journal 恢复移动文件和 rewrite consumer 的精确 pre-run bytes，不依赖 Git HEAD。
- 临时树覆盖 apply/rollback、dirty target、dirty source、private、binary、manifest drift 与 source drift。

Verification: `python -m pytest -q tests/test_physical_source_layout.py -k executor` — 5 passed.

## Final Verification

`python -m pytest -q tests/test_physical_source_layout.py` — 9 passed（主代理复验补充未安装 checkout 的兼容入口测试）。

真实仓库 dry-run 对当前 dirty overlap 返回非零并指出首个冲突 `integration/scripts/core/local_embed.py`；这是计划要求的 fail-closed 行为，不是测试失败。没有执行 `--apply`。

## Deviations from Plan

**[Rule 2 - Missing critical safety] Added canonical package-side executor and explicit rewrite rollback.** Plan named the legacy integration entry, while the migration contract requires `python -m personal_knowledge.governance.apply_source_migration`. Added the canonical module plus a compatibility entry, and journaled consumer rewrites so rollback restores exact bytes.

**[Main-agent verification fix] Made the legacy entry runnable before editable install and added explicit `--dry-run`.** The first real-checkout verification exposed `ModuleNotFoundError`; the wrapper now resolves the repository `src/` path and a regression test confirms the command reaches fail-closed preflight.

**Total deviations:** 2 auto-fixed execution/safety requirements. **Impact:** no scope expansion into migration execution or private data.

## Self-Check: PASSED

- 206/206 tracked source entries, unique case-folded targets and exact inverse mapping.
- Dirty overlap is explicit; apply fails closed.
- Temporary-tree apply/rollback restores exact bytes.
- No current source/data files were moved, deleted or overwritten.

## Next Phase Readiness

Ready for 19-02 immutable cohort review/checksum checkpoint. The full PHY-02/PHY-07 phase outcomes remain subject to later source moves, consumer-zero checks and parity validation.
