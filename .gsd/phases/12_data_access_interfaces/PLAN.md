# Phase 12 Plan: Data Access Interfaces

## Objective

Add a bounded, paginated, exportable data access layer for events, memories, relations, aggregation, timeline analysis, and data quality checks.

The phase is complete when local REST and ChatGPT MCP tools can browse the full 8136-event dataset safely with pagination and filters, export bounded datasets for offline analysis, and inspect memory/relation records by id.

## Scope

### In Scope

1. Add P0 event list/export/time/source/service/category filters.
2. Add P1 memory/relation list and explicit id fetch contracts.
3. Add P1 aggregation and P2 timeline/data-quality read-only contracts.
4. Expose the new contracts through `/data/*` REST endpoints.
5. Expose the new contracts through ChatGPT MCP tools.
6. Update project docs and tests.

### Out of Scope

- Write/update/delete actions.
- Public deployment.
- OAuth/PRMD metadata.
- Full dashboard redesign.
- Unbounded raw database dump through ChatGPT.
- New storage schema.

## Wave 1: Backend Data Contracts

Files:

- `integration/scripts/unified_search.py`
- `integration/scripts/api_server.py`
- `tests/test_data_access_contracts.py`

Tasks:

1. Add `list_events` contract with:
   - `limit`, default `100`, hard max `500`,
   - `offset`, default `0`,
   - filters: `source`, `service`, `category`, `start_time`, `end_time`, `keyword`,
   - `fields` allow-list with compact defaults.
2. Add `export_all/export_query` contract with:
   - `format=jsonl|csv`,
   - same filters as `list_events`,
   - hard cap and `truncated` flag.
3. Add `list_memories` contract with:
   - `limit`, `offset`,
   - `memory_type`,
   - `subject_like`.
4. Add `list_relations` contract with:
   - `limit`, `offset`,
   - `relation_type`,
   - `status` for LLM judgment status when present.
5. Add explicit id getters:
   - `get_event_by_id`,
   - `get_memory_by_id`.
6. Add `aggregate` contract:
   - group by `month`, `source`, `service`, `category`, `memory_type`, `relation_type`,
   - metric `count` first.
7. Add `timeline` contract:
   - `subject`,
   - bucket `month` first,
   - count events and memory evidence where possible.
8. Add `data_quality_report` contract:
   - missing/empty time fields,
   - duplicate event ids,
   - missing rich content rows,
   - orphan memory links,
   - orphan memory relations,
   - low confidence memories,
   - LLM relation judgment status distribution.
9. Add `/data/*` REST routes returning top-level contract JSON, not `{data: ...}` wrappers.
10. Preserve existing compatibility routes.

Verification:

```powershell
python -m unittest tests.test_data_access_contracts tests.test_memory_contracts tests.test_apps_sdk_data_contracts
python -m py_compile integration\scripts\unified_search.py integration\scripts\api_server.py
```

Acceptance criteria:

- Event pagination returns distinct pages and total/returned counts.
- Time/source/service/category filters affect counts predictably.
- CSV and JSONL exports are parseable and bounded.
- Memory/relation list endpoints return totals, offset, and truncation.
- Explicit id endpoints avoid `fetch` auto-detection ambiguity.

## Wave 2: ChatGPT MCP Tool Layer

Files:

- `integration/apps/personal_data_chatgpt/server.mjs`
- `integration/apps/personal_data_chatgpt/test/contract.test.mjs`

Tasks:

1. Add read-only MCP tools:
   - `Data.list_events`,
   - `Data.list_memories`,
   - `Data.list_relations`,
   - `Data.aggregate`,
   - `Data.timeline`,
   - `Data.export_all`,
   - `Data.export_query`,
   - `Data.get_event_by_id`,
   - `Data.get_memory_by_id`,
   - `Data.data_quality_report`.
2. If dotted names are unsuitable in MCP tool names, use snake_case names and set titles to the `Data.*` names.
3. Add input schemas with bounded `limit`, explicit filters, and field selection.
4. Add output schemas with `ok`, `scope`, `counts`, `items` or `text`.
5. Keep all annotations read-only.
6. Keep existing Phase 11 tools stable.
7. Extend Node contract tests:
   - tool list includes new data tools,
   - data tools call `/data/*`,
   - returned data appears in `structuredContent`.

Verification:

```powershell
npm test --prefix integration/apps/personal_data_chatgpt
```

Acceptance criteria:

- ChatGPT sees deterministic data access tools.
- `Data.list_events` can page records without returning full content by default.
- `Data.aggregate` can answer source/month/category count questions.
- Export tools return bounded text payloads with clear truncation metadata.

## Wave 3: Documentation Update

Files:

- `README.md`
- `integration/README.md`
- `integration/apps/personal_data_chatgpt/README.md`
- `.gsd/phases/12_data_access_interfaces/EXECUTION_SUMMARY.md`
- `.gsd/phases/12_data_access_interfaces/VERIFICATION_2026-07-03.md`

Tasks:

1. Update REST API docs with `/data/*` endpoints.
2. Update ChatGPT app docs with the new data tools.
3. Document field selection and hard caps.
4. Record verification outputs and current dataset counts.
5. Do a secret scan for known key/token patterns.

Verification:

```powershell
rg -n "sk-|clp_|gho_|ghp_|CONTROL_PLANE_API_KEY\\s*[:=]\\s*[A-Za-z0-9]" README.md integration .gsd/phases/12_data_access_interfaces
```

Acceptance criteria:

- Docs match implemented endpoint names and parameters.
- Docs do not contain secrets.
- Phase summary lists files changed and tests run.

## Integration Verification

Run:

```powershell
python -m unittest tests.test_data_access_contracts tests.test_memory_contracts tests.test_apps_sdk_data_contracts
npm test --prefix integration/apps/personal_data_chatgpt
python -m py_compile integration\scripts\unified_search.py integration\scripts\api_server.py
```

Manual service probes:

```powershell
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/events?limit=2&offset=0"
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/events?limit=2&offset=2"
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/aggregate?group_by=source"
curl.exe --noproxy "*" "http://127.0.0.1:8000/data/quality"
```

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Export sends too much to GPT | Enforce hard caps, return `truncated`, default compact fields. |
| Dotted MCP tool names are rejected | Fall back to snake_case names with `Data.*` titles. |
| Query logic duplicates old `query_events` behavior | Keep new contracts in `unified_search.py`, route old APIs through existing functions unchanged. |
| Data quality report becomes expensive | Use SQL aggregate checks only; avoid full content scans. |
| Docs drift from code | Update docs after implementation and verify endpoint names against tests. |

