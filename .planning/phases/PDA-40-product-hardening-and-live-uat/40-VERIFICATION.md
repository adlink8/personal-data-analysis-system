---
phase: 40-product-hardening-and-live-uat
status: blocked
verification_mode: automated_plus_human_checkpoint
requirements:
  UX-01: pending_human_uat
  UX-02: automated_pass_human_pending
  QA-01: passed
  QA-02: pending_human_uat
technical_status: passed
security_status: pending_human_uat
---

# Phase 40: Product Hardening and Live UAT — Verification Plan

## Automated Evidence (2026-07-27)

- Frontend: `npm run build` passed; `npm run test` passed with 24 files / 255 tests.
- Python UI Projection + orchestration/replay/e2e matrix passed.
- Browser dependency review selected manual local-only UAT; no browser runner was added.
- See `40-UAT.md` for the remaining blocking human checkpoint.

## Completion Conditions

| Requirement | Future acceptance evidence |
|---|---|
| UX-01 | Cockpit is usable at 320/768/1024/1440 widths, keyboard-only and 200% zoom with clear focus, reduced motion and no clipped critical state. |
| UX-02 | UI displays operational truth and recovers from individual REST/MCP/Widget/Chroma/authority faults without presenting an unsafe action. |
| QA-01 | Deterministic, component, contract and browser checks are reproducible; docs describe only actually obtained results. |
| QA-02 | Same-origin low-risk prepare → exact preview → explicit confirm → exact replay is observed in a real browser with authority safety evidence. |

## Automated Gates

1. Correct the Cockpit README/WIP wording first, then run build, type, component and contract suites with recorded versions and results.
2. Run responsive, keyboard, focus, Esc, reduced-motion and 200% zoom checks at all required viewports.
3. Execute fault matrix for REST, MCP widget, Chroma and one authority; assert scoped recovery, no console/DOM/URL/storage/artifact leakage and no bypass of same-origin/truth gates.
4. Before browser automation, perform an explicit dependency/runner review. Do not add `@playwright/test` or any dependency without separate approval. If no approved runner exists, retain documented manual UAT rather than claiming automated E2E.
5. With disposable authority fixtures—or a separately authorized one-time live write—test the full project+low exact replay path and verify receipts/fingerprints/provider/external/promotion counters.

## Required Human UAT

| Flow | Evidence required |
|---|---|
| Read-only cockpit | State/external/evidence remain distinguishable under normal and degraded responses. |
| Guarded write | Preview is exact, confirmation text is specific, cancel is no-op, replay returns the same event. |
| Responsive/a11y | Screen/keyboard inspection at required widths and zoom with no blocked key task. |
| Privacy | Review screenshots/logs/exports for raw personal data, confirmation material and secrets. |

## Blocking Rules

- A plan, screenshot, local widget load or component test is not Live UAT evidence.
- Browser UAT stays `blocked` until the runner/dependency review and disposable-authority or explicit live-write authorization are satisfied.
- Any README claim that Phase 40 is complete before these gates is a documentation defect.
- Any cross-origin write, duplicate event, raw-data leak or degraded-state action affordance blocks release readiness.

