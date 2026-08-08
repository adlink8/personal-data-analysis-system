---
phase: 53
status: approved
nyquist_compliant: true
---

# Phase 53 Validation Strategy

| Area | Requirements | Command/checkpoint |
|---|---|---|
| Preregistration and paired receipts | EVAL-01 | `python -m pytest tests/e2e/test_pi_legacy_baseline.py -q` |
| Fault matrix | EVAL-02 | `python -m pytest tests/e2e/test_pi_kernel_fault_matrix.py -q` |
| Browser/privacy UAT automation | EVAL-02, ACT-01 | `npm test --prefix apps/personal_decision_cockpit -- --run src/test/piRuntimeUatContracts.test.ts` |
| Real Provider + user UAT | EVAL-01, ACT-01 | manual authorization and signed UAT report |

No real calls run without checkpoint; synthetic green cannot satisfy EVAL-01.
