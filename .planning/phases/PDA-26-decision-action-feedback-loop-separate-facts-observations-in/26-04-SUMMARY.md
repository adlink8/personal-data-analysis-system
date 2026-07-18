---
phase: 26-decision-action-feedback-loop
plan: 04
subsystem: decision-feedback-interfaces-acceptance
tags: [cli, rest, mcp, privacy, checksums, acceptance]
requires:
  - phase: 26-03
    provides: Typed outcomes and observational non-causal effectiveness
provides:
  - One checksum-verifying decision read service shared by CLI, REST and MCP
  - Explicit human-bound local CLI writes with optimistic sequence and idempotency
  - Metadata-only live acceptance with a complete disposable sandbox loop
affects: [phase-26-verification, phase-27]
tech-stack:
  added: []
  patterns: [genesis-rooted hydration, read-only transport adapters, exact local confirmation, live fingerprints]
key-files:
  created:
    - src/personal_knowledge/intelligence/decision/service.py
    - src/personal_knowledge/intelligence/decision/cli.py
    - docs/runbooks/decision-feedback.md
    - tests/contract/test_decision_interfaces.py
    - tests/integration/test_decision_feedback_acceptance.py
  modified:
    - src/personal_knowledge/services/api_server.py
    - src/personal_knowledge/services/mcp_server.py
    - tests/integration/test_decision_feedback_privacy.py
key-decisions:
  - "Every decision read revalidates the Phase 25 source, decision run, support refs, sole publication genesis, typed rows and complete checksum chain."
  - "REST and MCP are read-only; only the local CLI can append and requires write, exact confirmation, human identity, expected sequence and caller idempotency."
  - "Acceptance writes only to a disposable database and treats live Phase 25/26 schema absence as an allowlisted read-only state, never as permission to migrate."
requirements-completed: [DEC-01, DEC-02]
completed: 2026-07-18
---

# Phase 26 Plan 04: Shared Interfaces and Metadata-only Acceptance Summary

**One reconstructable decision service, human-bound local append surface, read-only REST/MCP adapters and zero-side-effect live acceptance**

## Accomplishments

- Added one `DecisionFeedbackService` for bounded recommendation list/get/history/outcome/effectiveness reads. Every operation fails closed on recommendation, decision-run, support, Phase 25 source-version, genesis, event-chain or typed-row drift.
- Added JSON CLI reads plus explicit local confirmation/action/outcome writes. A write requires `--write`, exact `--i-confirm <recommendation-id>`, a human identity hash, caller `expected_sequence` and caller idempotency key.
- Added five REST GET/MCP read contracts over the shared service. No REST POST or MCP confirm, action, outcome-write, execute, send, schedule, purchase, publish or dispatch capability exists.
- Added privacy-safe metadata contracts and a runbook that preserves the fact/observation/inference/recommendation/confirmation boundary and the non-causal meaning of effectiveness.
- Added an acceptance command that proves accepted and rejected histories in a disposable SQLite database, then inspects live authority metadata and Phase 24 checkpoints with identical before/after fingerprints.

## Task Commits

1. **Task 1: Failing interface, permission and integrity contracts** — `1cd98ec`
2. **Task 2: Shared decision reads and guarded local writes** — `75aec7d`
3. **Task 3: Read-only REST/MCP interfaces and runbook** — `11feda6`
4. **Task 4: Metadata-only acceptance and privacy proof** — `85c6671`

## Verification

- Phase 26 unit/contract/integration suite: **53 passed**.
- Apps SDK, Phase 25 interface, knowledge search and serving-snapshot regression: **45 passed**.
- Governance preflight: **13/13 PASS**.
- Full repository: **776 passed, 2 skipped**; two pre-existing `SyntaxWarning` messages only.
- Live `acceptance --dry-run --metadata-only --json`: exit 0, `technical_status=passed`, `release_status=release_blocked`.

The exact live fingerprint checksum was unchanged at `99b5dacbb9e3ba3ed6c67512d01bae3d2988ffce47e70a2d5da05154e198324c`. `persisted_rows`, `mutations`, `private_bodies`, `external_actions`, `network_calls` and `paid_calls` were all zero. The intentionally unapplied live Phase 25/26 schemas were reported as `source_analysis_unavailable` and `decision_schema_unapplied`; no migration was run.

The disposable sandbox produced one accepted seven-event history through non-causal effectiveness and one rejected two-event history. The assessment was `effective` with `causal_claim=false`; this is technical contract evidence, not a live effectiveness or causal claim.

## Bounded Checkpoint Approval

Auto-chain approval covers only Phase 26 interface behavior, sandbox explicit-write safeguards and live metadata-only zero mutation. It does not approve Phase 24, a live schema migration/publication, lifecycle apply, serving/pointer/watermark change, external action or REST/MCP write authority.

Phase 24 remains verbatim:

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`
- Human review strict: false
- Lifecycle strict: false; applied manifests and events remain zero

## Next Phase Readiness

- Phase 26 has 4/4 implementation plans complete and is ready for independent phase verification.
- Phase 27 may use the technically verified sandbox/read contracts after Phase 26 verification, while live adoption remains release-blocked by Phase 24.

## Self-Check: PASSED

- All four task commits and planned artifacts exist.
- All plan, adjacent, governance, full-repository and live metadata-only checks passed.
- No live migration/write, lifecycle/serving/pointer/watermark change, network/paid call or external action occurred.

---
*Phase: 26-decision-action-feedback-loop*
*Completed: 2026-07-18*

