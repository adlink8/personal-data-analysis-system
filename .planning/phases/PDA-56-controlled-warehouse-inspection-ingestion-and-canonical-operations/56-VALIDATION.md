# Phase 56 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Inspect/lineage/quality bounded reads | WARE-01 | `python -m pytest tests/contract/test_pi_warehouse_read_tools.py -q` |
| Ingestion/canonical transaction protocol | WARE-02 | `python -m pytest tests/integration/test_pi_warehouse_mutations.py -q` |
| Forbidden capabilities/fingerprint invariants | SEC-03 | `python -m pytest tests/security/test_pi_warehouse_tool_containment.py -q` |
| Crash/replay/compensation | WARE-02 | `python -m pytest tests/e2e/test_pi_warehouse_recovery.py -q` |

Live authority paths are forbidden in automated tests.
