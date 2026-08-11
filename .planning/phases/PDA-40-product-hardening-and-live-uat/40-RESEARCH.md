---
phase: 40
slug: product-hardening-and-live-uat
date: 2026-07-22
requirements: [UX-01, UX-02, QA-01, QA-02]
depends_on: [36-secure-projection-and-cockpit-baseline, 37-authority-aware-state-external-and-evidence, 38-guarded-decision-workspace, 39-feedback-proactive-and-runtime-truthfulness]
research_mode: implementation
research_status: complete
confidence: high
---

# Phase 40 Research: Product Hardening and Live UAT

## Research Question

如何在不新增事实权威、不扩大浏览器写权限、也不把组件测试误当作产品验收的前提下，验证 Personal Decision Cockpit 已经在真实浏览器中可访问、可降级、可恢复、可审计？

Phase 40 是 **release evidence / recovery evidence** 阶段，而不是继续实现功能的阶段。它只能在 Phase 36–39 的安全传输、authority/snapshot/evidence 真值、受控确认与只读反馈页面都已验收后开始。

## Scope and Non-goals

### In scope

```text
同源 /app 真实浏览器读取
→ 低风险 project + low prepare / confirm / exact replay
→ 响应式、键盘、焦点、Esc、reduced motion、200% 缩放
→ REST / MCP Widget / Chroma / 单 authority 降级真值
→ UI Projection、前端、orchestration/replay/privacy 定向回归
→ 可复现 UAT 报告、失败恢复记录和发布判定
```

### Explicitly out of scope

- 新建 Personal Wiki、Topic Page、backlinks 或 LLM Wiki narrative（v1.5）。
- 新增浏览器事实缓存、Service Worker、localStorage/IndexedDB 业务数据、浏览器端生命周期规则。
- 新增 REST 写入路由、Proactive control 写入、自动 promotion、外部动作或高风险域写入。
- 为了通过 UAT 重置真实 authority、删除 append-only event、修改 Serving Snapshot 或 Watermark。
- 把“自动化浏览器测试已绿”表述成无障碍或真实产品使用已经完全证明。

## Existing Capability Map

| Concern | Current code / asset | Existing value to retain | Hardening gap / Phase 40 evidence needed |
|---|---|---|---|
| Application shell | `apps/personal_decision_cockpit/src/components/layout/AppShell.tsx` | 1024+ side rail、768–1023 horizontal nav、<768 mobile nav，focus ring classes already exist | Prove real layout/reflow at 320/768/1024/1440 and long Chinese/ID; component rendering alone cannot prove it. |
| Reduced motion | `src/design-system/tokens.css` | `prefers-reduced-motion: reduce` globally shortens animations and disables smooth scrolling | Verify it in an actual browser media context; ensure loading skeleton and route transitions do not create a contradictory motion affordance. |
| Dialog / drawer keyboard behavior | `NewSessionDialog.tsx`, `ConfirmDrawer.tsx` | Escape closes, focus is moved into the panel and restored, Tab loop is implemented | Prove focus order and Escape do not invoke `onConfirm`, and busy state does not let a user create duplicate writes. |
| Error/empty/partial UI | `components/feedback/StatePanel.tsx`, page query hooks | Separate loading, empty, partial, error panels; error uses `role=alert` | Test realistic transport and authority fault shapes, not only mocked React Query errors.  Each state must name a recovery path. |
| Runtime health | `ui_projection.py:_system_status_get`, `SystemPage.tsx` | Separate REST, MCP, Tunnel, Chroma and authority DB signals; `get_knowledge_status(probe_chroma=True)` exists for the system projection | Verify UI never calls REST healthy as Chroma healthy.  Existing `/health` intentionally uses `probe_chroma=False`, so it is not an end-to-end retrieval proof. |
| Evidence surface | `pages/evidence/EvidencePage.tsx` | Legacy MCP widgets are explicitly labelled historical/diagnostic | It currently embeds hard-coded `http://127.0.0.1:8789/widgets` iframes. Phase 37 must first provide authority evidence drill-down and non-blank Widget failure handling; Phase 40 proves both available and unavailable cases. |
| Local privacy | `app/providers.tsx` | Only `cockpit.theme` and `cockpit.density` are intended localStorage keys; TanStack Query is memory-only | Inspect browser storage, DOM, console, network and captured artifacts after read/write UAT. Do not infer privacy from source comments. |
| Test baseline | Vitest + Testing Library, Python contracts, orchestration tests | Fast component/DTO/replay regression suite exists | No Cockpit-specific browser E2E runner is declared in `package.json`; dependency and artifact policy must be decided explicitly before adding one. |

