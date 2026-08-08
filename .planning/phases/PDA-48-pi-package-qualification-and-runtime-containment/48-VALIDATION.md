---
phase: 48
slug: pi-package-qualification-and-runtime-containment
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-08-04
---

# Phase 48 — Validation Strategy

## Test Infrastructure

| Property | Value |
|---|---|
| **Framework** | Node `node:test` + Python pytest |
| **Config file** | `apps/personal_intelligence_kernel/package.json`, `pyproject.toml` |
| **Quick run** | `npm test --prefix apps/personal_intelligence_kernel` |
| **Full suite** | `python -m pytest tests/contract/test_pi_package_qualification.py tests/contract/test_pi_runtime_containment.py tests/governance/test_pi_package_decision.py -q` |
| **Estimated runtime** | <120 seconds, excluding registry latency |

## Sampling Rate

- 每个 task 后运行对应 Node/Python定向测试。
- 每个 plan wave 后运行当时已有的全部 Phase 48 tests。
- Phase 48 verify 前必须从 clean `npm ci --ignore-scripts` 开始执行完整 gate。
- 最大本地反馈延迟 120 秒；npm registry 超时单独标记 infrastructure failure，不降级为通过。

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---|---:|---:|---|---|---|---|---|---|
| 48-01-01 | 01 | 1 | SEC-01 | T48-01 | exact pin/integrity/script policy | contract | `python -m pytest tests/contract/test_pi_package_qualification.py -q` | ⬜ |
| 48-01-02 | 01 | 1 | SEC-01 | T48-01 | audit High/Critical blocks | node+contract | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=package-qualification` | ⬜ |
| 48-02-01 | 02 | 2 | TOOL-02 | T48-02 | zero ambient resource/built-ins | node | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=runtime-containment` | ⬜ |
| 48-02-02 | 02 | 2 | SEC-02 | T48-03 | fs/process/network/credential fail closed | contract | `python -m pytest tests/contract/test_pi_runtime_containment.py -q` | ⬜ |
| 48-03-01 | 03 | 3 | SEC-01..02 | T48-04 | report privacy and fingerprint integrity | governance | `python -m pytest tests/governance/test_pi_package_decision.py -q` | ⬜ |
| 48-03-02 | 03 | 3 | TOOL-02 | T48-04 | only accepted unlocks next phase | full gate | `node apps/personal_intelligence_kernel/scripts/qualify-packages.mjs --check` | ⬜ |

## Wave 0 Requirements

- [ ] `apps/personal_intelligence_kernel/package.json` and exact lockfile.
- [ ] Node test directory and package qualification fixtures.
- [ ] Python contract/governance test files listed above.
- [ ] `governance/manifests/ai/` package/tool/network manifest directory.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|---|---|---|---|
| Registry/source review | SEC-01 | License/repository ownership requires human acceptance | Compare report repository/tag/integrity with official registry and approve decision field |

## Validation Sign-Off

- [x] Every task has an automated command or Wave 0 dependency
- [x] No three consecutive tasks lack automated feedback
- [x] No watch-mode command
- [x] High/Critical, unknown capability and privacy findings are blocking
- [x] `nyquist_compliant: true`

**Approval:** approved for planning 2026-08-04
