# Phase 57: Semantic/Retrieval Maintenance and Guarded Release Tools — Context

<domain>
## Phase Boundary

把知识抽取、repair/backfill、索引 build/reconcile/evaluate 和 Serving Snapshot release/rollback 变成正式 Data-plane Tools，并统一 mutation protocol。本阶段不定义上层 Skills。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** S/R/A 是可重建制品；Pi 可按批准 policy 自动生成，但不能自动绕过 evaluation/promotion。
- **D-02:** 抽取和修复只写 Candidate/staging，必须绑定 source evidence、extractor/model receipt 和 schema version。
- **D-03:** 索引 build 使用新 generation，reconcile 要求 missing/orphan/duplicate 全为零。
- **D-04:** snapshot prepare 固定 manifest/checksum/eval/fingerprints；activate/rollback 是 L3 人工确认操作。
- **D-05:** active pointer 原子切换；失败或进程退出保持原 active，不能留下 split generation。
- **D-06:** 所有写 Tool 共用 Phase 56 operation ledger 和 preview/receipt/compensation 状态机。

### the agent's Discretion

各 pipeline adapter 的命令封装和 fixture 数据规模。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `src/personal_knowledge/application/knowledge/`
- `src/personal_knowledge/application/serving/`
- `src/personal_knowledge/retrieval/`
- `governance/policies/`
- `.planning/phases/PDA-56-controlled-warehouse-inspection-ingestion-and-canonical-operations/56-CONTEXT.md`
</canonical_refs>

<deferred>
## Deferred Ideas

跨工具业务编排：Phase 58 Skills；真实主路径：Phase 60。
</deferred>
