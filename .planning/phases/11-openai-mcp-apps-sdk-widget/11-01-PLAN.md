# Phase 11 Plan: OpenAI MCP Tunnel Apps SDK Widget

## Objective

Build a read-only ChatGPT integration path for the personal data system using MCP, OpenAI Secure MCP Tunnel, and Apps SDK widgets.

The phase is complete when ChatGPT can call local personal-data MCP tools through the official tunnel and render a memory graph / LLM relation review widget from bounded structured data.

## Scope

### In Scope

1. Add bounded JSON data contracts for memory graph and relation review queue.
2. Add a ChatGPT-facing HTTP MCP Apps server that wraps the existing local REST API.
3. Add Apps SDK widget resources for memory graph and relation review inspection.
4. Add a separate tunnel profile/runbook for `personal-data-app`.
5. Add local tests and manual UAT prompts for ChatGPT connector validation.

### Out of Scope

- Public REST deployment.
- Long-term memory writes from ChatGPT.
- Review/approval mutations from widget buttons.
- Full Streamlit dashboard embedding.
- Replacing existing stdio MCP clients.
- Modifying the existing `codexpro` tunnel profile.

## Wave 1: Backend Data Contracts

Files:

- `integration/scripts/unified_search.py`
- `integration/scripts/api_server.py`
- `integration/scripts/query_graph.py`
- `tests/test_apps_sdk_data_contracts.py`

Tasks:

1. Extract or reuse graph loading logic so it can return JSON, not only pyvis HTML.
2. Add `GET /memory/graph` with parameters:
   - `subject` optional,
   - `hops` default `1`,
   - `include_llm` default `false`,
   - `limit` default bounded, max bounded.
3. Add `GET /memory/relation-review` with parameters:
   - `limit` default `50`, max bounded,
   - optional `status=review|accepted|rejected`.
4. Ensure responses include:
   - `ok`,
   - `scope`,
   - `counts`,
   - `nodes`/`edges` or `items`,
   - `truncated`.
5. Keep all new endpoints read-only.
6. Preserve existing `/memory`, `/memory/<subject>`, `/search/*`, and `/stats` behavior.

Verification:

```powershell
python -m unittest tests.test_memory_contracts tests.test_apps_sdk_data_contracts
curl.exe --noproxy "*" "http://127.0.0.1:8000/memory/graph?include_llm=1"
curl.exe --noproxy "*" "http://127.0.0.1:8000/memory/relation-review?limit=10"
```

Acceptance criteria:

- Graph endpoint returns bounded JSON with current memory graph counts.
- Relation review endpoint returns the current review queue without mutating tables.
- Existing memory contract tests still pass.

## Wave 2: HTTP MCP Apps Server

Files:

- `integration/apps/personal_data_chatgpt/package.json`
- `integration/apps/personal_data_chatgpt/server.mjs`
- `integration/apps/personal_data_chatgpt/README.md`
- `integration/apps/personal_data_chatgpt/test/contract.test.mjs`

Tasks:

1. Create a minimal Node HTTP MCP server for ChatGPT Apps.
2. Keep it as a thin adapter over `http://127.0.0.1:8000`.
3. Expose read-only tools:
   - `search`,
   - `fetch`,
   - `show_memory_graph`,
   - `show_memory_subject`,
   - `show_relation_review_queue`,
   - `get_system_stats`.
4. For every tool:
   - provide clear descriptions,
   - define input schema,
   - define output schema when returning `structuredContent`,
   - set read-only annotations.
5. For widget-backed tools:
   - set `_meta.ui.resourceUri`,
   - keep optional OpenAI compatibility metadata only where useful.
6. Add local contract tests that list tools and call at least:
   - `get_system_stats`,
   - `show_memory_graph`,
   - `show_relation_review_queue`.

Verification:

```powershell
cd integration\apps\personal_data_chatgpt
npm install
npm test
npm start
```

Acceptance criteria:

- Server starts on `127.0.0.1:8789`.
- MCP endpoint is reachable at `http://127.0.0.1:8789/mcp`.
- Tool list includes all planned tools.
- Tool calls return structured data, not only text.

## Wave 3: Apps SDK Widgets

Files:

- `integration/apps/personal_data_chatgpt/public/memory-graph-widget.html`
- `integration/apps/personal_data_chatgpt/public/relation-review-widget.html`
- `integration/apps/personal_data_chatgpt/public/widget-harness.html`
- `integration/apps/personal_data_chatgpt/test/widget-fixtures/*.json`
- `integration/apps/personal_data_chatgpt/test/widget-render.test.mjs`

Tasks:

1. Build `memory-graph-widget.html`.
   - Render nodes and edges from `structuredContent`.
   - Distinguish rule edges from LLM judgment edges.
   - Show node type, relation type, confidence, and gate status.
   - Support local filtering by memory type and edge source.
2. Build `relation-review-widget.html`.
   - Render review queue rows.
   - Show candidate id, subjects, relation type, confidence, gate status, and reason.
   - Keep first version read-only.
