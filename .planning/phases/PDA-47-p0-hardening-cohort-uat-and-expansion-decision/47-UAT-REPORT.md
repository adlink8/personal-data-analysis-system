---
phase: 47
status: live_readonly_p0_pass_expansion_deferred
daily_use_proof: PASS_SCOPED_READ_ONLY
---

# v1.5 UAT Report

## Automated fixture evidence

- P0 cohort manifest：三类 topic、opaque identity、fixture-only boundary。
- Authority states：fresh、stale、partial、unavailable、privacy sealed、evidence mismatch、retrieval unavailable、widget unavailable。
- Frontend fixture contract：3 tests passed。
- Full frontend suite：28 files / 267 tests passed。
- Production build：passed；仅有 bundle size warning。

## Live read-only evidence

已完成当前代码构建的本地授权只读复验（当前服务端口 8000；服务已替换为最新代码）：

- 目录真实发布 5 个 P0 主题：1 个 Decision `fresh`、1 个 Goal 与 3 个 Project `stale`；stale 原因显示为 `serving_snapshot_changed`，未伪装为 fresh。
- Project 详情真实加载 current/observation/recommendation/External/backlinks 分区，并显示“主题投影已偏旧”；Decision 详情显示 `fresh_wiki`。
- Decision 推荐证据抽屉真实打开，显示稳定引用、snapshot、checksum 与“已核验”；关闭后页面恢复，无确认/行动/写入控件。
- 320/768/1024/1440 viewport 复验均无横向溢出；长 opaque id 可见且不破坏布局。
- 200% 等效设备视口（CSS width 640、device scale factor 2）复验 `scrollWidth == clientWidth == 625`，无横向溢出；`prefers-reduced-motion: reduce` 生效，动画/过渡压缩为 `0.00001s` 且滚动行为为 `auto`。
- 真实键盘 UAT：证据抽屉打开后发送 Escape，dialog 关闭且 Decision 页面仍可用。
- 真实 degraded/offline UAT：阻断同源 `/ui/topics*` 后显示“知识目录服务不可达”及安全恢复说明；清除阻断并点击“重试”后恢复目录，未把空白或旧缓存伪装成当前结果。
- 初始页面网络审计仅出现同源 GET：`/app/knowledge`、静态 JS/CSS、`/ui/overview`、`/ui/system/status`、`/ui/topics?limit=50`；无非 2xx、失败请求、非 GET 或外部/provider 请求。应用 error 日志为 0；页面未显示 raw token-like 内容。
- Personal State 权威表在物化前后保持 `personal_state_runs=1`、`personal_state_publications=1`；批量写入仅落在 Wiki 专用 metadata-only derived store。

本次仍未读取或保存真实主题正文，也未执行任何 authority/provider/external-action 写入。以上为授权的本地、只读、去标识化 cohort 证据，不等同于扩大到新 topic domain 的产品授权。

## Expansion

Skill、Career、External Topic、Notes、LLM narrative、broader entities 均维持 `DEFER`，详见 `47-EXPANSION-DECISION.md`。
