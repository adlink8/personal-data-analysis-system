# Phase 57 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Extraction/repair/backfill staging | WARE-03 | `python -m pytest tests/integration/test_pi_semantic_maintenance.py -q` |
| Index build/reconcile/evaluation | WARE-03 | `python -m pytest tests/integration/test_pi_retrieval_maintenance.py -q` |
| Preview/confirm/replay protocol | PTOOL-02 | `python -m pytest tests/contract/test_pi_guarded_write_tools.py -q` |
| Snapshot activate/rollback fault drill | WARE-04 | `python -m pytest tests/e2e/test_pi_snapshot_release.py -q` |

Automated activation targets temporary serving roots only; a live-pointer drill is a manual checkpoint.
