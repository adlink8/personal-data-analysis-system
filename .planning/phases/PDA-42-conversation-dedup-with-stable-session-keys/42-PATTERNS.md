# Phase 42 Pattern Mapping: Conversation Dedup with Stable Session Keys

**Mapped:** 2026-07-27
**Inputs:** 42-CONTEXT.md（D-01~D-05）、42-RESEARCH.md（§7 三 Plan 划分）、代码库只读勘察
**待改文件（4 核心 + 1 文档）:** builder 改造 ×1、一次性迁移脚本（新建）×1、fixture 测试（新建）×1、doctor 接线 ×1、runbook 注记 ×1

---

## 全局项目惯例（所有 Plan 必须遵守）

| 惯例 | 出处（file:line） | 内容 |
|---|---|---|
| **源库只读连接** | `src/personal_knowledge/adapters/agentsview.py:134-140` | `f"file:{path.as_posix()}?mode=ro"` + `PRAGMA query_only=ON`；builder 内部对 normalized/legacy 也全部 `mode=ro`（build_canonical_agent_conversations.py:150, :173, :503, :579）。本 phase 不新增对 AgentsView live 库的任何依赖（R1 红线），原生 id 从 normalized `sessions.source_session_id` 取 |
| **staging → os.replace 原子发布** | `build_canonical_agent_conversations.py:431, :641-650` | 写 `<stem>.staging.sqlite` → dry-run 时 `staging.unlink()` 返回 None → write 时旧库先 `os.replace(dest, backup)` 再 `os.replace(staging, dest)`。两步 replace 之间的崩溃窗口是已知 M4 债（deferred，可顺带修：backup 改 copy + 单次 replace） |
| **不硬删 / tombstone / 折叠不删除** | normalized `source_tombstones`（tests/integration/test_agentsview_normalization.py:420-424 验证）；`build_canonical_knowledge_units.py:260-265` 的 `canonical_unit_members` 叠加表（`INSERT OR IGNORE`，member 行永存） | superseded 会话走 lifecycle 标记 + `session_source_links` 保留 lineage，绝不 DELETE |
| **失败不静默** | `CrosswalkStats.duplicate_source_links`（builder :142，run() :687 打印 "must be 0"，:694 作 exit code 门） | 所有降级/跳过/映射失败路径必须有 stats 计数并进报告 |
| **迁移脚本标准形态（governance/GOV-06 期望）** | `tools/migrations/backfill_ku_data_debts.py`、`abandon_orphan_runs.py`、`requeue_schema_invalid.py` | 模块 docstring 写明背景+语义+用法（含 dry-run/写两条命令行示例）；默认 dry-run、`--write` 才落库；写前备份 UNIFIED_DB；单事务；幂等（重跑 no_op）；`sys.path.insert(0, ROOT/"src")` 引导；结尾打印 JSON/统计摘要 |
| **默认 dry-run 的 CLI 骨架** | builder main() :707-708：`if not args.dry_run and not args.write: args.dry_run = True` | 新脚本沿用同款语义 |

---

## 文件 1（修改）：`src/personal_knowledge/application/conversation/build_canonical_agent_conversations.py`

**角色:** builder（Plan 42-01 主体）。数据流位置：normalized + legacy → canonical SSOT（`pk-sync conversations` 经 `application/sync.py:60-73` → `run_pipeline.run_agentsview_stage` 调用）。每次 sync **全量 DROP+重建**（:436-439），所以稳定键 crosswalk、supersede 判定、确定性 ORDER BY 全部写进本文件、每次重建确定性重算——**不是**一次性脚本。

**类比 = 本文件自身既有段落**（改造对象即样板）：

1. **稳定 csid 铸法现成样板** — Pass 2/Pass 3 已经是目标形态，Pass 1 改为向它们看齐：

```python
# :125-127 —— id 铸造惯例（所有新 id 沿用）
def _norm_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(p) for p in parts)
    return f"{prefix}|{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"

# :351  Pass 2（稳定，保持）：  csid = _norm_id("cs", "agentsview", av_sid)
# :386  Pass 3（稳定，保持）：  csid = _norm_id("cs", "legacy", leg_sid)
# :305  Pass 1（反模式，取消）：csid = _norm_id("cs", "merged", fh)   # 身份随内容漂移
```

2. **source_links / match_method 惯例** — schema 已预留 `source_mapping`，零 schema 改动：

