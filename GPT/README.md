# GPT 数据模块

本模块按raw、structured、analysis三层组织。原始导出数据保留在：

`C:\Users\li\Desktop\数据分析\GPT\raw`

## 目录结构

- `structured/raw_index`：GPT 原始导出文件索引。
- `structured/details`：清洗后的 CSV / JSONL / XLSX 和分析用 JSON。
- `structured/db`：ChatGPT SQLite 数据库。
- `structured/by_filetype`：处理结果按扩展名复制归类。
- `structured/attachments_by_type`：原始导出附件类型汇总，不复制大体量原始附件。
- `structured/scripts`：分析和整理scripts。
- `analysis/reports_html`：分析报告和数据库仪表盘。
- `analysis/charts_png`：报告图表。

## 当前统计

- 原始文件：186
- 原始体量 MB：129.11
- QA 明细行：85465
- 报告 HTML：5
- 图表 PNG：3
- SQLite 数据库：1

## 原始附件分组

- 图片附件: 177
- 导出核心文件: 7
- 文档表格附件: 2
