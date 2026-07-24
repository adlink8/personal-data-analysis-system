# 门禁体系

> **一句话：** 系统在三个位置设了检查点——检索时（每结果过 6 关）、写入时（4 道关卡）、出站时（隐私封存）。任何一关不过就阻断，不给模糊空间。

---

## 场景：一次搜索过程中门禁做了什么

假设你搜 `rag-search "我的身份证号码是多少"`：

```
第 1 关：敏感查询检测
  查询含"身份证"→ "sensitive_value_request" → 阻断 ❌
  这条查询匹配的知识单元全部不返回

→ 搜索结果显示 abstain，一条结果都没有
```

假设你搜 `rag-search "Python 调试"`，知识层命中了一条知识单元：

```
第 2 关：生命周期检查
  知识单元的 lifecycle = "deprecated"（已标记为旧答案）
  → "lifecycle_not_current" → 阻断 ❌

第 3 关：隐私检查
  知识单元的 privacy = "secret"（涉及私密信息）
  → "privacy_or_provenance_veto" → 阻断 ❌

第 4-6 关：证据 + 词汇覆盖检查
  evidence 解析 → status = "ok"（证据可正常读取）
  query 和 candidate 的词汇重叠 = ["python", "调试"]
  → "eligible_evidence" + "query_candidate_grounded" → 通过 ✅
```

最终：这条知识单元出现在结果里，但 `support_reason_codes` 里能看到它通过了哪些检查。

---

## 检索门禁 6 关详解

代码位置：`retrieval/relevance.py`，函数 `decide_evidence_support()`

| 关卡 | 检查什么 | 触发条件 | 阻断后的 reason_code |
|------|---------|---------|-------------------|
| ① | 查询是否在要敏感信息 | 含"身份证/密码/API key/私钥/助记词" | `sensitive_value_request` |
| ② | 知识单元生命周期 | `lifecycle` 为 deprecated/superseded/conflict/retracted/deleted | `lifecycle_not_current` |
| ③ | 隐私标记/来源可用性 | `privacy` 为 secret/blocked/excluded/system/private_secret | `privacy_or_provenance_veto` |
| ④ | 必须字面量（仅查询含"仅当证据包含XXX"时触发） | 证据正文不含指定字面值 | `required_literal_absent` |
| ⑤ | 证据状态 | evidence status 为 ineligible/blocked/secret/missing | `evidence_ineligible` / `evidence_missing` |
| ⑥ | 词汇覆盖 | 查询词和知识单元无词汇重叠 | `query_candidate_ungrounded` |

### 第 ⑥ 关词汇覆盖怎么算

```python
# 从查询中提取特征词：
"Python 循环导入报错怎么解决"
  → CJK 二元组: {"循环", "导入", "报错", "解决"}
  → latin ≥ 2: {"python"}
  → 排除通用词({"用户", "个人", "信息", ...})
  → 最终: {"循环", "导入", "报错", "解决", "python"}

# 和候选文本对比：
"from a import b 导致循环引用，改为在函数内部导入"
  → 提取的特征词: {"循环", "导入", "引用", "function"...}

# 重叠量: {"循环", "导入"} → 2 个
# 如果重叠 ≥ 1 → 词汇覆盖通过
# 如果重叠 = 0 → query_candidate_ungrounded
```

### 不阻断但标注的：uncertain

6 关全过但证据不太确定时，不阻断但标记 `uncertain`，结果仍然返回：

| 状态码 | 含义 |
|--------|------|
| `evidence_reference_absent` | 知识单元没有证据引用（可能来自旧构建） |
| `evidence_unresolved` | 有引用但无法解析到具体证据 |
| `evidence_support_indeterminate` | 综合不确定 |

---

## 写入门禁 4 关

知识单元写入管线上设了 4 道关卡：

```powershell
① extract-gate    ← 提取完成后。检查：
                     yield ≥ 0.7（70% 以上成功提取）
                     隐私门禁通过
                     schema 有效
                     未通过 → 不能进入 canonical

② canary --strict ← 索引构建后。检查：
                     30 条测试查询
                     LLM 标签
                     critical 数量 = 0
                     未通过 → 不能 promote

③ promote         ← 晋升 active 时。检查：
                     canary strict PASS
                     eval gate PASS
                     未通过 → 保持当前 active

④ watermark       ← promote 后。检查：
                     promote 已完成
                     源 checksum 匹配
                     未通过 → 不推进水印
```

---

## 出站隐私封存

所有通过 REST API 和 MCP 返回的数据，在出站前过 `privacy_guard`：

```python
# 扫描所有字段，匹配以下模式 → [REDACTED]
sk-...              → OpenAI API Key
ghp_...             → GitHub Token
AIza...             → Google API Key
-----BEGIN PRIVATE KEY----- → 私钥
access_token=...    → 访问令牌
身份证号、护照号    → 个人身份信息
```

REST 用 `guard_jsonable()` 扫描 JSON 中所有值，MCP 用 `guard_mcp_payload()` 扫描格式化后的文本。保持结构不变，只替换敏感值。

---

## LLM 调用错误分类

知识提取时 LLM 调用会失败，分类处理：

| HTTP 状态码 | 分类 | 行为 |
|------------|------|------|
| 429 | retryable | 重试（最多 6 次） |
| 500, 502, 503 | retryable | 重试 |
| 400, 401, 403, 404 | terminal | 立即失败，标记为 terminal_failed |
| 超过 6 次重试 | → 升格 terminal | 防止死循环 |

---

## 门禁状态码速查表

| 看见这个 | 说明 | 在哪关 |
|----------|------|--------|
| `sensitive_value_request` | 查询在要密码/密钥，被拦截 | 检索 ① |
| `lifecycle_not_current` | 知识单元已弃用/冲突 | 检索 ② |
| `privacy_or_provenance_veto` | 隐私标记或来源不可用 | 检索 ③ |
| `required_literal_absent` | 必须字面量不在证据里 | 检索 ④ |
| `evidence_ineligible` | 证据状态为不可用（blocked/secret） | 检索 ⑤ |
| `evidence_missing` | 证据找不到 | 检索 ⑤ |
| `query_candidate_ungrounded` | 查询词和候选无词汇重叠 | 检索 ⑥ |
| `eligible_evidence`, `query_candidate_grounded` | ✅ 通过 | 检索 ⑥ |
| yield < 0.7 | 提取成功率太低 | 写入 ① |
| critical > 0 | 金丝雀发现严重问题 | 写入 ② |