```python
# :96 CHECK 约束已含目标值
("match_method", "TEXT NOT NULL CHECK(match_method IN "
 "('file_hash','source_mapping','review_required','single_source'))"),
# :326-341 Pass1 现有 link 写法（新 source_mapping pass 照抄结构，只换 match_method）
source_links.append({
    "link_id": _norm_id("link", csid, "agentsview", av_sid),
    "canonical_session_id": csid, "source": "agentsview",
    "source_session_id": av_sid, "source_raw_file": None,
    "match_method": "file_hash", "match_confidence": "strong",
})
```

3. **stats 扩展类比** — `CrosswalkStats`（:130-143）dataclass 直加字段即可；`merged_by_source_mapping`（:135）已声明从未累加，本 phase 补上；`duplicate_source_links`（:142）展示了"gate 型计数"写法（run() :687 打印 `(must be 0)`、:694 `return 0 if stats.duplicate_source_links == 0 else 1`）。新增 `stable_key_matched / file_hash_confirmed / file_hash_divergent / superseded_marked` 沿用同款：dataclass 字段 + run() 打印段（:674-694）逐行输出。

4. **D-04 确定性 ORDER BY 落点**（现状即反模式）：

```python
# :152-158 _load_agentsview_sessions —— SELECT ... FROM sessions   （无 ORDER BY）
# :176-179 _load_legacy_sessions   —— SELECT ... FROM agent_sessions_meta（无 ORDER BY）
# :182-190 去重"保留第一条"——第一条由物理扫描序决定
# :303-304 Pass1 代表行 leg_sess = leg_sessions[0] ——组内无排序
```
改法（RESEARCH §3.2）：legacy SQL 加 `ORDER BY timestamp ASC, raw_file ASC, rowid ASC`；AV SQL 加 `ORDER BY started_at, session_id`；Pass 1 组内代表行按同规则排序后取首。

5. **schema 加列类比** — `CANONICAL_SCHEMA` 是 dict 字面量（:42-60），canonical 全量重建意味着**直接在 `canonical_sessions` 列表尾部追加** `("lifecycle", "TEXT NOT NULL DEFAULT 'active'")`、`("superseded_by_canonical_id", "TEXT")` 即可，无需 ALTER 迁移；同时 `_write_canonical_store` 的 INSERT（:452-463，写死 16 个 `?`）**必须同步扩位**——这是本文件最易漏的耦合点。下游安全依据：`retrieval/evidence.py:68-81` EvidenceResolver 用动态列探测（`_columns`），加列安全。

6. **消息写入 / cm id 铸造（R3 红线：原样保持）**：

```python
# :541 AV 侧（不含 csid —— 改会话键零 ref 破坏的依据）
_norm_id("cm", "av", m["source_message_id"] or m["message_id"]),
# :604 legacy 侧
_norm_id("cm", "legacy", m["session_id"], m["event_index"]),
```

**要复用的惯例:** `_norm_id` 铸键；`mode=ro` 读源；staging+replace 发布；stats 全量打印 + gate 型 exit code；merged 语义只落 `merged` 列与 source_links（不进身份键）。

**要避免的反模式:**
- `av_by_hash[fh] = s` 后写覆盖先写（:276-281）——同 hash 多会话静默丢失；新索引按 `source_session_id` 建，天然唯一（AV id 实测 0 重复），仍要对"意外重键"计数
- 身份键掺内容 hash（`cs|merged|<fh>` :305）
- 无 ORDER BY 的 SELECT / 列表首元素当代表行
- 新增跳过路径不计数（违反 D-05）
- 把 supersede 判定做成一次性 UPDATE 脚本——下次 sync DROP+重建即冲掉（RESEARCH §3.1）

---

## 文件 2（新建）：`tools/migrations/remap_superseded_session_refs.py`

**角色:** 一次性迁移脚本（Plan 42-02）。数据流位置：**只写 unified DB**（`knowledge_unit_evidence.evidence_ref` 40 个 + `knowledge_units.source_message_ref` 89 个 + `knowledge_inventory_items.evidence_ref` 连带），canonical 侧由 builder 天然收敛。读 canonical DB 仅只读（content_hash 对齐映射）。

**类比 A（首选骨架）= `tools/migrations/backfill_ku_data_debts.py`** —— 同样是"unified DB 的 ref 级修正 + 需要 JOIN canonical 库"：

