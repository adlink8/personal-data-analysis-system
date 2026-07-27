---
phase: 40-product-hardening-and-live-uat
plan: 03
status: blocked
requirements: [UX-01, UX-02, QA-01, QA-02]
---

# 40-03 Summary

自动化与依赖审查已完成，但计划要求的 blocking human-verify 尚未执行，因此本计划及 Phase 40 不能标记为完成。

完成内容：

- 检查前端依赖，确认仓库没有现成的 `@playwright/test` 或其他浏览器 runner；未新增浏览器依赖、生产进程或测试旁路。
- 记录拒绝新增 runner、采用记录化手动 local-only 浏览器 UAT 的依赖审查结论。
- 补充 UAT 矩阵、artifact 忽略规则、敏感信息脱敏和禁止外传约束。
- 更新 `40-UAT.md` 与 `40-VERIFICATION.md`，明确自动化证据已通过、真人 UAT 仍为 pending。

验证：

- `npm run build`：通过。
- 前端完整 Vitest：24 个测试文件、255 个测试通过。
- Python UI Projection + orchestration/replay/e2e 定向矩阵：通过。
- `git diff --check`：通过。

待完成的人审门：

- 真实同源浏览器在 320/768/1024/1440 宽度、200% 缩放、键盘与 reduced-motion 下检查布局和可访问性。
- 检查 read-only、offline/partial/recovery 状态的真实文案与恢复行为。
- 在 disposable authority 上完成一次 `project + low` 的 prepare → exact preview → explicit confirm → same-payload exact replay，并核对 append-only fingerprint 与事件重放一致性。
- 检查 DevTools/DOM/URL/storage/console 及测试 artifact，不泄露 authority、preview、confirmation、HMAC、provider body、凭据或完整本地路径。

在用户完成并接受上述 UAT 前，不宣称 Phase 40 已发布或通过，也不执行 live authority 写入。
