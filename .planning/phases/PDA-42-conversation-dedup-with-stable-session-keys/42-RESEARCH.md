# Phase 42 Research: Conversation Dedup with Stable Session Keys

**Researched:** 2026-07-27
**Inputs:** 42-CONTEXT.md（D-01~D-05 已锁）、ROADMAP Phase 42（DED-01/DED-02）、build_canonical_agent_conversations.py / build_agentsview_normalized.py / agentsview.py / eligibility.py / refresh_knowledge_units.py 源码、canonical/normalized/legacy/unified 四库只读实测、AgentsView live 库只读探测（mode=ro + query_only）
**Requirements:** DED-01（稳定键去重 + supersede 语义）、DED-02（全量重建幂等 + 跨运行确定性）

> 注：DED-01/DED-02 的正式条文只存在于 `ROADMAP.md:140-152`（success criteria 即定义）；`.planning/REQUIREMENTS.md` 是 v1.4 需求集，未收录 DED 组。Planner 应以 ROADMAP 的两条 success criteria 为验收基准。

---

## 0. 一句话结论

去重键唯一现状是 file_hash（Pass 1 精确匹配，`build_canonical_agent_conversations.py:298-344`），而 AgentsView 的 `sessions.id` 本身就是**跨 append 稳定的原生复合键**（`codex:<rollout-uuid>`、`zcode:sess_…` 等，实测 6/6 双份会话都能靠它唯一对上 AV 侧活会话）——推荐把 crosswalk 的第一优先级从 file_hash 换成 **(source, AV sessions.id / legacy 原生 id 归一)** 的 source_mapping pass（schema 里 `match_method='source_mapping'` 早已预留、`merged_by_source_mapping` 统计字段声明了却从未实现），file_hash 降级为变更检测。canonical store 是**每次 sync 全量 DROP+重建**的，所以"迁移"分两半：canonical 侧的 supersede 标记必须由 builder 每次重建时确定性生成（一次性脚本会被下次 sync 冲掉），unified DB 侧的 evidence ref 重映射才是真正的一次性迁移（存量影响面小：40 个 evidence ref + 89 个 unit source ref 落在 6 个双份会话里）。**evidence ref 不受会话键重铸影响**——`cm|` id 的铸造不含 canonical_session_id。

---

## 1. Q1 — 现状精确画像（全部实测，2026-07-27）

### 1.1 去重键现状：只有 file_hash，一处铸键三处受害

| 环节 | 位置 | 行为 |
|---|---|---|
| Pass 1 merge 键 | build_canonical_agent_conversations.py:298-305 | `AV sessions.file_hash == legacy source_files.sha256` 精确匹配；merged csid = `cs\|merged\|<file_hash>`（**身份随内容漂移**） |
| `av_by_hash` 覆盖写 | :276-281 | 同 hash 多 AV 会话时后写覆盖先写（实测当前 normalized 与 AV live 库 dup file_hash 组均为 0，是潜在而非现实风险） |
| Pass 2 AV-only csid | :351 | `cs\|agentsview\|<av_sid>` —— **已经是稳定键**，AV-only 会话无身份漂移问题 |
| Pass 3 legacy-only csid | :386 | `cs\|legacy\|<legacy_session_id>` —— 稳定，但与 AV 侧同一会话失联即成双份 |
| source_mapping 匹配 | 模块 docstring :8-10 声明为优先级 2；schema :96 预留 `match_method='source_mapping'`；stats :136 预留 `merged_by_source_mapping` | **从未实现**（实测 session_source_links 中 source_mapping 计 0；crosswalk_review 0 行） |

失败链（与审计一致，已实测复现）：会话 jsonl 追加 → AV `file_hash` 变 → 与 legacy 快照 `sha256`（冻结值）不再相等 → Pass 1 失配 → AV 侧进 Pass 2、legacy 侧进 Pass 3 → **同一会话两份 canonical session，双双 evidence_eligible=1**。

### 1.2 双份实测规模

canonical 库（926 sessions / 80,516 messages）：

