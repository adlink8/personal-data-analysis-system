---
phase: 40-product-hardening-and-live-uat
plan: 01
status: complete
requirements: [UX-01, QA-01]
---

# 40-01 Summary

纠正 Cockpit README 的 WIP/验收边界，新增 `docs/live-uat.md` 验收矩阵，并补齐导航文本标签、focus class、移动 More 菜单和 ConfirmDrawer 的确定性回归入口。未新增浏览器 E2E 依赖；真实 viewport、200% zoom、reduced-motion、浏览器隐私和同源写入仍属于后续 Live UAT。

验证：

- `npm run test -- --run src/test/AppAccessibility.test.tsx src/test/ConfirmDrawer.test.tsx src/test/appSmoke.test.tsx`：25 passed。
- `npm run build`：通过。
- README 未再将 Phase 40 或 Phase 36–39 验收表述为 shipped；UAT 矩阵包含 UX-01/02、QA-01/02 与 D-40-01..07。

