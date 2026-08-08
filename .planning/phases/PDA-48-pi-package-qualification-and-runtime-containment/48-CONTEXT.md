---
phase: 48
status: ready_for_planning
source: approved_v2_requirements_and_spike_reuse
gathered: 2026-08-04
---

# Phase 48: Pi Package Qualification and Runtime Containment — Context

<domain>
## Phase Boundary

本阶段只建立可进入产品树的 Pi package baseline、能力边界和自动化资格决议。它不迁移现有 AI 工作流、不调用真实 Provider、不读取真实个人正文、不修改 supervisor，也不激活 Pi Kernel。Phase 48 只有在 package 和 runtime containment 同时 `accepted` 时才允许 Phase 49 引用候选依赖。

</domain>

<decisions>
## Implementation Decisions

### Package baseline

- **D-01:** 产品候选放在独立 `apps/personal_intelligence_kernel/` Node ESM 应用；不复用 Spike 的 `node_modules`，不把依赖加入 Python `pyproject.toml` 或现有 Cockpit/ChatGPT 应用。
- **D-02:** `@earendil-works/pi-coding-agent`、`pi-ai`、`pi-storage-sqlite-node` 精确锁定 `0.83.0`；执行前从 npmjs.org 再核对版本、integrity、engine、license 和 repository。所有安装使用 `npm ci --ignore-scripts`。
- **D-03:** 当前 `undici <8.9.0` 与 `brace-expansion <5.0.9` 风险必须通过兼容性验证后的 exact override、上游安全版本或拒绝决议闭合；不得仅 suppress audit。

### Runtime containment

- **D-04:** 生产 bootstrap 显式实例化 `DefaultResourceLoader`，设置 `noExtensions`、`noSkills`、`noPromptTemplates`、`noThemes`、`noContextFiles`，并以 `noTools: "builtin"` 加自定义 allowlisted Domain Tools 启动。
- **D-05:** cwd、agentDir、用户目录、`.pi`、`.agents/skills`、settings/auth 和环境变量中放置 decoy 后，加载结果仍必须是零 ambient resource、零 coding built-in、零凭据发现。
- **D-06:** 资格决议只允许 `accepted | conditional | rejected`；`conditional` 和 `rejected` 都不能解除 Phase 49 的生产依赖门。

### the agent's Discretion

- 资格工具内部模块拆分和 JSON 字段顺序。
- Node `node:test` fixture 的帮助函数命名。
- 审计 Markdown 的排版，只要 JSON 是机器可校验的主证据。

</decisions>

<canonical_refs>
## Canonical References

### Approved scope

- `.planning/REQUIREMENTS.md` — SEC-01、SEC-02、TOOL-02 的正式验收范围。
- `.planning/ROADMAP.md` — Phase 48 目标、依赖和 success criteria。
- `.planning/PROJECT.md` — Pi 控制面与 Python authority 的不可跨越边界。

### Validated spike evidence

- `.planning/spikes/pi-embedded-personal-kernel/001-runtime-containment/README.md` — 已验证的 containment API 与遗留供应链缺口。
- `.planning/spikes/pi-embedded-personal-kernel/prototype/agent-runtime/runtime-containment.mjs` — `DefaultResourceLoader`、`noTools` 和 decoy fixture 的可运行模式。
- `.planning/spikes/pi-package-qualification/INVENTORY.md` — 官方候选包和 deferred/rejected 类别。
- `.planning/spikes/pi-package-qualification/DECISION.md` — 当前 conditional 决议，不能冒充 production accepted。
- `.planning/spikes/pi-package-qualification/SECURITY-REVIEW.md` — 必须自动化的负向测试清单。

### Existing product patterns

- `apps/personal_data_chatgpt/package.json` — 本仓库 Node ESM/private app 和 `node:test` 模式。
- `ops/runtime/start-agent-stack.ps1` — 后续 supervisor 的 ownership/readiness 模式；本阶段只读参考。
- `tests/ops/test_agent_stack_script.py` — PowerShell/Node 跨进程契约测试模式。
- `src/personal_knowledge/core/privacy_guard.py` — 现有安全输出和脱敏边界。

</canonical_refs>

<specifics>
## Specific Ideas

- 当前 registry 版本仍为 Pi `0.83.0`，Node engine `>=22.19.0`，license MIT。
- 2026-08-04 使用 npmjs.org audit 复核仍为 2 High + 1 Moderate；npmmirror audit 404 不能作为安全通过证据。
- `pi-web-ui` 和全部社区 package 不进入 Phase 48 产品候选。

</specifics>

<deferred>
## Deferred Ideas

- Kernel service lifecycle 和 event protocol：Phase 49。
- Python Domain Tool bridge、durable task、Session Store：Phase 50。
- Provider、Skill、真实模型和工作流迁移：Phase 51 以后。

</deferred>

---

*Phase: 48-pi-package-qualification-and-runtime-containment*
*Context gathered: 2026-08-04 via approved requirements express path*
