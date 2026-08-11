# Verification Results

Date: 2026-08-10

## Automated

| Command | Result |
|---|---|
| `npm test` | PASS · 2 files, 10 tests |
| `npm run build` | PASS · TypeScript + Vite, 658 transformed modules |
| `npm audit --omit=dev --registry=https://registry.npmjs.org --json` | PASS · 0 known vulnerabilities at verification time |

Build output: JS 461.80 kB / 140.05 kB gzip; CSS 12.03 kB / 3.34 kB gzip. Dependency inventory reported 90 production and 248 total dependency entries. This is acceptable for a desktop UI Spike, but production adoption remains conditional because `@assistant-ui/react` brings a materially larger supply-chain surface than hand-written primitives.

The default npm mirror did not implement the audit API (404), so the audit was rerun against the official npm registry without changing project configuration.

## Browser UAT

Runtime: Vite dev server on loopback + real headed Chromium through Playwright CLI.

Verified flow:

1. Open `/` → current conversation and Composer visible; history/evidence drawers closed.
2. Open AgentsView history → left drawer lists Codex/ZCode conversations; close returns to thread.
3. Submit `检查会话来源并给我一个只读建议` → named fake bridge returns a display-safe answer.
4. assistant-ui renders a `data-tool-receipt` row with query ID, row count and duration.
5. AI shows a non-modal hint; it does not auto-open the drawer.
6. Click hint → right drawer shows checksum-bound receipt, candidate card and metadata-only adapter events.
7. Reload after adding an inline favicon → Playwright console reports 0 errors and 0 warnings.

Screenshot: [`selected-c-evidence.png`](./selected-c-evidence.png).

## Security Negatives

- Generic bridge names are rejected.
- Raw SQL, filesystem paths, provider bodies and nested forbidden fields are rejected.
- Tampered checksum and unapproved statement display are rejected.
- Nested result objects are removed from receipt rows; only bounded primitive values remain.
- Candidate buttons are intentionally inert in this Spike; no authority write occurs.
- Fixture audit records text length and IDs, never the submitted text body.

## Limitations

- The prototype uses a fake named bridge, not the production Electron preload.
- No real AgentsView/canonical database is opened.
- No real Provider, Kernel or Candidate write is called.
- Existing request/response DesktopBridge cannot prove streaming or running cancel; see Spike 010.
- `@assistant-ui/react` is exact-pinned with a lockfile, but has not yet passed a separate production package qualification decision.

## Existing Desktop Regression Found

The focused Main/Preload + renderer contract suite passes `50/50`. The existing full desktop UAT fixture passes `7/8`; D1 fails at `harness:new-conversation` before any Spike code is involved.

Evidence from current production code: `synthesizeProviderMeta()` adds `session_id` only for `intent === "turn"`, while Kernel `createConversationSession()` requires `session_id`. The resulting Kernel response is non-success, so the test assertion “new-conversation must reach its bound provider” fails. This Spike did not modify production routing; the failure is recorded as a prerequisite fix for real integration, not counted as a pass.
