# 数据分析项目 - 工作区指令

> **完整 Agent 操作手册:** [`docs/AGENTS.md`](docs/AGENTS.md)  
> **对话同步:** [`docs/runbooks/product-sync.md`](docs/runbooks/product-sync.md)  
> **KU 增量:** [`docs/runbooks/ku-incremental.md`](docs/runbooks/ku-incremental.md)  
> **产品就绪分:** [`.planning/PRODUCT-READINESS.md`](.planning/PRODUCT-READINESS.md)  
> **当前状态:** [`.planning/STATE.md`](.planning/STATE.md)

默认中文；优先本地事实（代码 / 路径 / 端口），再下结论。

---

## 产品主流程（必读）

| 目的 | 命令 |
|------|------|
| 同步本地对话 → 项目 SSOT | `pk-sync conversations` / `pk-sync conversations --write` |
| KU 全链路 | **`pk-ku`**（`inspect` → `prepare` → `extract` → … → `canary` → `promote` → `watermark`） |
| 流程说明 / 体检 | `pk-ku workflow` · `pk-ku doctor` |
| 成长线 / 生命周期（不删行） | `pk-ku history --subject …` · `pk-ku reconcile --dry-run` |
| 启动 REST + MCP + Tunnel | `apps/personal_data_chatgpt/scripts/启动服务.bat` 或 `start-services.ps1` |
| 检索 CLI | `rag-search …` |

**已退役：** `rag-pipeline`（exit 2 → 改用 `pk-sync` / `pk-ku`）。取证：`PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated`。

**知识 SSOT** = KU 表 + **active** 向量集合（`var/db/knowledge_index_active.txt`），不是 memory 实验层。

**KU 硬规则：**

1. 日常只用 **`pk-ku`**；策略用 flag，**不要为跑数改代码**  
2. 默认只抽 watermark 后 **new**；禁止日常全量 inventory + `prod --start`  
3. `inspect` 有 delta 而 `prepare` 为 `no_op` → **停**  
4. promote **默认要 eval**；全量 `--start` 需 `PK_KU_ALLOW_FULL_INVENTORY_START=1`  
5. 成长线：**标 lifecycle / supersede，不硬删** knowledge 行  
6. 新代码 import **`application.*` / `evaluation.*`**，不要写 `domains.*`（facade 仅遗留兼容）

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
pk-ku doctor --skip-ports
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
| `src/personal_knowledge/application/` | **canonical** 构建/生命周期/`ku.py`/`sync.py` |
| `src/personal_knowledge/evaluation/` | **canonical** 评测 |
| `src/personal_knowledge/domains/` | 可选 re-export facade（application 已 0 引用） |
| `apps/personal_data_chatgpt/` | ChatGPT MCP Apps |
| `data/` | 私有数据（勿提交内容） |
| `var/` | DB / runtime / reports / active pointer |
| `docs/AGENTS.md` | **Agent 全流程手册** |
| `.planning/` | GSD roadmap（当前 Phase 22 已落地代码） |

路径 SSOT：`src/personal_knowledge/core/project_paths.py`。

对话 SSOT：`data/canonical/agent/structured/db/agent_conversations.sqlite`  
AgentsView live：**只读**，永不搬迁。

---

## Agent 硬约束（摘要）

1. 对话更新用 **`pk-sync`**，不用 `rag-pipeline`  
2. 不写 `~/.agentsview/sessions.db`  
3. 不把 memory / personal_events 当知识 SSOT  
4. 不提交 data/var 私有库与密钥  
5. 改动后：`pk-ku doctor` 或相关 pytest  
6. 详见 [`docs/AGENTS.md`](docs/AGENTS.md)  
