# Phase 49 Research — Kernel Host and Event Lifecycle

## Findings

- Phase 48 的 package/resource boundary 应成为 Host bootstrap 的唯一构造入口，避免 server 另建一套宽松 Session。
- 现有 Python API 使用 `BaseHTTPRequestHandler`、静态 safe errors 和 loopback；Node ChatGPT app 使用 private ESM。Kernel 应沿用 private ESM + Node built-in HTTP，暂不增加 Web framework。
- Spike streaming 已验证 cursor replay、duplicate suppression 和 cancel projection；生产设计需要把 cursor 绑定 append-only SQLite sequence，而不是进程内数组。
- 事件正文不能复制 canonical 数据。`payload_ref + checksum + privacy_class` 足以驱动后续 Tool 获取受控数据。

## Recommended Structure

```text
apps/personal_intelligence_kernel/src/
├── server.mjs
├── kernel-host.mjs
├── events/schema.mjs
├── events/journal.mjs
└── transport/sse.mjs
```

## Validation Architecture

- Node unit/contract：schema、canonical checksum、journal idempotency、SSE cursor/reconnect。
- Python cross-process：loopback-only bind、health/readiness、restart persistence、safe error/privacy scan。
- Authority fingerprints：启动、事件追加、重启前后 canonical/active/watermark 不变。

## Risks

- SQLite writer contention：Host 必须单 writer、bounded busy timeout、transactional sequence。
- SSE reconnect duplicate：Last-Event-ID 必须映射 durable sequence，并让客户端按 event_id 去重。
- readiness 不能等同 listener：只有 package decision accepted、schema migration complete 和 journal integrity ok 才 ready。