## Preconditions and Release Gates

Phase 40 should be planned as a hard gate, not as an optimistic cleanup list.

| Gate | Must already be true | Why Phase 40 must not compensate for it |
|---|---|---|
| Phase 36 transport | Production `/app` same-origin policy is active; wildcard CORS is removed; cross-origin session mutation is rejected before delegation | A browser UAT cannot make an unsafe transport boundary acceptable. |
| Phase 36 projection | Public errors/limitations are safe, version and operation DTOs are exact, WIP is tracked/auditable | UAT screenshots and console inspection are meaningless if the response contract can leak data. |
| Phase 37 truth | State, External, evidence, stale/partial/conflict/binding gates are implemented | Phase 40 verifies their behavior; it must not invent browser-only interpretations of authority state. |
| Phase 38 writes | Only existing `project + low` guarded flow is exposed and exact replay has contract coverage | A manual UI click must never be used to bypass prepare/preview/confirm/sequence/idempotency. |
| Phase 39 status | Feedback/proactive/runtime are strictly read-only and causality limitations are visible | Phase 40 must not add operational buttons just to make the dashboard appear complete. |

**Current planning caution:** `apps/personal_decision_cockpit/README.md` currently claims “Phase 40 已完成” and calls the Phase 36–39 range equivalent, while the active GSD roadmap marks phases 36–40 as not planned/executed. The earlier Phase 36 baseline plan must correct this premature claim before Phase 40 evidence is allowed to say `passed`.

## Standard Stack

Use the repository stack first.  Do not introduce an extra production server, visual-design platform, telemetry vendor, persistent browser store, or E2E framework implicitly.

| Need | Required stack | Why |
|---|---|---|
| Build and static delivery | Existing React 18, TypeScript, Vite, Python REST `/app` static hosting | The product is local/single-user; it avoids a second production Node process. |
| Component / DTO regression | Existing Vitest + Testing Library + Zod | Fast checks for route render, state badges, drawers, safe error labels and metadata-only fixtures. |
| Service / authority regression | Existing Python `pytest` contracts plus orchestration/replay/privacy suites | Proves browser-facing contract is backed by server authority rather than only mocks. |
| Browser acceptance | **One reviewed real-browser harness**, preferably `@playwright/test` if a dependency review explicitly approves it | Playwright supports a `webServer`, project configuration, viewport/device emulation and test artifacts. It is not currently declared in Cockpit `package.json`, so Phase 40 must not assume it already exists. |
| Accessibility methodology | Browser keyboard assertions + manual review against WCAG 2.2 AA-relevant criteria | Automated accessibility testing finds only a subset of issues; use it as a supplement, not an acceptance substitute. |
| UAT evidence | Versioned Markdown report plus privacy-safe screenshots/traces only on failure or approved redacted capture | Evidence must identify build/source/authority bindings without storing raw personal contents, confirmation material, HMAC or provider payloads. |

### Browser-harness decision rule

