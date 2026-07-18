---
phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance
status: clean
depth: deep
files_reviewed: 22
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings: 6
release_status: release_blocked
technical_status: passed
reviewed_at: 2026-07-18
---

# Phase 27 / Target D Deep Code Review

## Verdict

Phase 27 深度审查发现的 3 个 Critical 与 3 个 Warning 已全部修复并由对应负向回归测试证明。复核状态为 `clean`，Target D 技术状态为 `passed`。

产品发布仍为 `release_blocked`：Phase 24 的人工 Gold/Judge/UAT 与 lifecycle 质量门未完成。本次修复未运行 live migration/write/apply，未修改 serving/pointer/watermark、KU/lifecycle 或 Phase 24 checkpoint，未执行网络、付费或外部动作。

## Resolved Findings

### CR-01 — RESOLVED: Target D acceptance 执行真实 disposable SQLite 全链

- `_technical_sandbox()` 现在在同一个临时 SQLite authority 内实际执行 Phase 25 → 26 → 27：状态 current/history、accepted/rejected recommendation history、action/outcome/non-causal assessment、八域 coordination、ranking/noise、run publication、suppress/status/restore、stale append、restore 后 future run，以及 shared get/explain。
- 所有 `stage_results` 都由真实调用结果计算；逐 stage 故障注入会使 `ok=false` 和对应 stage=false。
- live applied 三态校验不再以表存在或空 inbox 作为通过证据。Phase 25/26/27 applied 状态必须存在 committed run，并验证 active snapshot/hash、manifest/checksum、publication/event/control frontier 与完整 child manifests；零 run、partial、corrupt 或 mixed binding 技术失败。

### CR-02 — RESOLVED: ResourceClaim 身份与 source 进入 canonical support

- `ResourceClaim` 新增显式 `resource_id`；共享资源不仅比较 type/unit/horizon，还必须具有相同可验证身份。
- 每个决定性 resource source 必须与 goal source 使用同一 snapshot/run binding，并进入 `CoordinationDraft.source_refs`。
- `plan_run()` 与发布事务内对 resource source 复用 authority/type/record checksum/source run/snapshot 校验；跨 snapshot、伪造、不一致 identity 与缺失 decisive support 均 fail closed。

### CR-03 — RESOLVED: exact replay 完整校验 proactive_candidate_support

- `_validate_existing()` 重建每个候选的完整 support 集合，逐列比较 canonical payload/checksum 与 deterministic support ID，并重新验证 source record/run/snapshot binding。
- 缺行、额外行、payload tamper 和 record checksum drift 四类回归均被 `existing_support_tampered` 拒绝。

### WR-01 — RESOLVED: restore 遵守历史 as_of

- restore 只有在 `created_at <= as_of` 时才撤销原控制。
- 回归覆盖 restore 前、边界时刻和 restore 后，未来补偿事件不再追溯修改历史 projection。

### WR-02 — RESOLVED: target specificity 为主排序维度

- precedence 从 `max(target_rank, scope_rank)` 改为 `(target_rank, scope_rank)` 字典序。
- exact target 始终高于 policy/domain/global target，scope specificity 仅作为次级维度；同级 denial 规则保持 fail closed。
- 矩阵回归覆盖 exact/global、exact/domain、policy/domain 及不同 scope specificity。

### WR-03 — RESOLVED: immutable run frontier 与 current control overlay 分离

- 每个新 run 持久化 immutable `control_frontier_manifest`；读取时逐项验证历史 event identity/sequence/checksum，额外的新控制不会使旧 run lineage 失效。
- get/inbox/explain 在历史 run 校验通过后投影当前 global/policy/domain/exact overlay，并公开历史 frontier 与 current frontier 两个 checksum。
- append 后 get/status/explain、restore 后 status 均可用；旧 run 的 lineage checksum 保持不变，future run 绑定新的 frontier。

## Commits

- `48cc568` — 添加六项审查缺口的 RED 回归测试。
- `206da27` — 修复资源谱系、support replay、时点/优先级与 current overlay。
- `7b50c44` — 实现真实 Target D disposable sandbox 与 live applied 完整性校验。

## Verification Evidence

- 审查新增及直接受影响测试：**49 passed**。
- Phase 27 全量：**86 passed**。
- Phase 25/26 相邻回归：**78 passed**。
- Apps SDK、knowledge search、serving snapshot：**33 passed**。
- Governance preflight：**13/13 PASS**。
- 全仓：**PASS，2 skipped**；仅 2 条既有 `SyntaxWarning`。
- `git diff --check`：PASS。
- live `acceptance --dry-run --metadata-only --json`：`technical_status=passed`、`release_status=release_blocked`；before/after fingerprint 均为 `4dd84122a832d593006f6f7107d96abe80fb6c77dfa7c2144cc06f0ec898476c`。
- live side effects：`persisted_rows=0`、`mutations=0`、`private_bodies=0`、`external_actions=0`、`network_calls=0`、`paid_calls=0`。

## Preserved Release Boundary

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`
- Human review strict: false
- Lifecycle strict: false
- Explicit product UAT: absent

因此 Phase 27 / Target D 的技术代码审查已 clean，但产品级 Target D 仍未签署完成，也不授权 live schema migration/publication、lifecycle apply、serving 变更或外部执行。
