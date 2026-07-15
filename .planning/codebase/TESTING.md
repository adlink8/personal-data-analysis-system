---
mapped: 2026-07-13
focus: quality
scope: full-repository
---

# 测试体系与治理门

## 当前测试体系

- Python 使用 pytest，配置位于 `pytest.ini`。
- `testpaths = tests` 已限制裸 `python -m pytest` 不进入 `_recycle/`、`integration/scripts/test_*.py`、私有数据目录或历史 `.gsd/`，修复了早期重复模块收集问题。
- 当前 `tests/` 有 58 个测试文件，静态计数约 408 个 `test_*` 函数。
- 2026-07-13 实测：`python -m pytest --collect-only -q` 成功；`python -m pytest -q --tb=short` 全量通过，耗时约 48.1 秒。
- GitHub Actions 位于 `.github/workflows/ci.yml`，使用 Ubuntu + Python 3.12，执行收集与全量测试；覆盖缺口审计当前为 informational、不会阻断。
- App widget 另有 Node 测试：`integration/apps/personal_data_chatgpt/test/contract.test.mjs` 与 `widget-render.test.mjs`，不在 Python pytest job 内。

## 测试组织

| 层级 | 位置/例子 | 目标 |
|---|---|---|
| unit/contract | `tests/test_*_contracts.py` | schema、API、路径和隐私契约 |
| pipeline | `tests/test_import_pipeline.py`, `test_run_pipeline_contracts.py` | dry-run、幂等、失败语义 |
| lifecycle | checkpoint、promotion、rollback、incremental tests | stage/gate/promote/rollback 一致性 |
| retrieval/eval | `test_knowledge_eval_*.py`, vector/search tests | 统一指标、gate、报告与 registry |
| service smoke | dashboard、MCP、Apps SDK tests | 入口可导入、协议字段稳定 |
| UAT | `.planning/phases/*/*-UAT.md` | 需要真实运行环境或人工判断的闭环 |

## 必须保持的测试规则

- 单元测试不得读取用户真实数据库、Google Takeout、AgentsView live DB 或网络服务；使用 `tmp_path`、内存 SQLite 和 synthetic fixtures。
- 涉及 live 数据的验证必须是显式命令，默认只读/dry-run，并记录到对应 VERIFICATION/UAT，不混入普通 CI。
- candidate/promote 测试必须验证 gate fail 时 active 不变、journal 可追溯、rollback 恢复 pointer 与数据版本。
- eval 测试必须固定 dataset/config/checksum，报告同时给绝对值、paired delta、置信区间、隐私命中和延迟；失败不得选择性隐藏。
- no-answer、secret/privacy、冲突、过时知识、paraphrase、cross-turn 是知识单元评测的固定切片。
- shim 必须有入口契约测试，确保旧 CLI 与领域模块行为一致；真实逻辑只在领域模块测试一次。

## 建议的四级治理门

### G0 — 本地快速门（每次改动）

目标时长小于 60 秒：

```powershell
python -m pytest --collect-only -q
python -m pytest -q --tb=short
```

并行加入静态检查：格式/lint、绝对路径扫描、inventory 未分类文件扫描、secret scan。

### G1 — PR 门（阻断合并）

- Python 3.12 与 3.14 双矩阵测试。
- Node widget contract/render tests。
- dependency lock/constraints 一致性与漏洞审计。
- planning consistency、README 入口有效性、shim budget、生成物/大文件检查。
- `_audit_test_gaps.py` 从 informational 改为带 baseline 的 regression gate：不要求一次补齐，但禁止新增 high gap。

### G2 — Candidate 发布门

- 构建隔离 candidate，不修改 active。
- Raw/L1/L2/L1+L2/Hybrid 统一 retrieval 与 answer evaluation。
- privacy hit 必须为 0；关键指标不得回退；满足预注册的提升阈值和置信区间。
- 生成 SQLite/JSON/HTML/PNG 版本化结果，checksum 写入 promotion journal。

### G3 — 生产与周期治理门

- canary、post-promote reconcile、rollback 演练。
- 每周/每次 source checksum 变化执行增量回归；每月执行全量数据 lineage、orphan、deprecated residue、备份可恢复性检查。
- 趋势面板展示测试数/耗时、覆盖缺口、检索/回答指标、隐私命中、索引规模、fallback rate 和回滚成功率。

## 当前缺口

- 没有 coverage.py/分支覆盖率基线，无法量化源码覆盖；现有 `_audit_test_gaps.py` 仅提示且 CI `continue-on-error`。
- Python CI 只测 3.12，而生产说明称本机 3.14 已验证；缺少跨版本门。
- requirements 只有范围，没有完全锁定；CI 每次可能安装不同依赖组合。
- Node app tests 未进入 `.github/workflows/ci.yml`。
- 缺少 lint/typecheck/secret scan/dependency audit/large-file/inventory/planning drift 等门。
- 真实 cross-turn gold、judge calibration 与 Phase 17 sandbox promote/rollback UAT 仍是人工未关闭项。

## 建议自动检查脚本

- `governance_inventory.py --check`：逐文件分类、owner、敏感级与生命周期。
- `check_path_policy.py`：绝对路径、用户名、Desktop、裸 sys.path 修改。
- `check_planning_consistency.py`：GSD 状态与文档事实同步。
- `check_shim_budget.py --baseline 86`：禁止兼容面扩大。
- `check_docs_links.py`：README 中本地入口、命令与模块是否存在。
- `check_artifacts.py`：数据库/个人数据/生成物/超大文件不得跟踪。

