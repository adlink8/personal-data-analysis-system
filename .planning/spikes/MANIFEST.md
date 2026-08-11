# Spike Manifest

## Idea

验证是否能把 Pi SDK 嵌入 `personal-data-analysis-system`，作为事件驱动的 Personal Intelligence Kernel：Pi 负责 Agent Loop、Session、Skill 与 Tool Calling；现有 Python 系统继续独占数据同步、Canonical Evidence、Knowledge Unit、任务幂等、水位、评测、promotion/rollback 和事实权威。

本工作源自 GitHub Issue #2。它是 vNext 的架构决策入口，不是当前 Roadmap Phase；在 Spike 得出 `proceed` 前，不修改 `.planning/ROADMAP.md` 游标、不修订 `PROJECT.md` 的 Agent Framework 边界、不添加生产依赖。

### Assistant UI Desktop

验证 Sketch 008 选择的 C 方案：在现有 Electron Main/Preload 和 named DesktopBridge 上，用 React + assistant-ui 组合 Codex 式对话主界面。AgentsView 历史、Tool/SQLite receipt 与 Candidate review 作为按需抽屉，不恢复浏览器 Cockpit，也不让 Renderer 获得任意网络、IPC、SQL、文件或数据库句柄。

## Requirements

- Pi 不得获得任意 SQL、任意文件、shell、进程或默认 coding tools。
- 无有效 Delta 时不得创建 AgentSession，模型调用数必须为 0。
- Python/person-data 继续拥有 SSOT、Delta、task idempotency、watermark、evaluation、promote 和 rollback。
- Pi Session 只保存运行轨迹，不是 Personal Fact、Artifact、Knowledge、Project State 或 Decision SSOT。
- Agent 只能创建 Candidate；不得推进 watermark、移动 active pointer、promote 或执行未确认的外部动作。
- 所有 Tool 必须版本化、scope-bounded、evidence-aware、可超时、可取消、可审计并返回 typed error。
- 第三方 Package 必须精确锁定版本或 commit、完成源码/License/权限审计，并默认 fail-closed。
- 第一阶段只允许单 Agent、官方核心包和自研 Domain Tools；社区包、MCP、Web access 与 subagents 不进入首个垂直切片。
- Legacy workflow 必须可通过 feature flag 回退，并保留 shadow/canary 对比窗口。
- Desktop Renderer 只消费 Main/Preload 投影后的 display-safe envelope；SQLite 读取仍是 Capability Registry 中的受控 Tool，不是独立旁路。
- assistant-ui 只负责 UI primitive 与外部状态适配，不成为 Conversation、Task、Session、Tool 或 Candidate 权威。
- 默认打开当前对话；历史、证据和审核不得变成永久仪表盘或被 AI 自动展开。

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|---|---|---|---|---|
| 001 | runtime-containment-and-package-baseline | standard | Pi 0.83.0 仅加载白名单 Domain Tools，且无 coding/ambient package 权限 | PARTIAL | pi, security, supply-chain |
| 002 | node-python-protocol-and-task-ledger | standard | Node/Python 间的 typed error、timeout、cancel、idempotency 与恢复一致 | VALIDATED | protocol, idempotency, cancellation |
| 003 | skill-selection-and-artifact-isolation | standard | 指定 Personal Skill 可稳定运行，Session 与 Candidate/SSOT 严格隔离 | VALIDATED | skills, artifacts, privacy |
| 004 | delta-triggered-vertical-slice | standard | Delta=0 零调用；Delta>0 单任务、可重放、失败不推进 authority | VALIDATED | delta, watermark, evaluation |
| 005 | streaming-control-and-baseline-comparison | comparison | SSE/WS、取消/steer/resume 可用，并可量化对比 legacy | PARTIAL | streaming, web, metrics |
| 006 | provider-auth-and-budget-fail-closed | standard | Provider 鉴权、配额、超时失败时不泄露凭据、不超预算且不改变 authority | PARTIAL | provider, auth, budget, fail-closed |
| 007 | concurrent-task-backpressure | standard | 多 Delta 并发时任务按稳定 key 合并、限流、可恢复且不产生重复 Candidate | PARTIAL | concurrency, backpressure, quotas |
| 008 | session-retention-and-privacy-expiry | standard | Session、日志与崩溃产物按保留策略过期，且不污染正式 SSOT | VALIDATED | privacy, retention, erasure |
| 009 | sdk-upgrade-and-requalification | standard | Pi SDK/协议/依赖变化可被检测、重新资格审查并安全回滚 | VALIDATED | upgrade, schema, supply-chain |
| 010 | assistant-ui-runtime-adapter | standard | assistant-ui ExternalStoreRuntime 可由现有 named DesktopBridge 驱动，且不暴露通用 transport/SQL | PARTIAL | desktop, assistant-ui, bridge, security |
| 011 | selected-c-desktop-composition | standard | Codex 式对话首屏、历史/证据抽屉、AI 提示入口与 Candidate 审核可组合成低启动成本桌面体验 | VALIDATED | desktop, react, ux, agentsview |

## Execution Order

`001 → 002 → 003 → 004 → 005`

本轮全部执行时扩展为：`001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009`。

Desktop UI 路径独立执行为：`010 → 011`。010 的 request/response 适配通过后可验证 011；正式实现 streaming/cancel 前仍须补齐 early task handle + named event subscription。

001 或 002 出现核心否决项时停止后续 Spike；003/004/005 可给出 `revise`，但不得跳过否决项直接创建正式里程碑。

## Work Packages

- `pi-embedded-personal-kernel/`：五个 Spike 的主计划、研究、验收与最终架构决议。
- `pi-package-qualification/`：依赖、兼容性、权限与供应链资格审查；作为 001 的强制子工作包。
- `pi-frontier-controls/`：006–009 的 Provider、并发、隐私留存与升级重资格实验。
- `assistant-ui-desktop/`：010–011 的 Runtime Adapter、选择 C 的 React 交互原型、供应链记录与真实浏览器验收。
