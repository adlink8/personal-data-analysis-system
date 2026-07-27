---
phase: 39-feedback-proactive-and-runtime-truthfulness
plan: 02
status: complete
requirements: [FDB-02]
---

# 39-02 Summary — FDB-02

完成 proactive/calibration 的只读真实投影：

- proactive 卡片使用 authority 的 `importance.final_score`，并透传 control `as_of`、append-only history 和 frontier checksum。
- Proactive 页面保持 Snooze/Suppress/限定 Scope/Restore disabled，不新增浏览器 REST 写入、optimistic state、promotion 或 external action。
- Calibration 展示 frozen/非因果、样本、限制、`promotion_available` 与 `external_action_available`，明确不自动 promotion、不执行 external action。
- 增加 projection、schema、页面和 GET-only/side-effect 边界回归覆盖。

验证：

- `python -m pytest tests/contract/test_ui_projection_actions_proactive.py tests/contract/test_proactive_interfaces.py tests/contract/test_proactive_boundaries.py -q`：38 passed。
- `npm run test -- --run src/test/ProactivePage.test.tsx src/test/ActionsPage.test.tsx src/test/actionProactiveSchemas.test.ts`：17 passed。
- `npm run build` 通过。

