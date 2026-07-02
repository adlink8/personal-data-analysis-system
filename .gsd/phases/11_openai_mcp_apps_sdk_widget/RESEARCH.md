# Phase 11 Research: OpenAI MCP Tunnel Apps SDK Widget

## Research Summary

Official OpenAI documentation supports the selected path:

- Apps SDK apps use MCP to connect tools to ChatGPT.
- A widget/UI bundle is optional and renders inside a ChatGPT iframe.
- The widget communicates with the host through the MCP Apps bridge using JSON-RPC over `postMessage`.
- Tool descriptors can point to UI templates through `_meta.ui.resourceUri`.
- Secure MCP Tunnel connects private/local MCP servers to supported OpenAI products without opening public inbound access.
- `tunnel-client` can target local stdio MCP commands or local HTTP MCP servers.

Official sources consulted:

- `https://developers.openai.com/apps-sdk/build/mcp-server`
- `https://developers.openai.com/apps-sdk/build/chatgpt-ui`
- `https://developers.openai.com/apps-sdk/mcp-apps-in-chatgpt`
- `https://developers.openai.com/apps-sdk/reference`
- `https://developers.openai.com/api/docs/guides/secure-mcp-tunnels`

## Option Comparison

| Option | Description | Advantages | Limits | Fit |
| --- | --- | --- | --- | --- |
| Extend current Python stdio MCP server | Add Apps metadata/resources to `integration/scripts/mcp_server.py` and connect via `--mcp-command` | Minimal service count; reuses current MCP entry | Current server is text-first; Apps resource support may be awkward in Python low-level server; harder to test ChatGPT iframe contract | Medium |
| Add HTTP MCP Apps server as thin adapter | New app server calls local REST and returns Apps SDK-compatible structured results/widgets | Clean separation; matches Apps SDK docs; avoids breaking existing MCP clients; good for tunnel `--mcp-server-url` | Adds Node/JS app surface and local port | High |
| Expose REST API through generic tunnel | ChatGPT or external tools call REST endpoints directly | Simple HTTP shape | Official Secure MCP Tunnel is for MCP, not generic REST exposure; public REST would need auth and ingress | Low |
| Embed Streamlit dashboard in ChatGPT | Try to iframe the existing dashboard | Reuses dashboard work | ChatGPT widget iframe/CSP/review constraints; large app surface; not query-scoped | Low |

## Recommendation

Use a new HTTP MCP Apps server as a thin adapter over the existing Python REST API.

Reasons:

- It preserves existing CLI/REST/MCP behavior.
- It aligns with official Apps SDK examples and metadata shape.
- It lets the widget receive compact `structuredContent` instead of scraping HTML.
- It gives the tunnel a clean `--mcp-server-url http://127.0.0.1:8789/mcp` target.
- It keeps the local REST API loopback-only and hidden behind MCP tools.

## Data Contract Research

The current REST API lacks widget-ready graph JSON. The existing `query_graph.py` can load a NetworkX graph and already supports LLM edges. The app should not parse `memory_graph_llm.html`; it should consume a bounded JSON graph contract.

Recommended graph payload:

```json
{
  "ok": true,
  "scope": {
    "subject": "Codex",
    "hops": 2,
    "include_llm": true
  },
  "counts": {
    "nodes": 52,
    "edges": 29,
    "truncated": false
  },
  "nodes": [
    {
      "id": "mem_...",
      "subject": "Codex",
      "memory_type": "tooling",
      "memory_subtype": "..."
    }
  ],
  "edges": [
    {
      "source": "mem_...",
      "target": "mem_...",
      "relation": "same_subject",
      "edge_source": "llm_judgment",
      "gate_status": "review",
      "confidence": 0.81
    }
  ]
}
```

Recommended review payload:

```json
{
  "ok": true,
  "count": 2,
  "items": [
    {
      "candidate_id": "candidate_...",
      "source_subject": "Python",
      "target_subject": "Python",
      "relation_type": "same_subject",
      "gate_status": "review",
      "confidence": 0.79,
      "reason": "risk_flags_present"
    }
  ]
}
```

## Security Notes

- Keep `CONTROL_PLANE_API_KEY` in environment variables only.
- Use a separate `personal-data-app` tunnel profile.
- Use a separate health/admin port such as `127.0.0.1:8081` to avoid the current CodexPro tunnel admin UI on `8080`.
- Keep the Apps server and REST API bound to `127.0.0.1`.
- Keep tool annotations read-only in Phase 11.
- Do not enable unsafe raw HTTP logging.
- Add tests or grep checks to ensure no `sk-`, `clp_`, or runtime tunnel secret appears in new files.

## Open Questions For Execution

- The user must provide or select the actual `tunnel_id` in Platform tunnel settings.
- ChatGPT workspace must have Developer Mode / connector access and tunnel permission.
- If ChatGPT Apps SDK access is unavailable in the account, the same MCP app server can still be tested locally and through supported API/connector surfaces.