```python
# :38-39 引导（所有迁移脚本统一）
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# :61-76 —— 分块 ref 索引查询，本脚本可直接复用改造
def _ref_index(canonical_con, refs) -> dict[str, tuple[...]]:
    for i in range(0, len(refs), 500):
        chunk = refs[i : i + 500]
        marks = ",".join("?" * len(chunk))
        rows = canonical_con.execute(
            "SELECT m.canonical_message_id, m.canonical_session_id, s.agent, m.role "
            "FROM canonical_messages m LEFT JOIN canonical_sessions s ...", chunk)

# :81-110 plan/apply 分离：plan_xxx() 返回 {rows, resolved, unresolved, by_prefix}
#          → _print_xxx_report() 打印 → apply_xxx() 在调用方事务里 UPDATE 并返回行数

# :231-236 备份
def _backup_unified_db(unified_db: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"personal_system_{stamp}.sqlite"
    shutil.copy2(unified_db, dest)
    return dest

# :240-243 dry-run/--write 互斥组；:267-277 单事务
mode = parser.add_mutually_exclusive_group()
mode.add_argument("--dry-run", action="store_true", default=True, ...)
mode.add_argument("--write", action="store_true", ...)
...
unified_con.execute("BEGIN"); ...; unified_con.commit()
except Exception: unified_con.rollback(); raise
# :296-297 收尾提示
print("\n(dry-run：未做任何修改；加 --write 执行)")
```

**类比 B（Phase 41 安全护栏 + 幂等 no_op）= `tools/migrations/abandon_orphan_runs.py`**：

```python
# :10-21 docstring 惯例：语义逐条编号 + "不删行，全程可审计" + 幂等声明 + 用法两条命令
# :90-100 保守护栏：解析失败按"最危险"处理
#   "无法解析的时间戳按'最近'处理，宁可拒绝也不误废活跃 run"
# :117-118 con.execute("PRAGMA busy_timeout=30000")
# :143-145 幂等 no_op：
if info["open_items"] == 0 and info["run_status"] == "aborted":
    print("  [no_op] 无未闭合项且已 aborted。")
# :158-177 with con: 单事务；INSERT OR IGNORE 幂等登记（:165-173）
# :184-185 机器可读摘要：print(json.dumps({"write": args.write, "runs": summary}, ...))
# :187-195 写完后重跑相关前置检查并打印剩余阻塞（收尾自验证）
```

（`requeue_schema_invalid.py:33-77` 是同族最小形态：`--db` 参数 + DB 不存在 exit 2 + no_op 短路，可对照。）

**本脚本要点（RESEARCH §3.1-2）:** 映射键 = cleaned content_hash 相同 + 同会话对，多义取 ordinal 最近；映射不了的 ref **保持原值** + 写孤儿报告（superseded 副本仍可回查，resolve=ineligible 属预期）；孤儿计数与 756 个既有静默孤儿（R4 存量债）**分列基线**，防止误判为 42 回归。

**要避免的反模式:**
- 对 canonical DB 做任何 UPDATE（会被下次 sync 冲掉，且违反"canonical 只由 builder 产出"）
- DELETE 任何行（ref 修正只 UPDATE，孤儿只报告）
- 无备份直写 / 多段散事务
- 报告混淆两类孤儿（42 映射失败 vs 756 存量 cm id 漂移债）

---

## 文件 3（新建）：`tests/integration/test_canonical_dedup_stable_keys.py`（或并入既有文件）

**角色:** 幂等/稳定键验收测试（Plan 42-01 内嵌交付）。

**类比 = `tests/integration/test_agentsview_normalization.py`**（唯一直接测 `build_canonical_agent_conversations` 的既有文件）：

```python
# :497-541 _make_normalized_fixture —— 手工 CREATE TABLE + INSERT 造 normalized 库
#   （sessions 14 列 + messages 13 列的最小 fixture，tmp_path 隔离）
# :544-572 test_canonical_av_path_skips_ineligible_sessions ——
#   调 build_canonical_run(dry_run=False, write=True, av_db=..., legacy_db=不存在路径, dest_db=...)
#   然后直接 sqlite3.connect(dest) 断言表内容；断言消息用 set 包含性
# :333-352 test_idempotent_same_dataset_hash —— 同输入跑两次、比对 hash 的幂等模板
#   （42 版加强：两库全表 sorted dump sha256 相等 + compute_source_checksum 相等，RESEARCH §4.1）
# :355-363 test_dry_run_no_file_written —— dry-run 返回 None、dest 不存在
# :366-375 test_atomic_publish_uses_staging —— staging 不残留
# :387-392 test_revision_gate_stats —— 直接构造 Stats 断言 gate 属性的纯单元写法
```

