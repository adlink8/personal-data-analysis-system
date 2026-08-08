# Execution Plan — Pi Embedded Personal Intelligence Kernel

## Scope Fence

本计划只允许在 Spike 目录和隔离的测试数据库中实验。不得修改 active pointer、正式 watermark、Canonical/KU authority、当前 Serving Snapshot 或生产 Cockpit 写入面；不得安装社区 Pi Package；不得创建正式 vNext Phase。

## Shared Prototype Layout

执行时建议建立：

```text
prototype/
├── agent-runtime/
│   ├── package.json
│   ├── package-lock.json
│   └── src/
│       ├── runtime.ts
│       ├── resource-loader.ts
│       ├── event-stream.ts
│       └── tools/
├── python-domain/
│   ├── app.py
│   ├── contracts.py
│   └── task_ledger.py
├── skills/maintain-conversation-delta/
├── fixtures/
└── ui/
```

所有运行状态写入 Spike 专用临时目录；测试结束后通过 feature flag 回到 legacy，不触碰正式数据库。

---

## Spike 001 — Runtime Containment and Package Baseline

**Given** Pi 0.83.0 被嵌入 Node runtime，**when** Session 启动并请求执行 Personal 任务，**then** 最终 Tool/Skill/Extension/Package 集合只能来自显式白名单，coding tools 和 ambient discovery 均不可达。

### Steps

1. 在 Spike prototype 中精确锁定：
   - `@earendil-works/pi-coding-agent@0.83.0`
   - `@earendil-works/pi-ai@0.83.0`
   - `@earendil-works/pi-storage-sqlite-node@0.83.0`
2. 记录 lockfile integrity、Node engine、License、transitive dependency 和 install script 清单。
3. 实现 custom `ResourceLoader`，关闭默认项目/全局 extensions、skills、prompts、settings、credentials 和 context discovery。
4. 使用 `noTools: "builtin"`，只注册两个无敏感数据的 stub Domain Tools。
5. 启动后读取最终 runtime state，生成 `loaded_tools/resources/packages` metadata-only 快照。
6. 进行负向测试：诱导调用 `bash/read/write/edit/ls/find/grep`、加载全局 Skill、访问父目录、安装 package、发起未允许网络请求。
7. 注入恶意 Extension/Skill fixture，证明不会被发现或执行。

### Must-Haves

- 最终工具集精确等于 allowlist；缺少或多出任何 Tool 都失败。
- Runtime 不读取用户全局 Pi/Codex/Claude 配置、credentials 或 Skills。
- 禁止动态安装、`latest`、模糊 semver 和 package auto-update。
- 未声明网络、文件、进程访问默认拒绝并记录 safe audit event。

### Test, Fix, and Confirm

- 单元：resource loader 输入相同则加载清单稳定。
- 契约：`session.agent.state.tools` 与 registry checksum 一致。
- 故障注入：ambient `.pi`、`.agents/skills`、恶意 extension、未知 package source。
- 隔离观察：进程/文件/网络访问审计中无未声明副作用。
- 连续三次冷启动结果一致后方可判定 `VALIDATED`。

### Rollback

删除 Spike prototype 的 Node 依赖和测试存储即可；生产代码和现有 workflow 不发生变化。

### Data and Privacy Impact

仅使用 synthetic fixture，不读取真实个人正文或生产凭据。

### Tool/Skill Contract Changes

定义未来 `pi-tool-registry-v1` 和 `pi-resource-manifest-v1` 草案；不发布为生产契约。

### Observability Evidence

`runtime_boot.jsonl`、resource/tool registry checksum、拒绝事件计数、文件/网络访问摘要。

### Kill Gate

若无法关闭 coding tools、ambient discovery、动态安装或未声明系统访问，则总体决议不得为 `proceed`。

---

## Spike 002 — Node/Python Protocol and Agent Task Ledger

