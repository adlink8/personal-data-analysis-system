# var/reports/analysis

分析产物根目录（Phase 20 自 `integration/analysis` 迁入）。

```
analysis/
  README.md                 # 本索引
  stage1_profile/           # 阶段一：跨模块画像/报表/CSV/HTML
  ai_context/               # 阶段二+：对话/记忆/知识/向量/评测
    charts/
    _archive/
  evaluations/              # Phase 17 knowledge eval runs
  refactoring/              # 重构验证笔记
```

## 去哪看什么

| 需求 | 路径 |
|------|------|
| 旧统合画像 HTML/CSV | `stage1_profile/profile.md` 等 |
| 向量库新旧对比 | `ai_context/vector_generation_comparison.md` |
| SQLite 分层对比 | `ai_context/sqlite_generation_comparison.md` |
| 合并报告 + 缺口 | `ai_context/generation_gap_analysis.md` |
| L1/L2 检索对比 | `ai_context/l1_l2_retrieval_comparison.json` |
| Knowledge eval HTML | `evaluations/<run>/report.html` |
| 历史 canary/pilot | `ai_context/_archive/` |

## 说明

- 代码通过 `project_paths.ANALYSIS_DIR` / `AI_CONTEXT_DIR` 解析（优先本目录）。
- 私有报告默认 gitignore；勿提交含个人正文的产物。
