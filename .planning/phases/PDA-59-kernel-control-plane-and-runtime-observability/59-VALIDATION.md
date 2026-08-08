# Phase 59 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Kernel operation schema/reducer | OPS-02 | `node --test apps/personal_intelligence_kernel/test/runtime-control.test.mjs` |
| Cancel/resume/reconcile and outcome_unknown | OPS-02 | `python -m pytest tests/integration/test_pi_runtime_control.py -q` |
| Metadata-only projection and Cockpit states | OPS-02 | `python -m pytest tests/contract/test_pi_operation_projection.py -q` plus `npm test --prefix apps/personal_decision_cockpit -- --run PiOperationStatus` |
| No Local Pi runtime dependency | OPS-02 | `rg -n "local-pi|pi --mode rpc|PI_CODING_AGENT_DIR" apps src tests ops` returns no new production integration |

All default validation uses deterministic fixtures and zero real Provider calls. Real Provider and activation remain Phase 60 checkpoints.
