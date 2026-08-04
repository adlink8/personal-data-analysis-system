---
phase: 48-pi-package-qualification-and-runtime-containment
plan: 02
verified: 2026-08-04
status: passed
score: 3/3 must-haves verified
---

# Phase 48-02 Verification Report

## 结论

48-02 已通过。Pi runtime 候选使用显式、内存态、deny-by-default 的资源和工具边界；ambient discovery、内置 coding tools、Provider、未知网络和写入 authority 均未被 probe 触达。

## 验证结果

| 检查 | 结果 |
|---|---|
| runtime Node 定向测试 | PASS，12/12 |
| 独立 runtime Node 测试 | PASS，6/6 |
| Python 零 ambient/零 mutation 契约 | PASS，3/3 |
| hostile fixture probe | PASS，18 个 fixture；provider calls=0 |
| 成功/失败/timeout 清理 | PASS；临时状态清理、failure/timeout exit code 均验证 |
| protected authority/session/candidate 指纹 | PASS；前后完全一致 |
| tool registry | PASS；仅 `domain_candidate`、`domain_inspect`，无重复 tool/event，能力列表为空 |
| network allowlist | PASS；default deny，hosts/ports/methods 为空，伪造 host 被契约拒绝 |
| 隐私安全输出 | PASS；仅 allowlisted schema/version/counts/tool names/reasons/checksums |

## 已验证控制

- `DefaultResourceLoader` 显式设置 `noExtensions`、`noSkills`、`noPromptTemplates`、`noThemes`、`noContextFiles`，并使用固定 synthetic system prompt。
- `SettingsManager.inMemory()`、`SessionManager.inMemory(cwd)`、显式 `cwd/agentDir`，不信任 SDK 默认发现路径。
- `createAgentSession` 使用 `noTools: "builtin"`，仅注册两个 synthetic Domain Tools，不调用 Provider。
- hostile fixtures 覆盖 local/global resource decoys、settings/auth、hidden tool、parent file、child-process marker、network host、oversized output 和 credential-like values。
- probe 输出不包含 seeded secret、临时路径、未知 host、Provider 错误正文或环境值；临时目录在 success/failure/timeout 后清理。

## 计划状态

- 48-01：完成，已提交 `468f4e3`。
- 48-02：完成，runtime containment 证据可供 48-03 综合门禁消费。
- 48-03：尚未执行；当前证据仍不能单独把候选标记为 `accepted`。

## 剩余风险

本计划不执行真实 Provider traffic、durable Session storage 或真实个人数据路径；这些边界按路线图继续留在后续阶段。验收过程中发现的一个测试生成临时目录已在验证后清理。
