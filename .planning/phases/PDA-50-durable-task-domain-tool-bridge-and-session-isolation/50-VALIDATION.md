---
phase: 50
status: approved
nyquist_compliant: true
---

# Phase 50 Validation Strategy

| Area | Requirements | Command |
|---|---|---|
| Task/session/candidate schemas | KERNEL-03, DATA-02, SESSION-01 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=ledger` |
| Python typed gateway | TOOL-01, DATA-01 | `python -m pytest tests/contract/test_pi_domain_gateway.py -q` |
| Cross-process crash/replay | KERNEL-03 | `python -m pytest tests/integration/test_pi_task_recovery.py -q` |
| Authority isolation/privacy | DATA-01, DATA-02 | `python -m pytest tests/integration/test_pi_artifact_isolation.py -q` |

Full gate requires all commands, SQLite integrity/FK checks, no real Provider and unchanged authority fingerprints.