| 指标 | 实测值 |
|---|---|
| canonical_sessions 总数 | **926**（AV-only 645 + merged 275 + legacy-only 6） |
| canonical_messages | 80,516（agentsview 77,712 + legacy 2,804；legacy 中 470 条是 merged 空壳填充、2,334 条在 legacy-only 会话里） |
| **现存双份组** | **6 组 / 12 个 session 行**（全部 codex；6 个 legacy-only 会话逐一在 AV live 按 `codex:<rollout-uuid>` 找到唯一活体，且 AV 侧消息数均 ≥ legacy 侧，如 1234→1550、223→2762，即"legacy=旧快照、AV=增长后同会话"） |
| 双份消息重复度 | legacy-only 2,334 条消息中 **2,220 条（95.1%）** content_hash 与 AV 侧消息完全一致 |
| 潜在双份池 | **275 个 merged 会话**——身份键是 `cs\|merged\|<fh>`，任何一个文件再追加一次就裂成新双份对，且 merged csid 本身漂移 |
| 同会话内重复 ordinal | 0（`(canonical_session_id, ordinal)` 无重复） |
| file_hash 为空的 AV 会话 | 264 个（chatgpt 等无文件源）——**file/hash 系身份对它们天然不可用**，原生 id 键可覆盖 |
| crosswalk_review | 0 行 |

按内容 hash 找到的 6 组 supersede 映射预览（迁移输入）：

| legacy-only csid（应 superseded） | AV twin csid（应保留） | 共享 content_hash |
|---|---|---|
| cs\|42579d9d… | cs\|64f51710… | 11/24 |
| cs\|319cc8d9… | cs\|a20c67e8… | 571/1218 |
| cs\|a041f296… | cs\|7334fcf7… | 105/219 |
| cs\|4710f90b… | cs\|41230a03… | 377/773 |
| cs\|738d57ef… | cs\|aa99a0e2… | 26/54 |
| cs\|1aa78d8e… | cs\|1481aa68… | 9/20 |

（"共享/总数"低于 95.1% 消息级重复率是因为这里限定 content_length>10 且按 distinct content_hash 计；短消息和多次重复的命令行占了差额。ordinal 无法直接对齐——legacy 填充的 ordinal 是自计数、与 AV ordinal 体系不同——**D-03 的"ordinal 对齐"实际要落地为 content_hash 对齐为主、ordinal 就近为辅**。）

### 1.3 Phase 41 evidence 引用的回溯安全性（关键结论：改键不破坏 ref）

`cm|` id 铸造与 canonical_session_id **无关**：AV 侧 `_norm_id("cm","av",<AV messages.id>)`（:541），legacy 侧 `_norm_id("cm","legacy",<legacy session_id>,<event_index>)`（:604）。所以**重铸会话键 / merged csid 换算法，全部 evidence ref 原样存活**。实测 KU 侧引用分布：

| 指标 | 实测值 |
|---|---|
| knowledge_units | 41,035；knowledge_unit_evidence 56,142 行 / 23,009 distinct refs |
| evidence refs 可解析到当前 canonical | 22,253 / 23,009（**756 个已孤儿，3.3%，且全部不在 knowledge_dead_refs 里——静默漂移存量债**，knowledge_dead_refs 22,548 distinct 全是 run_abandoned/schema_invalid/terminal 类） |
| units.source_message_ref 可解析 | 39,897 / 41,035（1,138 未解析）；inventory items 40,526 / 41,605 |
| refs 落在 **legacy-only 双份会话** | evidence 表 40 个 distinct ref；units.source_message_ref 89 个 unit |
| refs 落在任何 legacy-source 消息（含 merged 填充） | evidence 表 90 个 ref；units 195 个 |

⇒ D-03 的 ref 映射存量工作量是**两位数**（40+89），不是全量重铸；756 个既有孤儿是上游 AgentsView 行为（re-normalization 使 `messages.id` 换新 / 会话重铸）造成的**另一类债**，本 phase 只记账不背锅（见 §6 R4）。

### 1.4 已存在的缓冲：eligibility 的 content_hash 去重

