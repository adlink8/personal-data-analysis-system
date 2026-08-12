# Conversation Source Fixtures

Redacted synthetic fixtures for Phase 62 family adapters. **Every fixture is
hand-written and contains no live conversation bodies** — they encode only
the structural shapes observed in local artifacts (see 62-RESEARCH.md
format matrix). Native IDs, prompts and outputs are fake.

Each fixture name starts with its owning family prefix so that adapters of
different plans never overwrite each other.

| Fixture | Family | Native shape | Semantics it proves |
|---|---|---|---|
| `codex_agent_sessions.jsonl` | codex | JSONL event stream | `session_meta`, `turn_context` turn IDs, `response_item`, `function_call`/`function_call_output` call-id pairing, top-level `context_compacted` as compaction event (not user message) |
| `claude_export.jsonl` | claude | JSONL UUID DAG | `uuid`/`parentUuid` parent relations, `isSidechain` sidechain relation |
| `qoder_export.jsonl` | qoder | Claude-like JSONL DAG | explicit `isCompactSummary` → compaction event + compacted-range relation |
| `pi_conversation.jsonl` | pi | JSONL event stream | independent `compaction` record with `summary`/`firstKeptEntryId`/`tokensBefore` → typed compaction + range relation |
| `workbuddy_session.jsonl` | workbuddy | JSONL | `reasoning`, `function_call`/`function_call_result` linked events |
| `kimi_turn.jsonl` | kimi / kimi-work | JSONL loop protocol | `turn_start`, `user_prompt`, `loop_iteration`, `context_append`, `task_complete` lifecycle |
| `copilot_trace.jsonl` | copilot / vscode-copilot | JSONL trace | `turn_start`/`turn_end`, `assistant_message`, `tool_execution_start`/`tool_execution_complete` native-ID pairing |
| `gemini_conversation.json` | gemini | single JSON | ordered `messages` array; whole-file immutable snapshot |
