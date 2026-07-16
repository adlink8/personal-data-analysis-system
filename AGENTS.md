# 数据分析项目 - 工作区指令

> **完整 Agent 操作手册（全流程）:** [`docs/AGENTS.md`](docs/AGENTS.md)  
> **对话同步 runbook:** [`docs/runbooks/product-sync.md`](docs/runbooks/product-sync.md)  
> **KU 增量 runbook（只抽新增）:** [`docs/runbooks/ku-incremental.md`](docs/runbooks/ku-incremental.md)

默认中文；优先本地事实（代码 / 路径 / 端口），再下结论。

---

## 产品主流程（必读）

| 目的 | 命令 |
|------|------|
| 同步本地对话 → 项目 SSOT | `pk-sync conversations` / `pk-sync conversations --write` |
| KU 增量产品入口 | **`pk-ku`**（`inspect` / `prepare` / `extract` / `extract-gate` / `canonical` / `publish` / `vector` / `promote`） |
| KU 流程说明 | `pk-ku workflow` · **必读** [`docs/runbooks/ku-incremental.md`](docs/runbooks/ku-incremental.md) |
| 启动 REST + MCP + Tunnel | `apps/personal_data_chatgpt/scripts/启动服务.bat` 或 `start-services.ps1` |
| 检索 CLI | `rag-search …` |

**已退役（不要当产品路径）：** `rag-pipeline`（统合 1–12 步 / personal_events+memory 批处理）。  
调用会 exit 2 并提示改用 `pk-sync` / `pk-ku`。取证才用 `PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated`。

**知识 SSOT** = KU + active index，不是 memory 实验层。  
**KU 硬规则：** 日常只用 `pk-ku`；只抽 prepare 队列（默认 watermark 后新增）；**禁止**全量 inventory + `prod --start`。  
策略调整走 CLI flag，**不要为日常运行改代码**。  
若 `inspect` 有 delta 而 `prepare` 为 `no_op` → **停**，不要换全量路径。

---

## MCP 服务依赖

工作区 MCP `personal-data` → `http://127.0.0.1:8789/mcp`（**非常驻**，需手动起）。

| 服务 | 端口 | 进程 |
|------|------|------|
| REST API (rag-api) | 8000 | `personal_knowledge` API |
| GPT Apps MCP | 8789 | `node apps/personal_data_chatgpt/server.mjs` |
| Tunnel（接 ChatGPT） | 8081 | `tunnel-client.exe` |

### 启动

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File "apps\personal_data_chatgpt\scripts\start-services.ps1"
```

独立 PowerShell 状态窗**不要关**（关窗会停掉子进程）。

### 健康检查

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8789/health
curl.exe --noproxy "*" http://127.0.0.1:8081/healthz
```

### 失败排查

1. 端口是否 LISTEN  
2. 重跑启动脚本  
3. 看 `apps/personal_data_chatgpt/logs/{mcp-app,rest-api,tunnel,watchdog}.log`  
4. Tunnel 需代理 `http://127.0.0.1:7897`；REST/MCP 仅 localhost  

---

## 项目结构要点

| 路径 | 说明 |
|------|------|
| `src/personal_knowledge/` | 产品源码（core / application / evaluation / retrieval / services） |
| `apps/personal_data_chatgpt/` | ChatGPT MCP Apps |
| `data/` | 私有数据（勿提交内容） |
| `var/` | DB / runtime / reports |
| `docs/AGENTS.md` | **Agent 全流程手册** |
| `.planning/` | GSD roadmap |

路径 SSOT：`src/personal_knowledge/core/project_paths.py`（Phase 20 优先）。

对话 SSOT：`data/canonical/agent/structured/db/agent_conversations.sqlite`  
AgentsView live：**只读**，永不搬迁。

---

## Agent 硬约束（摘要）

1. 对话更新用 **`pk-sync`**，不用 `rag-pipeline`  
2. 不写 `~/.agentsview/sessions.db`  
3. 不把 memory / personal_events 当知识 SSOT  
4. 不提交 data/var 私有库与密钥  
5. 改动后做健康检查或相关测试  
6. 详见 [`docs/AGENTS.md`](docs/AGENTS.md) 第 7–8 节 checklist  