`eligibility.py:188-192` 按清洗后 content_hash 全局去重（扫描序 `started_at DESC`，:158）——双份会话中内容相同的消息**只有一份进 eligible 集**。所以双份的现实危害不是"KU 双倍抽取"，而是：(a) 双份都可被检索/下钻/计数（覆盖矩阵、UI、doctor 统计失真）；(b) 代表 ref 在 `cm|av|…` 与 `cm|legacy|…` 之间取决于 started_at 排序，键序一变 ref 就换人（inventory churn）；(c) 无 supersede 语义，旧副本永不退场。

---

## 2. Q2 — 稳定键候选评估（服从 D-01：(source, source_session_id) 复合键）

AgentsView live 库只读探测（`sessions` DDL + 逐 agent 抽样）：

| 候选 | 实测语义 | 评估 |
|---|---|---|
| **AV `sessions.id`（TEXT PRIMARY KEY）** | 已是 `agent:原生会话标识` 复合形态：`codex:019eb17a-…`（rollout uuid）、`zcode:sess_…`、`workbuddy:<uuid>`、`chatgpt:<uuid>`、claude 主会话 `<uuid>` / 子代理 `agent-xxx`。库里有 `next_ordinal`/`last_entry_uuid`/`last_write_incremental`/`transcript_revision` 增量追加簿记 → **append 不换 id**（id 唯一性实测 0 重复，deleted_at 全空） | **推荐**。normalized `sessions.source_session_id` 已原样保存它（build_agentsview_normalized.py:99），链路零新增拷贝 |
| AV `source_session_id`（列） | 外部 lineage，仅 claude/grok/qoder 有值且**不唯一**（实测 1 个 ref 挂 19 个会话：主会话+18 个 subagent 共享）| 不能当身份键；可作 relation 辅助 |
| file_path / file_inode | live 库有 `file_path/file_inode/file_device`，但 normalized 白名单未复制路径（隐私）；zcode/mimocode 等是 `db.sqlite#sess_…` 虚拟路径 | 不引入；隐私面扩大且非必要 |
| 首消息 hash | 会话开头可能被 compact/重写（`is_compact_boundary` 存在） | 否 |
| file_hash | 天然随内容漂移（本 phase 要修的对象） | 降级为变更检测信号（D-01） |

**legacy 侧稳定键与跨源对齐键**：legacy `session_id` = rollout 文件名 stem（`rollout-<ts>-<uuid>`），其内嵌 uuid 与 AV `codex:<uuid>` 一一对应（6/6 实测命中且唯一）。归一函数：`legacy session_id --regex--> <uuid>` ⇔ `AV id 去 "codex:" 前缀`。legacy 只有 Codex（281 unique / 831 meta 行），归一规则单一。

**推荐落法**（属 discretion，给 planner 的具体建议）：
- canonical 会话身份 = `cs|av|<AV sessions.id>`（AV 在场时，不再区分 merged/AV-only 两种铸法）、`cs|legacy|<legacy_session_id>`（真 legacy-only）。即：**取消 `cs|merged|<fh>` 铸法**，merged 与否只体现在 `merged` 列和 source_links。275 个 merged 会话的 csid 会换值——安全性见 §5.1。
- crosswalk 匹配顺序改为：Pass 1 = source_mapping（native id 归一相等，strong）；Pass 2 = file_hash 相等（作确认信号/兜底，同时校验与 Pass 1 一致性，不一致计数进 stats）；Pass 3/4 = 单源。
- `session_source_links.match_method` 沿用既有 CHECK 值 `source_mapping`，无 schema 改动。

---

## 3. Q3 — 迁移策略

### 3.1 关键架构事实：canonical 是全量重建，"迁移"必须拆两半

`_write_canonical_store` 每次 DROP TABLE + staging + `os.replace`（:436-439, 641-650）。**对 canonical DB 做一次性 UPDATE 的迁移脚本会被下一次 `pk-sync conversations` 无痕冲掉。**因此：

1. **canonical 侧（builder 改造，非一次性）**：稳定键 crosswalk + supersede 标记逻辑写进 `build_crosswalk`，每次重建确定性重算。D-03 的"保留消息最全/最新的一份，其余标 superseded"：
   - 强匹配（native id 对上）：并成一个 canonical session（同今日 file_hash merge 的待遇），legacy 行保留在 `session_source_links`（match_method=source_mapping）——**这是 6 组存量双份的归宿**，"不硬删"由 source_links 的 lineage 回查性满足；
   - 需要独立 superseded 行的情形（弱匹配、或同源两份都存在时）：canonical_sessions 增列 `lifecycle TEXT DEFAULT 'active'` + `superseded_by_canonical_id TEXT`（幂等 ALTER 由 builder schema 定义直接扩展即可，反正全量重建），superseded 行 `evidence_eligible=0` + `ineligible` 原因走既有语义;
   - eligibility 无需改 SQL（`s.evidence_eligible=1` 过滤天然排除 superseded，eligibility.py:155）。
