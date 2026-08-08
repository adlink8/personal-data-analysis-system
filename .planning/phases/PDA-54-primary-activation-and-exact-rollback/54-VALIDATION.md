---
phase: 54
status: approved
nyquist_compliant: true
---

# Phase 54 Validation Strategy

| Area | Requirement | Command/checkpoint |
|---|---|---|
| Activation ledger/config | ACT-02 | `python -m pytest tests/contract/test_pi_runtime_activation.py -q` |
| Primary route/no bypass | ACT-02 | `python -m pytest tests/integration/test_pi_primary_routing.py -q` |
| Stop/rollback/restore drill | ACT-02 | `python -m pytest tests/e2e/test_pi_activation_rollback.py -q` |
| User activation acceptance | ACT-02 | manual signed activation/UAT record |

No primary switch is authorized by automated tests alone.
