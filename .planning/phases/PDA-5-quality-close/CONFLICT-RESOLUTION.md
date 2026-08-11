# Phase 5b: 16 条 Conflict 裁决标记处置报告

- **日期**: 2026-08-11
- **数据源**: `var/db/personal_system.sqlite` — `canonical_knowledge_units`
- **方式**: 全部标记（lifecycle 变更），**零 DELETE**，保留 lineage 可回滚
- **备份**: `var/backups/personal_system_pre_conflict_resolution_20260811T063247Z.sqlite`
- **处置 manifest**: `klm_0e779b8ee83ac8257feae210`（knowledge_lifecycle_manifests，status=applied）

## 裁决结果（7 组）

| 组 | 主题 | Current（胜者） | Superseded/Deprecated（败者） | 裁决依据 |
|---|---|---|---|---|
| 1 | Android SDK | ② `cu|0d0c4d9a…` C:\Users\li\AppData\Local\Android\Sdk 2.46GB | ① `cu|9a24e2ef…` 已移动到 D 盘 | 时间推进：② created_at 07-12 > ① 07-10，新者胜 |
| 2 | Git 远程仓库 | 两条均 current：`cu|14ece801…` aliyun、`cu|a53512f6…` github | — | **多值共存**：同一 repo 双 remote 不冲突，均保留，不互相 supersede |
| 3 | 计算机组成原理实验 | 实验五 `cu|1f6f8566…`（微程序控制器） | 实验四 `cu|7a1773e5…`（寄存器堆 RF） | created_at 相同 → 内容裁决（见下） |
| 4 | 设备激活状态 | 已激活成功 `cu|407ca86d…` | 尚未激活 `cu|54985b8d…` | 时间推进：已激活为最新状态 |
| 5 | 项目文件所有权 | —（不产生 current） | 4 条全部 deprecated | **无效断言**（见下），互不设 supersedes_id |
| 6 | 项目目标 | DuckyClaw `cu|8f8abd4d…` | 网站所有歌曲深读 `cu|01e23865…` | created_at 相同 → 内容裁决（见下） |
| 7 | 项目阶段 | Phase 2 验收 `cu|18918714…` | 总结架构阶段 `cu|3e7061dc…` | 时间推进：② created_at 07-12 > ① 07-10 |

## 关键裁决的时间依据

### 组 3（计算机组成原理实验）— created_at 相同，内容裁决

两条记录 created_at **完全相同**（`2026-07-12T06:17:41Z`），无法按时间区分：

- 实验五记录 `cu|1f6f8566…` 的 answer 明确写道：「正在进行…**实验五**（微程序控制器实验），并且**之前已经完成了实验四**（手动控制数据通路实验）」
- 实验四记录 `cu|7a1773e5…` 的 answer 为「正在进行…**实验四**（寄存器堆 RF）」

结论：实验四为已完成的前置实验，实验五为当前进行实验 → **实验五 current，实验四 superseded**。与任务书中「先做四后做五」的预期一致。

### 组 6（项目目标）— created_at 相同，内容裁决

两条记录 created_at **完全相同**（`2026-07-12T06:17:41Z`），无法按时间区分：

- DuckyClaw 记录 `cu|8f8abd4d…` 的 answer 为「用户将项目目标**切换到 DuckyClaw**」→ 切换动作指向 DuckyClaw 为最新目标
- 深读记录 `cu|01e23865…` 的 answer 为「用户当前的目标是确保网站所有歌曲都有深读」→ 旧目标

结论：DuckyClaw 为当前项目目标 → **DuckyClaw current，深读 superseded**。

## 组 5「无效断言」说明

4 条记录 `cu|6fe9974b…`、`cu|1a8c5b4f…`、`cu|84972e8f…`、`cu|d8612eeb…` 各自声称**「唯一拥有」**一个不同的文件（均为 docs/ALBUM-RECLASSIFY-*.json）：

- 4 条均使用「唯一拥有/当前仅拥有」表述，但指向 4 个不同文件
- 「唯一拥有」断言在不同时间点指向不同文件，**断言本身不成立**（不可能同时唯一拥有多个文件）
- 因此：4 条全部标记 **deprecated**（无有效替代、无胜者），**不产生 current**，**互不设置 supersedes_id**
- 说明：组 5 使用 `deprecated` 而非 `superseded`，与库内既有数据不变量一致（deprecated 惯例无 supersedes_id；superseded 惯例必有 supersedes_id），且语义上「无效断言」无替代关系。

## 变更统计

| 指标 | 处置前 | 处置后 | 变化 |
|---|---|---|---|
| `conflict` 单元 | 16 | **0** | -16 |
| `current` 单元 | 39880 | 39887 | +7（7 条胜者恢复 current） |
| `superseded` 单元 | 309 | 314 | +5（组 1/3/4/6/7 败者） |
| `deprecated` 单元 | 212 | 216 | +4（组 5） |
| 总单元数 | 40417 | 40417 | 0（零删除） |

版本号：全部 16 条 version 2 → 3（与既有 lifecycle 事件 version 递增约定一致）。

## 事件与审计记录

`knowledge_lifecycle_events` 新增 16 条事件（manifest `klm_0e779b8ee83ac8257feae210`）：

- 7 × `restore`（conflict → current）
- 5 × `supersede`（conflict → superseded，supersedes_after 指向胜者）
- 4 × `deprecate`（conflict → deprecated）

`knowledge_lifecycle_actions` 新增 16 条 action（action=restore/supersede/deprecate），全部 expected_lifecycle=conflict、expected_version=2，与处置前状态精确匹配。

## 测试结果

```
python -m pytest tests/ -q -k "lifecycle or canonical or supersede"
```

- `tests/unit/test_lifecycle_events.py`、`tests/unit/test_reconcile_knowledge_lifecycle.py`、`tests/unit/test_canonical_knowledge_units.py`：**48 个全部通过**
- 唯一失败：`tests/governance/test_physical_source_layout.py::test_canonical_preview_is_exact_and_records_phase17_conflicts` — **既有失败，与本次变更无关**（该测试只检查文件系统中的 canonical-src.json 目标文件，7 个 target 已在 commit `af6d698`（旧管线死模块归档）中移除但 manifest 未同步更新；不引用 personal_system.sqlite）

## 约束符合性

- [x] 仅 UPDATE `var/db/personal_system.sqlite`，未改任何源码
- [x] 零 DELETE，全部标记，lineage 完整可回滚
- [x] 操作前已备份至 `var/backups/`
- [x] 未做 git commit（数据库变更不提交）
- [x] 未遇到字段缺失/表结构不符（supersedes_id、version、knowledge_lifecycle_events 等全部存在）