2. **unified DB 侧（一次性迁移脚本，参照 tools/migrations 形态）**：把落在被 supersede 副本上的 ref 重映射到保留副本的同内容消息——`knowledge_unit_evidence.evidence_ref`（40 个）、`knowledge_units.source_message_ref`（89 个）、`knowledge_inventory_items.evidence_ref`（同键连带）。映射键：**cleaned content_hash 相同 + 同会话对**（95.1% 可映射）；一对多时取 ordinal 最近者；映射不了的写孤儿报告（D-03/D-05，预计 ≤114 条消息对应的 ref 子集）。脚本形态照抄 `tools/migrations/backfill_ku_data_debts.py`：dry-run 默认、`--write` 先备份 `var/backups/personal_system_<ts>.sqlite`、单事务、统计报告（:239-271）。

### 3.2 crosswalk 受影响面

- `_legacy_session_to_hash` / `_build_legacy_file_hash_index`（:193-259）保留，但产物从"身份判定"降级为"变更检测 + 一致性校验"。
- Pass 1 的 `leg_sessions[0]` 代表行（:303-304）与 `_load_legacy_sessions` 去重保首条（:182-190）：**D-04 落地点**。现状 `SELECT … FROM agent_sessions_meta` 无 ORDER BY，831 行去重到 281，代表行取决于物理扫描序（agent_data.sqlite 冻结所以当前碰巧稳定，VACUUM/重建即漂移；实测同 session_id 双行 timestamp 确实不同：`2026-05-06T12:00:33` vs `14:13:55`）。改法：SQL 加 `ORDER BY timestamp ASC, raw_file ASC, rowid ASC`，Pass 1 组内代表行同规则排序后取首。
- `_load_agentsview_sessions`（:152-158）同样无 ORDER BY——顺带加 `ORDER BY started_at, session_id`，让 stats/输出顺序也确定。
- `CrosswalkStats.merged_by_source_mapping`（:136）终于有增量来源；新增计数：`stable_key_matched`、`file_hash_confirmed`、`file_hash_divergent`（=检测到内容增长）、`superseded_marked`、`ref_remap_failed`（D-05：失败不静默）。

### 3.3 顺序建议（降低 delta 归因噪声）

normalized 快照严重滞后：import_runs 生成于 **2026-07-16**，AV live 已 1,159 sessions / 102,881 messages（normalized 920/含 77,712 条入 canonical），kimi 等新 agent 完全缺席。**建议先用旧代码跑一次干净 `pk-sync conversations --write` + 正常 inspect/prepare 周期消化数据增量，再上 Phase 42 改键重建**——否则"改键造成的 delta"和"12 天数据积压的 delta"混在一起无法验收。

---

## 4. Q4 — 幂等性验证方案（可执行）

### 4.1 重建幂等（DED-02 主命题）

```bash
# 固定输入：拷贝 normalized + legacy 到临时目录，连续两次构建到不同 dest
python -m personal_knowledge.application.conversation.build_canonical_agent_conversations \
  --write --av-db <tmp>/norm.sqlite --legacy-db <tmp>/legacy.sqlite --dest-db <tmp>/canon_a.sqlite
python -m personal_knowledge.application.conversation.build_canonical_agent_conversations \
  --write --av-db <tmp>/norm.sqlite --legacy-db <tmp>/legacy.sqlite --dest-db <tmp>/canon_b.sqlite
```

比对（python，两库全表 sorted dump 的 sha256 必须相等；`compute_source_checksum(canon_a)==compute_source_checksum(canon_b)` 亦必须相等——它含逐条 content hash，比行数比对强）。

### 4.2 零重复验收 SQL（重建后对正式库跑，全部期望 0）

