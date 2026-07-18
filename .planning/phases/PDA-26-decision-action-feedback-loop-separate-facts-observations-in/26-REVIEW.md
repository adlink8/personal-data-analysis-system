---
phase: 26
reviewed: 2026-07-18
depth: deep
status: clean
files_reviewed: 24
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings: 3
release_status: release_blocked
---

# Phase 26 Code Review

## Verdict

Phase 26 深度审查发现的 3 项完整性问题均已修复并由负向测试复现后转绿。decision acceptance 现在明确区分完整未应用、完整应用和部分应用 schema；assessment 写入口从数据库重建 recommendation、action 与 outcome，并用版本注册表中的规则重新推导后逐字段核对；`release_ready` 仅在技术验收通过且 Phase 24 所有 blocker 均解除时成立。

复核状态为 `clean`。Phase 24 的人工 Gold/Judge/UAT 与 lifecycle 质量门仍未完成，因此项目发布状态继续为 `release_blocked`。本次修复和验证没有运行 live migration/write、生命周期 apply、服务快照或 pointer/watermark 变更、外部动作、网络或付费调用。

## Resolved Findings

### CR-01 — 部分 decision schema fail-open

- **状态:** resolved
- **修复:** acceptance 对八张 decision 表执行三态判定。全部不存在才返回 allowlisted `decision_schema_unapplied`；全部存在才执行完整 replay；任意部分存在均返回 `decision_schema_partial`、列出 `existing_tables`/`missing_tables` 并使 technical gate 失败。
- **测试:** 八张表逐表缺失均覆盖；fixture 中保留 recommendation、support、run 和 genesis 数据，证明部分有数据也不能降级 PASS。

### WR-01 — assessment 写入口信任调用方对象

- **状态:** resolved
- **修复:** `record_assessment()` 要求受控 assessment 类型，在同一数据库事务内校验并重建 recommendation、outcome 和 terminal action，解析受版本注册表约束的 rule，再次执行 `assess_outcome()`；assessment ID、verdict、rule、inputs、limitations、confidence、uncertainty 等全部字段必须与重算结果完全一致。
- **测试:** 缺失 observed value、存在 confounder 的 forged `effective` assessment 均被 `assessment_derivation_mismatch` 拒绝；未知 rule/version 被 `unknown_effectiveness_rule` 拒绝；零 effectiveness 行落库。

### WR-02 — technical failure 可报告 release_ready

- **状态:** resolved
- **修复:** `release_ready = technical_ok and not phase24.release_blocked`。输出新增分列的 `release_blockers.technical` 与 `release_blockers.phase24`，避免混淆技术失败和外部质量门。
- **测试:** 模拟 Phase 24 全部 resolved 后篡改 genesis，结果仍为 `technical_status=failed`、`release_status=release_blocked`，且仅列 technical blocker。

## Commits

- `e41fe3c` — 先加入可稳定复现三项审查问题的失败测试。
- `093296f` — 修复 schema 三态、assessment 派生完整性和 release gate。

## Verification Evidence

- RED：新增的 12 个审查场景在原实现上全部失败。
- GREEN 定向：acceptance、concurrency、effectiveness 共 **41 passed**。
- Phase 26 全量：**65 passed**。
- 相邻 Phase 25、Apps SDK、接口、knowledge search、serving snapshot：**55 passed**。
- Governance preflight：**13/13 PASS**。
- 全仓：**788 passed, 2 skipped**；仅 2 条既有 `SyntaxWarning`。
- Live metadata-only acceptance：exit 0，`technical_status=passed`，`release_status=release_blocked`；decision schema 为完整未应用态；before/after fingerprint 均为 `99b5dacbb9e3ba3ed6c67512d01bae3d2988ffce47e70a2d5da05154e198324c`。
- Live 副作用计数：`persisted_rows=0`、`mutations=0`、`private_bodies=0`、`external_actions=0`、`network_calls=0`、`paid_calls=0`。
- Phase 24 checkpoint 保持 `awaiting_human`、`human_verification_required`、`blocked_on_human_and_quality_gates`，没有伪造解除。

## Remaining Release Boundary

Phase 26 代码审查已 clean，但这不代表 Phase 24 或 Target B/C 的人工与质量证据已经完成，也不授权 live schema migration/publication、lifecycle apply、serving 变更、外部执行或 REST/MCP 写能力。Phase 27 只能依赖当前已验证的 sandbox/read-only 技术合同继续推进。

## F-01 Reverification Addendum

独立验证随后发现 local append 未在写事务内重验 Phase 25 source binding。该缺口现已修复：四个 append 入口在同一 `BEGIN IMMEDIATE` connection 中、幂等回放与 insert 之前调用共享只读 validator，重算 Phase 25 input/output manifest checksum，并核对 publication sequence、snapshot ID/hash 与 decision run/support binding；失败统一为 `source_binding_invalid` 且零 typed row、零 event、sequence 不变。

- RED：output manifest、input checksum、publication sequence、snapshot 四类篡改分别穿透 CLI confirmation、action、outcome、assessment，原实现 4/4 失败。
- GREEN：新增负测 4/4 通过；Phase 26 全量 69/69，通过后 review 结论仍为 `clean`。
- 扩大回归：Phase 25/Apps SDK/knowledge search/serving snapshot 120/120；preflight 13/13；全仓 792 passed、2 skipped。
- Live metadata-only acceptance：`technical_status=passed`、`release_status=release_blocked`，before/after fingerprint 均为 `99b5dacbb9e3ba3ed6c67512d01bae3d2988ffce47e70a2d5da05154e198324c`，所有 mutation/external/network/paid counters 为 0。
