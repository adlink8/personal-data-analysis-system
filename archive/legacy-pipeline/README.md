# archive/legacy-pipeline/ — PDA-2 阶段 2：旧管线关闭（2026-08-11）

## 背景

Phase 20 迁移后，旧目录 `Agent/`、`GPT/`、`Google/`、`imports/`、`_recycle/` 已从仓库删除。
以下 18 个模块仍引用这些已删除路径（如 `ROOT/"Agent"/"structured"/"db"/"agent_data.sqlite"`、
`ROOT/"GPT"/"structured"/"db"/"chatgpt_data.db"`），运行时必然报错或返回空，属死代码。
新管道（`pk-sync conversations`，数据源 `~/.agentsview/sessions.db`）不依赖它们。

依赖审计见 `.planning/phases/PDA-2-legacy-pipeline-close/2.1-dependency-audit.md`。

## 归档内容（镜像仓库相对路径，可回滚）

### src/personal_knowledge/application/（canonical 模块，已加 DEPRECATED 头）
- `run_import_pipeline.py` — GPT/Google 导出导入（GPT_DB / imports/ 旧路径）
- `conversation/build_gpt_conversation_summary.py` — GPT 对话叙述压缩（GPT_DB）
- `conversation/build_conversation_segments.py` — 用户想法片段切分（AGENT_DB + GPT_DB）
- `conversation/summary.py` — 对话结构化叙述摘要（AGENT_DB）
- `enrich_unified_events.py` — 语义增强层（AGENT_DB；输出 unified_events_rich 仅供 legacy 链消费）
- `build_integrated_system.py` — 统合库构建（AGENT_DB + GPT_DB）
- `memory/build_mem0_candidate_memory.py` — mem0 候选实验（Phase 07 已降级）

### src/personal_knowledge/domains/（re-export facade，转发上述 canonical）
- `conversation/build_conversation_segments.py`
- `conversation/build_gpt_conversation_summary.py`
- `conversation/build_conversation_summary.py`
- `memory/build_mem0_candidate_memory.py`

### tools/compat/v1_1/（compatibility shim，转发 domains/canonical）
- `run_import_pipeline.py`
- `build_gpt_conversation_summary.py`
- `build_conversation_segments.py`
- `build_conversation_summary.py`
- `enrich_unified_events.py`
- `build_integrated_system.py`
- `build_mem0_candidate_memory.py`

## 恢复方式

按上述镜像路径 `git mv` 回原位置即可；原文件内容未被修改（仅在头部追加了 DEPRECATED 注释块）。

## 相关联动（未移动，需知晓）

- `src/personal_knowledge/application/run_pipeline.py`：`--legacy-integrated` 步骤 1/2 仍指向
  上述两个模块（字符串分发）；legacy 模式本身已死（DB 已删），未改。
- `src/personal_knowledge/services/dashboard.py`：help 文本仍提示 `python -m
  personal_knowledge.application.enrich_unified_events`（仅文档过期，无 import）。
- `src/personal_knowledge/evaluation/conversation/build_conversation_eval_set.py`：函数内 import
  summary（自身依赖已删的 agent_data.sqlite，同属历史遗留）。
- `tests/integration/test_import_pipeline.py`、`tests/unit/test_conversation_summary_parse.py`：
  已改为守卫 import + skip 标记。
- `governance/manifests/entrypoints.yaml`：shim 计数 85→78（`baseline_only_down: true` 允许下降）。
