# Personal Data ChatGPT Tunnel Runbook

This runbook connects the read-only personal data MCP Apps server to ChatGPT through OpenAI Secure MCP Tunnel.

## Prerequisites

- REST API running at `http://127.0.0.1:8000`.
- Apps MCP server running at `http://127.0.0.1:8789/mcp`.
- `CONTROL_PLANE_API_KEY` available in the local environment.
- A tunnel id created in the OpenAI Platform tunnel settings.
- ChatGPT account/workspace with connector or Apps SDK developer access.

Do not write API keys or tunnel secrets into repo files. Keep credentials in the environment or a secure credential store.

## Start Local Services

From the project root:

```powershell
python integration\scripts\api_server.py --host 127.0.0.1 --port 8000
```

From the app directory:

```powershell
cd integration\apps\personal_data_chatgpt
npm start
```

Verify:

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8789/health
```

## Create A Separate Tunnel Profile

Do not modify the existing `codexpro` profile. Create a dedicated profile:

```powershell
cd C:\Users\li\Desktop\tunnel-client

.\tunnel-client.exe init `
  --profile personal-data-app `
  --tunnel-id <tunnel_id> `
  --mcp-server-url http://127.0.0.1:8789/mcp `
  --health-listen-addr 127.0.0.1:8081
```

Check the generated file before running:

```powershell
Get-Content "$env:APPDATA\tunnel-client\personal-data-app.yaml"
```

It should reference:

- `api_key: "env:CONTROL_PLANE_API_KEY"`
- `listen_addr: "127.0.0.1:8081"`
- `url: "http://127.0.0.1:8789/mcp"`

## Validate And Run The Tunnel

```powershell
cd C:\Users\li\Desktop\tunnel-client

.\tunnel-client.exe doctor --profile personal-data-app --explain
.\tunnel-client.exe run --profile personal-data-app
```

Expected local checks:

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8081/healthz
curl.exe --noproxy "*" http://127.0.0.1:8081/ui
```

## ChatGPT Connector Setup

In ChatGPT:

1. Open connector / app developer settings.
2. Create or edit a local MCP connector.
3. Choose the tunnel connection option.
4. Select or paste the tunnel id used in `personal-data-app`.
5. Refresh the connector after tool descriptor or widget resource changes.

Manual UAT prompts:

- `打开我的长期记忆图谱，显示 LLM 判断边。`
- `查看 Codex 相关的记忆和 2 跳邻居。`
- `列出需要人工审查的长期记忆关系。`
- `用我的历史数据搜索最近关于 MCP 或 Apps SDK 的记录。`

## Local MCP Probe

Without ChatGPT, verify the app server directly:

```powershell
$body = @{jsonrpc='2.0'; id=1; method='tools/list'; params=@{}} | ConvertTo-Json -Depth 8
Invoke-RestMethod -Uri 'http://127.0.0.1:8789/mcp' -Method Post -ContentType 'application/json' -Body $body -NoProxy
```

Graph tool call:

```powershell
$body = @{
  jsonrpc='2.0'
  id=2
  method='tools/call'
  params=@{
    name='show_memory_graph'
    arguments=@{include_llm=$true; limit=200}
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Uri 'http://127.0.0.1:8789/mcp' -Method Post -ContentType 'application/json' -Body $body -NoProxy
```

## Safety Boundary

- The current app exposes read-only tools only.
- It does not write to `memory_items`, `memory_links`, or `memory_relations`.
- It does not expose the REST API publicly.
- It should not be run with raw unsafe HTTP logging enabled.
