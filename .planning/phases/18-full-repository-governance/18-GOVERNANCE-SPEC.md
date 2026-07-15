# Phase 18 Governance Specification

## Logical zones

```text
src/          tracked product code and entrypoints
tests/        tracked deterministic tests
assets/       tracked prompts/evals/vendor assets
docs/         tracked architecture, ADRs and runbooks
governance/   policies, schemas and sanitized summaries
data/         ignored raw/staging/canonical private planes
var/          ignored db/runtime/reports/logs
archive/      indexed, retention-bound cold material
.planning/    authoritative GSD lifecycle
```

现有路径先映射到上述逻辑 zone；是否物理迁移由 18-06 决定。

## Per-file inventory schema

每个节点必须生成：`path, node_type(file|directory|symlink|reparse), zone, kind, owner_module, maintainer, privacy_class, git_policy, source_of_truth, producer, consumers, schema_version, format, size, mtime, content_hash_policy, run_id, input_hashes, config_hash, retention, disposal, backup, restore_tested_at, validation, status, replacement, last_reviewed`。

默认 R3/R4 `content_hash_policy=none|filesystem-metadata`，scanner 禁止 open/read；不将正文、可逆摘要或内容 hash 写入 inventory。若某权威 artifact 必须计算完整 hash，必须走独立、显式授权、本地-only checkpoint，且只输出 digest；tracked summary 只保存计数和规则覆盖。

## Metadata applicability

策略必须定义 `kind × required_fields` matrix。owner/maintainer/privacy/git/status/retention/validation 对所有节点必填；generated/database/vector/report 必须有 producer/run/input/config/schema lineage；source 必须有 source_of_truth/consumers；directory 必须有 owner/zone/status。只有 policy 明确允许时才能写 N/A，且必须同时提供 `na_reason` 与 `policy_id`。空值、无理由 N/A 和 orphan 无 owner/deadline 均 fail closed。

## Policy precedence

规则按 specificity + explicit priority 计算；每个非 Git-internal 节点（文件、目录、空目录、symlink、junction/reparse）必须 exactly one effective policy。显式 node override > nearest directory policy > zone default；deny/private 优先于 allow。冲突、未知、大小写碰撞、外部 traversal、symlink/reparse escape 均 fail closed。Excluded zone 仍枚举并统计最深后代，但不读取内容。

## Privacy classes

- R1 public：源码、公开文档、synthetic fixtures。
- R2 internal：内部元数据、非私人运维信息。
- R3 derived personal inference：画像、聚合、embedding、脱敏报告。
- R4 raw/linkable evidence：会话、活动、数据库、private eval、secret-bearing 内容。

## Architecture invariants

1. private/raw → normalize → canonical → candidate → eval → promote → read-only distribution。
2. 下游不得写 live external source。
3. source 不依赖 archive/quarantine/raw 的具体物理路径。
4. generated artifacts 必须可追溯 producer/run/input/config/schema。
5. mutable publish 必须 stage/gate/promote/journal/rollback。
6. `.planning` 状态必须与运行事实和 phase artifacts 一致。

## Governance gates

`inventory-check`, `privacy-check`, `path-policy`, `shim-budget`, `dependency-lock`, `architecture-boundary`, `docs-coverage`, `artifact-lineage`, `planning-consistency`, `storage-retention`, `secret-scan`, `test-matrix`。
