# Engineering Structure and Testing Contract

本契约适用于新增产品行为、修复 Bug、修改公共接口、状态机、数据转换或安全策略。权威机器策略为：

- `governance/policies/architecture.yaml` 的 `module_design`
- `governance/policies/testing.yaml`

## 1. 先声明公开 seam

实现前记录以下四项：

1. **公开接口**：调用者实际使用的函数、命令、路由、IPC、事件或存储契约。
2. **可观察行为**：给定输入后，调用者能看到的输出、状态或错误。
3. **不变量**：权限、隐私、幂等、权威数据和失败语义必须保持什么。
4. **定向命令**：能够在 60 秒左右返回结果的最小验证命令；较慢套件按 seam 拆分。

测试只通过已确认的公开 seam 观察行为。私有函数、内部调用顺序和内部调用次数不是产品契约。

Phase 61 已确认的主要 seam 是：Renderer → Preload 命名方法、Preload/Main → 固定本地路由、Kernel conversation turn、Skill lease → Capability broker、Python Domain Gateway → 权威模块、Event Journal、Candidate review、Projection 读取/注入，以及只读 SQLite descriptor tool。

SQLite 数据访问必须保持两条不同的 seam：

```text
AI 查询：Pi Agent loop -> Skill lease -> Capability Broker
        -> evidence.sqlite_query Tool -> Python RO adapter -> approved SQLite

固定桌面读取：Renderer -> named DesktopBridge -> fixed read-model provider
            -> metadata-only projection
```

前者属于 Tool 层，必须产生受治理的 Tool receipt；后者只服务最近会话、服务健康、
freshness 等预定义桌面状态，不能接受 SQL、数据库路径、任意查询描述符或数据库句柄。
Renderer、Preload 和 Electron Main 均不得直接打开权威 SQLite。所谓 AI “直接访问底层
SQLite”只表示证据查询无需绕行通用业务 Read Model，不表示绕过 Skill/Tool 治理。

## 2. Red → Green → 定向回归

对行为变更、Bug、公共契约、数据转换和安全策略使用一个纵向切片循环：

1. **Red**：先运行定向测试，确认它因为目标行为缺失或错误而失败。
2. **Green**：只实现让该测试通过的最小生产改动。
3. **定向回归**：重跑同一测试，再运行受影响 seam 的相关套件与 `git diff --check`。
4. 进入下一个行为切片；重构留到行为已稳定并通过审查之后。

Bug 修复必须保留能在修复前复现问题的回归测试。纯文档、注释、样式或非行为配置可以不先 Red，但必须执行对应构建、渲染、Lint 或冒烟命令。

## 3. 测试层次

| 层次 | 使用范围 |
|---|---|
| Unit | 纯规则、解析、转换和确定性状态归约 |
| Contract | Schema、Receipt、状态、错误和 Provider/Consumer 兼容性 |
| Integration | 真实本地适配器、临时 SQLite、Event Journal 和固定路由 |
| E2E/UAT | 每个关键能力至少一条完整用户纵向路径 |

公共接口变更同时验证 Provider、Consumer 和一个真实适配器。不要用“每个函数一个单元测试”替代 seam 测试。

## 4. Mock 边界

Mock 只放在真实系统边界：外部 API、模型 Provider、时钟、随机性和必要的文件系统边界。项目内部模块使用真实实现，数据库优先使用临时 SQLite，模型优先使用确定性 replay provider 或本地 stand-in。

以下测试无效：Mock 内部协作者后断言调用次数；直接测试私有方法；测试 Helper 重写生产算法；期望值按生产逻辑重新计算。

## 5. 必测反向场景

涉及相应能力时，至少验证：

- 无授权、无 Lease 或越权工具调用被拒绝。
- 只读 SQLite Tool 拒绝任意 SQL、多语句、`ATTACH`、危险 `PRAGMA`、扩展加载和越界结果；桌面 Read Model 拒绝任何动态查询输入。
- stale/unknown 不得显示为 current。
- cancel 和 `outcome_unknown` 不得呈现为成功。
- draft/ignored Candidate 不得进入 Projection；重放不得产生重复副作用。
- 权威数据库和 active pointer 的指纹在只读、拒绝和失败路径保持不变。
- 日志、Receipt、UI Telemetry 和测试证据不含正文、凭据、原始 SQL 或物理 Schema。
- Renderer 保持 Node 隔离、固定 IPC allowlist 和受限导航。

Phase 61 的完整反向矩阵由 `.planning/phases/PDA-61-conversation-first-desktop-harness-and-evidence-bound-reflec/61-VALIDATION.md` 维护，本文件不复制阶段命令。

## 6. 模块内聚与拆分

一个模块只有一个主要变化原因，并通过一个主要公开 seam 提供能力；同一责任下的紧密 Helper 可以共存。出现以下任一情况时，在继续添加行为前拆分：

- 出现第二个彼此独立的变化原因。
- 出现第二套状态机或生命周期。
- 出现第二个数据权威或权限所有者。
- 同一文件同时承担 UI、传输、领域规则和持久化。
- 为隔离一个公开行为必须 Mock 项目内部实现。

对新增或修改文件使用评审阈值：生产文件 500 行、函数 80 行、测试文件 700 行。阈值不是正确性的证明；超过后必须先拆分，或在计划/审查中记录无法拆分的具体理由和后续拆分条件。

## 7. 完成门槛

交付前必须满足：

- 行为修改有测试，或属于已声明例外并有替代验证。
- Bug 有回归测试；公共接口有 Provider、Consumer 和真实适配器验证。
- 新增 `skip`/`xfail` 记录原因、追踪项和删除条件；重试不掩盖 flaky failure。
- 定向测试、相关回归和 `git diff --check` 通过。
- 关键权限与安全策略覆盖所有声明的 allow/deny 分支；变更行覆盖率目标至少 85%，总体覆盖率不下降。
- 测试使用最小、脱敏、确定性 Fixture，并按需求、决策和反向场景建立映射。
