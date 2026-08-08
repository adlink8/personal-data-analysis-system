# UI-SPEC — Phase 52: Pi Runtime Activity

## 1. Existing Design System

Reuse the current Cockpit React/Vite/Tailwind tokens, `AppShell`, page header, cards, badges, drawers, focus ring and responsive breakpoints. Do not add `pi-web-ui`, a second icon set, gradients, chat bubbles or a new dashboard shell.

## 2. Information Architecture

- Add “AI Runtime” under the existing System/runtime navigation group.
- Page order: Kernel status → active/recent tasks → selected task timeline → recovery guidance.
- Global activity indicator may show active task count only; it must not show personal prompt text.

## 3. Component Contract

| Component | Required states | Interaction |
|---|---|---|
| KernelStatusCard | ready/degraded/offline/stale | read-only retry guidance |
| TaskList | empty/queued/running/terminal/partial | keyboard-select row |
| TaskTimeline | reconnecting/replayed/live/outcome_unknown | event metadata and evidence refs |
| TaskControls | cancelable/cancel_requested/resumable/disabled | exact confirmation copy for state-changing control |
| RuntimePrivacyNotice | always present | explains omitted prompt/Tool bodies |

## 4. Visual and Responsive Rules

- Desktop ≥1024: task list 5/12 columns, timeline 7/12 columns.
- Tablet 768–1023: stacked cards with task list before timeline.
- Mobile 320–767: one column; controls remain in document flow, never fixed over content.
- IDs use monospace with middle truncation plus accessible full-value copy action.
- State is never color-only; badge includes icon/text and `aria-label`.
- Respect reduced motion: no pulsing/spinning progress; use text and static indicator.

## 5. Copy and Truthfulness

- Use “已请求取消” before terminal acknowledgement; never say “已取消” early.
- `outcome_unknown`: “结果状态未知；系统不会自动重试，请先恢复/核对。”
- stale/offline data includes observed timestamp and exact recovery action.
- Never display “思考过程”; use “处理中” and typed event labels.

## 6. Accessibility and Safety

- Full keyboard navigation, visible focus, Esc closes details drawer, focus returns to opener.
- SSE announcements use a throttled polite live region; do not announce every token/event.
- Cancel/resume controls require same-origin mutation contract and are disabled on stale version.
- DOM, title, URL, localStorage, console and telemetry contain no raw personal body or credential.

## UI Verification Dimensions

1. Design-system consistency — no new visual system.
2. Responsive layout — 320/768/1024/1440 and 200% zoom.
3. State completeness — empty/loading/live/replay/stale/offline/error/outcome_unknown.
4. Accessibility — keyboard, focus, Esc, live region, reduced motion.
5. Truthfulness — control and readiness labels match backend state.
6. Privacy/security — no raw bodies, cross-origin writes or browser persistence.