```sql
-- A. 一个源会话只允许归属一个 canonical session
SELECT COUNT(*) FROM (SELECT source, source_session_id FROM session_source_links
  GROUP BY 1,2 HAVING COUNT(DISTINCT canonical_session_id)>1);
-- B. 稳定键唯一：active canonical session 不允许共享稳定键
SELECT COUNT(*) FROM (SELECT s.source, s.source_session_id FROM session_source_links s
  JOIN canonical_sessions c USING(canonical_session_id)
  WHERE c.lifecycle IS NULL OR c.lifecycle='active'
  GROUP BY 1,2 HAVING COUNT(DISTINCT s.canonical_session_id)>1);
-- C. 消息键唯一
SELECT COUNT(*) FROM (SELECT canonical_session_id, ordinal FROM canonical_messages
  GROUP BY 1,2 HAVING COUNT(*)>1);
-- D. codex 双份归零：legacy-primary eligible 会话中，内嵌 uuid 能在 AV 链接里找到的 = 0
--（实现为迁移报告断言或 doctor 检查；uuid 提取在 SQL 里用 substr/instr 或落到 python）
```

### 4.3 增长≠新会话（DED-01，fixture 单测）

fixture normalized DB：会话 X（n 条消息，file_hash=H1）构建 → 追加 2 条消息、file_hash 改 H2 → 重建：断言 canonical_session_id 不变、消息为超集、canonical_sessions 行数不变、stats.file_hash_divergent=1。

### 4.4 重跑 sync 端到端

`pk-sync conversations --write` 连续两次（第二次 AV 快照若无新会话）：`import_runs.dataset_hash` 一致、§4.2 全 0、`pk-ku inspect` 第二次 `source_changed=false`（watermark checksum 等值实测口径：当前 `committed`=`committed_assistant`=`87e24e2a…` 且等于现库 checksum，说明该判据在实践中有效）。

---

## 5. Q5 — 下游影响面

### 5.1 canonical_session_id 换值（275 个 merged + 6 个并入）影响谁

| 消费方 | 位置 | 影响 |
|---|---|---|
| evidence ref（KU 全链） | cm\| 铸造 :541/:604 | **无影响**（不含 csid；§1.3 实测） |
| EvidenceResolver | retrieval/evidence.py:68-81 | 按 cm ref 查消息再 JOIN session 查 evidence_eligible；动态列探测（`_columns`），**加列安全**；superseded 副本消息 resolve → `ineligible` 属预期（ref 已被迁移走） |
| conversation_repository / turns | core/conversation_repository.py:175-193 | 全量迭代，csid 只作分组键，重建后自然一致 |
| serving snapshot | application/serving/snapshots.py:409-414 | `d.canonical_conversation`/`d.canonical_message` 的 version=DB 文件 checksum，任何重建本来就换版本，无键耦合 |
| UI projection / api | services/ui_projection.py | evidence resolve 走 stable_id=cm ref + snapshot checksum，不持久化 csid |
| session_relations / parent_canonical_id | :624-636 | 同库同轮重建，内部一致；parent 回填缺失是既有 L3 债（deferred） |

### 5.2 watermark / checksum（研究问题里的"伪 delta"担忧，实测定性）

`compute_source_checksum`（refresh_knowledge_units.py:64-85）= schema hash + 计数 + **逐条 (canonical_message_id, content_hash)**。Phase 42 必然使它变化（加列改 schema hash；superseded 副本消息仍在库里但其 eligible 集变化）。后果链：`source_changed=true` → inspect 出 delta。其中：
- **new_refs**：改键本身不产生（cm id 不变）；
- **deleted_refs**：被 supersede 副本的 eligible 消息退出 `compute_eligible_messages`（evidence_eligible=0）→ 若其 ref 曾进 inventory 则出现在 deleted_refs → 走 affected_subjects/lifecycle 流程。量级 = 双份副本中曾入 inventory 的 ref 数（上限 2,334 中 eligible 且入过 inventory 的部分；且 95.1% 内容与保留副本重复、eligibility 去重本来只放行一份，实际远小于上限）。
- **不是伪 delta，是真实的口径修正**——与 41-RESEARCH R6 同型，plan 里写明"首轮 delta 突增为预期"，避免 Gate B STOP 反射。user/assistant 两条 watermark key（`committed`/`committed_assistant`，refresh:1693）都会经历同一次突变，两轨都要走一次受控 inspect→prepare。

