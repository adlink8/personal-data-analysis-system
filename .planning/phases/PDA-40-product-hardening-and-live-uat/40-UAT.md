---
status: passed
phase: 40-product-hardening-and-live-uat
source: [40-VERIFICATION.md, docs/live-uat.md, docs/browser-e2e-dependency-review.md]
started: 2026-07-27
updated: 2026-07-28
---

# Phase 40 Live UAT

## Automated evidence already collected

- Frontend `npm run test`: 24 files / 255 tests passed.
- Frontend `npm run build`: passed.
- Python UI Projection + state/external/decision + orchestration/replay/e2e matrix: passed.
- Browser runner review: no existing runner; no new dependency added; manual UAT path selected.

## Runtime preflight — 2026-07-28

- Existing REST owner was already listening on `127.0.0.1:8000`; no process restart or authority mutation was performed.
- `GET http://127.0.0.1:8000/health` returned HTTP 200 with the service health envelope.
- `GET http://127.0.0.1:8000/app/` returned HTTP 200 and served the built Cockpit shell.
- This is a read-only availability check only. It does not prove browser viewport/accessibility/privacy behavior or guarded write/replay acceptance.

## Human checkpoint — user accepted 2026-07-28

用户在正式激活 v1.5 前明确确认：“v1.4 UAT通过了”。该确认作为本次人工验收结论记录；自动化和 runtime evidence 仍保留如下，未伪造浏览器工具输出。

The following must be inspected on the production same-origin `/app/` by the user or an explicitly authorized operator. Component/contract tests do not close these items:

1. 320/768/1024/1440 viewport, 200% zoom, long Chinese/IDs, no clipped critical state or horizontal page overflow.
2. Keyboard-only Tab/Shift+Tab, visible focus, Esc/focus restore, reduced-motion behavior.
3. Read-only overview/state/external/evidence/actions/proactive/system paths under normal and degraded responses.
4. One disposable `project + low` prepare → exact preview → explicit confirm → same-payload exact replay, with append-only fingerprint unchanged except for the intended single event and replay returning the same event.
5. Browser DevTools/DOM/URL/storage/console/artifact privacy review: no raw personal content, PII, preview, confirmation/HMAC, provider body, credentials, complete local paths or tunnel URL.

## Current verdict

`passed_by_user_confirmation`. No production authority write was performed as part of this acceptance. If a live authority write is required later instead of a disposable fixture, obtain separate authorization immediately before that one write and retain the append-only evidence; do not reset or delete any event.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0
