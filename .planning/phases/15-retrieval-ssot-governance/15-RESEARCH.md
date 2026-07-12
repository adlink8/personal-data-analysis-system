# Phase 15 RESEARCH — 调查资料清单与结论

**Date:** 2026-07-12  
**Method:** 实库探测 + 既有代际对比报告 + 代码路径阅读  
**Status:** 调查完成，足以进入 PLAN

---

## 1. 推荐方向（结论）

### 最推荐：Phase 15「检索 SSOT + 分层 Fallback 治理」

**为什么不是别的：**

| 候选方向 | 为何不优先 |
|---|---|
| 立刻 Google 全量 KU | 活动日志 ≠ 用户断言；extractor 不适用；ROI 低于检索纠偏 |
| 删 raw / 清 Chroma | 用户明确保留对照；且 Google 仍依赖 raw |
| Phase 08 memory 合并 | 与 career-os/KU 主路径弱相关；291 vs 30k 已说明 KU 为 SSOT |
| 只刷 hybrid 到 0.85 不改路由 | 在错误 fallback 上调参，治标不治本 |

**本方向同时处理：** 架构清晰度 + G1 证据 + G2 召回 + View 对齐。

---

## 2. 调查资料清单（GSD 编排）

### 2.1 必读文档（已存在）

| ID | 路径 | 用途 |
|---|---|---|
| R01 | `integration/analysis/ai_context/generation_gap_analysis.md` | 合并缺口 G1–G10 |
| R02 | `…/vector_generation_comparison.md` + charts | 向量代际数据 |
| R03 | `…/sqlite_generation_comparison.md` + charts | SQLite 分层数据 |
| R04 | `.planning/phases/14-*/14-CONTEXT.md` | KU 硬约束（不写 View、evidence） |
| R05 | `.planning/phases/13.5-*/13.5-CONTEXT.md` | AgentsView 只读/canonical |
| R06 | `integration/scripts/source_adapters/agentsview.py` | View adapter 契约 |
| R07 | `integration/scripts/vector/unified_search.py` | hybrid 实现 |
| R08 | `integration/scripts/knowledge/build_knowledge_inventory.py` | inventory 仅 canonical |
| R09 | `Google/structured/db/google_data_README.md` | Google 旧层能力 |
| R10 | `.planning/STATE.md` / `ROADMAP.md` | 进度与开放项 |

### 2.2 必跑探针（已跑，可复跑）

| ID | 命令 / 脚本 | 产出 |
|---|---|---|
| P01 | `_tools/_audit_raw_fallback_coverage.py` | View vs personal_events vs Google 覆盖 |
| P02 | `_tools/_inspect_agentsview.py` | live View 表规模 |
| P03 | `_tools/_inspect_agentsview_insights.py` | insights 几乎为空 |
| P04 | `vector/compare_vector_generations.py` | 向量对比 JSON/图 |
| P05 | `vector/compare_sqlite_generations.py` | SQLite 对比 JSON/图 |
| P06 | `_tools/build_generation_gap_analysis.py` | 缺口合并 |
| P07 | `python -c` Chroma counts + source dist | personal_events 源分布 |

### 2.3 规划前仍建议补的「薄调查」（PLAN Wave 0）

| ID | 问题 | 方法 | 完成标准 |
|---|---|---|---|
| I01 | frozen 20 题中哪些是 code-literal vs profile | 人工/脚本标注 `suite_tag` | 标注文件入库 evals/ |
| I02 | hybrid 未命中的 5 题 raw 来自哪 collection/source | 跑 evaluate + per_query dump | 表：miss → source |
| I03 | draft 无 evidence 的 unit 是否都有 `source_message_ref` | SQL | 可回填比例 ≥ X% |
| I04 | conversation_turns 对 code 题 R@5 | 现成 evaluate 或小脚本 | 数字进 RESEARCH 附录 |
| I05 | Google activity 是否值得轻量「主题断言」 | 抽样 50 条人工 | go/no-go Phase 16 |

**I01–I04 为 Phase 15 执行前 Wave 0；I05 可并行但不阻塞。**

---

## 3. 关键实测摘要（调查结果）

### 3.1 AgentsView / canonical

| 指标 | 值 |
|---|---:|
| View messages | 58,321 |
| canonical messages | 57,765（~99%） |
| View sessions | 624 |
| inventory source=agentsview | 18,736 |
| KU evidence 全部 `cm|` | 15,589 / 15,589 |
| insights 有效行 | 0（1 行 403 失败） |

### 3.2 personal_events（当前 raw fallback）

| source | count | 含义 |
|---|---:|---|
| Agent | 5,857 | 多为 file/session/skill/memory，**非** message 流 |
| GPT | 3,123 | 导出消息事件 |
| Google | 2,016 | 活动+附件 |
| **合计** | **10,996** | |

→ **对话不全；跨源兜底有用。**

### 3.3 Google 结构化深度

| 层 | 状态 |
|---|---|
| activities + FTS | 有（1696 + 320 附件） |
| normalized_events | **0 行** |
| knowledge inventory / KU | **无** |
| personal_events | 有 2016 |

### 3.4 质量缺口（from generation_gap_analysis）

| ID | 优先级 | 当前 | 目标 |
|---|---|---|---|
| G2 hybrid R@5 | P0 | 0.75 | 0.85 |
| G1 evidence 覆盖 | P1 | 0.511 | 0.85 |
| G3 pure KU R@5 | P1 | 0.65 | 0.75 |
| G6 抽取 residual | P1 | success 0.87 | ≥0.9 / terminal→0 |
| G8 memory vs KU | P2 | 291 vs 30k | 文档 SSOT |
| G9 Chroma 堆积 | P3 | deferred | 对照后再清 |

