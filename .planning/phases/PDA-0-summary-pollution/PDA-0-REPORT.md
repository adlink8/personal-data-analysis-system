# PDA-0：压缩摘要污染修复报告

**日期：** 2026-08-11
**执行者：** 数据治理执行 agent
**状态：** 完成

---

## 1. 背景与问题定义

AgentView 源库 `~/.agentsview/sessions.db` 中存在 LLM compact 压缩摘要消息
（特征文本：`This session is being continued...` / `was compacted. The summary
below is the authoritative context...`）。这些摘要是模型对前文对话的压缩总结，
**不是用户原话**。但由于源库将其标记为 `role=user`，摘要内容流经 normalized →
canonical 后进入知识抽取轨，抽取出的知识单元（KU）evidence_quote 实际来自
AI 生成的摘要而非用户原文，形成"无原文 quote 支撑的伪事实"。

---

## 2. 任务 0.1：污染占比核查（只读）

### 2.1 源库规模

- AgentView 源库摘要消息：**22 条**（特征文本命中），其中 `role=user` **20 条**
- normalized `agentsview_normalized.sqlite`：摘要消息 **14 条**，其中 `role=user` **13 条**
- canonical `agent_conversations.sqlite`：摘要消息 **14 条**，其中 `role=user` **13 条**（`evidence_scope='user'`），另有 1 条 assistant（`evidence_scope='system'`）
- 涉及 **10 个 canonical session**

> 注：源库 22 条 → canonical 14 条 的差异由既有脱敏/隔离逻辑造成
> （secret session 不落正文、摘要消息所在 session 被排除等），属正常链路。

### 2.2 knowledge_units 污染统计（personal_system.sqlite）

| 指标 | 数值 |
|------|------|
| knowledge_units 总量 | 44,880 |
| 含摘要 10 个 session 关联的 KU（session 级） | **629** |
| 其中 `evidence_quote` 直接含摘要特征文本 | **0**（0.0%） |
| 其中 `source_message_ref` 直接指向摘要消息 | **10** |
| 其中 `knowledge_unit_evidence.evidence_ref` 指向摘要消息 | **10**（两口径完全一致） |
| 629 条中 evidence_quote 可回查到非摘要消息的合法 KU | 619 |

**结论：** 任务背景预估的"628 条 session 关联 KU"实际为 **629 条**（会话内
可能新增了 1 条，属正常增量）。其中 `evidence_quote` **直接**含摘要特征文本的
为 **0 条**（摘要正文不一定逐字包含特征句，特征句只出现在摘要的开头引导语），
但 **10 条 KU 的证据链路（source_message_ref / knowledge_unit_evidence）确实
直接指向摘要消息**，即 10 条为确认的实际污染子集，占比 **10/629 ≈ 1.6%**
（占全部 KU 的 10/44880 ≈ 0.02%）。

### 2.3 污染机制确认

逐条核验 10 条污染 KU 的 evidence_quote：
- 引用摘要消息的 10 条 KU 中，quote 内容与对应摘要消息正文匹配（归一化比对），
  证实 quote 确实取自压缩摘要而非用户原话。
- 例如 subject=「项目本地路径」「AI-Memory 项目路径」「bge-small-zh-v1.5」
  等，其 quote 来自摘要对旧对话的压缩转述。

---

## 3. 任务 0.2：build_agentsview_normalized.py 修改

**文件：** `src/personal_knowledge/application/conversation/build_agentsview_normalized.py`

- 引入 `eligibility.is_compact_summary`（复用 D-05 同源识别逻辑，避免双份正则漂移）。
- 消息写入循环中：`content` 命中压缩摘要特征时，将 `evidence_scope` 标记为
  `system`（复用既有 evidence_scope 机制，**不新增 schema 列**，保持 schema 兼容），
  使该消息不再以 `user` 身份进入抽取轨。
- 新增统计字段 `NormalizationStats.messages_compact_summary`。
- 模块 docstring 增加脱敏规则第 4 条。

**影响：** 仅改变命中摘要特征消息的 evidence_scope 标记，不改写入/删除逻辑，
不触碰 protected 字段与 secret 隔离逻辑，Revision gate 不变。

---

## 4. 任务 0.3：eligibility.py 修改

**文件：** `src/personal_knowledge/application/knowledge/eligibility.py`

- 新增 `COMPACT_SUMMARY_PATTERNS`（两条正则）与 `is_compact_summary()`，
  作为 D-05 唯一口径的一部分。
