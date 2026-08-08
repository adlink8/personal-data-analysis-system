# Phase 56 Research

## Findings

- 项目已有多套 importer/reconcile/doctor 命令，但参数、输出和恢复方式不是 Agent Tool 契约。
- 安全做法不是 SQL proxy，而是给既有 application/service 建立 narrow command facade。
- canonical 历史和 raw source 需要补偿事件；可重建制品不应混入本阶段。
- mutation ledger 只存 operation metadata/checksum/count/fingerprint，不复制个人正文。

## Validation Architecture

- 临时复制数据库和去标识 fixture，不指向 live authority。
- 任意 SQL/path/delete/schema/oversized/secret fixtures 全部在调用前拒绝。
- crash before/after commit、duplicate idempotency、stale preview、fingerprint mismatch。
- raw immutable、canonical compensation chain 和 watermark invariants。
