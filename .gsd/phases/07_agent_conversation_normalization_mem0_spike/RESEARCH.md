# Phase 07 Research: Agent Conversation Normalization + Mem0 Spike

Status: Planned
Date: 2026-06-27
Basis: Local Agent log inspection, Phase 06 mem0 demo, and current project constraints

## Research Summary

Phase 07 should use mem0 for compression, not authority. The local demo showed mem0 can produce dense cross-event facts, but it also confused user actions with topics/news/recommendations and did not preserve this repo's evidence chain by default.

| Finding | Planning consequence |
| --- | --- |
| mem0 can compress noisy conversations into dense facts | Worth testing as a candidate generator |
| mem0 confused "user did" with "user talked about" | Add pre-filtering and review status |
| mem0 output lacks local evidence chain by default | Wrap every candidate with source ids |
| Agent logs contain many system/developer/tool records | Normalize before mem0 ingestion |
| Existing memory layer has evidence coverage | Do not bypass `memory_links` discipline |

## Agent Log Taxonomy

Observed Codex session top-level records:

| Top-level type | Meaning | Memory input |
| --- | --- | --- |
| `session_meta` | Session identity, cwd, model, origin | Metadata only |
| `turn_context` | Turn environment and settings | Metadata only |
| `response_item` | Messages, tool calls, reasoning items | Selectively |
| `event_msg` | Runtime events, display stream, token counts | Selectively |
| `compacted` | Compaction replacement history | Review only |

Important `response_item.payload.type` values:

- `message`: keep user/assistant messages; exclude developer by default.
- `function_call`, `custom_tool_call`, `web_search_call`, `tool_search_call`: keep as tool calls.
- `function_call_output`, `custom_tool_call_output`, `tool_search_output`: keep as tool outputs with summaries.
- `reasoning`: exclude from user memory extraction.

Important `event_msg.payload.type` values:

- `user_message`, `agent_message`: useful display-stream messages.
- `task_started`, `task_complete`, `turn_aborted`: lifecycle events.
- `token_count`: usage metrics.
- `exec_command_end`, `patch_apply_end`, `web_search_end`: execution status.

## Proposed Data Model

Keep existing Agent tables and add v2 tables:

| Table | Purpose |
| --- | --- |
| `agent_turns` | One row per `turn_id` inside a session |
| `agent_messages` | Clean user/assistant/developer/system messages |
| `agent_tool_calls` | Tool call request records with tool name and argument summary |
| `agent_tool_outputs` | Tool output records linked by `call_id` |
| `agent_lifecycle_events` | Started/completed/aborted/compacted events |
| `agent_usage_metrics` | Token/context metrics |

This model is better than physical user/assistant tables because it preserves chronology, turn boundaries, tool causality, and future roles.

## Mem0 Spike Contract

Inputs:

- Cleaned user message segments.
- Assistant confirmations only when they prove something was done.
- Tool call/output summaries only when they support a user-relevant project or workflow fact.

Outputs:

- `candidate_id`
- `candidate_type`
- `subject`
- `claim`
- `confidence`
- `source_segment_ids`
- `source_refs`
- `acceptance_status`: `candidate | rejected | promoted`
- `reject_reason`

Acceptance gates:

- Candidate has at least one source segment or raw ref.
- Candidate distinguishes action/preference/fact from news/recommendation/topic mention.
- Candidate is not promoted unless evidence can join back to source.

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Agent parser overfits Codex logs | Other agent sources stay noisy | Start with Codex, preserve raw type fields |
| mem0 adds dependency weight | Pipeline becomes harder to run | Optional spike script, not default pipeline |
| LLM extraction leaks private text | Privacy risk | Default to dry-run/sample mode; require explicit env config |
| Candidate facts pollute memory | Bad long-term profile | Store candidates separately |
| Tool output is too long | Slow extraction | Summarize deterministically before mem0 |

## References

- `.gsd/phases/06_deep_memory_graph_mining/SUMMARY_两个Demo反馈总结.md`
- `Agent/结构化数据/脚本/build_agent_dataset.py`
- `https://github.com/mem0ai/mem0`
- `https://docs.mem0.ai/`
