---
phase: 47
plan: 02
status: live_readonly_p0_pass
---

# Phase 47-02 Summary — Authorized read-only cohort UAT

当前代码在最新本地服务端口 8000 完成真实浏览器只读复验：

- 目录显示 5 个 P0 topic：Decision fresh；Goal 与 3 个 Project stale，原因 `serving_snapshot_changed`。
- Project 详情加载 current/observation/recommendation/External/backlinks 分区；Decision 详情显示 `fresh_wiki`。
- Recommendation 证据抽屉打开并显示稳定引用、snapshot、checksum 与“已核验”；Esc/关闭后恢复页面。
- 320/768/1024/1440 viewport 均无横向溢出。
- 200% 等效设备视口无横向溢出；reduced-motion 媒体条件生效。
- 阻断 `/ui/topics*` 后显示安全 degraded/offline 状态，清除阻断并重试后恢复。
- 初始页面仅同源 GET，无失败/非 GET/外部请求；应用 error 日志为 0。
- Personal State `personal_state_runs` 与 `personal_state_publications` 物化前后均为 1 行；写入仅发生于 Wiki 专用 metadata-only 派生库。

结论：WIKI-04 的 P0 授权只读 cohort 通过；扩域继续 DEFER，不新增 topic domain、editor 或写权限。
