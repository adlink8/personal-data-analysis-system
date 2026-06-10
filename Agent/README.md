# Agent 数据模块

Agent 模块纳入 Windows 和 WSL 上的 AI Agent 工具数据，包括 Codex、WorkBuddy、Hermes、Claude、Cline、Cursor、Gemini、`.agents` skills、WSL Ubuntu-D 中的 agent 数据等。

本模块只保留三层：

- `原始数据`：可分析原始副本和 WSL 归档。
- `结构化数据`：原始索引、明细 CSV、SQLite、按来源/类型拆分和构建脚本。
- `分析数据`：HTML 摘要、classification summary、旧工作文件。

统合模块读取：

```text
Agent/结构化数据/SQLite数据库/agent_data.sqlite
```

当前构建结果：

- 原始文件索引：2932 个
- 原始副本体积：约 1327.31 MB
- WSL 归档：约 243.56 MB，清单 6145 行
- skills：527 条
- memory 文件：347 个
- session 文件：518 个
- session 消息摘要行：20324 行
- SQLite 表清单：83 行

重建命令：

```powershell
python Agent\结构化数据\脚本\build_agent_dataset.py
```
