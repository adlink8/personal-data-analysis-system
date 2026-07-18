---
phase: 26
reviewed: 2026-07-18
depth: deep
status: issues_found
files_reviewed: 21
findings:
  critical: 1
  warning: 2
  info: 0
  total: 3
release_status: release_blocked
---

# Phase 26 Code Review

## Verdict

Phase 26 的主体边界、append-only 事务、genesis/checksum 链、并发与幂等、CLI 显式确认、REST/MCP 只读面以及 Phase 24 阻断保持均有较强测试覆盖；定向套件 53 项全部通过。但深度审查发现 3 个可复现的完整性问题，其中 acceptance 对部分 schema 的 fail-open 会把迁移漂移降级为技术 PASS，因此当前审查状态为 `issues_found`，Phase 26 不应在修复和复核前进入最终技术验收。

Phase 24 仍为 `release_blocked`。本审查没有运行 live migration/write、生命周期 apply、服务快照变更、外部动作、网络或付费调用。

## Findings

### CR-01 — 部分应用的 decision schema 被当作“未应用”并技术 PASS

- **文件:** `src/personal_knowledge/intelligence/decision/cli.py:396`
- **影响:** 只要八张 decision 表中任意一张缺失，`decision_ready = all(...)` 就为 false，代码直接保留 `decision_gate.ok=true` 和 `reason=decision_schema_unapplied`，不会检查其余已存在表中的数据或迁移漂移。部分迁移、意外删表或不完整升级因此可被 acceptance 误报为 `technical_status=passed`，违反“仅完整未应用 schema 可 allowlist、完整性错误不可降级 PASS”的验收边界。
- **复现证据:** 在完整临时 fixture 中仅删除空的 `decision_effectiveness` 表后运行 `run_acceptance()`，返回 `ok=true`、`technical_status=passed`、`decision_schema_applied=false`、`reason=decision_schema_unapplied`。数据库仍保留 decision run、recommendation、support 和 genesis 数据，因此它不是未应用状态，而是部分应用/漂移状态。
- **修复要求:** 明确区分“八张表全部不存在”“八张表全部存在”“仅部分存在”。只有全部不存在且 Phase 25 source 状态也属于允许的空态时才可返回 allowlisted empty；部分存在必须返回稳定的 `decision_schema_partial`/`schema_drift` 错误并使 technical gate 失败。增加逐一缺表和部分有数据的 acceptance 负向测试。

### WR-01 — assessment 写入口可持久化未由规则推导的伪造 verdict

- **文件:** `src/personal_knowledge/intelligence/decision/state_machine.py:714`
- **影响:** `record_assessment()` 只检查 `cognitive_type=inference`、`causal_claim=false`、verdict 枚举以及 outcome/checksum 绑定；它不验证参数是 `EffectivenessAssessment` 的受信实例，也不根据持久化 outcome、action state 和声明的 rule 重新运行 `assess_outcome()`。调用方可为缺失观测值且存在 confounder 的 outcome 构造任意 `effective` verdict、任意 rule ID/version 和空 limitations，并写入 append-only authority。随后 service 会将该记录作为 checksum 合法的效果评估返回。
- **复现证据:** 临时 fixture 记录了 `observed_value=None`、`confounders=('seasonality',)` 的 outcome；手工构造 `EffectivenessAssessment(verdict='effective', rule_id='forged', limitations=())` 后，`record_assessment()` 成功插入 `decision_effectiveness`，数据库值为 `effective/forged`，payload 中没有 `confounded` 或 `missing_observed_value`。同一 outcome 通过 `assess_outcome()` 应为 `inconclusive`。
- **修复要求:** 让持久化入口接收受版本注册表约束的 rule 标识并从数据库重新 hydrate outcome/action 后重新推导 assessment，要求推导结果与提交对象逐字段一致；或将 assessment 构造与写入合并为唯一受控 API。拒绝未知 rule/version、伪造 ID、verdict/limitations/confidence 不一致，并加入 confounded/missing outcome 的伪造写负向测试。

### WR-02 — 技术验收失败时仍可能报告 `release_ready`

- **文件:** `src/personal_knowledge/intelligence/decision/cli.py:414`
- **影响:** `release_status` 只取决于 Phase 24 的 `release_blocked`，没有包含 `technical_ok`。一旦 Phase 24 未来通过，任何 sandbox、Phase 25、decision integrity 或 fingerprint 失败都会得到 `ok=false`、`technical_status=failed`，但同时报告 `release_status=release_ready`。这会向后续自动化或人工验收输出相互矛盾的发布信号。
- **复现证据:** 在临时 fixture 中篡改 sequence=1 genesis 使 decision gate 返回 `event_checksum_mismatch`，并模拟 Phase 24 已解除阻断；结果为 `ok=false`、`technical_status=failed`、`release_status=release_ready`。
- **修复要求:** `release_ready` 必须同时要求 `technical_ok` 和全部外部 release blockers 已解除；否则返回 `release_blocked`，并分别列出 technical 与 Phase 24 blocker reason。增加 Phase 24 resolved + technical failure 的 acceptance 测试。

## Verified Boundaries

- `a.decision_feedback` 是非 serving 的 A-layer authority，未加入 `required_serving_roles`。
- 推荐发布与 sequence=1 `recommendation_published` genesis 在一个 `BEGIN IMMEDIATE` 事务中；故障注入覆盖 recommendation/genesis、typed row/event 回滚。
- confirmation/action/outcome 使用 expected sequence、idempotency key 和 checksum 链；REST/MCP 仅暴露五个读取 surface，没有 decision 写入或外部执行工具。
- action metadata 禁止 command/URL/connector/credential/dispatch 字段；confirmation 和 local CLI guard 要求显式 `--write`、精确 `--i-confirm` 与 user actor。
- outcome/effectiveness schema 固定 `causal_claim=false`；但 WR-01 表明 verdict 推导完整性仍需在写边界补强。
- 当前 Phase 24 checkpoint 状态仍为 `awaiting_human`、`human_verification_required`、`blocked_on_human_and_quality_gates`。

## Review Evidence

- 审查了 21 个指定去重文件，并追踪 schema、publication、state projection、assessment、service hydration、CLI、REST/MCP 与 acceptance 调用链。
- 定向 Phase 26 套件：`53 passed`。
- 两个临时 SQLite 复现分别证明 partial-schema technical PASS 与伪造 assessment 成功持久化。
- 一个临时 acceptance 复现证明 technical failure 与 `release_ready` 可同时出现。
- 所有复现均使用一次性临时目录；未修改 live DB、active pointer、Phase 24 checkpoint、生命周期、KU、watermark 或 serving authority。

