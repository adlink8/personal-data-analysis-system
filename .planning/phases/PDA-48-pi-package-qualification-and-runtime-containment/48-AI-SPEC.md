# AI-SPEC — Phase 48: Pi Package Qualification and Runtime Containment

> v2.0 Pi Kernel 的框架与安全资格契约。Phase 48 只决定生产候选能否进入 Phase 49，不激活真实 Agent 工作流。

## 1. System Classification

**System Type:** Hybrid event-driven personal intelligence Agent runtime

**Description:** Pi SDK 将成为本地个人决策智能系统的主 AI 控制面；Python Domain API 继续是事实、证据和生命周期权威。本阶段验证 SDK package 和资源加载边界是否满足高隐私、可回滚、fail-closed 的生产前提。

**Critical Failure Modes:**

1. Pi 自动发现 coding tools、宿主 `.pi`、skills、auth、settings 或 extension。
2. transitive package 漏洞或 install script 获得未审计 filesystem/process/network 能力。
3. Agent 绕过 Python Domain API 修改 authority、watermark、promotion 或 active pointer。
4. Session、日志或审计报告泄露个人正文、凭据、绝对用户路径或 provider body。
5. conditional/rejected package 被后续阶段误当成 accepted。

## 1b. Domain Context

**Industry Vertical:** Personal decision intelligence / local-first knowledge system  
**User Population:** 单用户、本地 Windows 环境，数据包含长期个人会话和决策证据  
**Stakes Level:** High  
**Output Consequence:** AI 候选可能影响个人决策，但不能自动成为事实、最终决策或外部动作。

### What Domain Experts Evaluate Against

| Dimension | Good | Bad | Stakes | Source |
|---|---|---|---|---|
| Authority separation | Pi 只能通过 typed Domain Tools | 直接读写 authority DB/Chroma | Critical | PROJECT/REQUIREMENTS |
| Resource containment | exact allowlist、零 ambient discovery | 加载宿主资源或 coding tools | Critical | Spike 001 |
| Supply chain | exact version/integrity、audit gate | range drift、High/Critical、scripts | Critical | package qualification |
| Privacy | metadata-only evidence | personal body/credential/path in logs | Critical | privacy contracts |

### Known Failure Modes in This Domain

- Session memory 被误当作长期个人事实。
- Agent 生成内容绕过 staging/evaluation 进入检索。
- 模型或工具失败后仍推进水位，造成不可见的数据缺口。
- “本地运行”被错误理解为 package 可任意读取用户目录。

### Regulatory / Compliance Context

未识别到本阶段必须适用的行业法规；仍按最小权限、数据最小化、可撤回和完整审计执行。

### Domain Expert Roles for Evaluation

| Role | Responsibility |
|---|---|
| System owner | 确认 package 决议和 primary 激活授权 |
| Security reviewer | 审阅依赖、capability 和负向测试 |
| Data-governance verifier | 验证 authority/Session/Candidate 零污染 |

## 2. Framework Decision

**Selected Framework:** `@earendil-works/pi-coding-agent` + `@earendil-works/pi-ai` + `@earendil-works/pi-storage-sqlite-node`  
**Version:** exact `0.83.0`; transitive security overrides必须单独精确锁定并通过兼容测试  
**Vendor Lock-In Accepted:** Partial — Pi 接管 AI runtime API，Domain Tool 和 authority contract 保持项目自有。

**Rationale:** Pi 提供 `AgentSession`、事件流、Tool、ResourceLoader、model/provider 和 Session primitives，能够替换散落的 AI 控制面，同时不要求把确定性 Python 领域内核迁移到框架内部。

**Alternatives Considered:**

| Framework | Ruled Out Because |
|---|---|
| 继续 legacy orchestration | 无法满足用户要求的统一 Pi Kernel |
| 直接使用 `pi-agent-core` | 缺少已验证的 coding-agent Session/ResourceLoader 集成层 |
| LangGraph/CrewAI 等 | 扩大依赖和迁移面，且不符合已批准 Issue/Spike 方向 |
| `pi-web-ui` | 观察版本与核心包不一致，Phase 48 明确 deferred |

## 3. Framework Quick Reference

### Installation

```powershell
npm ci --ignore-scripts --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel
```

### Core Imports

```javascript
import { createAgentSession, DefaultResourceLoader, defineTool, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
```

### Entry Point Pattern

使用 `DefaultResourceLoader` 的全部 `no*` 开关、in-memory settings/session、`noTools: "builtin"` 和 exact `customTools` 构建 synthetic containment session；Phase 49 才替换为 durable host/session。

### Key Abstractions

