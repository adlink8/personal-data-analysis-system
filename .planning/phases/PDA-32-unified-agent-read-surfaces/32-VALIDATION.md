---
phase: 32
slug: unified-agent-read-surfaces
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-18
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|---|---|
| **Framework** | pytest 9.0.2 + Node `node:test` |
| **Config file** | `pytest.ini`; `apps/personal_data_chatgpt/package.json` |
| **Quick run command** | `python -m pytest tests/unit/test_agent_read_services.py -q` |
| **Full suite command** | `python -m pytest tests/unit/test_agent_read_services.py tests/integration/test_agent_read_authority_integrity.py tests/contract/test_agent_read_interfaces.py tests/contract/test_agent_read_end_to_end.py -q` |
| **Estimated runtime** | <60 seconds on local fixtures |

## Sampling Rate

- **After every task commit:** Run the task's targeted `pytest` or `node --test` command.
- **After every plan wave:** Run the plan-level `<verification>` command.
- **Before `$gsd-verify-work`:** Python and Node Phase 32 suites must be green.
- **Max feedback latency:** 60 seconds.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---|---:|---:|---|---|---|---|---|---|---|
| 32-01-01 | 01 | 1 | AGENT-02 | T-32-01/02 | Tamper fails closed; provider bodies excluded | unit | `python -m pytest tests/unit/test_agent_read_services.py -q` | ❌ W0 | ⬜ pending |
| 32-01-02 | 01 | 1 | AGENT-01/03/04 | T-32-01/03 | Four authority reads preserve boundaries | unit | `python -m pytest tests/unit/test_agent_read_services.py -q` | ❌ W0 | ⬜ pending |
| 32-01-03 | 01 | 1 | AGENT-01..04 | T-32-01/04 | DB fingerprints unchanged | integration | `python -m pytest tests/integration/test_agent_read_authority_integrity.py -q` | ❌ W0 | ⬜ pending |
| 32-02-01 | 02 | 2 | AGENT-01..04 | T-32-03 | REST delegates only to shared service | contract | `python -m pytest tests/contract/test_agent_read_interfaces.py -q -k rest` | ❌ W0 | ⬜ pending |
| 32-02-02 | 02 | 2 | AGENT-01..04 | T-32-03/05 | MCP schemas are bounded and read-only | contract | `python -m pytest tests/contract/test_agent_read_interfaces.py tests/contract/test_mcp_server_contracts.py -q` | existing + ❌ W0 | ⬜ pending |
| 32-02-03 | 02 | 2 | AGENT-01..04 | T-32-03 | REST/MCP parity and legacy compatibility | contract | `python -m pytest tests/contract/test_agent_read_interfaces.py tests/contract/test_mcp_server_contracts.py -q` | existing + ❌ W0 | ⬜ pending |
| 32-03-01 | 03 | 3 | AGENT-01..04 | T-32-05 | Truthful Apps MCP annotations | Node contract | `node --test apps/personal_data_chatgpt/test/agent-read-tools.test.mjs` | ❌ W0 | ⬜ pending |
| 32-03-02 | 03 | 3 | AGENT-01..04 | T-32-02 | Compact default payload and drill-down | Node contract | `node --test apps/personal_data_chatgpt/test/agent-read-tools.test.mjs` | ❌ W0 | ⬜ pending |
| 32-03-03 | 03 | 3 | AGENT-01..04 | T-32-01..05 | End-to-end zero mutation | integration | `python -m pytest tests/contract/test_agent_read_end_to_end.py -q` | ❌ W0 | ⬜ pending |

## Wave 0 Requirements

- [x] Existing test runners and shared Phase 28–31 fixtures cover framework needs.
- [ ] Create the four Phase 32 test files named above as part of their owning tasks.

## Manual-Only Verifications

All Phase 32 behaviors have automated verification. Real ChatGPT Developer Mode acceptance belongs to Phase 35.

## Validation Sign-Off

- [x] All tasks have automated verification.
- [x] Sampling continuity has no three-task gap.
- [x] Wave 0 dependencies are identified.
- [x] No watch-mode flags.
- [x] Feedback latency target is below 60 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-07-18
