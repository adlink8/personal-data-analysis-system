---
phase: 56
plan: 02
subsystem: warehouse-mutations
tags: [operation-ledger, idempotency, confirmation, recovery, compensation]
requires: [56-01]
provides: [pi-data-operation-ledger, exact-preview-commit, outcome-unknown-recovery]
affects: [Phase 57, Phase 59, Phase 60]
tech-stack:
  added: []
  patterns: [metadata-only-ledger, append-only-compensation, receipt-reconciliation]
key-files:
  created:
    - src/personal_knowledge/services/warehouse_mutations.py
    - tests/integration/test_pi_warehouse_mutations.py
    - tests/e2e/test_pi_warehouse_recovery.py
  modified:
    - src/personal_knowledge/services/pi_domain_gateway.py
requirements-completed: [WARE-02, SEC-03]
duration: 25 min
completed: 2026-08-05
---

# Phase 56 Plan 02: Guarded ingestion and canonical maintenance

Implemented the `pi_data_operations` metadata ledger and exact preview protocol.
Each operation binds a logical authority, source checksum, snapshot/watermark,
idempotency identity, plan checksum and before/after fingerprint. A commit must
use the server-issued unexpired preview with the same idempotency identity;
tampered, stale or binding-drifted previews fail before the fixture adapter is
changed. Duplicate commits return the original receipt.

Raw rows are immutable. Candidate ingestion is represented by bounded metadata
events, while canonical correction is an append-only compensation event linked
to the original operation. Canonical operations require explicit confirmation.
The Pi gateway routes exact previews to this Python ledger and never receives a
database handle, SQL, path or callable.

Crash injection covers before-transaction, after-store-before-receipt and
after-receipt states. `outcome_unknown` rejects blind retry; receipt
reconciliation converges to one committed receipt, and compensation is a
separate declared append-only operation.

## Verification

- `python -m pytest tests/integration/test_pi_warehouse_mutations.py tests/e2e/test_pi_warehouse_recovery.py -q` — 8 passed.
- `python -m pytest tests/contract/test_pi_warehouse_read_tools.py tests/security/test_pi_warehouse_tool_containment.py tests/integration/test_pi_capability_tools.py tests/contract/test_project_capability_registry.py -q` — 31 passed.
- `python -m compileall -q src/personal_knowledge/services/warehouse_tools.py src/personal_knowledge/services/warehouse_mutations.py src/personal_knowledge/services/pi_domain_gateway.py` — passed.

## Deviations from Plan

- [Rule 1 - Local authority fixture] Automated verification uses an in-memory
  authority adapter plus a temporary SQLite operation ledger. No live
  `var/db` authority is opened, and no production watermark or pointer is
  advanced.

**Total deviations:** 1 intentional safety boundary. **Impact:** protocol and
recovery semantics are proven without performing a live data mutation.

## Self-Check: PASSED

- Implementation commit: pending
- Raw fingerprint remains byte-identical in integration and recovery tests.
- Ready for Phase 57.
