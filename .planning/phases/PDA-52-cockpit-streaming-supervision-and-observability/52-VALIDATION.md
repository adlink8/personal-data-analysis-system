---
phase: 52
status: approved
nyquist_compliant: true
ui_spec_verified: true
---

# Phase 52 Validation Strategy

| Area | Requirements | Command |
|---|---|---|
| Same-origin SSE/control API | UI-01 | `python -m pytest tests/contract/test_pi_cockpit_transport.py -q` |
| React runtime page/states | UI-01 | `npm test --prefix apps/personal_decision_cockpit -- --run src/test/PiRuntimePage.test.tsx` |
| Supervisor ownership/readiness | OPS-01 | `python -m pytest tests/ops/test_pi_kernel_stack.py -q` |
| Privacy/accessibility contracts | UI-01, OPS-01 | `npm test --prefix apps/personal_decision_cockpit -- --run src/test/piRuntimeUatContracts.test.ts` |

Manual browser UAT is deferred to Phase 53; component and contract verification is mandatory here.