### 5.3 doctor / 覆盖矩阵

- 41 已落地 coverage_matrix（application/knowledge/coverage_matrix.py）以 canonical 为分母——supersede 生效后 legacy 双份退出分母，矩阵数值小幅下修（预期，报告里注明）。
- 42-CONTEXT 建议的新 doctor 检查项：**双份率**（§4.2 的 B/D 两条 SQL 包成 `_check_session_dedup`，warn-only，不进 hard_fail_ids），与迁移孤儿报告数一起呈现。

---

## 6. Q6 — 风险与红线

| # | 风险/红线 | 等级 | 处置 |
|---|---|---|---|
| R1 | **AgentsView live 只读**：任何连接 mode=ro + query_only（adapters/agentsview.py:3-12），本 phase 所有"原生 id"都从 normalized 库取，不新增对 live 库的依赖路径 | 红线 | 已满足：normalized `source_session_id` 就是 AV id |
| R2 | **不硬删**：superseded 走标记（lifecycle 列 + source_links 保留 lineage）；normalized 的 source_tombstones（secret/excluded/deleted/source_disappeared）语义不动 | 红线 | builder 内实现，§3.1 |
| R3 | **不重铸 cm\| id**：D-02 的"(session_key, ordinal) 消息身份"只作**对齐/去重键**使用；若把 AV 侧 cm 铸造从 `<AV messages.id>` 换成 `(session_key, ordinal)`，23,009 个 evidence ref 全体作废。本 phase 保持铸法不变 | 红线 | 明写进 plan 的"不做" |
| R4 | **既有 756 个静默孤儿 ref**（3.3%，不在 dead_refs）：根因是 AV `messages.id` 为整型自增，AgentsView full re-normalization（transcript_revision 翻转）会换 id → cm id 漂移。本 phase 不修（那是消息身份重铸，被 R3 挡住），但迁移报告应把孤儿计数固化为基线，防止把存量债误判为 42 的回归 | 中 | 报告基线 + doctor 计数 |
| R5 | **迁移映射失败**：6 组双份中 4.9% 消息（≈114 条）无 content_hash 对应（legacy 抓取与 AV 解析的差异），其上 ref 无法自动重映射 | 低 | D-03 孤儿报告 + D-05 计数；ref 保持原值（superseded 副本仍可回查，只是 resolve=ineligible） |
| R6 | **claude 子代理共享 source_session_ref**（1 ref 挂 19 会话实测）：若误用 `source_session_ref` 当稳定键会把主会话+18 个 subagent 卷成一个 | 中 | 键 = `sessions.id`（唯一），`source_session_ref` 只喂 relation；加负向单测 |
| R7 | **delta 突变与数据积压混淆**：normalized 滞后 12 天（1,159 vs 920 会话） | 中 | §3.3 先常规 sync 消化，再上改键 |
| R8 | 发布崩溃窗口（两步 os.replace 之间 dest 缺失，:646-649，审计 M4） | 低 | deferred（CONTEXT 已列）；如顺带修，改为 backup 用 copy + 单次 replace |
| R9 | eligibility 代表 ref 翻转：dedup 保留哪份取决于 `started_at DESC` 扫描序（eligibility.py:158），supersede 落地后双份消失、翻转源头随之消除；过渡期两次构建间 ref 可能换人 | 低 | 迁移与重建同一窗口完成，验收 §4.4 |

---

## 7. Plan 划分建议（3 个 PLAN）