1. **First inspect existing workspace tooling** and any central browser runner before adding a package.
2. If no reusable runner exists, submit a narrow dependency review for `@playwright/test`: locked version, Chromium-only local target, no cloud upload/report publishing, `.gitignore` for raw `test-results`, and a documented redaction policy.
3. If the review is not approved, retain Vitest/Python automated checks and run the documented real-browser UAT manually; do **not** claim the missing automated browser coverage is complete.
4. A browser runner may start only disposable local services and disposable test databases. It must never use the live personal authority, a paid model/provider, or an active production tunnel.

The choice is deliberately deferred to the implementation plan because `40-CONTEXT.md` D-40-07 forbids smuggling in a new dependency. The phase success criterion is browser evidence, not a particular test library.

## Architecture Patterns

### 1. Two complementary acceptance layers

```text
deterministic contracts and component tests
  ├─ DTO / version / operation / state vocabulary
  ├─ cross-origin zero-write, preview integrity and exact replay
  ├─ safe error and privacy-unit regressions
  └─ route render and accessible component semantics

real browser acceptance
  ├─ same-origin `/app` and real HTTP boundary
  ├─ viewport/reflow/keyboard/zoom/motion
  ├─ controlled failure injection and recovery language
  ├─ storage / console / network / artifact privacy inspection
  └─ at least one audited project+low prepare/confirm/replay journey
```

Neither layer is sufficient alone.  jsdom does not prove browser layout, CORS or zoom; a manual click-through does not replace regression coverage for integrity and replay.

### 2. Fault injection at the correct boundary

Degraded-state verification must isolate failures without modifying personal facts:

```text
REST offline
  → browser cannot load same-origin Projection
  → page error panel + safe retry; no cached success claim

MCP Widget unavailable
  → authority evidence page remains available
  → Widget card has an explicit degraded/recovery state, not a blank iframe

Chroma unavailable
  → `/ui/system/status` returns actual Chroma probe state / partial limitation
  → UI says Chroma/retrieval unavailable, while independent authorities can remain readable

one authority unavailable
  → affected Projection section is null/partial with binding/freshness/limitation
  → unrelated sections remain truthful; prepare/confirm remains blocked where evidence gate requires it
```

Use a controlled temporary configuration, injected read-service failure, a test-only loopback substitute, or a disposable service fixture. Do not terminate arbitrary processes, mutate a live authority database, or fake an `ok` envelope in the page.

### 3. Evidence package is redacted and binding-aware

Every UAT result records:

```text
source revision / package-lock hash
Cockpit build result and asset location
server / projection schema version
Personal / External / Serving snapshot IDs or short redacted forms
authority freshness time
test fixture identity (disposable vs live read-only)
scenario, observed state, pass/fail and recovery action
```

It does **not** record raw messages, query result bodies, user goal text, long decision payloads, preview JSON, confirmation, HMAC, provider body, credential, tunnel URL, or full local paths.  A failure needs a typed code and redacted diagnostic reference, not a copied private payload.

### 4. UAT writes are bounded, reversible only by append-only compensation

The browser test may prove one existing low-risk flow:

```text
same-origin read
→ session.prepare (no event written)
→ exact preview
→ explicit confirm
→ repeat identical confirm
→ same receipt / event / checksum / `replayed=true`
```

Use a disposable fixture authority.  If a deliberate UAT write is made under a user-approved live authority, record its intent and preserve it; never “clean it up” by delete/reset.  A failed release is recovered by reverting frontend/configuration artifacts or by typed runtime recovery—not by rewriting decision history.

### 5. Accessibility is a product path, not decorative CSS

The current CSS and dialog components provide useful starting points, but UAT must exercise them:

- Tab / Shift+Tab can reach every interactive control in logical order; no keyboard trap outside the intended modal trap.
- Focus is visibly perceivable, including custom links/cards/tabs and mobile navigation.
- Escape closes `NewSessionDialog` / `ConfirmDrawer`, restores focus, and never triggers confirmation.
- Status, risk, partial, candidate and external semantics have text/icon labels in addition to color.
- Tables/charts have an equivalent DOM text or table representation.
- Long Chinese strings and identifiers wrap without hiding context or forcing page-level horizontal scroll.
- 200% browser zoom preserves content and functionality; device pixel ratio is not a substitute for zoom validation.

