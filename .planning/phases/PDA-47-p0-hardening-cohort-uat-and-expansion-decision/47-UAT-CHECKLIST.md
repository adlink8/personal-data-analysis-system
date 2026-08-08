---
phase: 47
status: live_readonly_p0_pass_expansion_deferred
---

# v1.5 P0 UAT Checklist

| Dimension | Result | Notes |
|---|---|---|
| Project/Goal/Decision 识别、当前/历史/类型分离 | PASS live | 最新 8000 服务真实显示 1 Decision fresh、1 Goal + 3 Project stale |
| fresh/stale/partial/unavailable 差异化恢复 | PASS fixture + PASS live fresh/stale | live 真实覆盖 fresh/stale；partial/unavailable 由契约矩阵覆盖 |
| evidence drawer、binding mismatch、privacy sealed | PASS fixture/component + PASS live drawer | live drawer 只显示稳定元数据并显示“已核验”；其余状态由契约覆盖 |
| 320/768/1024/1440 | PASS live | 四档无横向溢出 |
| keyboard、focus、Esc、200% zoom、reduced motion | PASS live | Esc 关闭抽屉；200% 等效设备视口无溢出；reduced-motion 媒体条件与 CSS 生效 |
| REST offline、single authority、retrieval/widget unavailable | PASS fixture + PASS live degraded | 阻断 `/ui/topics*` 后安全降级，清除阻断并重试恢复；其余状态由契约覆盖 |
| URL/storage/console/network privacy review | PASS scoped live | 初始页面仅同源 GET、无失败/非 GET/外部请求；应用 error 日志 0；页面未展示 raw token-like 内容 |
| zero write/provider/external-action fingerprint | PASS scoped live + automated | Personal State 权威表 1/1 行数未变化；仅写入 Wiki 派生库 |

WIKI-04：PASS（限定 P0、授权、本地、只读 cohort）。Skill、Career、External Topic、Notes、LLM narrative、broader entities 继续 DEFER。
