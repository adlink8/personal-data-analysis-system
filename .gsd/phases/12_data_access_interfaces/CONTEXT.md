# Phase 12 Context: Data Access Interfaces

## Current Facts

- Project root: `C:\Users\li\Desktop\数据分析`.
- Authoritative phase history is `.gsd/phases/`; `.planning/ROADMAP.md` is absent.
- Phase 11 added a ChatGPT-facing HTTP MCP Apps adapter and read-only memory graph widgets.
- Current live dataset shape:
  - `unified_events`: 8136 rows.
  - `unified_events_rich`: 8136 rows.
  - `event_categories_v2`: 8136 rows.
  - `memory_items`: 194 rows.
  - `memory_links`: 1478 rows.
  - `memory_relations`: 27 rows.
  - `memory_relation_candidates`: 2 rows.
  - `memory_relation_judgments`: 2 rows.
- Current REST/API limitations:
  - `query_events()` supports filters but no pagination offset.
  - Time filtering is month-prefix only, not `start_time/end_time`.
  - `search` returns large content by default.
  - `fetch` uses auto event/memory detection, which is useful but not enough for deterministic id fetch.
  - Long-term memory has subject lookup and graph views but no general paginated memory/relation list.
  - No bulk export contract exists for offline analysis, backup, or external visualization.

## Problem

The ChatGPT connector and local REST API can inspect selected records, but cannot systematically browse, export, aggregate, or audit the full dataset.

The immediate pain points are:

- 8136 events cannot be paged reliably.
- Offline analysis needs `jsonl` or `csv` export.
- Trends require time slicing.
- GPT, Agent, Google, Codex, WorkBuddy, and other service/source groupings need first-class filters.
- Memory and relation libraries need browsable list endpoints, not only subject lookup.
- Deterministic `get_event_by_id` and `get_memory_by_id` should exist as explicit tools.
- Data quality issues should be visible before downstream LLM analysis trusts the data.

## User Priorities

### P0

- `list_events(limit, offset, filters)`.
- `export_all(format=jsonl/csv)`.
- `start_time/end_time` filtering.
- `source/service/category` filtering.

### P1

- `aggregate(group_by, metric, filters)`.
- `list_memories`.
- `list_relations`.
- `get_event_by_id`.
- `get_memory_by_id`.
- Search/list field selection to avoid oversized content payloads.

### P2

- `timeline(subject, bucket)`.
- `data_quality_report`.

## Design Decisions

### One Backend Contract Layer

All new behavior should live first in `integration/scripts/unified_search.py` as pure read-only functions. REST and MCP tools must be thin adapters over those functions.

### Bounded Outputs

Every list/export endpoint must enforce hard limits. Defaults should be useful for GPT and dashboards without dumping the full database by accident.

### Default Compact Fields

Event list/search outputs should default to compact fields:

- `event_id`
- `source`
- `service`
- `event_time`
- `month`
- `category_v2`
- `title`

Large fields like `content` and `content_rich` should appear only when explicitly requested via `fields`.

### Explicit Data Namespace

Use REST paths under `/data/*` for the new systematic access layer so it does not blur with old `/search/*`, `/event/*`, and `/memory/*` compatibility routes.

Candidate REST paths:

- `GET /data/events`
- `GET /data/export`
- `GET /data/memories`
- `GET /data/relations`
- `GET /data/aggregate`
- `GET /data/timeline`
- `GET /data/event/<event_id>`
- `GET /data/memory/<memory_id>`
- `GET /data/quality`

### ChatGPT MCP Tool Names

Expose GPT-facing tools with stable names:

- `Data.list_events`
- `Data.list_memories`
- `Data.list_relations`
- `Data.aggregate`
- `Data.timeline`
- `Data.export_all`
- `Data.export_query`
- `Data.get_event_by_id`
- `Data.get_memory_by_id`
- `Data.data_quality_report`

If the MCP server rejects dots in tool names, use snake_case names but preserve the title/description as `Data.*`.

## Non-Goals

- No write or mutation tools.
- No unbounded database dump through ChatGPT.
- No new database tables.
- No new web framework dependency.
- No OAuth/PRMD work in this phase.
- No full BI dashboard replacement.

## Canonical References

- `integration/scripts/unified_search.py` - core data access contracts.
- `integration/scripts/api_server.py` - local REST API.
- `integration/apps/personal_data_chatgpt/server.mjs` - ChatGPT MCP Apps adapter.
- `tests/test_memory_contracts.py` - existing local memory/API contracts.
- `tests/test_apps_sdk_data_contracts.py` - Phase 11 Apps SDK data contracts.
- `integration/apps/personal_data_chatgpt/test/contract.test.mjs` - Node MCP contract tests.
- `README.md` and `integration/README.md` - user-facing interface documentation.

