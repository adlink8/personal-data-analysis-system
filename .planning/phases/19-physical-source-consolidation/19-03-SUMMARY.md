---
phase: 19
plan: "03"
subsystem: physical-source-migration
tags: [consumer-cutover, compatibility, tooling, rollback]
requires: [19-02]
provides: [zero-root-scripts, governed-compatibility-tree, classified-tools]
affects: [19-04, 19-05]
tech-stack:
  added: []
  patterns: [immutable-cohort-manifest, workspace-contained-journal, editable-console-entrypoints]
key-files:
  created:
    - governance/manifests/source/root-shims.json
    - governance/manifests/source/tools.json
    - tools/compat/v1_1/README.md
    - tools/supported/README.md
  modified:
    - src/personal_knowledge/governance/source_manifest.py
    - src/personal_knowledge/governance/apply_source_migration.py
    - pytest.ini
    - governance/stable_modules.yaml
    - governance/manifests/entrypoints.yaml
key-decisions:
  - "All journals, backups and temporary stages fail closed unless resolved inside the workspace."
  - "The 88 root scripts remain as governed v1.1 compatibility files; canonical consumers import personal_knowledge directly."
  - "The 26 tool files are classified as supported, migrations, forensics or documentation."
requirements-completed: [PHY-03, PHY-05, PHY-07]
duration: 2h
completed: 2026-07-13
---

# Phase 19 Plan 03: Consumer, shim and tool consolidation Summary

全部根级兼容脚本和工具已用不可变清单物理迁移；消费者切换到 `personal_knowledge`，`integration/scripts/*.py=0`，旧 `_tools`/`examples` 目录不存在。

## Results

- Root-shims: 88 operations, 50 consumer rewrites. Manifest checksum `e8a197f05b5f505adf1296151e3358c15e39a33ba32cc8e8711a214788feba5e`；file SHA-256 `ba5a81e632898f3adf3f2081c6325f29185539f3fa049412a07a825e98d6faf2`。
- Tools: 26 operations；19 forensics、2 migrations、3 supported、2 documentation. Manifest checksum `05c5f128f5d7de17ee46efdbb25b45abb6fb5c03621ba53d38870c4ad11596fe`；file SHA-256 `577471cbe590c701fcd7dfce56cb73c245fbc36a4ef12e7da04ac17ae3d2cce6`。
- 两个 cohort 均执行 dry-run → apply → exact rollback drill → dry-run/re-apply；最终 journals 分别为 138/26 records，全部位于 `var/runtime/migration/`。
- 迁移执行器新增 workspace containment gate，外部 journal 写入测试 fail closed；没有写入桌面根目录。
- 五个 `rag-* --help` console smoke 全部 exit 0。
- Full pytest: 464 passed, 1 skipped（85.2s）。
- Governance preflight: 12/12 PASS；shim registry 86 static shims、tool registry 26，docs coverage 100%，secret/privacy gates PASS。

## Deviations from Plan

**[Rule 2 - Missing critical safety] Workspace containment regression gate.** 迁移器原先允许 CLI 传入项目外 journal；现在 apply/rollback 均在任何写入前拒绝 workspace 外路径，并增加测试。

**[Rule 1 - Migration regression] Corrected consumer import aliases and src-relative roots.** 首次全量回归发现 bare import 改写丢失别名，以及迁移后 `parents[3]` 指向 `src/`。修正生成器、消费者与 41 个领域模块的项目根计算后，全量测试恢复为全绿。

**[Rule 3 - Governance metadata] Updated shim/tool/docs/secret scanner surfaces.** Phase 18 的 stable-module/tool registry 仍指向旧目录，且不可变 manifest 内嵌带明确 synthetic marker 的测试 fixture。同步到新路径，并仅对明确标记的 synthetic fixture 豁免扫描。

**Total deviations:** 3 in-scope migration/safety fixes. **Impact:** no private/data migration and no production data mutation.

## Self-Check: PASSED

- Root Python count = 0；old `_tools`/`examples` absent。
- 114 migrated files have project-local backups; all 232 Phase 19 backups remain under `.migration-backup/` for final gate。
- Full collect, full pytest, five consoles, rollback drills and 12-gate preflight passed。
- `Agent/`, `Google/`, `imports/`, databases, runtime data, analysis and quarantine were not migrated or modified by this plan。

## Next Phase Readiness

Ready for 19-04 assets/apps/tests/docs consolidation. Phase 17 human checkpoints remain open.
