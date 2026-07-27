---
phase: 39-feedback-proactive-and-runtime-truthfulness
plan: 03
status: complete
requirements: [RUN-01]
---

# 39-03 Summary — RUN-01

完成来源可追溯的运行时 observation matrix。REST 当前响应、MCP/Tunnel listener、Chroma probe、Authority readability/freshness 和 supervisor last-observed 状态彼此独立，均带 state、source、observed_at、scope 与 recovery_hint。`agent-stack.json` 只公开经过校验的历史 service 状态，不公开 PID、完整 URL 或原始异常，也不被当作当前 ownership/readiness。

验证：

- `python -m pytest tests/contract/test_ui_projection_actions_proactive.py tests/contract/test_ui_projection.py -q` 通过。
- `npm run test -- --run src/test/SystemPage.test.tsx`：2 passed。
- `npm run build` 通过。