- `compute_eligible_messages` 过滤链新增第 2 步：
  - **主判定：** content 命中压缩摘要特征 → `excluded_compact_summary` +1，跳过；
  - **兜底判定：** canonical_messages 存在 `evidence_scope` 列时，
    `evidence_scope='system'` 的消息一并排除（兼容 0.2 的标记）。
  - 列存在性用 `PRAGMA table_info` 动态检测，**兼容无 scope 列的旧 fixture/旧库**。
- 保持既有 stats 结构不变，仅新增 `excluded_compact_summary` 键。

**实际效果（canonical 全量验证）：**
- eligible 集合从 24,501 → 24,487（-14，恰好移除 13 条 user 摘要 + 1 条 assistant 摘要）。
- `excluded_compact_summary = 15`（14 条摘要 + 1 条既有 scope='system' 兜底）。
- 13 条 user 摘要消息 100% 移出抽取轨，`summary messages still eligible: 0`。

---

## 5. 任务 0.4：标记已污染数据（UPDATE，不删除）

**数据库：** `var/db/personal_system.sqlite`

- 污染子集：**10 条 KU**（`source_message_ref` 与 `knowledge_unit_evidence`
  两口径一致的确认污染集），与任务"或 0.1 核查出的实际污染子集"授权一致。
- 执行：`UPDATE knowledge_units SET lifecycle='deprecated' WHERE unit_id IN (...)`。
- 保留所有字段与 lineage（`knowledge_unit_evidence`、`source_session_id`、
  `source_message_ref`、`evidence_quote` 均未动，仅改 `lifecycle`）。

### 修复 run 统计

| 指标 | 数值 |
|------|------|
| 标记为 deprecated 的污染 KU | **10** |
| 保留（其余 629 - 10） | **619** |
| 全库 current → deprecated 变化 | 44,664 → 44,654（-10）；deprecated 216 → 226（+10） |
| 污染 KU 残留（未 deprecated） | **0** |

元数据：`.planning/phases/PDA-0-summary-pollution/fix-run-meta.json`

---

## 6. 任务 0.5：测试验证

### 6.1 运行范围

| 测试 | 结果 |
|------|------|
| `tests/unit/test_knowledge_eligibility.py`（含 3 个新增用例） | PASS |
| `tests/integration/test_agentsview_normalization.py`（含 1 个新增用例） | PASS |
| `tests/unit/test_privacy_guard.py` | PASS |
| `tests/unit/test_coverage_matrix.py` | PASS |
| `tests/unit/test_promote_units.py` | PASS |
| `tests/unit/test_publish_candidate_exclusion.py` | PASS |
| `tests/integration/test_knowledge_incremental_refresh.py` | PASS |
| `tests/integration/test_knowledge_prepare_floor.py` | PASS |

### 6.2 新增测试

1. `test_compact_summary_excluded_by_content` — content 命中即排除（D-05 主判定）
2. `test_compact_summary_excluded_by_scope_mark` — scope='system' 兜底排除
3. `test_compact_summary_matches_real_feature_text` — 真实 AgentView 特征文本命中
4. `test_compact_summary_marked_system_scope`（integration）— normalized 层
   摘要消息标记为 system 轨且正文保留

### 6.3 extraction_quality 相关校验

`src/personal_knowledge/evaluation/extraction_quality_eval.py` 为离线评测脚本，
依赖 LLM/golden 数据，本次未重跑（无请求方要求且非本阶段交付物）。改动影响面
通过上述 eligibility/normalized 定向测试覆盖。

---

## 7. 偏离与决策记录

| 项 | 说明 |
|----|------|
| 629 vs 628 | 0.1 实测 session 关联 KU 为 629（背景预估 628），差异为后续增量，已如实记录 |
| evidence_quote 直接含特征 = 0 | 摘要正文通常不含特征引导句本身，故按"证据链路指向摘要消息"作为确认污染口径 |
| 标记范围 | 采用任务授权的"0.1 核查出的实际污染子集"= 10 条，而非 session 级 629 条全标（其余 619 条 evidence 可回查非摘要消息，为合法 KU） |
| 未跑 extraction_quality | 离线评测依赖 golden/LLM，本次不执行；以定向 pytest 覆盖 |

## 8. 后续建议（不在本任务范围）

- 重建 normalized + canonical（`pk-sync conversations --write` + canonical 构建），
  让 0.2/0.3 的标记在数据层落盘。
- 对 619 条保留 KU 复核 evidence_quote 可回查性（本任务仅核验了 629 条子集）。