This aligns with WCAG 2.2 requirements for keyboard operation, visible focus and 200% text resize.  It also follows Playwright's own guidance that automated scans catch some invalid/missing properties but require manual and inclusive assessment for the rest.

## Code Examples and Concrete Integration Points

These are planning anchors, not changes made by this research task.

### A. Build and source-truth checks

| Path | Role in Phase 40 |
|---|---|
| `apps/personal_decision_cockpit/package.json` | Existing `test` and `build` commands. If a browser runner is approved, its script and lockfile change must be reviewed explicitly. |
| `apps/personal_decision_cockpit/vite.config.ts` | `/app/` base and `127.0.0.1:8000` development proxy. Browser tests must use the same-origin production path for the final UAT, not only the Vite proxy. |
| `src/personal_knowledge/services/api_server.py` | Owns `/app` static delivery, `/ui/*`, `/agent/session/*` and CORS/Origin behavior. Phase 40 consumes the secured Phase 36 behavior; no test-only bypass belongs in the browser. |
| `apps/personal_decision_cockpit/README.md` | Must no longer claim Phase 40 shipped before actual acceptance. It should state commands, known runtime constraints and links to evidence. |

### B. Responsive, motion and keyboard anchors

| Path / symbol | Required verification |
|---|---|
| `src/components/layout/AppShell.tsx:NAV_ITEMS` | 320 mobile five-item navigation, 768 tablet horizontal navigation and 1024 desktop rail are all reachable and have no navigation gap. |
| `src/components/layout/MobileNav.tsx` | Focus order, selected state and safe area / long label presentation on 320 width. |
| `src/design-system/tokens.css:@media (prefers-reduced-motion: reduce)` | Actual browser media emulation plus manual observation; do not rely only on text grep. |
| `src/components/decision/NewSessionDialog.tsx` and `ConfirmDrawer.tsx` | Esc/Tab loop/focus restoration and busy button behavior. Confirm action count stays zero on Esc/overlay/cancel. |
| `src/pages/**` | Inject max-length Chinese and IDs via test fixture; assert card width/reflow and accessible text, not a screenshot-only assertion. |

### C. Degradation and runtime truth anchors

| Path / symbol | Required verification |
|---|---|
| `src/personal_knowledge/services/ui_projection.py:_collect` | Controlled single-section failure creates `partial=true`, `authorities[name]=error`, safe limitation, and does not erase healthy sections. |
| `ui_projection.py:_system_status_get` / `_knowledge_status_section` | Chroma is probed separately (`probe_chroma=True`) and `chroma_error` is represented honestly. |
| `api_server.py:/health` | It calls `probe_chroma=False`; never use HTTP 200 here as proof Chroma/retrieval is live. |
| `src/pages/system/SystemPage.tsx` / `SystemHealthStrip.tsx` | Port states, Chroma, authority freshness and recovery guidance are distinguishable; REST up does not turn every item green. |
| `src/pages/evidence/EvidencePage.tsx` | Phase 37 must replace/guard blank iframe behavior. Phase 40 proves MCP unavailable reveals a non-empty degraded state while authority evidence drill-down remains useful. |
| `src/components/feedback/StatePanel.tsx` | Offline, empty, partial and error must have different user-facing semantics and a safe retry/recovery affordance. |

### D. Decision-write and privacy anchors

