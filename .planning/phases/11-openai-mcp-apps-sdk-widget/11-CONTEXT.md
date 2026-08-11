# Phase 11 Context: OpenAI MCP Tunnel Apps SDK Widget

## Current Facts

- Project root: `$HOME\Desktop\数据分析`.
- The project uses `.gsd/phases/` as the authoritative phase history. `.planning/ROADMAP.md` is absent and `.planning/STATE.md` is stale by design.
- Current MCP server:
  - `integration/scripts/mcp_server.py`
  - transport: stdio
  - server name: `personal-data`
  - exposed tools: `search_semantic`, `query_events`, `get_event_detail`, `stats`, `list_categories`, `get_memory_profile`, `get_memory_by_subject`
- Current REST API:
  - `integration/scripts/api_server.py`
  - running locally at `http://127.0.0.1:8000`
  - health verified with `/health`
- Current dashboard:
  - Streamlit dashboard at `http://127.0.0.1:8502`
- Current graph server:
  - static graph server at `http://127.0.0.1:8765`
- Current official tunnel client:
  - binary: `$HOME\Desktop\tunnel-client\tunnel-client.exe`
  - current health endpoint: `http://127.0.0.1:8080/healthz`
  - current profile: `$HOME\AppData\Roaming\tunnel-client\codexpro.yaml`
  - current profile points to CodexPro at `http://127.0.0.1:8788/mcp`, not this data-analysis project.
- Latest verified memory graph data:
  - `memory_items=194`
  - `memory_links=1478`
  - `memory_relations=27`
  - `memory_relation_candidate_proposals=21`
  - `memory_relation_candidates=2`
  - `memory_relation_judgments=2`
  - `memory_relation_review_queue=2`
  - `memory_graph.html`: 52 nodes / 27 edges
  - `memory_graph_llm.html`: 52 nodes / 29 edges

## Official Product Boundary

OpenAI's current documented path for this use case is:

1. ChatGPT Apps use MCP to expose tool capabilities to ChatGPT.
2. Apps SDK widgets are optional UI bundles rendered inside ChatGPT's iframe.
3. Secure MCP Tunnel connects private MCP servers to supported OpenAI products without exposing the local server publicly.
4. `tunnel-client` can target either:
   - a local stdio MCP command via `--mcp-command`, or
   - a local HTTP MCP server via `--mcp-server-url`.

For this project, the next phase should use an HTTP MCP app server as a thin ChatGPT-facing layer, then connect that layer through Secure MCP Tunnel.

## Problem

The project can already answer memory/search questions through local CLI, REST, MCP, and dashboard surfaces, but it is not yet packaged as an official ChatGPT app/connector experience.

Current gaps:

- The existing `mcp_server.py` returns text-only MCP results, not Apps SDK `structuredContent` plus widget metadata.
- No app resource templates exist for ChatGPT iframe widgets.
- No bounded graph JSON endpoint exists for a widget to render directly.
- The existing tunnel profile points to CodexPro, so ChatGPT cannot use this project's MCP tools through the official tunnel.
- There is no runbook or verification path for ChatGPT Developer Mode connector setup.

## Goal

Create a read-only ChatGPT integration layer that lets GPT use the personal data system through:

- MCP tool calls,
- OpenAI Secure MCP Tunnel,
- Apps SDK widgets for graph and memory inspection.

The first successful user-facing workflow should be:

1. User asks ChatGPT to inspect their memory graph.
2. ChatGPT calls the project's MCP app tool.
3. The local server returns bounded structured graph data.
4. ChatGPT renders a widget showing memory nodes, rule edges, and LLM-judged edges.
5. User can inspect nodes/relations and ask follow-up questions.

## Non-Goals

- Do not expose the REST API directly to the public internet.
- Do not modify or overwrite the existing `codexpro` tunnel profile.
- Do not store `CONTROL_PLANE_API_KEY`, OpenAI keys, cookies, or tokens in repo files.
- Do not write to `memory_items`, `memory_links`, or `memory_relations` from ChatGPT in this phase.
- Do not add approval/write actions to the widget in the first version.
- Do not require the full Streamlit dashboard to render inside ChatGPT.
- Do not send the full database to GPT. Tool outputs must be query-scoped and bounded.