**Given** Python Domain 继续拥有任务和数据权威，**when** Pi 调用 Domain Tool、发生超时/取消/重启/重复提交，**then** task state、Tool result 与 Candidate side effect 保持一致且可恢复。

### Steps

1. 定义 `personal_domain_tool_request_v1`：`task_id`、`tool_call_id`、`idempotency_key`、`schema_version`、purpose、scope、sensitivity、deadline、args checksum。
2. 定义 `personal_domain_tool_result_v1`：status、typed error、evidence refs、result checksum、truncated、retryability、terminal state。
3. 以独立 SQLite 建立 append-only Agent Task Ledger：task、attempt、tool_call、transition、artifact_ref、audit_event。
4. Python 提供最小 loopback Domain API；Node 只通过该 API 调用，不访问 SQLite/Chroma。
5. 实现 deadline/cancel propagation：Node abort → HTTP cancellation → Python cooperative cancellation → terminal state。
6. 实现稳定 task key：`source + version + from_watermark + to_watermark + skill + policy_version`。
7. 覆盖重复请求、并发抢占、超时后迟到结果、Node 崩溃、Python 崩溃、服务重启和 unknown outcome。

### State Machine

```text
created → claimed → running → cancelling → cancelled
                         ├── succeeded
                         ├── failed_retryable → queued
                         ├── failed_terminal
                         └── outcome_unknown → manual_reconcile
```

同一 task key 同时最多一个 active attempt；`outcome_unknown` 不得自动重放写操作。

### Must-Haves

- Python Ledger 是任务权威；Pi Session 状态不能覆盖 task terminal state。
- 重复 idempotency key 返回 exact replay 或 typed conflict。
- timeout/cancel 后不得出现未登记 Candidate。
- 任何失败均不推进 watermark、promotion 或 active index。

### Test, Fix, and Confirm

- 契约测试：Node/Python schema、checksum 和 typed error 一致。
- 并发测试：两个 worker 竞争同一 task key，只能一个 claim 成功。
- 故障注入：Tool 前/中/后崩溃、网络断开、迟到响应、进程重启。
- 恢复测试：重启后 terminal/queued/outcome_unknown 分类稳定。
- DB 指纹：authority 表、active pointer、watermark 在全部失败用例前后不变。

### Rollback

关闭 `PI_KERNEL_ENABLED`，停止 Node prototype，保留测试 Ledger 供审计；legacy 不依赖新 Ledger。

### Data and Privacy Impact

Ledger 只存 hash、opaque ID、状态、计数和 safe error；不存 Tool 原始正文、provider body 或 secret。

### Tool/Skill Contract Changes

形成 Node/Python transport、Task Ledger 和 cancellation contract 草案。

### Observability Evidence

任务 transition chain、attempt durations、cancel latency、replay count、unknown outcome count、authority fingerprint。

### Kill Gate

若 cancel、idempotency、unknown outcome 或恢复无法 fail-closed，则不得进入 003。

---

## Spike 003 — Skill Selection and Artifact Isolation

**Given** 一个确定性 Delta Manifest，**when** Pi 执行 `maintain-conversation-delta`，**then** 它稳定加载正确 Skill、只能调用 allowed tools，并生成与 Session 隔离的 evidence-bound Candidate。

### Steps

1. 建立最小 Skill：`maintain-conversation-delta`，包含 `SKILL.md`、`skill.yaml`、input/output schema、examples、tests。
2. Skill manifest 声明 allowed tools、max model/tool calls、domain、sensitivity、artifact type、approval/evaluation policy。
3. 比较两种路由：显式 deterministic skill binding 与模型自动 Skill selection；自动选择仅作为测量项，不作为安全边界。
4. 实现只读工具：`inspect_personal_delta`、`search_personal_knowledge`、`get_conversation_evidence`、`get_existing_knowledge`。
5. 实现唯一写入工具 `create_candidate_artifact`，其服务端只允许 staging Candidate schema。
6. Candidate 强制包含 `task_id`、`source_cutoff`、`evidence_refs`、policy/schema version、payload checksum 和 uncertainty。
7. 对 Pi Session store、Task Ledger、Candidate store 做数据库与 schema 级隔离。
8. 注入 prompt-injection、敏感正文、缺证据、跨域 Tool、超预算 Tool call 和 schema mismatch。

