---
phase: 48-pi-package-qualification-and-runtime-containment
verified: 2026-08-04
status: gaps_found
decision: conditional
accepted: false
reason_codes:
  - runtime_evidence_missing
---

# Phase 48 Verification Report

## 结论

Phase 48 的 package qualification 与 runtime containment 已实现并通过自动化验证，但 composite decision 为 `conditional`，不能标记为 `accepted`。SEC-01 通过；SEC-02 和 TOOL-02 因同一 run 缺少持久化 runtime evidence 而阻断。Phase 49 保持 blocked。

## Composite decision

- schema：`pi-package-qualification-v1`
- decision/status：`conditional`
- accepted：`false`
- reason：`runtime_evidence_missing`
- run_id：`piq_f7896e839999ed2eac87ebd4`
- evidence checksum：`64965a9d6a9079e63013efc45a1458667751397b1db7c3ac1d052557dfd046e2`
- package security：`true`
- runtime containment：`false`
- SEC-01：pass；SEC-02/TOOL-02：blocked

同一 run 已绑定 `package.json`、`package-lock.json`、package baseline、tool registry、network allowlist 的 SHA-256；runtime evidence 缺失明确编码为 `null`，不会被当作 accepted。

## 验证命令

| 命令 | 结果 |
|---|---|
| `npm ci --ignore-scripts --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel` | PASS；229 packages，0 vulnerabilities |
| `npm audit --omit=dev --registry=https://registry.npmjs.org --prefix apps/personal_intelligence_kernel` | PASS；0 vulnerabilities |
| `npm test --prefix apps/personal_intelligence_kernel` | PASS；12/12 |
| `python -m pytest tests/contract/test_pi_package_qualification.py tests/contract/test_pi_runtime_containment.py tests/governance/test_pi_package_decision.py -q` | PASS；24 passed |
| `node apps/personal_intelligence_kernel/scripts/qualify-packages.mjs --check` | PASS；conditional，accepted=false |

## 已验证安全边界

- package、lock、metadata、integrity、registry、license、engine、install-script 和 audit gate 均通过；High/Critical、malformed audit、版本/host/integrity drift 均 fail-closed。
- runtime 仅暴露两个 synthetic Domain Tools；ambient resources、builtin tools、Provider、未知网络和 authority 写入均不可达。
- composite gate 对 tool registry 和 network allowlist 做内容校验，不仅计算 checksum；篡改或删除 required evidence 会进入 rejected。
- JSON/Markdown/decision 的 status、run_id、evidence checksum 一致；治理字段、expiry、requalification triggers、allowed scope 和隐私输出通过独立测试。
- 资格报告是 evidence only，不安装依赖、不激活 Pi、不调用 Provider、不修改 authority。

## 阻断与后续

当前不能宣称 SEC-02/TOOL-02 完成，也不能执行 Phase 49。后续只有在同一 exact-lock run 生成并校验 runtime containment evidence 后，composite decision 才可能从 conditional 进入 accepted；若 evidence 缺失、过期、混合 run 或指纹变化，decision 必须 rejected/conditional 并继续阻断。

Phase 49–54 当前工作区没有可执行计划文件/实现入口；按既有路线图依赖关系不自动推进，不创建未授权替代计划。
