---
spike: 005
name: streaming-control-and-baseline-comparison
type: comparison
validates: "Given a running Agent Task, when the Cockpit reconnects and sends cancel, then event order, replay and control state remain consistent without unsafe payloads."
verdict: PARTIAL
related: [002, 004]
tags: [streaming, web, metrics, privacy]
---

# Spike 005: Streaming Control and Baseline Comparison

## Research

基于 Pi SDK 的 `AgentSession.subscribe()` 与 `abort()` 事件生命周期，以及现有 Cockpit/REST 宿主，先实现 SSE-style cursor replay，控制命令走 POST；没有引入 WebSocket。

## How to Run

```powershell
cd <repo-root>\.planning\spikes\pi-embedded-personal-kernel\prototype
node streaming_control.mjs
```

## Investigation Trail

- 构造 sequence/event_id/safe summary 事件流，验证 `after` cursor 重放、重复事件去重和旧序列拒绝。
- 启动临时 localhost HTTP server，验证 UI 页面、`/events?after=1` 和 `/control`。
- 取消命令携带 task/version/args checksum；UI 不接收 raw tool/provider payload。
- 真实 Pi/legacy 成本、质量、token 和 browser visual UAT 没有在本 Spike 中伪造或替代。

## Results

控制与恢复协议通过；判定 `PARTIAL`，因为真实 baseline window 和人工浏览器视觉 UAT 仍未执行。
