# 检索三层 SSOT 与 hybrid 路由

> Phase 15 治理文档。与 `get_knowledge_status()` 返回的 `ssot` / `fallback_policy` 字段对齐。  
> 实现主路径：`integration/scripts/vector/unified_search.py`（CLI / REST / MCP 共用）。

## 1. 三层 SSOT

| 层 | SSOT | 用途 |
|---|---|---|
| **对话采集** | AgentsView `sessions.db`（**只读**）→ canonical `agent_conversations.sqlite` | 原文、工具、密钥、message 级证据 |
| **个人知识** | `canonical_knowledge_units` + active KU Chroma collection | 偏好 / 决策 / 可答断言；供 career-os 取证 |
| **跨源非对话** | `unified_events` / `personal_events`（过渡） | Google 等非对话；遗留语义兜底 |

补充约束：

- `memory_items` 是实验层，**不得**与 KU 并列作为消费 SSOT。
- AgentsView `insights` 为可选旁路，**不得**覆盖 KU。
- **禁止**写入 AgentsView live DB（`C:\Users\li\.agentsview\sessions.db`）。

### 1.1 状态 API 字段

`get_knowledge_status()` 固定暴露：

```json
{
  "ssot": {
    "dialogue": "agentsview_canonical",
    "knowledge": "canonical_knowledge_units",
    "non_dialogue_raw": "personal_events"
  },
  "fallback_policy": "layered",
  "allow_legacy_pad": true
}
```

| 键 | 含义 |
|---|---|
| `ssot.dialogue` | 对话全文 / message 证据真相源 = AgentsView → canonical dialogue |
| `ssot.knowledge` | 结构化知识真相源 = `canonical_knowledge_units` + active index |
| `ssot.non_dialogue_raw` | 非对话 raw 过渡层 = `personal_events`（及 unified 投影） |
| `fallback_policy` | 当前 hybrid 补洞策略（默认 **layered**；可用 env/CLI 改 `legacy`） |
| `allow_legacy_pad` | layered 仍不足时是否用非 Google `personal_events` 填充（默认 true） |

## 2. 目标 hybrid 路由

`search_knowledge_units` 的**目标**分层（Wave 2 起落地；在 dialogue_fallback 达标前允许过渡）：

```text
search_knowledge_units (layered 默认):
  1) active KU collection              # knowledge-first
  2a) canonical_messages 片段/词检索    # message 级 dialogue（W4；code-literal 主力）
  2b) conversation_turns 向量           # 叙述级 dialogue（辅）
  3) personal_events source=Google      # 非对话 raw
  4) optional legacy_pad                # 非 Google PE 填充（可关）
```

Wave 4 frozen 评测（gold evidence）：**layered R@5 = 1.00**（legacy 约 0.65；dialogue_only 1.00）。

### 2.1 `fallback_policy` 取值

| 值 | 行为 | 何时 |
|---|---|---|
| **`layered`**（**当前默认**） | KU → `conversation_turns` dialogue → Google `personal_events` → 可选 legacy_pad | Phase 15 Wave 2 已落地 |
| **`legacy`** | KU 后全量 `personal_events` 补洞 | 回滚 / 对比评测：`--fallback-policy legacy` 或 env `PERSONAL_DATA_FALLBACK_POLICY=legacy` |

`route_policy` 字符串仍为人类可读摘要：`knowledge-first + raw fallback`，与 `fallback_policy` 机器枚举并存，不破坏既有契约。

## 3. 明确边界

### 3.1 `personal_events` ≠ 全量 View 消息流

- `personal_events` / `unified_events` 是**跨源事件级**汇总，粒度与 AgentsView 的 **message 级**对话流不同。
- 实测量级差约一个数量级（Agent 事件级数千 vs View 消息级数万）。
- **不得**把 `personal_events` 当作对话全文库或 AgentsView 等价物。
- 对话补洞应优先 canonical / View 只读路径（`agent_conversations`、已发布 snapshot、可选 FTS 探针）。

### 3.2 Google 轻量结构化（Phase 16）

- 明细：`activities` + FTS；跨源 raw：`unified_events` / `personal_events`。
- **规范化事件**：`normalized_events`（`event_id` 前缀 **`g|`**，与对话 `cm|` 分离）。
- **轻断言**：`google_light_assertions`（主题/服务/频道/域名聚合信号，**不是**对话 knowledge unit）。
- **禁止**对 Google 跑对话 `knowledge_unit_extractor`。
- 隐私：支付/金融/卡、Maps **可进 normalized_events**，**不进**兴趣断言。
- 构建：
  ```text
  python integration/scripts/build_google_normalized_events.py --write
  python integration/scripts/build_google_light_assertions.py --write
  ```
- 报告：`integration/analysis/ai_context/google_light_structure_report.json`

### 3.3 career-os 消费方式

- 本仓库是**个人数据仓库**，通过 MCP / REST / CLI 提供只读证据。
- **career-os 经 LLM 中介消费 KU**（取证 → 提案 → 确认 → 写入 career-os），**不做**批量同步写库。
- 详见 [integration/README.md](../README.md)「下游消费：Career OS」。

## 4. 消费入口（只读）

| 能力 | CLI | REST | MCP |
|------|-----|------|-----|
| 语义检索 | `unified_search.py semantic` | `POST /search/semantic` | `search_semantic` |
| 知识状态（含 `ssot` / `fallback_policy`） | `unified_search.py knowledge` | `GET /knowledge` | `knowledge_status` |

Active 指针：`integration/db/knowledge_index_active.txt`。  
promote / rollback **不**经分发接口。

## 5. 相关代码

- 状态与检索 backend：`integration/scripts/vector/unified_search.py`  
  - `get_knowledge_status`  
  - `search_knowledge_units`（分层 merge 属 Wave 2，本文件仅定义契约）
- 契约测试：`tests/test_knowledge_distribution_contracts.py`
- Phase 上下文：`.planning/phases/15-retrieval-ssot-governance/15-CONTEXT.md`
