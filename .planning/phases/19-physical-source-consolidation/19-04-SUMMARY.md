---
phase: 19
plan: "04"
subsystem: physical-source-migration
tags: [apps, assets, docs, tests, rollback, governance]
requires: [19-03]
provides: [physical-app-layout, versioned-assets, layered-tests, exact-layout-rollback]
affects: [19-05, phase-20-private-eval-data]
tech-stack:
  added: []
  patterns: [immutable-layout-manifest, explicit-asset-classification, five-layer-test-layout]
key-files:
  created:
    - governance/manifests/source/apps-assets-docs-tests.json
    - governance/manifests/asset_classification.json
    - apps/personal_data_chatgpt/package.json
    - assets/evals/knowledge_units/eval_v1.yaml
    - assets/prompts/knowledge_unit_extractor/v1_main.md
    - assets/vendor/vis-9.1.2/vis-network.min.js
    - docs/architecture/retrieval-ssot.md
  modified:
    - src/personal_knowledge/governance/source_manifest.py
    - src/personal_knowledge/governance/apply_source_migration.py
    - governance/policies/architecture.yaml
    - governance/stable_modules.yaml
key-decisions:
  - "Four *.private.jsonl evaluation datasets remain under integration/evals for Phase 20; Phase 19 moved only public/versioned eval contracts."
  - "Tests are physically split into unit, contract, integration, e2e and governance with unique module identity and unchanged collection coverage."
  - "Every failed verification triggered exact journal rollback before the manifest generator was corrected and the cohort was reapplied."
requirements-completed: [PHY-04, PHY-06, PHY-07]
duration: 2h
completed: 2026-07-13
---

# Phase 19 Plan 04: Apps, assets, docs and tests physical layout Summary

应用、公开评测契约、prompts、vendor 运行依赖、模块文档和测试源码已用不可变清单完成物理收口；144 个文件完成移动，112 个消费者按精确 prestate 改写，私有评测数据未被读取、移动或复制。

## Results

- Manifest checksum：`c03c8d6f51e0759bc39145686d5b981ddb36f087707857842d1540ffee6c1577`。
- Manifest file SHA-256：`c2349762436499df7660746c56726f8064f2b8303c4834c5bc4297524a7d8a8c`。
- Operations：144；consumer rewrites：112；post-reapply mismatch：0。
- Asset classification：application source、prompt contract、eval contract、vendor runtime dependency、docs、module contracts 和 tests 均唯一分类；ambiguous=0。
- Tests：unit 32、contract 8、integration 17、e2e 1、governance 11；collect 465，较基线 464 不减，新增 1 个 manifest contract test；test basename 唯一。
- `integration/apps`、`integration/prompts`、`integration/lib`、`integration/docs` 已无文件并移除空物理树。
- `integration/evals` 仅保留 4 个 `*.private.jsonl`，处置为 `phase20-pending`；公开 eval 资产和旧公开路径引用均为 0。

## Verification

- `python -m pytest -q`：464 passed，1 skipped。
- `python -m pytest --collect-only -q`：465 collected，退出 0。
- `npm test --prefix apps/personal_data_chatgpt`：10/10 passed。
- Phase 17 eval tests：26/26 passed。
- Layout/docs/eval 定向复验：22 passed。
- `python integration/scripts/governance/preflight.py --ci`：12/12 PASS。
- 旧 apps/prompts/lib/docs 与公开 eval 引用扫描：0。

## Rollback Drill

最终批准清单执行 `apply → full verification → rollback → exact prestate audit → dry-run → re-apply`：

- 144 个 source prestate mismatch：0。
- 112 个 consumer rewrite prestate mismatch：0。
- rollback 后残留 target：0。
- re-apply 后 source/target mismatch：0。
- canonical journal、backup、stage 均限制在 workspace 内；没有写入桌面根目录。

## Deviations from Plan

**[Rule 1 - Path rewrite regression] Completed component-built path rewrites.** 首轮验证发现部分 Python 通过 `Path / "integration" / "prompts|evals"` 构造路径，精确字符串映射未覆盖。生成器补充 component rewrite，并将公开 eval 与 4 个 private eval 明确分流。

**[Rule 1 - Historical manifest preservation] Excluded immutable manifests from consumer rewrites.** 首轮误将历史 signed manifest 当普通文本消费者；事务立即回滚，随后将 `governance/manifests/` 全部排除，历史 checksum 保持有效。

**[Rule 2 - Governance metadata synchronization] Synchronized zones, stable modules and module READMEs.** 新物理树要求 architecture/stable-module/docs coverage 同步；9 个领域 README 随 canonical 模块收口，治理 preflight 恢复 12/12。

**[Rule 2 - Windows-safe Python path text] Normalized moved test command examples.** Windows 反斜杠路径迁入 `tests/unit` 后出现 `\u` 字面量风险，生成器对测试文档字符串改用正斜杠，collect 恢复且身份唯一。

**Total deviations:** 4 in-scope migration/safety fixes. **Impact:** no private/data/archive migration and no production database mutation.

## Self-Check: PASSED

- Manifest、classification、inverse、checksum、journal 和 rollback 均可复验。
- Full Python、Node、eval、docs、prompt 和 12-gate preflight 全绿。
- 4 个 private eval 文件保持原位，仅元数据标记为 Phase 20 pending。
- 未 stage、未 commit；未进入 19-05。

## Next Phase Readiness

Ready for 19-05 final inventory/reconcile. Phase 17 human checkpoints remain open; Phase 20 owns private eval and other data/runtime relocation.
