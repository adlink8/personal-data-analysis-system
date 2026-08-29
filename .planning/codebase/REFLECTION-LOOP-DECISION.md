<!-- 决策备忘：反思闭环处置 | 2026-08-29 | 状态：待用户拍板 -->
# 反思闭环（Reflection Loop）处置决策备忘

**结论先行：推荐选项 A（接上启动点），但分两步走——先验证生产者能产出 committed delta，再接 dispatcher 启动点。本备忘不改动任何代码，等待用户拍板。**

## 1. 现状核实（2026-08-29，全部基于源码与只读查询）

三段链路均已建成，但从未在生产流通过一次：

| 环节 | 实现 | 状态 |
|------|------|------|
| 生产者 | `src/personal_knowledge/application/sync.py:109,203`（`publish_conversation_delta_committed`，`pk sync conversations` 提交后调用）→ `POST :8790/internal/v1/conversation-deltas`（内核 internal capability 门禁） | 代码已接线；**journal 实测 0 条 delta**（见下） |
| 账本 | 内核 `events/journal.mjs`（append-only SQLite，`var/db/pi_kernel_events.sqlite`） | 在役；实测 2050 事件、`conversation.delta.committed` = **0**、consumer checkpoint = **0** |
| 消费者 | `apps/personal_intelligence_kernel/src/reflection/conversation-delta-dispatcher.mjs`（98 行，durable replay + 命名 checkpoint `conversation-reflection-v1`，fail-closed） | **已建成，无生产启动点**——仅 `test/conversation-delta-reflection.test.mjs` 与 `apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs`（测试资产）引用；`ops/runtime/start-agent-stack.ps1` 仅管理 rest/mcp/pi-kernel/tunnel 四服务（:162），无 dispatcher 进程、无定时任务 |
| 下游 | 网关 `conversation.reflection.stage`（`pi_domain_gateway.py:68`）→ `harness_reflection.py`（:359 懒加载；metadata-only 台账 `var/db/conversation_reflection.sqlite`，未创建） | 已实现，等待触发 |

即：**断点在 kernel 侧消费端没有启动器**；同时生产端也从未实际发过一条 delta（两端均为"建成未通电"）。

## 2. 选项 A：接上启动点（推荐）

**需要什么**
1. 消费入口：`runKernelServerCli`（server.mjs）加一个受 env/CLI 开关控制的周期 dispatcher tick（如 `PI_REFLECTION_DISPATCH_INTERVAL`），或独立 runner 注册为 start-agent-stack 第 5 服务。二选一，前者改动最小。
2. stage seam 绑定真实网关：`kernel-host.mjs:1067-1077` 的 bridge allowlist 需追加 `conversation.reflection.stage`（目前 CONVERSATION_THREAD_OPERATIONS 五个 conversation.* 里没有它，直接调用会 `skill_tool_escalation`）；stage 回调补 binding 三元组（task_id 可用 `pi_reflection_<event_id>` 策略，idempotency_key 派生自 event_id，天然重放安全）。
3. 启动注册：`start-agent-stack.ps1` 无需改（若选 in-process tick）；健康检查可复用 `/health` 的 provider_calls 风格计数。
4. 前置第一步（关键）：先跑一次 `pk sync conversations` 对着在役内核，确认 journal 落下至少 1 条 committed delta——生产者从未被真实触发过，先证生产再接消费，避免接线后空转。

**影响面**
- 改动集中在内核 `server.mjs`/`kernel-host.mjs`（+ 约 30-50 行）与网关 allowlist 一行；不写 canonical 库（adapter 只写自己的 metadata-only 台账并经 guarded gateway 产 Candidate）。
- 失败语义已有保障：dispatcher fail-closed、cursor 不越过失败事件；adapter 精确重放 duplicate、分歧身份拒收。最坏情况是"没有 Candidate 产生"，不会污染数据。
- Candidate 产出后进入既有 `/ui/review` 评审台（在役），有人工闭环可接。

**建议时机**
- 若产品方向仍要"对话→反思→候选"的自动闭环：现在就做第一步（生产者冒烟验证，零代码），第二步（消费接线）在生产者验证通过后实施，预计一个小改动面。
- 若近期不需要反思候选：可以只在备忘里保留本方案，不接线——链路本身不会腐坏（纯代码 + 测试在位），唯一的维护成本是它继续作为"已知半孤儿"留在测绘文档里。

## 3. 选项 B：明确拆除

**删什么**
- `src/reflection/conversation-delta-dispatcher.mjs`（整个模块）与 `test/conversation-delta-reflection.test.mjs`。
- `apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` 中的 dispatcher import 与调用（:86,:998）——注意 desktop 处于"已实现、使用度未验证"状态，动它需连带跑 desktop 测试。
- 可一并拆除（若连生产通道也不留）：`/internal/v1/conversation-deltas` 分发分支与 `sync.py` 的 publish 函数；网关 `conversation.reflection.stage` 注册与 `harness_reflection.py`。

**保留什么（建议即使选 B 也保留）**
- 内核事件账本与其 append-only/幂等/checkpoint 机制（dispatcher 之外仍被 SSE replay、生命周期事件使用）。
- `/internal/v1/conversation-deltas` 生产端点（journal 作为持久事件日志本身有价值；保留成本为零——当前 0 流量）。

**代价**
- 报废 Plan 61-06/07 已验收的资产（dispatcher 的 durable replay 语义、adapter 的 fail-closed 反思键绑定都经过了红绿测试）；反思方向若重启，重建成本远高于保存。
- 测试套件少 1 个文件、desktop fixture 需回归。

## 4. 推荐

**推荐 A，分两步**：先做零代码的生产者冒烟（确认 delta 能落账本），再接 in-process 消费 tick。理由：
1. 全链路代码与测试已建成且 fail-closed，接线是"通电"而非"造轮子"，改动面小、可回滚（开关关闭即回到现状）。
2. 拆除（B）是单向门：报废已验收资产，且反思是个人知识系统的核心闭环方向之一，重启代价高。
3. 当前 0 流量意味着接错的暴露面也接近 0——风险最低的接线窗口就是现在。

**待用户拍板**：A / B / 暂缓（保持现状，仅保留本备忘与测绘文档中的半孤儿标记）。