| Concept | What It Is | Phase 48 use |
|---|---|---|
| `AgentSession` | 模型、Tool 和事件运行会话 | synthetic API/stream smoke |
| `DefaultResourceLoader` | extension/skill/prompt/context 发现器 | 显式关闭并做 decoy 负向测试 |
| `SettingsManager` | SDK settings 来源 | 仅 `inMemory()`，禁止宿主扫描 |
| `SessionManager` | 会话轨迹 | 仅隔离 fixture，不作为 authority |
| `defineTool` | 自定义 Tool schema | 两个无副作用 synthetic Domain Tools |

### Common Pitfalls

1. 仅设置 `noTools` 不会自动关闭 extension/skill/context discovery。
2. 默认 cwd/agentDir 可能让 ambient resource 进入运行时。
3. exact 顶层 Pi 版本仍可能通过 transitive range 引入漂移或已知漏洞。
4. package audit 通过不代表 runtime capability containment 通过。

### Recommended Project Structure

```text
apps/personal_intelligence_kernel/
├── package.json
├── package-lock.json
├── scripts/qualify-packages.mjs
├── src/runtime/resource-policy.mjs
├── src/runtime/containment-probe.mjs
└── test/*.test.mjs
```

## 4. Implementation Guidance

**Model Configuration:** Phase 48 使用 deterministic Provider stub 或不触发模型调用；真实模型、temperature 和 token budget 延至 Phase 51/53。  
**Core Pattern:** package gate → explicit resource policy → synthetic session → negative capability fixtures → immutable decision report。  
**Tool Use:** 只注册 `domain_inspect` 和 `domain_candidate` synthetic tools；无 filesystem/process/network side effect。  
**State Management:** 临时目录和 in-memory Session；审计报告只含 metadata/checksum。  
**Context Window Strategy:** Phase 48 不注入个人上下文或 AGENTS/skills 文件。

## 4b. AI Systems Best Practices

### Structured Outputs

Node 侧所有 qualification/containment 输出使用版本化 JSON schema；Python contract test 负责独立解析和字段 allowlist。不得依赖模型生成结构化结果。

### Async-First Design

SDK 初始化、reload、session dispose 和 fixture cleanup 必须 await；超时后强制失败，不遗留后台 Session。

### Prompt Engineering Discipline

仅使用固定 synthetic system prompt；不读取用户 prompt template 或真实 conversation。

### Context Window Management

无真实上下文；测试断言 prompt/context file 数量为零。

### Cost and Latency Budget

Phase 48 真实 Provider 调用预算为 0；所有验证可离线执行，只有 npm metadata/audit 使用 registry 网络。

## 5. Evaluation Strategy

| Dimension | Rubric | Measurement | Priority |
|---|---|---|---|
| Supply-chain integrity | exact version/integrity，0 High/Critical | npm/lock parser | Critical |
| Runtime containment | exact two tools，零 ambient resources | node:test | Critical |
| Authority isolation | fingerprints unchanged | Python contract | Critical |
| Privacy | report key/value allowlist，无正文/credential/path | deterministic scan | Critical |
| Reproducibility | clean `npm ci --ignore-scripts` 后相同决议 | repeated CI/local run | High |

**Primary Tool:** Node `node:test` + Python pytest + npm audit；不新增 eval framework。  
**Reference Dataset:** 至少 12 个 decoy/capability fixtures，覆盖 local/global extension、skill、prompt、context、auth/settings、filesystem、process、network 和 oversized input。  
**Labeling:** deterministic expected outcome；无需 LLM judge。

## 6. Guardrails

### Online

| Guardrail | Trigger | Intervention |
|---|---|---|
| Package decision | 非 `accepted` | 阻断 Phase 49 product dependency |
| Resource registry | unexpected tool/resource | dispose session and fail |
| Network policy | non-registry host in qualification | block and record safe code |
| Sensitive output scan | credential/path/body match | reject report |

### Offline

| Metric | Sampling | Action |
|---|---|---|
| npm audit severity | every clean install and lock change | requalify |
| package integrity | every install | reject mismatch |
| containment fixtures | every change | block merge/execution |

## 7. Production Monitoring

Phase 48 不进入生产。产物只记录 package versions、integrity、capabilities、test counts、safe reason codes 和决议。后续 Phase 49/52 再定义 runtime tracing。

## Checklist

- [x] System type and critical failures classified
- [x] Domain stakes and expert criteria defined
- [x] Framework and exact version selected
- [x] Alternatives and lock-in documented
- [x] Installation/import/entry pattern documented
- [x] Evaluation dimensions and deterministic tooling defined
- [x] Guardrails and requalification triggers defined
- [x] Phase 48 provider budget fixed at zero