3. Use the MCP Apps bridge lifecycle:
   - handle `ui/notifications/tool-result`,
   - render from `structuredContent`,
   - optionally support `tools/call` for subject drilldown after the basic path is stable.
4. Avoid external network assets in the first version.
5. Add a local harness so widgets can be tested without ChatGPT.
6. Use Playwright or a small browser test to assert:
   - widget renders nonblank,
   - expected node/relation text appears,
   - no overlapping critical controls at desktop/mobile widths.

Verification:

```powershell
cd integration\apps\personal_data_chatgpt
npm run test:widgets
```

Acceptance criteria:

- Widgets render from fixture data locally.
- Graph widget shows rule and LLM edges distinctly.
- Review widget shows the current review queue clearly.
- No external asset dependency is required for local rendering.

## Wave 4: Secure MCP Tunnel Profile And Runbook

Files:

- `integration/apps/personal_data_chatgpt/TUNNEL_RUNBOOK.md`
- `C:\Users\li\AppData\Roaming\tunnel-client\personal-data-app.yaml` (generated locally, not committed)

Tasks:

1. Document prerequisites:
   - `CONTROL_PLANE_API_KEY` set in environment,
   - tunnel id from Platform tunnel settings,
   - ChatGPT Developer Mode / connector access,
   - REST API running on `127.0.0.1:8000`,
   - Apps MCP server running on `127.0.0.1:8789`.
2. Create a separate tunnel profile:

```powershell
cd C:\Users\li\Desktop\tunnel-client
.\tunnel-client.exe init `
  --profile personal-data-app `
  --tunnel-id <tunnel_id> `
  --mcp-server-url http://127.0.0.1:8789/mcp `
  --health-listen-addr 127.0.0.1:8081
```

3. Verify profile:

```powershell
.\tunnel-client.exe doctor --profile personal-data-app --explain
.\tunnel-client.exe run --profile personal-data-app
```

4. Document ChatGPT connector setup:
   - Settings -> Connectors -> Create,
   - choose Tunnel,
   - select/paste tunnel id,
   - refresh connector after tool or metadata changes.
5. Document manual UAT prompts:
   - "打开我的长期记忆图谱，显示 LLM 判断边。"
   - "查看 Codex 相关的记忆和 2 跳邻居。"
   - "列出需要人工审查的长期记忆关系。"
   - "用我的历史数据搜索最近关于 MCP 或 Apps SDK 的记录。"

Verification:

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8789/health
curl.exe --noproxy "*" http://127.0.0.1:8081/healthz
```

Acceptance criteria:

- `codexpro.yaml` remains unchanged.
- `personal-data-app` profile exists outside the repo.
- Tunnel doctor passes when runtime credentials are available.
- Local tunnel admin UI is reachable on `127.0.0.1:8081/ui`.

## Wave 5: Integration Verification

Files:

- `.gsd/phases/11_openai_mcp_apps_sdk_widget/VERIFICATION_2026-07-02.md`
- `README.md`
- `integration/README.md`

Tasks:

1. Run Python contract tests:

```powershell
python -m unittest tests.test_memory_contracts tests.test_apps_sdk_data_contracts
```

2. Run Node app tests:

```powershell
cd integration\apps\personal_data_chatgpt
npm test
npm run test:widgets
```

3. Start local services:

```powershell
python integration\scripts\api_server.py --host 127.0.0.1 --port 8000
cd integration\apps\personal_data_chatgpt
npm start
```

4. Verify tunnel:

```powershell
cd C:\Users\li\Desktop\tunnel-client
.\tunnel-client.exe doctor --profile personal-data-app --explain
```

5. Verify ChatGPT manually with the UAT prompts from Wave 4.
6. Record:
   - exposed tools,
   - graph node/edge counts,
   - relation review count,
   - tunnel profile name,
   - tests run,
   - any ChatGPT connector limitations.

Success criteria:

- Existing local MCP/REST behavior remains stable.
- ChatGPT-facing MCP app lists and calls tools.
- Widget renders graph/review data locally.
- Secure MCP Tunnel connects to the new app profile.
- No long-term memory tables are mutated by the integration.
- No secrets are written to the repo.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| ChatGPT account lacks Apps/Connector/Tunnel entitlement | Keep local MCP app and widget harness testable; document account-side blocker explicitly. |
| Payload too large for widget/model | Enforce node/edge limits and truncation flags. |
| REST and app server ports collide | Use fixed defaults `8000`, `8789`, `8081`, with documented overrides. |
| Existing MCP clients break | Add a separate app server; do not replace `mcp_server.py`. |
| Widget accidentally implies writes/review approval | Keep Phase 11 read-only; defer write tools to a future phase. |
| Secrets leak into config/docs/logs | Use env references only and add grep-based verification. |

## Follow-Up Phase Candidates

- Phase 12: Review/apply workflow for memory relation judgments from ChatGPT with explicit confirmation and audit logs.
- Phase 13: Company Knowledge-compatible `search`/`fetch` citation hardening.
- Phase 14: Publishable app submission hardening: OAuth, privacy policy, screenshots, localization, and review package.
