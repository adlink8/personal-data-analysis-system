---
phase: 19
plan: "02"
subsystem: physical-source-migration
tags: [src-layout, windows, rollback, phase17]
requires: [19-01]
provides: [canonical-python-src, immutable-approved-manifest, windows-safe-rollback]
affects: [19-03, 19-04, 19-05]
tech-stack:
  added: []
  patterns: [journal-first-rewrite, bounded-windows-retry, exact-prestate-rollback]
key-files:
  created:
    - governance/manifests/source/canonical-src.json
    - governance/reports/script-audits/apply_source_migration-production-readiness.md
  modified:
    - src/personal_knowledge/governance/source_manifest.py
    - src/personal_knowledge/governance/apply_source_migration.py
    - src/personal_knowledge/cli.py
    - tests/test_physical_source_layout.py
key-decisions:
  - "User-approved dirty and untracked current bytes are authoritative prestate; never restore from HEAD."
  - "Phase 17 private eval data remains in place; only canonical Python implementation moves in this cohort."
  - "Windows consumer replacement is journal-first and retries only WinError 5/32 with bounded exponential backoff and jitter."
requirements-completed: [PHY-01, PHY-02, PHY-07]
duration: 2h
completed: 2026-07-13
---

# Phase 19 Plan 02: Canonical Python src-layout migration Summary

118 个 canonical Python 实现已从 `integration/scripts` 领域目录物理迁移到 `src/personal_knowledge`，包含 12 个 Phase 17 evaluation 模块和 4 个已批准的未跟踪实现；190 个消费者文件按精确 prestate 改写，私有评测数据没有移动。

## Results

- Manifest checksum：`8c2f889fbb65f26267ca6685c17988df0a4297f597e24215502ddcf6294f01a6`
- Manifest file SHA-256：`fe1aecc94458bb2c1c340f38c5afcc8cea0867f1115ceed34c45d3c18963023b`
- Operations：118；consumer rewrites：190；final hash mismatch：0；old cohort source files：0。
- 五个 console 入口 `rag-pipeline/search/api/mcp/dashboard --help` 均退出 0；API、MCP、dashboard 和关键领域模块 import parity 通过。
- 定向 migration/fault-injection 测试：13 passed；Phase 17/L2/knowledge/AgentsView/Google 相关测试：90 passed。
- rollback drill：118 source 与 190 consumer prestate mismatch 均为 0；target=0、backup=0；随后 dry-run 和 re-apply 成功。
- 最终保留 `.migration-backup` 118 项，供 Phase 19 最终 gate 使用。

## Interrupted-state reconciliation

一次中断留下 90 个 source、28 个 target 且 backup 为空。只读 reconcile 证明 28 项同时满足 journal backup filename、journal SHA-256、隔离 manifest SHA-256、隔离内容 SHA-256 和 target SHA-256。使用隔离副本重建项目内 backup 后，幂等 rollback 恢复全部 prestate；隔离区未修改。

## Deviations from Plan

- 补齐 `evaluation`、动态 `import_module()`、bare core helper 与 `unified_search` 消费者映射。
- 针对 Windows WinError 5/32 增加有界重试、属性恢复、journal-first 和中断 rollback 幂等恢复。
- 静态审计的三个 High 为一次性迁移不适用/误报，已在中文生产加固结论中逐项给出运行时证据。

## Self-Check: PASSED

未触碰 Agent、Google、imports、数据库、runtime 数据或私有 eval 内容；未 stage、未 commit。Plan 19-02 完成，可进入 19-03，但本次按要求停在此处。
