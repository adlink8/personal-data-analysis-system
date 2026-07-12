# Phase 01: 增量导入流水线

## 目标

把后续新导出的 Google / GPT 数据接入一条可重复运行的链路：

```text
新导出数据 -> 批次化保存 -> 文件去重 -> 记录去重 -> 追加进 SQLite -> 重跑分析摘要
```

## 范围

- 新增统一入口目录 `imports/incoming/google` 和 `imports/incoming/gpt`。
- 每次导入创建独立批次目录 `imports/batches/<batch_id>`。
- 对批次内文件计算 SHA-256，并和既有工作区文件做文件级去重。
- 把重复批次文件移动到 `duplicate_audit/quarantine`，不删除。
- 解析 Google Takeout 常见 JSON/CSV 和 ChatGPT `conversations.json`。
- 写入目标数据源 SQLite 的导入控制表和 `normalized_events` 标准事件表。
- 生成导入摘要报告，作为“重跑分析”的最小稳定产物。

## 不做

- 不覆盖现有 Google / GPT raw。
- 不重写已有深度画像报告。
- 不训练模型。
- 不删除隔离区文件。

## 验收

- `python pipelines/run_import_pipeline.py --init` 可初始化目录和数据库表。
- `python pipelines/run_import_pipeline.py --source google --input imports/incoming/google --dry-run` 可运行。
- `python pipelines/run_import_pipeline.py --source gpt --input imports/incoming/gpt --dry-run` 可运行。
- SQLite 中存在 `import_batches`、`source_files`、`normalized_events`。
- README 说明新增导入链路。
