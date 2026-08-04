---
phase: 48-pi-package-qualification-and-runtime-containment
plan: 01
verified: 2026-08-04
status: passed
score: 3/3 must-haves verified
---

# Phase 48-01 Verification Report

## 结论

48-01 已通过。Pi 0.83.0 候选包保持独立、精确锁定、npmjs.org 来源、`--ignore-scripts` 安装策略和 fail-closed 资格门禁；审计清洁只产生 `conditional`，不会绕过 48-02 的 runtime containment 前置条件。

## 验证结果

| 检查 | 结果 |
|---|---|
| Node 定向资格测试 | PASS，6/6 |
| `npm test --prefix apps/personal_intelligence_kernel` | PASS，6/6 |
| Python 契约测试 | PASS，7 passed |
| `npm run qualify --prefix apps/personal_intelligence_kernel` | PASS，exit 0；`conditional`、`package_security_pass=true`、`accepted=false` |
| `npm audit --omit=dev --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel` | PASS，0 vulnerabilities |
| 中文 Windows 路径默认运行 | PASS；`fileURLToPath` 正确解析路径 |
| Windows npm 元数据/audit 子进程 | PASS；使用 `npm.cmd`、固定 npmjs.org registry |
| malformed/empty audit envelope | PASS；缺失或非数字计数 fail-closed |
| `git diff --check` | PASS；目标内容在提交前将再次按暂存文件复核 |

## 已验证控制

- 三个 Pi 直接依赖均为精确 `0.83.0`，lockfile 含 npmjs.org `resolved` 和 `sha512` `integrity`。
- 生命周期脚本仅按 `ignore-scripts` 策略处理，未知安装脚本、版本漂移、integrity/host 不匹配均拒绝。
- metadata 的版本、integrity、license、repository、engine 与 baseline 不一致时拒绝。
- audit 只接受结构完整的 npm audit v1/v2 报告，要求 `info/low/moderate/high/critical/total` 全部为非负有限数字；High/Critical 或任何审计不可用均拒绝。
- 报告只输出固定字段和安全 reason code，不输出绝对路径、环境变量、凭据、npm auth/proxy 或原始错误正文。

## 计划状态

- 48-01：完成并可进入 48-02。
- 48-02：尚未执行；runtime containment 证据仍缺失，因此当前候选不能标记为 `accepted`。

## 人工复核

官方仓库归属和许可证接受仍需按 `48-VALIDATION.md` 做人工复核；这不影响本计划的自动化测试结果，但在 48-03 综合门禁前必须保留证据。
