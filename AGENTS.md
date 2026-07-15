# 数据分析项目 - 工作区指令

## MCP 服务依赖

本项目配置了工作区级 MCP server `personal-data`(见 `.zcode/config.json`),指向 `http://127.0.0.1:8789/mcp`。

**该 MCP server 不是常驻系统服务,需要手动启动。** 它由三个本地进程组成:

| 服务 | 端口 | 进程 |
|------|------|------|
| REST API (rag-api) | 8000 | python `personal_knowledge.cli.api` |
| GPT Apps MCP | 8789 | `node apps/personal_data_chatgpt/server.mjs` |
| Tunnel (可选,接 ChatGPT 用) | 8081 | `tunnel-client.exe` |

### 启动方式

双击 `apps/personal_data_chatgpt/scripts/启动服务.bat`,或:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "D:\ADLINK\数据分析\apps\personal_data_chatgpt\scripts\start-services.ps1"
```

启动后会有独立 PowerShell 窗口显示实时状态面板。MCP 工具调用前必须确认 8789 在监听。

### 如果 MCP 工具调用失败

1. 检查 8789 端口是否在监听(`Get-NetTCPConnection -LocalPort 8789`)
2. 若没起,运行"启动服务.bat"
3. 若起了但调用报错,查 `apps/personal_data_chatgpt/logs/{mcp-app,rest-api}.log`

### 网络要求

- Tunnel(8081)需要代理 `http://127.0.0.1:7897` 才能连 OpenAI 控制面
- REST/MCP 只走 localhost,不需要代理
- 脚本已自动给 tunnel 进程注入 `HTTPS_PROXY` 并排除 localhost

## 项目结构要点

- `src/personal_knowledge/` - 产品源码(domains, retrieval, services, evaluation)
- `apps/personal_data_chatgpt/` - ChatGPT MCP Apps 适配器(Node.js,HTTP MCP server)
- `data/` - 私有数据(raw / staging / canonical / imports)
- `var/` - DB, runtime, reports, logs, cache
- `.planning/` - 权威 GSD roadmap 和 phase artifacts

路径解析见 `src/personal_knowledge/core/project_paths.py`,优先 Phase 20 位置。