### Must-Haves

- 首个 P0 流程使用 deterministic skill binding；模型不能提升自身权限或切换到未授权 Skill。
- allowed tools 由 Runtime 与服务端双重校验。
- Session 只保留摘要/opaque refs；正式 Candidate 存于 Python staging authority。
- 缺 `evidence_refs/source_cutoff/task_id` 的输出必须被 deterministic gate 拒绝。

### Test, Fix, and Confirm

- Skill 路由矩阵：正例、近似任务、冲突 Skill、恶意 Skill、未注册 Skill。
- Tool budget：达到上限后停止并返回明确 terminal state。
- Privacy：Session、日志、SSE payload 中无 raw secret/provider body/未裁剪正文。
- Isolation：删除 Session DB 不影响 Candidate；删除 Candidate test DB 不改变 Session audit。
- 重放：相同 Candidate checksum 不重复插入。

### Rollback

移除 prototype Skill 和 Candidate 测试库；关闭 feature flag 后 legacy 提取路径不变。

### Data and Privacy Impact

先使用 synthetic conversation；真实授权 cohort 只在 004 后半执行，且日志 metadata-only。

### Tool/Skill Contract Changes

输出 `personal-skill-manifest-v1`、`knowledge-candidate-v1` 与 allowed-tools policy 草案。

### Observability Evidence

Skill selected/expected、Tool sequence、budget usage、gate rejection reasons、Session/Candidate storage fingerprints。

---

## Spike 004 — Delta-triggered Vertical Slice

**Given** canonical conversation 的确定性 Delta，**when** watcher 和 trigger policy 运行，**then** 无 Delta 零模型调用，有 Delta 只生成一个可评测 Candidate，并在失败时保持所有 authority 不变。

### Steps

1. 复用 `eligibility.py` 和现有 committed watermark 口径，生成 metadata-only Delta Manifest。
2. 实现 deterministic trigger policy：empty、low-value、already-processed、budget-blocked 均在模型前停止。
3. 场景 A：Delta=0，不创建 task/session，LLM calls=0。
4. 场景 B：单个 synthetic valuable Delta，创建唯一 task，执行 Skill 和至少两个 Domain Tool Call，生成 Candidate。
5. 调用现有 schema/evidence/privacy/dedup/time evaluation adapter，输出 `accepted | rejected | needs_review`，但不 promote。
6. 场景 C：在 Agent、Tool、model、evaluation 各阶段注入失败，验证 task terminal 和 no-advance。
7. 同一 Delta 重跑、并发执行和服务重启后重放，验证 Candidate 不重复。
8. 在用户授权后，用小规模真实只读 Delta cohort 复验；报告只存 opaque refs 与统计。

### Must-Haves

- Delta=0：task=0、session=0、model calls=0。
- Delta>0：同一 task key 最多一个逻辑 Candidate。
- Candidate 经过现有 deterministic evaluation；Pi 不决定 promotion。
- Spike 不推进正式 watermark；仅在测试 ledger 中模拟 success policy。
- 所有失败场景 authority fingerprint 完全一致。

### Test, Fix, and Confirm

- A/B/C/D 四类端到端场景。
- 重复/并发/崩溃恢复至少各 3 次。
- 对比 legacy 的 model calls、token、latency、candidate count、duplicate rate、evidence pass rate。
- 若 Pi 质量较差，区分 Skill/Tool/context/model/SDK 根因，不直接调宽治理门。

### Rollback

feature flag 切回 legacy；丢弃测试 Delta、Task、Session 与 Candidate store；正式 watermark 不需回滚。

### Data and Privacy Impact

真实数据仅限授权、只读、最小 cohort；不得在报告中保存正文、完整 URL、HAR、provider payload 或 secret。