| Path / symbol | Required verification |
|---|---|
| `src/api/orchestration.ts` | Relative request URLs, one in-memory actor lifetime, preview passed unchanged, idempotency key reuse for the same retry. |
| `src/components/decision/ConfirmDrawer.tsx` | Exact preview display, action-specific confirmation text, no confirm on Esc/cancel, busy state prevents double activation, replay is not a new receipt. |
| `src/components/feedback/TypedRecoveryPanel.tsx` | `stale`, confirmation, integrity, risk, runtime and `provider_outcome_unknown` are never silently retried or payload-replaced. |
| `src/app/providers.tsx` | Storage audit allows only `cockpit.theme` / `cockpit.density`; no raw data, actor hash, preview, token or query cache is persisted. |
| `src/test/liveContract.test.ts` | Fixtures remain metadata-only. Keep failure diagnostics from exposing real payloads in artifacts; do not replace with live personal-data capture. |
| `tests/contract/test_orchestration_interfaces.py`, `tests/integration/test_orchestration_replay.py`, `tests/e2e/test_orchestration_acceptance.py` | Retain server-side exact replay, privacy and at-most-once checks alongside browser evidence. |

### Suggested browser-test shape (only after approved dependency review)

```ts
// Conceptual example; use a disposable authority and real same-origin `/app/`.
test('project+low confirm is exact replay, not a second write', async ({ page }) => {
  await page.goto('/app/');
  // Open the existing low-risk session flow, prepare, inspect the exact preview.
  // Confirm once and retain the returned receipt identity.
  // Send the same confirmation request once more through the UI retry path.
  // Assert one event identity and visible `replayed=true` wording.
  // Assert no external action or automatic promotion has occurred.
});
```

The test must not contain real user goal strings, actual evidence text, secret configuration, live tunnel endpoints or raw preview/confirmation material in snapshots/traces.

## Don't Hand-Roll

| Do not build | Why it is unsafe / low-value | Reuse instead |
|---|---|---|
| A second browser-only health model | It will disagree with Projection freshness, Chroma probing and authority status | `CockpitProjectionService.system.status.get` and the Phase 39 read model. |
| “Offline mode” cache or service worker for authority payloads | It can show old personal data as current and creates privacy/revocation obligations | Existing in-memory query cache and explicit error/partial/stale panels. |
| A client-side accessibility score or single color health score | It hides which criterion/service failed and produces false certainty | Scenario-level evidence, semantic controls and separate status labels. |
| A custom exact-replay simulator in React | It risks duplicating or bypassing HMAC, sequence and idempotency authority | `GuardedOrchestrationInterface` and existing orchestration/replay contracts. |
| A test utility that edits the live user SQLite/Chroma state | It contaminates the very authority UAT is supposed to observe | Disposable temporary authority fixtures or a non-mutating controlled failure seam. |
| Screenshot-only visual QA | Screenshots cannot prove Tab order, Escape semantics, focus restoration, 200% text zoom or zero writes | Browser interaction assertions plus a documented manual checklist. |
| An unreviewed E2E dependency or cloud report uploader | It broadens supply-chain, privacy and runtime surface | Explicit Phase 40 dependency review and local-only artifacts. |
| An automatic “repair/restart” button | It contradicts RUN-01 and risks an operational control plane in the Cockpit | Read-only recovery text that directs the user to existing supervisor/runbook. |

## Common Pitfalls

