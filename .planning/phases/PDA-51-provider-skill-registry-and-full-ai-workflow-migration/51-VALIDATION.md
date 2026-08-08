---
phase: 51
status: approved
nyquist_compliant: true
---

# Phase 51 Validation Strategy

| Area | Requirements | Command |
|---|---|---|
| Provider routing/auth/budget | MODEL-01, MODEL-02 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=provider` |
| Skill registry/selection | SKILL-01 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill` |
| Python provider parity | MODEL-01 | `python -m pytest tests/contract/test_pi_provider_adapter.py -q` |
| Full callsite migration | MODEL-01, MODEL-02, SKILL-01 | `python -m pytest tests/governance/test_pi_ai_entrypoint_inventory.py -q` |

Full gate prohibits real Provider calls and requires zero unclassified production AI callsites.