## Proposed Architecture

```text
ChatGPT / GPT app
  -> OpenAI Secure MCP Tunnel
  -> local tunnel-client profile: personal-data-app
  -> local HTTP MCP Apps server, e.g. http://127.0.0.1:8789/mcp
  -> local REST API http://127.0.0.1:8000
  -> SQLite / Chroma / memory graph tables
```

The HTTP MCP Apps server should be a thin adapter. It should not duplicate memory logic. It should call existing Python REST endpoints and return Apps SDK-compatible tool results.

## Design Decisions

### Use a New HTTP MCP Apps Layer

- Keep `integration/scripts/mcp_server.py` stable for existing local MCP clients.
- Add a separate Apps SDK-oriented server under `integration/apps/personal_data_chatgpt/`.
- Use the HTTP MCP path for ChatGPT Apps and Secure MCP Tunnel.
- Keep existing stdio MCP tests intact.

### Add Bounded Data Endpoints

The widget needs graph-shaped JSON. Add a small backend data contract rather than scraping generated HTML.

Candidate endpoints:

- `GET /memory/graph?include_llm=1&subject=&hops=&limit=`
- `GET /memory/relation-review?limit=`

These endpoints should return bounded, deterministic JSON:

- nodes: memory id, subject, type, subtype, description summary
- edges: source id, target id, relation, source layer (`rule` or `llm_judgment`), confidence/status when present
- counts and truncation flags

### Tool Set for ChatGPT

Expose a small read-only tool set:

- `search`: OpenAI connector-compatible search wrapper over semantic search.
- `fetch`: OpenAI connector-compatible fetch wrapper for event/memory ids.
- `show_memory_graph`: returns graph structured data and launches graph widget.
- `show_memory_subject`: returns a subject detail view and launches graph/detail widget.
- `show_relation_review_queue`: returns LLM relation judgments needing review and launches review widget.
- `get_system_stats`: returns current data counts without launching a widget.

All tools in this phase should be read-only.

### Widget Set

Build two widgets first:

- `memory-graph-widget.html`
  - renders memory nodes and relation edges,
  - distinguishes rule edges from LLM judgment edges,
  - supports subject/type/status filtering,
  - lets users inspect a selected node and edge evidence summary.
- `relation-review-widget.html`
  - renders the Phase 10 review queue read-only,
  - shows relation type, confidence, gate status, candidate id, and reason.

### Security Boundary

- Tunnel is MCP transport only; local REST remains loopback-only.
- Widget should not fetch arbitrary external URLs.
- Tool outputs should include only bounded records selected by query/graph scope.
- No payload capture or raw unsafe tunnel logging should be enabled by default.
- No write tools until a later explicit phase adds review/apply semantics.

## Acceptance Criteria

- Existing MCP/REST contract tests still pass.
- A new local HTTP MCP Apps server starts on a non-conflicting local port.
- The app server lists Apps SDK-compatible tools with:
  - `outputSchema` for structured results,
  - `_meta.ui.resourceUri` for widget-backed tools,
  - read-only annotations.
- `memory-graph-widget.html` renders from fixture `structuredContent` without requiring ChatGPT.
- A new tunnel profile can be created for this app without modifying `codexpro.yaml`.
- `tunnel-client doctor --profile personal-data-app --explain` passes when credentials and tunnel id are available.
- ChatGPT connector setup has a documented runbook and manual UAT prompts.
- No repo file contains API keys or tunnel runtime secrets.

## Canonical References

- `integration/scripts/mcp_server.py` - existing local MCP server and tool semantics.
- `integration/scripts/api_server.py` - existing REST API surface.
- `integration/scripts/unified_search.py` - core data access contracts.
- `integration/scripts/query_graph.py` - existing graph loading and visualization behavior.
- `tests/test_memory_contracts.py` - current core/CLI/REST/MCP contract test.
- `$HOME\Desktop\tunnel-client\ops\watchdog\watchdog.production.config.json` - existing tunnel watchdog pattern.
- `$HOME\AppData\Roaming\tunnel-client\codexpro.yaml` - current profile to avoid mutating.
