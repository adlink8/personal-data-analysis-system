---
phase: 48
status: complete
source: reused_spikes_plus_targeted_refresh
researched: 2026-08-04
---

# Phase 48 Research — Pi Package Qualification and Runtime Containment

## Research Outcome

Phase 48 不需要重新探索框架选型。用户已锁定 `earendil-works/pi`，Spike 001 已证明 `createAgentSession`、`DefaultResourceLoader`、`SettingsManager.inMemory()`、`SessionManager.inMemory()`、`noTools: "builtin"` 和显式 `customTools` 可形成最小 containment。当前主要未知项是“安全依赖修复后是否仍与 Pi 0.83.0 兼容”，因此应把 package override、API smoke 和负向能力测试放在同一个 fail-closed gate 中。

## Targeted Package Refresh

| Item | 2026-08-04 observation | Planning consequence |
|---|---|---|
| Pi official packages | coding-agent/ai/agent-core/storage 均为 `0.83.0` | exact pin，不使用 caret/range |
| Node engine | `>=22.19.0`; local Node 24.13.0 | engine gate 可满足 |
| License/repository | MIT; `github.com/earendil-works/pi` | 记录 package → repository directory |
| npm audit | 2 High + 1 Moderate | Phase 48 当前默认失败 |
| `undici` | Pi lock 中 8.5.0；advisory 要求 `>=8.9.0` | 候选 exact override，必须跑 API/网络负向测试 |
| `brace-expansion` | Pi nested range 可落到受影响版本；安全线 `>=5.0.9` | 候选 exact override，必须跑 resource discovery/DoS fixture |
| npmmirror audit | endpoint 404 | 只用 npmjs.org audit 形成决议 |

## Existing Codebase Patterns

- Node 运行面均位于 `apps/*`，使用 private ESM package 和 `node --test`。
- Python contract tests 可通过 `subprocess.run()` 驱动 Node/PowerShell，并验证零写入和 typed exit code。
- `ops/runtime/start-agent-stack.ps1` 已建立 child ownership、bounded readiness 和 structured log 模式；Phase 48 不修改它，Phase 49 再接入。
- 安全输出应沿用 `privacy_guard` 和静态 safe code，不把路径、环境值、credential 或 package body 写入 report。

## Recommended Implementation

1. 创建独立、private 的 `apps/personal_intelligence_kernel` candidate package。
2. 只允许 exact Pi versions 和审计所需 exact overrides；lockfileVersion、integrity、resolved host、scripts、license、engine 全部进入机器决议。
3. 资格工具默认只读 lockfile/node_modules；安装步骤由执行计划显式运行 `npm ci --ignore-scripts`。
4. runtime test 在临时 cwd/agentDir/home 中种植 decoy，使用显式 ResourceLoader 和两个 synthetic Domain Tools。
5. 报告同时绑定 git worktree dirty-state-independent 的输入 checksum，以及 authority fingerprint before/after；任何未知项判 `rejected`。

## Validation Architecture

### Fast feedback

- Node package/unit：`npm test --prefix apps/personal_intelligence_kernel`
- Python contract：`python -m pytest tests/contract/test_pi_package_qualification.py tests/contract/test_pi_runtime_containment.py -q`

### Full Phase 48 gate

```powershell
npm ci --ignore-scripts --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel
npm audit --omit=dev --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel
npm test --prefix apps/personal_intelligence_kernel
python -m pytest tests/contract/test_pi_package_qualification.py tests/contract/test_pi_runtime_containment.py tests/governance/test_pi_package_decision.py -q
node apps/personal_intelligence_kernel/scripts/qualify-packages.mjs --json ops/reports/audits/pi-package-qualification.json
```

### Mandatory failure assertions

- audit 中存在 High/Critical、range/integrity 漂移、lifecycle script 未批准或 package 来源未知时 exit non-zero。
- decoy extension/skill/context/auth/settings 被加载、coding built-in 出现或工具集不是 exact allowlist 时 exit non-zero。
- 测试前后 authority、watermark、active pointer、Session/Candidate fixture 指纹不一致时 exit non-zero。

## Open Risk

Exact overrides 属于本地兼容修复，不等于上游正式支持。即使 audit 清零，只要 Pi API、streaming 或 ResourceLoader 负向测试失败，Package Decision 仍必须是 `rejected`，不能以“漏洞已修复”单独放行。
