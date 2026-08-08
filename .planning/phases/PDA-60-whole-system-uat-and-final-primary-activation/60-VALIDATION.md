# Phase 60 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Capability/Tool/Skill/data fault matrix | EVAL-03 | `python -m pytest tests/e2e/test_pi_capability_os_uat.py -q` |
| Real paired baseline closure | ACT-03 | `python tools/supported/pi_real_baseline.py --check-preregistration --execute` (manual authorization) |
| Browser/operator privacy UAT | EVAL-03 | `python -m pytest tests/e2e/test_pi_capability_os_browser.py -q` plus human checklist |
| Primary/rollback/restore | ACT-03 | `python -m pytest tests/e2e/test_pi_capability_os_activation.py -q` plus manual confirmations |

Real Provider, live data L3 operations and activation are explicit human checkpoints.
