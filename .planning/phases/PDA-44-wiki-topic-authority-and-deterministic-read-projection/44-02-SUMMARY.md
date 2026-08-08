---
phase: 44
plan: 02
status: complete
---

# Phase 44-02 Summary

完成 `TopicProjectionService` 与同源只读 REST 契约。列表使用 opaque topic id；详情绑定 authority snapshot、freshness、partial、limitations、checksum 与 evidence refs；Decision feedback 标记 `causal_claim=false`；backlinks 只接受显式精确 join。默认读取不调用 provider、Chroma、KU 写入或外部动作。

验证：topic projection 定向 Python 测试、HTTP contract tests 均通过；真实本机 preflight 显示 Personal State 尚无 committed run，因此 Project/Goal 保持不可发布，未伪造主题。