| Plan | 范围 | 边界 | 依赖 |
|---|---|---|---|
| **42-01 稳定键 crosswalk + 确定性**（DED-02 主体） | build_crosswalk 加 source_mapping Pass（native id 归一）；csid 铸法统一 `cs\|av\|<id>` / `cs\|legacy\|<id>`；file_hash 降级变更检测 + `file_hash_divergent` 等新 stats；D-04 确定性 ORDER BY（legacy meta / AV sessions / Pass1 代表行）；lifecycle/superseded_by 列 + supersede 判定；fixture 单测（增长≠新会话、双跑 byte-stable、R6 负向用例） | 不动 unified DB、不动 eligibility SQL、不动 cm 铸法 | 无（先于迁移） |
| **42-02 存量 ref 迁移脚本**（DED-01 收尾） | tools/migrations/remap_superseded_session_refs.py：content_hash 映射 40 evidence ref + 89 source_message_ref + inventory 同步；孤儿报告；dry-run/--write/备份/单事务；孤儿与 756 存量债分列基线 | 只写 unified DB；canonical 由 42-01 的 builder 天然收敛 | 42-01 已重建 |
| **42-03 端到端验收 + doctor 接线** | §3.3 顺序执行（先常规 sync 消化积压 → 42-01 重建 → 42-02 迁移）；§4 全套验收；两轨 inspect→prepare 受控消化 delta（预期突增注记）；doctor `_check_session_dedup`（warn-only）；ROADMAP/STATE 更新 | 不含 KU 重抽 | 42-01、42-02 |

---

## 8. 关键 file:line 速查

| 主题 | 位置 |
|---|---|
| Pass1 file_hash merge / merged csid 铸法 | build_canonical_agent_conversations.py:298-344, :305 |
| av_by_hash 覆盖写隐患 | :276-281 |
| Pass2/Pass3 稳定 csid 铸法（现状即样板） | :351, :386 |
| legacy 代表行无 ORDER BY（D-04 落点） | :164-190（`_load_legacy_sessions`）、:303-304（`leg_sessions[0]`）、:152-158（AV 无序加载） |
| cm\| id 铸造（不含 csid，改键安全的依据） | :541（AV）、:604（legacy） |
| 发布两步 replace（M4 崩溃窗口） | :641-650 |
| match_method CHECK 已含 source_mapping / stats 字段已预留 | :96、:136 |
| AV 原生 id + 增量簿记（append 不换 id 的证据） | AgentsView live sessions DDL：id TEXT PK、next_ordinal、last_entry_uuid、last_write_incremental、transcript_revision（只读探测） |
| normalized 保存 AV id / source_session_ref | build_agentsview_normalized.py:98-107, :371 |
| eligibility 的 session 门 + content_hash 去重 + 扫描序 | eligibility.py:150-160, :188-192, :158 |
| source checksum（含逐条内容 hash） | refresh_knowledge_units.py:64-85 |
| 双 watermark key | refresh_knowledge_units.py:1693, :1215-1233 |
| EvidenceResolver 动态列 + eligible 门 | retrieval/evidence.py:68-81 |
| serving snapshot canonical 成员 | application/serving/snapshots.py:409-414 |
| sync 编排（inventory→normalized→canonical 串行） | application/sync.py:60-73、run_pipeline.py:254-294 |
| 迁移脚本形态样板 | tools/migrations/backfill_ku_data_debts.py:239-271 |
| import gate（orphan/重复 ordinal fail-closed） | import_agentsview_sessions.py:71-99 |

---

## RESEARCH COMPLETE

- 现存双份实测 **6 组/12 行**（全 codex，AV twin 全部可由原生 id 唯一定位），潜在双份池 = 275 个 merged 会话（csid 随 file_hash 漂移）；evidence ref 铸造不含会话键，**改键零 ref 破坏**。
- 推荐键：`(source, AV sessions.id)`——AV id 已是 `agent:原生标识` 复合稳定键（append 不换 id 有 live 库簿记字段佐证）；schema 的 `source_mapping` match_method 与 stats 字段早已预留、从未实现，本 phase 即补全该 pass。
- canonical 每次 sync 全量重建 ⇒ supersede 标记必须由 builder 确定性生成；一次性迁移只针对 unified DB 的 40+89 个存量 ref（content_hash 映射 95.1% 可达，孤儿入报告）。
- 已量化下游：watermark 双 key 会经历一次真实口径 delta（非伪 delta）；756 个既有静默孤儿 ref 是 AV messages.id 漂移的存量债，本 phase 只固化基线不重铸消息身份。
- normalized 快照滞后 12 天（920 vs 1,159 会话）——建议先常规 sync 消化积压再上改键，保证验收 delta 归因干净。
