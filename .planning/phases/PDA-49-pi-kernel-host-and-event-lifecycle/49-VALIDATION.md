---
phase: 49
status: approved
nyquist_compliant: true
---

# Phase 49 Validation Strategy

| Task area | Requirement | Automated command |
|---|---|---|
| Event schema/checksum | KERNEL-02 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=event-schema` |
| Journal/idempotency/restart | KERNEL-02 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=event-journal` |
| Host health/readiness/shutdown | KERNEL-01 | `python -m pytest tests/contract/test_pi_kernel_host.py -q` |
| SSE cursor/replay/privacy | KERNEL-01, KERNEL-02 | `python -m pytest tests/integration/test_pi_kernel_events.py -q` |

Full gate: Node tests plus both Python files; zero Provider calls and unchanged authority fingerprints are mandatory.
