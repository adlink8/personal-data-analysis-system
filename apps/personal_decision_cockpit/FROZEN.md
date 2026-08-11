# Personal Decision Cockpit —— 冻结说明（FROZEN 2026-08-11）

> **冻结状态（2026-08-11）：** 本应用（web 前端）已冻结。产品方向调整为 **wiki 作为统合层**，
> web 不再是核心入口。**代码完整保留备查，不删除**（`src/`、`dist/` 构建产物与 node 工具链
> 均保留）；仅**入口已停用**。如需恢复，见下方"如何恢复"。

## 冻结范围

| 类别 | 状态 | 说明 |
|------|------|------|
| 前端源码 | 保留 | `src/` 全部代码、`package.json`、Vite 配置等不删不改 |
| 构建产物 | 保留 | `dist/` 不删除 |
| `/app[/<path>]` 静态托管 | **已停用** | REST 进程（127.0.0.1:8000）不再托管 cockpit 前端（SPA） |
| Cockpit 专用 REST 接口 | **已停用** | 下方 10 条 `/ui/*` 只读投影路由一律返回 404 |
| wiki REST 接口 | 保持可用 | `/ui/topics`、`/ui/topic`、`/ui/topic/backlinks`、`/ui/topic/resolve` 不受影响 |
| 启动脚本 | 无改动点 | `apps/personal_data_chatgpt/scripts/start-services.ps1` 为薄包装，不含 cockpit 托管逻辑（见下） |

## 已停用的入口

1. **`GET /app[/<path>]`** —— Cockpit 前端静态托管（SPA fallback）
2. **`GET /ui/overview`** —— Cockpit 总览投影
3. **`GET /ui/system/status`** —— Cockpit 系统状态
4. **`GET /ui/personal-state`** —— Cockpit 个人状态投影
5. **`GET /ui/external/delta`** —— Cockpit 外部数据增量投影
6. **`GET /ui/decision-queue`** —— Cockpit 决策队列投影
7. **`GET /ui/decision/workspace`** —— Cockpit 决策工作区投影
8. **`GET /ui/actions/recent`** —— Cockpit 近期行动投影
9. **`GET /ui/proactive/summary`** —— Cockpit 主动情报摘要
10. **`GET /ui/calibration/overview`** —— Cockpit 校准总览
11. **`GET /ui/evidence/resolve`** —— Cockpit 只读证据解析

停用方式：`src/personal_knowledge/services/api_server.py` 的 `do_GET` 中，将 `/app` 静态托管段与
上述 10 条路由的注册分发**整体注释**（带 `FROZEN 2026-08-11` 说明）。请求现在落入统一 404
"未知路径"分支；相关处理函数、投影服务与辅助函数（`meta_handlers.serve_cockpit_static`、
`CockpitProjectionService`、`ui_rest_contract` 等）均原样保留。

## 保持可用（不受冻结影响）

- wiki 4 条：`GET /ui/topics`、`GET /ui/topic`、`GET /ui/topic/backlinks`、`GET /ui/topic/resolve`
- 999.5 单人评审台：`GET /ui/review`、`POST /ui/review/labels`（独立内部工具，非 cockpit 前端）
- 其余全部 API：`/health`、`/stats`、`/knowledge`、`/memory`、`/search/*`、`/agent/*`、
  `/decision/*`、`/proactive/*`、`/intelligence/*`、`/data/*`、`/profile`、`/event/*`、`/api/pi/*` 等

## 启动脚本说明

`apps/personal_data_chatgpt/scripts/start-services.ps1` 是薄包装（代理到
`ops/runtime/start-agent-stack.ps1`），其中**没有任何 cockpit 托管段**（无 serve dist、无 `/app`、
无 npm 构建），只启动 REST + MCP + Tunnel + pi-kernel 核心服务。因此该脚本无需改动；
cockpit 的唯一托管入口就是 REST 进程内的 `/app` 路由（已停用）。

## 测试处理

因停用而必然失败的 HTTP 契约测试已标记 `pytest.mark.skip`（reason 含 `FROZEN 2026-08-11`），
**测试未删除**：

- `tests/contract/test_ui_projection_state_external.py::test_ui_routes_serve_new_endpoints`
- `tests/contract/test_ui_projection_actions_proactive.py::test_ui_routes_serve_phase39_endpoints`
- `tests/contract/test_ui_projection_evidence.py::test_ui_route_serves_evidence_resolve_and_rejects_post`
- `tests/contract/test_cockpit_transport_security.py::test_missing_cockpit_asset_returns_safe_error_without_path_echo`
- `tests/contract/test_cockpit_transport_security.py::test_cockpit_not_built_returns_safe_error`

服务层单测与 wiki 测试（`tests/contract/test_topic_projection.py`）不受影响，保持通过。

## 如何恢复（取消冻结）

1. 打开 `src/personal_knowledge/services/api_server.py`
2. 在 `do_GET` 中找到两段 `FROZEN 2026-08-11` 注释：
   - 取消注释 `/app[/<path>]` 静态托管段（`meta_handlers.serve_cockpit_static` 调用）
   - 取消注释 cockpit 10 条 `/ui/*` 路由分发段（`ui_handlers.handle` 调用）
3. 删除/还原对应测试上的 `pytest.mark.skip` 标记
4. 重启 REST 服务，访问 `http://127.0.0.1:8000/app/` 验证
