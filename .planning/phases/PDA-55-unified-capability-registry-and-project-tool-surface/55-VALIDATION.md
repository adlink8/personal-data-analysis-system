# Phase 55 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Registry schema/checksum/profile | CAP-01, CAP-02 | `python -m pytest tests/contract/test_project_capability_registry.py -q` |
| Deterministic descriptor generation | CAP-01 | `python tools/supported/generate_capability_descriptors.py --check` |
| Pi/MCP read tool parity | PTOOL-01 | `python -m pytest tests/integration/test_pi_capability_tools.py -q && npm test --prefix apps/personal_data_chatgpt` |
| Containment/fingerprint regression | CAP-02 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=capability-registry` |

No live provider or authority mutation is permitted in Phase 55 validation.
