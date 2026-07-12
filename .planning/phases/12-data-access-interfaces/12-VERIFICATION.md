# Phase 12 Verification - 2026-07-03

## Automated Tests

### Python Contract Tests

Command:

```powershell
python -m unittest tests.test_data_access_contracts tests.test_apps_sdk_data_contracts tests.test_memory_contracts
```

Result:

- Passed.
- 17 tests.

Coverage:

- `/data/events` pagination and field selection.
- `start_time/end_time` REST alias.
- source/service/category filters.
- JSONL and CSV export.
- aggregate by event dimensions, `memory_type`, and `relation_type`.
- timeline.
- memory id and event id fetch.
- rule relation list and LLM judgment `status` relation list.
- data quality report.
- existing memory and Apps SDK contracts.

### Node MCP Apps Tests

Command:

```powershell
npm test --prefix integration/apps/personal_data_chatgpt
```

Result:

- Passed.
- 9 tests.

Coverage:

- Tool descriptor list contains 17 read-only tools.
- New data tools call `/data/*` REST paths.
- `show_data_browser` renders the Data browser widget, and the widget calls `data_*` tools through the MCP Apps bridge.
- `structuredContent` returns normalized `counts`, `items`, `rows`, and `text/content` fields where applicable.
- Existing widget tests still pass.

### Python Compile Check

Command:

```powershell
python -m py_compile integration\scripts\unified_search.py integration\scripts\api_server.py
```

Result:

- Passed.

## Live Service Verification

Services restarted after implementation and the `status` relation filter patch:

- REST API: PID 30916, `127.0.0.1:8000`
- MCP Apps server: PID 27068, `127.0.0.1:8789`
- Tunnel daemon: PID 29304, `personal-data-app`, `127.0.0.1:8081`

Health:

- `GET http://127.0.0.1:8000/health` -> HTTP 200
- `GET http://127.0.0.1:8789/health` -> HTTP 200
- `GET http://127.0.0.1:8081/healthz` -> `live`, HTTP 200
- `GET http://127.0.0.1:8081/readyz` -> `ready`, HTTP 200

### `/data/events`

Command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/events?limit=2&offset=0&fields=event_id,source,event_time,title"
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/events?limit=2&offset=2&fields=event_id,source,event_time,title"
```

Result:

- Page 1 count: 2
- Page 2 count: 2
- Total: 8136
- Page 1 first id differs from page 2 first id.
- `truncated=true`

### `/data/aggregate`

Command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/aggregate?group_by=source"
```

Result:

- Agent: 4324
- Google: 2016
- GPT: 1796

### `/data/export`

Command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/export?format=jsonl&limit=2&fields=event_id,source,title"
```

Result:

- format: `jsonl`
- count: 2
- total: 8136
- content non-empty
- `truncated=true`

### `/data/memories`

Command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/memories?limit=3&memory_type=tooling"
```

Result:

- count: 3
- total tooling memories: 21
- first subject: GPT
- `truncated=true`

### `/data/relations`

Rule relation command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/relations?limit=3&relation_type=uses_tool"
```

Result:

- count: 3
- total `uses_tool` relations: 10
- first relation: `uses_tool`
- first edge source: `rule`
- `truncated=true`

LLM judgment status command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/relations?limit=3&status=review"
```

Result:

- review judgment relations: 2
- accepted judgment relations: 0
- rejected judgment relations: 0
- first status-filtered edge source: `llm_judgment`

### `/data/quality`

Command:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/quality"
```

Result:

- events: 8136
- duplicate event ids: 0
- missing `event_time`: 1060
- missing `title`: 1618
- memories: 194
- dangling relations: 0

## MCP Tool Verification

Command:

```powershell
$body = '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"data_list_events","arguments":{"limit":2,"offset":0,"source":"GPT","fields":"event_id,source,event_time,title"}}}'
$body | curl.exe --noproxy "*" -s -H "Content-Type: application/json" --data-binary "@-" http://127.0.0.1:8789/mcp
```

Result:

- `structuredContent.ok=true`
- count: 2
- total GPT events: 1796
- normalized `counts.returned=2`
- first item source: GPT
- tool text: `Loaded 2 event(s).`

## Known Notes

- `/data/*` returns top-level contract JSON, not the legacy `{ok,data}` wrapper.
- Data quality report intentionally surfaces missing `event_time` and `title` rows; these are not regressions from this phase.
- ChatGPT tool names use snake_case (`data_list_events`) because they are safer for MCP tooling; titles preserve requested `Data.*` names.
- Local probes should use `curl.exe --noproxy "*"` or set `NO_PROXY=127.0.0.1,localhost`; otherwise PowerShell/Python may route localhost through a proxy and report false 502 errors.

## Final Hygiene

- `git diff --check` passed for the Phase 12 implementation, Apps adapter, and documentation files. Git only reported LF-to-CRLF conversion warnings.
- Strict token scan passed with no real `sk-`, `clp_`, GitHub token, or inline `CONTROL_PLANE_API_KEY` values found in the touched documentation/source scope.
