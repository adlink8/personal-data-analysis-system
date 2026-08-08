---
phase: 47
status: complete_authorized_live_read_only
classification: fixture_and_authorized_live_read_only
---

# v1.5 P0 UAT Protocol

`apps/personal_decision_cockpit/src/test/fixtures/wiki-uat-*.json` 只证明脱敏 fixture 的契约和降级边界，不能证明真实个人日常效用。真实 UAT 只有在用户明确授权本次 Project/Goal/Decision 只读 cohort 后执行；不得执行 prepare、confirm、action/outcome、provider 调用、索引写入、promotion 或外部动作。

允许留存的报告字段只有 build/revision、opaque topic id/type、短 binding/checksum、status/reason code、任务结果和 zero-write fingerprint。禁止保存原始正文、完整个人 URL、DOM/HAR/video、凭据、preview/confirmation payload 或 tunnel 地址。没有授权或当前服务未加载最新代码时，`daily_use_proof` 固定为 `DEFER`。
