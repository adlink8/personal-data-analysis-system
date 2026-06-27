# Phase 04 Wave 5: 记忆图谱消费层(A+B)

**Created:** 2026-06-17
**Status:** Executed
**Depends on:** Wave 3(已完成:194条记忆 + memory_items/links/relations 表)
**Goal:** 把记忆图谱从"孤立的数据库"变成"可被检索系统和 AI 消费的活数据"

**Executed:** 2026-06-17
**Implemented files:** `统合模块/脚本/unified_search.py`, `统合模块/脚本/api_server.py`, `统合模块/脚本/mcp_server.py`, `统合模块/脚本/build_profile_from_memory.py`, `统合模块/脚本/run_pipeline.py`, `README.md`, `统合模块/README.md`

## 背景

Wave 3 完成了记忆对象层(tooling/preference/fact/project/habit/capability 6类,194条),
以及 memory_items / memory_links / memory_relations 三张表。
但当前这些记忆**只能通过单独脚本查看**,没有接入项目的主检索链路。

本 Wave 解决"最后一公里":让记忆图谱真正被用起来。

## 范围

两个交付(A + B):

- **A. 图谱接入检索** — 在 unified_search.py 增加 memory 查询能力,让"语义检索/精确查询"之外多一条"记忆查询"通道。
- **B. 生成 person_profile 图谱版** — 把记忆 + 关系导出成 Markdown,可直接注入 AI system prompt。

## 不做

- 不重构现有 unified_search 的语义/精确查询逻辑(只新增,不改)。
- 不引入 LLM 抽取/推理(纯规则查询)。
- 不做记忆的自动更新(增量抽取留到后续 Wave)。
- 不重写 dashboard(只补必要的记忆展示)。

---

## 任务拆解

### A. 图谱接入检索(unified_search.py 扩展)

**目标:** 让 unified_search 能查记忆,不只是查事件。

**子任务:**

1. 在 `unified_search.py` 新增 4 个纯函数:
   - `get_memory_profile(memory_type=None)` — 按类型取记忆概览(如所有 tooling)
   - `get_memory_by_subject(subject)` — 按主体查单条记忆(如 "Codex")
   - `get_memory_neighbors(subject, hops=2)` — N跳邻居(复用 query_graph 逻辑)
   - `get_memory_relations(subject)` — 该记忆的所有关系
2. 新增 CLI 子命令:
   - `python unified_search.py memory` — 列出全部记忆(按类型分组)
   - `python unified_search.py memory --type tooling` — 按类型过滤
   - `python unified_search.py memory --subject Codex` — 查单条 + 关系
   - `python unified_search.py memory --subject Codex --neighbors 2` — 含N跳邻居
3. 在 `api_server.py` 新增端点:
   - `GET /memory` — 记忆概览(可选 ?type= 过滤)
   - `GET /memory/<subject>` — 单条记忆详情 + 关系
4. 在 `mcp_server.py` 新增 MCP tool:
   - `get_memory_profile` — AI 调用,获取用户记忆概览

**验收:**
- `python unified_search.py memory --type tooling` 返回 21 条 tooling 记忆
- `GET /memory/Codex` 返回 Codex 记忆 + uses_tool 关系 + 关联能力
- 三个入口(CLI/API/MCP)行为一致

### B. person_profile 图谱版

**目标:** 把记忆导出成 AI 可读的 Markdown,替代/补充现有 person_profile.md。

**子任务:**

1. 新增 `build_profile_from_memory.py`(或扩展 build_context_doc.py):
   - 读 memory_items + memory_relations
   - 生成 `统合模块/分析数据/ai_context/person_profile_v2.md`
2. 文档结构(按 AI 消费优化):
   ```
   # 用户记忆画像(自动生成)
   
   ## 工具偏好(tooling)
   - 持续主力: Codex / ChatGPT / WorkBuddy / YouTube
   - 衰减: Claude(曾经主力,近3月淡出)
   - ...
   
   ## 内容关注(preference)
   ...
   
   ## 核心能力(capability)
   ...
   
   ## 关键事实(fact)
   ...
   
   ## 项目(project)
   ...
   
   ## 工作流习惯(habit)
   ...
   
   ## 记忆间关系(图谱摘要)
   - 你用 Codex 做 CLI搭建,关联开发技术主题
   - ...
   ```
3. 对比验证:
   - 与现有 person_profile.md 内容一致性检查
   - 确保新版本信息更全(含关系推理)

**验收:**
- person_profile_v2.md 包含全部 6 类记忆
- 含至少 5 条跨类关系描述(来自 memory_relations)
- 文档可作为 system prompt 注入(长度可控,< 4000 token)

---

## 风险

- unified_search 扩展时若改动现有函数签名,可能破坏 CLI/MCP/API 一致性 → 只新增函数,不改旧的。
- person_profile_v2 若过长,AI 注入会超 token → 加摘要模式(--summary)。
- 记忆数据若后续更新,profile 会过期 → 文档头部注明生成时间 + 数据快照版本。

## 实施顺序

1. **先做 A**(检索接入) — 让记忆"可查",这是基础。
2. **再做 B**(profile 生成) — 基于 A 的查询能力,生成更准的画像。
3. **最后验证** — 跑通 CLI/API/MCP 三个入口 + profile 对比。

## 成功标准

- 记忆图谱可通过 CLI / API / MCP 三个入口查询,行为一致。
- person_profile_v2.md 可直接注入 AI system prompt。
- 现有 unified_search/api_server/mcp_server 的旧功能不被破坏。
- 文档说明清楚"事件检索"和"记忆检索"的区别与配合方式。

---

*Wave 5 规划 · 基于 Wave 3 已交付的 194 条记忆 + memory_relations 表*