| Pitfall | Why it would fail v1.4 | Required prevention / acceptance evidence |
|---|---|---|
| Green Vitest suite is called UAT | jsdom cannot prove real browser layout, zoom, CORS or iframe failure behavior | Require a separate browser checklist/report and document exact environment. |
| Running only Vite `npm run dev` | Proxy can conceal same-origin `/app` static-host behavior and server headers | Final UAT targets `http://127.0.0.1:8000/app/` after a production build. |
| Treating `/health` 200 as Chroma availability | API health intentionally uses `probe_chroma=False` | Use `system.status.get` Chroma probe and show it independently. |
| Blank MCP iframe is accepted as “offline” | Empty content hides recovery instructions and could be mistaken for no evidence | Provide a non-empty Widget degradation card and confirm independent authority evidence still works. |
| Test stops services or changes local ports blindly | Could interrupt user processes and is not a controlled fault test | Use disposable fixture/injection; only manipulate processes explicitly created for test. |
| UAT write to the live authority is deleted afterward | Append-only history must not be erased; deletion hides audit evidence | Use disposable database; if live use is explicitly approved, retain it and record its intent. |
| Browser screenshot/trace contains personal text, preview token or provider body | Artifact becomes a secondary sensitive data store | Metadata-only fixtures; redaction review; default ignore/delete test output generated by the test itself. |
| `localStorage` audit ignores query cache or URL fragments | Sensitive data can leak through more than explicit storage calls | Inspect local/session storage, URL, DOM, console and network before/after read/write cases. |
| Reduced motion test only asserts CSS exists | A global style may be overridden or animations may be JS-driven | Emulate reduced motion in browser and observe no blocking/motion-dependent interaction. |
| 200% test is replaced with high-DPI `deviceScaleFactor` | Pixel density is not browser text zoom/reflow | Perform a manual 200% browser zoom check and record result. |
| Color-only risk/partial labels | Fails accessible semantic communication | Verify text/icon/ARIA equivalents for every status family. |
| Exact replay shown as a second success | Misstates append-only audit history | Assert same `event_id`, checksum and `replayed=true`; visible copy says no duplicate write. |
| README says phase shipped before evidence exists | Planning state becomes untrustworthy and bypasses GSD acceptance | Correct documentation in Phase 36 and link only actual Phase 40 report after pass. |

## Recommended Future Validation

### 1. Deterministic pre-UAT command matrix

Run after implementation in a clean, controlled local environment. Record the actual command, exit status, revision and whether it used fixtures only.

```powershell
Set-Location <repo-root>\apps\personal_decision_cockpit
npm run test
npm run build

Set-Location <repo-root>
$env:PYTHONPATH = "$PWD\src"
python -m pytest `
  tests/contract/test_ui_projection.py `
  tests/contract/test_ui_projection_state_external.py `
  tests/contract/test_ui_projection_decision.py `
  tests/contract/test_ui_projection_actions_proactive.py `
  tests/contract/test_orchestration_interfaces.py `
  tests/integration/test_orchestration_replay.py `
  tests/e2e/test_orchestration_acceptance.py -q
