# 搜索机制

> **一句话：** 一条查询先进知识库（结构化 Q&A）找最佳匹配，不够再从对话原文、原始事件里逐层补。每层有独立的 telemetry，一眼看出搜到了什么、在哪个层找到的。

---

## 一个搜索请求的真实旅程

假设你搜 `rag-search "Python 循环导入报错"`，系统内部做了这些事：

### Step 1：向量化

```
输入: "Python 循环导入报错"
  │
  ▼
local_embed.embed(query)
  │
  ▼
模型: bge-small-zh-v1.5 → 512 维向量 [0.123, 0.456, ..., -0.789]
```

如果 embedding 失败（模型未加载等）→ 跳过知识层向量检索，降级走分层 SQLite fallback（`route=fallback_raw`）；两层都无结果才返回 `route=abstain`。

### Step 2：确定去哪里搜

```
active knowledge collection 的优先级：
  ① collection_override（评测时指定） ≠ None  → 用它
  ② serving snapshot 绑定的 collection ≠ None → 用它
  ③ knowledge_index_active.txt 读到的        → 用它（降级路径）

结果: 去 knowledge_units_empty_kg_20260812T025401Z_live 搜
```

### Step 3：知识层检索

```
ChromaClient(port=8001)
  → 找到 collection
  → query(query_embeddings=[512维向量], n_results=top_k)
  → Chroma 内部做 cosine 相似度对比
  → 返回相似度降序的结果

对每个结果做 6 道门禁检查：
  ① 查询是否在要密码/密钥？           → 是则丢弃
  ② 知识单元是否已弃用/过期？         → 是则丢弃
  ③ 隐私标记是否敏感？               → 是则丢弃
  ④ 查询是否要求"必须包含XXX"？       → 检查证据正文
  ⑤ 证据状态是否可解析？             → 不可用则丢弃
  ⑥ 查询词和知识单元有词汇重叠吗？   → 无重叠则丢弃

门禁全过 → 保留（最多 1 条）
门禁不过 → 丢弃（abstained 计数+1）
```

### Step 4：分层回落（如果知识层不够）

假设你要 top_k=3，但知识层只找到 1 条合格结果。剩下 2 个位置按顺序补：

```
Phase 2a: canonical_messages（消息级文本检索）
  去哪里：agent_conversations.sqlite
  怎么查：提取 "Python 循环导入" 中的特征词 → AND LIKE 检索
  怎么打分：0.92 - 0.02×排名，user 消息 +0.03

Phase 2b: conversation_turns（对话轮次向量检索）
  去哪里：Chroma "conversation_turns" 集合
  怎么查：用同样的 512 维向量做 cosine 检索

Phase 3: non_dialogue_raw（非对话原始事件）
  去哪里：Chroma "personal_events" 集合
  默认只搜 Google 源的事件

Phase 4: legacy_pad（如果还不够，非 Google 事件补充）
  去哪里：Chroma "personal_events"（排除 Google）
  可选，默认开启
```

### Step 5：合并返回

```
知识层结果（1条） + fallback 结果（2条）
  → seen_ids 去重（同一事件只出现一次）
  → 编号 rank
  → 计算 telemetry（每层耗时/命中数）
  → 返回
```

---

## 实际返回看一下

```json
{
  "route": "knowledge",
  "results": [
    {
      "rank": 1,
      "unit_id": "ku|e8a3f1c2...",
      "subject": "Python 循环导入",
      "answer": "将 from a import b 改为在函数内部导入，避免模块加载时的循环引用。",
      "score": 0.9214,
      "retrieval_unit": "knowledge_unit",
      "source": "Agent"
    },
    {
      "rank": 2,
      "unit_id": "ev|7b2d4e1f...",
      "subject": "解决 from a import b 报错",
      "answer": "Traceback (most recent call last):\n  File \"test.py\", line 1...",
      "score": 0.8342,
      "retrieval_unit": "event",
      "source": "Agent",
      "event_time": "2026-03-15T10:30:00"
    }
  ],
  "telemetry": {
    "layers": [
      {"name": "knowledge_unit", "attempted": true, "hits": 1, "latency_ms": 45},
      {"name": "canonical_messages", "attempted": true, "hits": 0, "latency_ms": 12},
      {"name": "conversation_turns", "attempted": true, "hits": 1, "latency_ms": 8},
      {"name": "non_dialogue_raw", "attempted": false, "hits": 0, "latency_ms": 0}
    ],
    "first_contributing_layer": "knowledge_unit",
    "total_latency_ms": 65.2
  }
}
```

**telemetry 很有用：** 如果搜索不准，看 `first_contributing_layer` 就知道结果来自哪层。如果总是 `non_dialogue_raw` 先命中，说明知识索引里没有相关内容。

---

## 另一种搜索：精确查询

语义搜索适合模糊问题。如果你知道精确条件，用 `query_events`：

```powershell
rag-search query --source Agent --month 2025-03 --category 调试 --limit 10
```

等效 REST：`POST /search/query` 或 `GET /data/events?source=Agent&month=2025-03`

这**不走向量检索**，直接 SQL 过滤：

```sql
SELECT ue.event_id, ue.source, ue.event_time, ue.title,
       COALESCE(r.content_rich, ue.content) AS content_rich,
       c.category_v2
FROM unified_events ue
LEFT JOIN unified_events_rich r ON r.event_id = ue.event_id
LEFT JOIN event_categories_v2 c ON c.event_id = ue.event_id
WHERE ue.source = 'Agent'
  AND substr(ue.month, 1, 7) = '2025-03'
  AND c.category_v2 LIKE '%调试%'
ORDER BY ue.event_time DESC
LIMIT 10
```

返回裸数组，没有 telemetry、没有 route。

---

## 常见问题

### Q：搜不到结果，为什么？

看 telemetry 的 `layers`：
- 所有层 `attempted=false` → embedding 失败
- `knowledge_unit` 有 `hits=0` 但其他层有 → 知识索引没相关内容
- 所有层 `hits=0` → 确实没有匹配数据
- `knowledge_unit` 有 `abstained=N` → 门禁拦截了 N 条，检查 support_reason_codes

### Q：知识索引有数据但搜不到？

可能是 **门禁拦截** 了。在返回结果里看 `support_reason_codes`：

| 常见原因 | 含义 |
|----------|------|
| `lifecycle_not_current` | 知识单元已标记为 superseded/deprecated |
| `evidence_missing` | 证据引用找不到（可能是 rebuild 后丢失） |
| `query_candidate_ungrounded` | 查询词和知识单元无词汇重叠 |

### Q：MCP 搜索和 REST 搜索结果不同？

MCP 的 `search_semantic` 进程内直连 `backend.search_knowledge_units`，与 REST 走同一套检索逻辑（不再经 HTTP 回环调 REST API），结果应一致。若仍不一致，先确认两边绑定的 knowledge collection 是否相同。

---

## 参数速查

| 参数 | 默认 | 作用 | 什么时候改 |
|------|------|------|-----------|
| `top_k` | 5 | 返回条数（上限 20） | 需要更多结果时 |
| `source` | None | 过滤 raw 事件源（不影响知识层） | 只想看某个来源时 |
| `dedup` | false | 按合并层折叠重复 | 结果太多重复时 |
| `fallback_policy` | layered | `layered` / `legacy` | 需要兼容旧行为时 |
| `include_evidence` | false | 返回证据正文 | 需要验证证据来源时 |