**42 需新增的用例（RESEARCH §4.3 + R6）:**
- 增长≠新会话：fixture 会话 X（file_hash=H1）构建 → 追加 2 条消息、hash 改 H2 → 重建：csid 不变、消息超集、会话行数不变、`stats.file_hash_divergent == 1`
- 双跑 byte-stable（DED-02）：同输入两 dest，全表 sorted dump sha256 相等
- R6 负向：两个会话共享 `source_session_ref`（1 主 + 1 subagent）→ 断言不被卷成一个 canonical session
- supersede：legacy 快照 hash ≠ AV 当前 hash 但原生 id 归一相等 → 断言合一（source_mapping link）而非双份；lifecycle 语义断言

**要复用的惯例:** `tmp_path` 全隔离、不碰真实库；fixture 手工建表（不 import builder 的 schema，防御 schema 漂移被静默吸收）；断言带中文失败消息（`assert h1 == h2, f"幂等失败: ..."`）。

**要避免的反模式:** 测试读正式 `data/` 库；只比行数不比内容（幂等要 dump hash 级）；fixture 里 legacy 路径传真实 AGENT_DB。

---

## 文件 4（修改）：`src/personal_knowledge/application/knowledge/doctor_ku.py`

**角色:** 观测接线（Plan 42-03）。新增 `_check_session_dedup`：RESEARCH §4.2 的 B/D 两条 SQL（active 会话稳定键唯一、codex 双份归零）+ 迁移孤儿基线呈现，**warn-only**。

**类比 = 同文件 `_check_coverage_matrix`（:342-434）**——Phase 41 刚立的"观测型 warn-only check"样板：

```python
# :70-76 返回结构
@dataclass
class CheckResult:
    id: str; ok: bool
    severity: str  # critical | warn | info
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

# :349-352 docstring 惯例（本 check 照抄立场声明）：
#   "ok 恒 True、severity='warn'、不进 hard_fail_ids——覆盖是观测问题
#    不是正确性问题（D-06 "WARN 不 FAIL"），exit code 不受影响。"
# :420-426 正常返回：CheckResult(id=..., ok=True, severity="warn", message=msg, detail=detail)
# :427-434 异常吞掉不阻断：
except Exception as exc:  # noqa: BLE001 — 观测 check 失败不阻断 doctor
    return CheckResult(id=..., ok=True, severity="warn",
                       message=f"... check failed: {exc}", detail={"error": str(exc)})
```

接线点：`checks.append(...)` 在 composite 区块（:734-744，紧邻 `_check_coverage_matrix` 之后）；**不加进** `hard_fail_ids`（:760-773，注释 :771-772 明确了排除惯例，本 check 追加同款注释）。DB 连接沿用 doctor 惯例 `mode=ro`（如 :298）。

**要避免的反模式:** `ok=False` 或进 hard_fail_ids（双份率是观测口径，不是正确性 gate）；check 内写任何状态（coverage 快照是唯一例外且有 docstring 特批）；异常上抛。

---

## 文件 5（修改，轻量）：`docs/runbooks/product-sync.md`

**角色:** 流程文档。注记两点：(a) RESEARCH §3.3 顺序——先常规 `pk-sync conversations --write` 消化 12 天积压，再上改键重建，delta 归因才干净；(b) 首轮重建后 `pk-ku inspect` 的 deleted_refs 突增为**预期口径修正**（双 watermark 轨 `committed`/`committed_assistant` 各走一次受控 inspect→prepare），避免 Gate B STOP 反射——与 41-RESEARCH R6 同型注记。类比：该 runbook 既有的 sync→inspect→prepare 段落（`application/sync.py:70` 也打印了同款下一步提示）。

---

## 跨文件红线速查（plan 里要写进"不做"）

| 红线 | 依据 |
|---|---|
| 不重铸 `cm\|` id（否则 23,009 evidence ref 全废） | builder :541/:604 铸法保持；RESEARCH R3 |
| 不新增 AgentsView live 库依赖；一切原生 id 取自 normalized | adapters/agentsview.py:134-140；RESEARCH R1 |
| 不硬删：superseded 走 lifecycle 标记 + source_links lineage | canonical_unit_members 叠加表思想（build_canonical_knowledge_units.py:260-265）；D-03 |
| `source_session_ref` 不作身份键（1 ref 挂 19 会话） | RESEARCH R6，加负向单测 |
| eligibility SQL 不改（`s.evidence_eligible=1` 天然排除 superseded） | eligibility.py:155 |
| canonical 侧逻辑进 builder、unified 侧修正进迁移脚本，二者不越界 | RESEARCH §3.1 |

## PATTERN MAPPING COMPLETE
共映射 5 个待改文件（builder 修改 1、迁移脚本新建 1、测试新建 1、doctor 修改 1、runbook 注记 1），类比摘录覆盖 7 个既有源文件。
