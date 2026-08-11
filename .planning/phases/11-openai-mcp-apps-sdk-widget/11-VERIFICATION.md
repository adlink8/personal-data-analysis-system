# Phase 11 Verification - 2026-07-02

Verdict: PARTIAL PASS - local implementation and automated verification passed; external ChatGPT tunnel connection requires human-provided tunnel id and connector access.

## What Changed

Backend REST contracts:

- Added `GET /memory/graph?subject=&hops=&include_llm=&limit=`.
- Added `GET /memory/relation-review?limit=&status=`.
- Added `tests/test_apps_sdk_data_contracts.py`.

ChatGPT-facing MCP app:

- Added `integration/apps/personal_data_chatgpt/server.mjs`.
- Added read-only tools:
  - `search`
  - `fetch`
  - `show_memory_graph`
  - `show_memory_subject`
  - `show_relation_review_queue`
  - `get_system_stats`
- Added widget resources:
  - `ui://personal-data/memory-graph-widget.html`
  - `ui://personal-data/relation-review-widget.html`
- Added local widget harness and fixtures.
- Added tunnel runbook.

## Local Services

| Service | URL | Status |
| --- | --- | --- |
| REST API | `http://127.0.0.1:8000` | running, PID observed `64296` |
| Apps MCP server | `http://127.0.0.1:8789` | running, PID observed `26420` |
| Apps MCP endpoint | `http://127.0.0.1:8789/mcp` | JSON-RPC probe passed |

## Data Contract Verification

REST graph probe:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/memory/graph?include_llm=1&limit=200"
```

Observed:

| Metric | Value |
| --- | ---: |
| total nodes | 52 |
| total edges | 29 |
| LLM judgment edges | 2 |
| truncated | false |

REST relation review probe:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/memory/relation-review?status=review&limit=10"
```

Observed:

| Metric | Value |
| --- | ---: |
| review count | 2 |
| returned items | 2 |
| first status | `review` |

## MCP App Verification

Tools listed from `POST /mcp`:

- `search`
- `fetch`
- `show_memory_graph`
- `show_memory_subject`
- `show_relation_review_queue`
- `get_system_stats`

`show_memory_graph` tool call returned:

| Metric | Value |
| --- | ---: |
| ok | true |
| nodes | 52 |
| edges | 29 |
| LLM judgment edges | 2 |

`resources/read` for `ui://personal-data/memory-graph-widget.html` returned:

| Metric | Value |
| --- | --- |
| mime type | `text/html;profile=mcp-app` |
| HTML length | 12834 |

## Automated Tests

Python:

```powershell
python -m unittest tests.test_apps_sdk_data_contracts tests.test_memory_contracts tests.test_memory_relation_candidates tests.test_memory_graph_visualization
```

Result:

- 18 tests passed.

Node:

```powershell
cd integration\apps\personal_data_chatgpt
npm test
```

Result:

- 8 tests passed.

Static checks:

```powershell
git diff --check -- integration\scripts\unified_search.py integration\scripts\api_server.py tests\test_apps_sdk_data_contracts.py integration\apps\personal_data_chatgpt .gsd\phases\11_openai_mcp_apps_sdk_widget
rg -n "sk-[A-Za-z0-9]|clp_[A-Za-z0-9]|CONTROL_PLANE_API_KEY\s*[:=]\s*[A-Za-z0-9]|gho_[A-Za-z0-9]" integration\apps\personal_data_chatgpt .gsd\phases\11_openai_mcp_apps_sdk_widget integration\scripts\unified_search.py integration\scripts\api_server.py tests\test_apps_sdk_data_contracts.py
```

Result:

- `git diff --check` passed.
- Secret pattern scan had no matches.

## Tunnel Status

`$env:APPDATA\tunnel-client\personal-data-app.yaml` does not exist yet.

This is intentional. Creating and running the profile requires:

- a real tunnel id,
- `CONTROL_PLANE_API_KEY` in the environment,
- ChatGPT connector/app developer access.

Runbook:

- `integration/apps/personal_data_chatgpt/TUNNEL_RUNBOOK.md`

Expected profile command:

```powershell
cd $HOME\Desktop\tunnel-client

.\tunnel-client.exe init `
  --profile personal-data-app `
  --tunnel-id <tunnel_id> `
  --mcp-server-url http://127.0.0.1:8789/mcp `
  --health-listen-addr 127.0.0.1:8081
```

## Safety Boundary

- No new code writes to `memory_items`, `memory_links`, or `memory_relations`.
- Existing stdio MCP server remains available.
- Existing `codexpro.yaml` was not modified.
- REST API remains loopback-only.
- Widget resources use inline HTML/CSS/JS and no external assets.

## Residual Risk

- The HTTP MCP implementation is intentionally minimal and verified locally through JSON-RPC; final compatibility must be confirmed through the official ChatGPT connector tunnel.
- ChatGPT account/workspace entitlement may block external UAT even when local MCP probes pass.
- The first version is read-only; approval/apply workflows are deferred to a future phase.
