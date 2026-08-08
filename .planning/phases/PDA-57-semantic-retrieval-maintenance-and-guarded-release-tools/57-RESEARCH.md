# Phase 57 Research

## Findings

- 现有 extraction/index/eval/promotion 命令已有严格门，但不是统一 Agent transaction surface。
- 最危险边界是 build 与 active switch 混在一次隐式操作；必须拆成 prepare 和 confirm。
- Candidate、index generation 和 active pointer 使用不同 authority，receipt 必须串联而不能合并存储。
- 现有 doctor/reconcile/evaluation 是 Python 真值，Pi 只能消费 typed result。

## Validation Architecture

- Candidate evidence/model/schema negative fixtures。
- Build/reconcile/eval 使用 isolated generation 和 known gold/negative fixtures。
- Pointer switch crash windows、stale manifest、tampered checksum、failed eval、rollback exactness。
- 全链前后 canonical/watermark/active/fingerprint assertions。