---

## 4. 架构目标态（检索）

```text
                    ┌─────────────────────┐
                    │  query (CLI/REST/MCP)│
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │ 1. Knowledge Units  │  active collection
                    │    (SSOT 知识)       │
                    └──────────┬──────────┘
                               │ slots 不足或 low score
                               ▼
                    ┌─────────────────────┐
                    │ 2. Dialogue fallback│  canonical / turns
                    │    (SSOT 采集证据)   │  可选 View FTS 只读
                    └──────────┬──────────┘
                               │ 仍不足且 query 偏活动/搜索
                               ▼
                    ┌─────────────────────┐
                    │ 3. Non-dialogue raw │  personal_events
                    │    source=Google…   │  (旧跨源)
                    └─────────────────────┘
```

---

## 5. 风险与依赖

| 风险 | 缓解 |
|---|---|
| dialogue 向量化成本 | 优先复用 `conversation_turns`；必要时 message 子集 embed |
| 改 hybrid 回归 | 保留 flag `--fallback legacy|layered`；契约测试双模式 |
| evidence 回填误挂 | 只信 `source_message_ref` / member 映射；gate 校验 ref 存在 |
| Google 用户期望 KU | 文档明确 Phase 16；本阶段不交付 Google KU |

---

## 6. 建议不纳入本阶段的调研

- AgentsView insights 产品化（额度 403，非主路径）
- mem0 / 深层图谱再实验
- career-os 批同步

---

## 7. Wave 0 检查清单（进入编码前勾选）

- [x] I01 suite_tag 标注 frozen+dev
- [x] I02 hybrid miss 归因表
- [x] I03 evidence 可回填比例
- [x] I04 conversation_turns 分场景 R@5
- [x] 更新 `15-RESEARCH.md` 附录数字
- [ ] 用户确认 D-02 过渡期是否允许 dual fallback（legacy + layered）

---

## Wave 0 Results

**Executed:** 2026-07-12 (I01–I04 investigation scripts; read-only DBs/Chroma)  
**Active KU collection:** knowledge_units_run_76c6259e_20260712062418 (30,012)  
**Artifacts:**
- integration/evals/knowledge_units/suite_tags.json
- integration/analysis/ai_context/phase15_hybrid_miss_audit.json
- integration/analysis/ai_context/phase15_evidence_backfill_feasibility.json
- integration/analysis/ai_context/phase15_turns_baseline.json
- probe script: integration/scripts/_tools/phase15_wave0_investigate.py

### I01 suite_tag counts (frozen+dev = 40)

| tag | overall | frozen | dev |
|---|---:|---:|---:|
| code | 10 | 6 | 4 |
| mixed | 18 | 7 | 11 |
| profile | 12 | 7 | 5 |
| google | 0 | 0 | 0 |

No eval query is Google-activity-like; google tag reserved for future suite expansion.

### I02 hybrid miss audit (frozen 20, gold_evidence_refs match)

| collection | R@5 |
|---|---:|
| knowledge_units (active) | 0.65 |
| personal_events | 0.50 |
| conversation_turns | 0.05 |
| hybrid_legacy (KU ∪ PE) | **0.80** |

- **miss_all (4):** frozen-001 (Azure JSON error dump), frozen-004 (agent rules/skills), frozen-011 (hardware card Q), frozen-016 (WPF C# source)
- **PE-only hits (3):** frozen-005, 009, 018 — raw still rescues some code/agent-history items
- **KU-only hits (6):** frozen-002, 003, 014, 017, 019, 020
- **turns_rescue:** none of the hybrid misses are saved by conversation_turns
- **PE top1 source dist:** Agent 10 / GPT 10 (Agent top1 often agent_file, not dialogue) — confirms personal_events is a poor dialogue SSOT

### I03 evidence backfill feasibility (live personal_system.sqlite)

| metric | value |
|---|---:|
| draft knowledge_units | 30,517 |
| with evidence rows | 30,517 |
| without evidence | **0** |
| live evidence coverage | **1.000** |
| stale gap-report coverage | 0.511 (sqlite_generation_comparison @ 07:49Z) |
| unique evidence_ref resolvable in canonical_messages | 13,579 / 13,579 (100%) |
| auto-backfill candidates (missing ev + resolvable smr) | **0** |
| canonical units with reachable member evidence | 30,012 / 30,012 |

**Implication:** presence-level G1 is already closed on live DB; bulk source_message_ref backfill is not the bottleneck. Refresh gap inventory metrics; residual work is multi-evidence depth / export path / gate, not fill-from-smr.

### I04 conversation_turns baseline by suite_tag (frozen)

| suite_tag | n | PE R@5 | KU R@5 | turns R@5 | avg top1 dist (PE / KU / turns) |
|---|---:|---:|---:|---:|---|
| code | 6 | 0.50 | 0.50 | **0.17** | 0.137 / 0.299 / 0.272 |
| mixed | 7 | 0.57 | 0.57 | 0.00 | 0.159 / 0.243 / 0.228 |
| profile | 7 | 0.43 | **0.86** | 0.00 | 0.158 / 0.211 / 0.278 |
| overall | 20 | 0.50 | 0.65 | 0.05 | — |

**Notes:**
- Profile is KU-strong (0.86); code is split and still weak on pure turns (3601 docs only).
- conversation_turns does **not** currently beat personal_events as gold-ref fallback; layered dialogue fallback needs denser message-level vectors/FTS, not turns alone.
- hybrid_legacy 0.80 on this audit (prior gap headline hybrid 0.75) — still short of 0.85 target; remaining misses are hard code-literal / system-prompt noise.

*Research assembled 2026-07-12 for GSD Phase 15 planning.*