### Tool/Skill Contract Changes

验证 `delta-manifest-v1`、trigger policy、Candidate evaluation bridge 和 feature flag contract。

### Observability Evidence

每个场景记录 task/session/model/tool/candidate/eval 计数、时延、token、reason code、fingerprint 和 replay 标志。

---

## Spike 005 — Streaming Control and Baseline Comparison

**Given** 一个运行中的 Agent Task，**when** Cockpit 订阅事件并执行 cancel/steer/resume，**then** UI 显示安全、可恢复、顺序一致的状态，且能量化 Pi 与 legacy 的成本/质量差异。

### Comparison Variants

| Variant | Use | Strength | Risk |
|---|---|---|---|
| 005a SSE | server → browser 流式事件；控制命令走普通 POST | 简单、适合单向事件和现有 Python HTTP 服务 | 双向控制需额外请求与 event cursor |
| 005b WebSocket | 同连接双向 stream/control | steer/cancel 交互自然 | 重连、鉴权、顺序和代理复杂度更高 |

先实现 005a；只有 SSE 无法满足恢复/steer 延迟时才构建 005b。

### Steps

1. 定义 `agent_task_event_v1`：sequence、event_id、task_id、type、safe summary、status、timestamp、usage、artifact ref。
2. 实现事件 cursor、Last-Event-ID/replay 和 bounded retention。
3. 映射 Pi event stream；Session replacement 后重新订阅并验证无丢失/重复。
4. Cockpit 最小页面显示步骤、Tool 摘要、Candidate preview、成本、失败原因与恢复操作。
5. 实现 cancel、retry、resume、steer；所有控制命令携带 task/version/args checksum。
6. 阻断网络、刷新页面、重启服务、重复订阅、慢客户端和乱序事件故障注入。
7. 运行 legacy vs Pi shadow comparison，生成 metadata-only report。

### Must-Haves

- UI 不显示 raw Tool input/result、secret、provider body 或完整敏感正文。
- 断线重连不改变 task authority，不重复创建 Candidate。
- cancel 反馈与 Ledger terminal state 一致；UI 不能只做视觉取消。
- 高风险写入仍走现有 exact preview + explicit confirm；本 Spike 不新增该能力。
- 比较报告同时呈现成本、质量、可靠性和复杂度，不只比较 token。

### Test, Fix, and Confirm

- 事件序列完整性、重放、断线、乱序、重复、慢消费者测试。
- 键盘、焦点、Escape、reduced motion、320/768/1024/1440 与 200% zoom。
- privacy/console/network/storage 审计。
- 用户可见 UAT：运行、取消、刷新恢复、Candidate 下钻和故障恢复。

### Rollback

关闭 Agent Workspace route 和 `PI_KERNEL_ENABLED`；保留现有 Cockpit 页面与 legacy workflow。

### Data and Privacy Impact

浏览器只接收 Projection/SSE 安全摘要；不持久化 raw personal data 或 provider credentials。

### Tool/Skill Contract Changes

形成 event stream、control command、Task Projection 和 UAT contract 草案。

### Observability Evidence

event lag、reconnect count、duplicate/gap count、cancel latency、resume success、model/tool/token/cost、candidate quality 与 privacy violations。

---

## Final Decision Procedure

1. 汇总五项 verdict 与 kill gate。
2. 对比 legacy 与 Pi 的 calls/delta、token/accepted candidate、duplicate、evidence pass、task reliability、watermark lag 和维护复杂度。
3. 在 `DECISION.md` 写入：
   - `proceed`：全部 kill gate 通过，创建新里程碑候选；
   - `revise`：核心可行但需限定方案，列出必须补的 Spike；
   - `reject`：保留 legacy，Pi 降级为外部 MCP/局部 UI Agent 候选。
4. 只有 `proceed` 后才允许：`gsd-new-milestone`、AI-SPEC、正式 requirements/roadmap/phase artifacts、`PROJECT.md` 边界修订。

