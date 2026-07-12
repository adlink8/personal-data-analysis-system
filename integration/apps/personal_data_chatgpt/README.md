# Personal Data ChatGPT MCP App

Read-only HTTP MCP Apps adapter for the local personal data REST API.

## Run

Prerequisites:

- Node.js 20 or newer.
- Python REST API running at `http://127.0.0.1:8000`.

```powershell
cd integration\apps\personal_data_chatgpt
npm install
npm start
```

Defaults:

- Apps MCP server: `http://127.0.0.1:8789`
- MCP endpoint: `http://127.0.0.1:8789/mcp`
- Health check: `http://127.0.0.1:8789/health`
- REST backend: `http://127.0.0.1:8000`

Override with environment variables:

```powershell
$env:PORT = "8789"
$env:HOST = "127.0.0.1"
$env:PERSONAL_DATA_REST_URL = "http://127.0.0.1:8000"
npm start
```

## Tools

- `search`: semantic search wrapper over `POST /search/semantic`.
- `fetch`: fetch one event id or memory subject.
- `show_memory_graph`: returns bounded graph `structuredContent` and the memory graph widget.
- `show_memory_subject`: returns one subject plus neighbors as graph `structuredContent` and the memory graph widget.
- `show_relation_review_queue`: returns relation review queue `structuredContent` and the review widget.
- `show_data_browser`: renders the Data browser widget. The widget calls the `data_*` tools through the MCP Apps bridge.
- `get_system_stats`: returns current `/stats` data.
- `data_list_events` (`Data.list_events`): pages event records with `limit`, `offset`, source/service/category/time filters, and optional field selection.
- `data_list_memories` (`Data.list_memories`): pages long-term memory records by type or subject substring.
- `data_list_relations` (`Data.list_relations`): pages rule and LLM memory relation records with `relation_type`, `subject`, memory id, and `status` filters.
- `data_aggregate` (`Data.aggregate`): counts records grouped by month, source, service, category, memory type, or relation type. Prefer `group_by_fields: ["source", "service"]` for multi-field grouping; `group_by` remains for single-field compatibility.
- `data_timeline` (`Data.timeline`): returns day/month/year counts, optionally filtered by subject.
- `data_export_all` (`Data.export_all`): exports a bounded event slice as JSON, JSONL, or CSV.
- `data_export_query` (`Data.export_query`): exports a bounded filtered event query as JSON, JSONL, or CSV.
- `data_get_event_by_id` (`Data.get_event_by_id`): fetches one exact event id.
- `data_get_memory_by_id` (`Data.get_memory_by_id`): fetches one exact memory id.
- `data_quality_report` (`Data.data_quality_report`): summarizes duplicate, missing-field, orphan-link, and judgment-status checks.

All tools are read-only and set `annotations.readOnlyHint = true`.

Widget-backed tools use the MCP Apps standard `_meta.ui.resourceUri` and the ChatGPT compatibility alias `_meta["openai/outputTemplate"]`.

Data access tools use snake_case MCP names for compatibility. Their titles preserve the `Data.*` names shown above. They also declare `_meta.ui.visibility = ["model", "app"]` and `_meta["openai/widgetAccessible"] = true` so widgets can call them through the bridge.

Event list/export tools default to compact fields and do not include full `content` or `content_rich` unless requested through `fields`.

## Widgets

- `public/memory-graph-widget.html`: renders nodes and edges from `structuredContent`, distinguishes `rule` and `llm_judgment` edges, and supports type, edge-source, and subject filters.
- `public/relation-review-widget.html`: renders the relation review queue as a read-only table.
- `public/data-browser-widget.html`: renders a compact browser for `/data/*` tools and calls `data_*` tools through `window.openai.callTool` or standard `tools/call` postMessage.
- `public/widget-harness.html`: local fixture harness for testing without ChatGPT.

The widgets listen for MCP Apps bridge messages:

```json
{
  "jsonrpc": "2.0",
  "method": "ui/notifications/tool-result",
  "params": {
    "structuredContent": {}
  }
}
```

## Test

```powershell
cd integration\apps\personal_data_chatgpt
npm install
npm test
```

The tests use mocked REST responses, so they do not require the Python REST server or ChatGPT.