```

These commands are recommended future verification steps. This research task did **not** run them, because the user requested planning only and the Cockpit is currently untracked/WIP.

### 2. Browser acceptance matrix

| Scenario | Required observation | Safety invariant |
|---|---|---|
| Production same-origin read | `/app/` loads from REST owner; nine projection reads have bounded safe responses | Browser does not contact SQLite/Chroma directly; static asset/build failure has safe recovery text. |
| Responsive layout | 320/768/1024/1440 route through all nav variants; no viewport-level horizontal overflow; long Chinese/long IDs wrap | No content or confirmation button becomes unreachable. |
| Keyboard / focus | Tab/Shift+Tab, dialog/drawer focus, Escape close/restore, disabled buttons, visible focus | Escape/cancel/overlay produce zero orchestration calls. |
| 200% and reduced motion | Manual 200% text zoom; browser `prefers-reduced-motion` emulation | No clipped content/function loss; no motion is required to understand state. |
| REST offline | Same-origin fetch failure shows error + retry rather than stale success or blank page | No cached personal fact is presented as current. |
| MCP widget offline | Evidence area shows meaningful degraded/recovery state; current authority evidence can still be read | Old Memory Graph is never relabelled as Personal State authority. |
| Chroma offline | System shows Chroma/retrieval unavailable separately from REST/other authorities | `/health` green is not reused as a false Chroma success. |
| Single authority fault | Only affected section is partial/error; snapshot/freshness/limitations remain visible; write gate blocks unsafe path | No browser-side invented fallback, no hidden auto-retry. |
| Guarded write | One disposable `project + low` prepare → confirm → identical retry returns exact replay | No provider call, external action, promotion or duplicate append-only event. |
| Privacy | Inspect storage, console, DOM, URL, network and approved artifacts | No raw message/PII/credential/HMAC/confirmation/provider body; only permitted UI preferences persist. |

### 3. Manual accessibility review checklist

Automated assertions should cover semantic roles and obvious regressions, then a human records:

- Page language/title, headings and navigation landmarks are understandable in Chinese.
- Focus remains visible against light/dark themes and all semantic color states also contain text/icon.
- Tables, metrics and any future chart have readable equivalent text/table content.
- Tooltips/title-only full IDs do not become the exclusive information path; short IDs remain distinguishable and expandable/readable.
- Modal/drawer close behavior restores focus to the invoker; no keyboard trap leaks into background content.
- 200% browser zoom preserves the actual decision confirmation action and recovery controls.
- Long text does not hide snapshot/freshness/limitations or make evidence/recovery link inaccessible.

This is intentionally a **recorded human check**, not an inferred pass from Tailwind class names.

### 4. Failure / recovery recording template

For each failure discovered during UAT, use:

```text
Scenario ID:
Build/source revision:
Authority fixture and snapshot binding (redacted):
Observed state and typed error/limitation code:
Expected truthful UI state:
Whether any write occurred (must include before/after disposable ledger fingerprint):
Recovery action attempted:
Recovery result:
Artifact path (redacted / access-controlled):
Release decision: block | fixed-and-retested | accepted limitation
```

Never mark a failed scenario as accepted just because another page remains functional.  The report should distinguish a product block, a known runtime prerequisite (for example a missing local confirmation secret), and a deliberately unsupported operation.

## Planning Recommendation

Plan Phase 40 in three ordered plans to preserve a clear release gate:

1. **Accessibility and responsive hardening** — close confirmed layout/focus/status/text alternatives, add deterministic unit coverage, and establish the reviewed browser-test/manual checklist. This plan cannot claim UAT pass.
2. **Truthful degraded-state and privacy regression** — add controlled fault fixtures/injection across REST, Widget, Chroma and one authority; audit storage/console/DOM/artifacts; retain no-new-write invariant.
3. **Real-browser acceptance and release evidence** — build, run the complete command matrix, execute the same-origin low-risk exact-replay journey on disposable data, record UAT/recovery evidence, and only then update milestone/README status if every required scenario passes.

If a required runtime prerequisite cannot be provided safely, Phase 40 remains `blocked`/`gaps_found`; it must not be closed with a mock-only substitute.

## Sources

### Repository sources

- `.planning/REQUIREMENTS.md` — UX-01, UX-02, QA-01, QA-02.
- `.planning/ROADMAP.md` — Phase 40 success criteria and predecessor ordering.
- `.planning/phases/PDA-40-product-hardening-and-live-uat/40-CONTEXT.md` — D-40-01 through D-40-07.
- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-RESEARCH.md` — same-origin, safe limitation and WIP-baseline prerequisites.
- `.planning/phases/PDA-38-guarded-decision-workspace/38-RESEARCH.md` — exact preview/replay and typed recovery boundaries.
- `apps/personal_decision_cockpit/{package.json,vite.config.ts,README.md,src/**}` — current WIP application and tests.
- `src/personal_knowledge/services/{api_server.py,ui_projection.py}` — `/app`, `/ui/*`, `/agent/session/*`, port/Chroma and read-only projection behavior.
- `tests/{contract,integration,e2e}` orchestration/UI projection suites — existing deterministic regression assets.

### Official external references (accessed 2026-07-22)

- Playwright configuration and local `webServer` model: https://playwright.dev/docs/test-configuration
- Playwright viewport/device/media emulation: https://playwright.dev/docs/emulation
- Playwright accessibility guidance: automated checks are supplemental to manual/inclusive review: https://playwright.dev/docs/accessibility-testing
- WCAG 2.2: keyboard operation (2.1.1), visible focus (2.4.7) and 200% resize text (1.4.4): https://www.w3.org/TR/WCAG22/
