# Phase 56: Controlled Warehouse Inspection, Ingestion and Canonical Operations — Context

<domain>
## Phase Boundary

让 Pi 通过受控 Python Tools 检查底仓，并执行 source discovery/validation/quarantine、增量导入和 canonical reconcile/correction。本阶段不执行 S/R 发布或 active pointer 切换。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** Pi 可以操作底仓流程，但永远不获得数据库连接、SQL、任意路径或 Python callable。
- **D-02:** Raw source immutable；canonical 修正使用 append-only compensation，不 UPDATE/DELETE 历史事实。
- **D-03:** 所有 mutation 使用 operation ledger、snapshot/watermark binding、idempotency key 和 before/after fingerprint。
- **D-04:** L0 read 与 L1 quarantine/candidate 可自动；canonical append/correction 属 L3，必须 exact preview 与确认。
- **D-05:** 结果采用 bounded counts、stable IDs、artifact refs 和 safe reason codes，不返回大正文或绝对路径。
- **D-06:** crash/outcome_unknown 必须先 reconcile receipt，再决定 resume/compensate，禁止盲重试。

### the agent's Discretion

Operation ledger SQLite schema、batch chunk size 和既有 importer adapter 封装方式。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `src/personal_knowledge/application/conversation/`
- `src/personal_knowledge/application/knowledge/`
- `src/personal_knowledge/services/pi_domain_gateway.py`
- `tools/split_sessions_db.py`
- `governance/policies/`
</canonical_refs>

<deferred>
## Deferred Ideas

Semantic/backfill/index/promotion：Phase 57；workflow Skills：Phase 58。
</deferred>
