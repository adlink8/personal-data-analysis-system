# Handover — Phase 62 v2 Native Conversation Pipeline (work done & how to audit)

**Audience:** any agent asked to review/continue this work. Read this file first,
then verify claims against the repo and the shadow DB — do not trust the summary alone.

## 1. What was built (one paragraph)

A Phase 62 v2 conversation capture pipeline that scans local AI client directories
directly (no AgentsView round-trip), stages family-mirrored artifacts, adapts them
into typed events with session context (cwd/model/title/git_branch/stop_reason),
relations (SUBAGENT/COMPACTED_RANGE/CALL_RESULT/TURN_MEMBERSHIP), usage metrics, and
honest fidelity declarations. Then a multi-round audit loop (subagent-driven random
sampling against original artifacts) found and fixed fidelity gaps (tool content,
timestamps, truncation, ordinal, model granularity).

## 2. Key entry points

| Seam | Path | Role |
|---|---|---|
| Discovery | `src/personal_knowledge/adapters/conversation_sources/discovery.py` | client roots → stage mirror (WAL-safe sqlite snapshot, hash dedup) |
| Shadow/activation | `src/personal_knowledge/application/conversation/v2_sync.py` | `--v2-native` (discover→stage→shadow, never activates) / `--v2-native-dry-run` |
| Event schema | `src/personal_knowledge/application/conversation/event_schema.py` | ce_sessions (+cwd/git_branch/model/title/stop_reason) / ce_events / ce_event_relations |
| Contract | `src/personal_knowledge/core/conversation_events.py` | AdaptedSession context fields; dataset_digest includes them |
| Projection | `src/personal_knowledge/application/conversation/compatibility_projection.py` | v2 → legacy canonical_sessions (cwd/git_branch/model now mapped) |

## 3. Adapter versions (all bumped this session)

codex 1.2.0 · claude_qoder 1.2.0 · workbuddy_kimi 1.2.0 · zcode 1.2.0 · pi 1.3.0 ·
grok 1.1.0 · mimo_opencode 1.1.0 · antigravity 1.1.0 · gemini 1.1.0 · copilot 1.0.0 ·
cursor 1.0.0

## 4. New test files (13) — all green

tests/contract/: test_session_context_contract · test_codex_context_extraction ·
test_codex_tool_content_and_model · test_codex_usage_fix · test_claude_qoder_context_extraction ·
test_workbuddy_kimi_context_extraction · test_pi_gemini_context_extraction ·
test_zcode_antigravity_context_extraction · test_misc_context_extraction ·
test_antigravity_protobuf_fix · test_cursor_session_timestamps
tests/integration/: test_conversation_client_discovery
fixture: tests/fixtures/conversation_sources/claude_qoder_context_extraction.jsonl

## 5. What each adapter gained (by family)

- **codex**: cwd/git_branch/model(concrete)/title(real user, skips system placeholders);
  tool_call content=arguments, tool_result content=output (cap 100k); USAGE from
  token_count payload; SUBAGENT_BOUNDARY for forked sessions; ordinal=line number;
  ~20 payload.type classifications (unknown 13.5%→0.5%).
- **claude/qoder**: cwd/git_branch/model(real name, incl. sub-agents)/title/stop_reason;
  tool_result full content (cap 100k), tool_call input (cap 50k); 10 metadata record
  types → SYSTEM_MESSAGE (unknown 6.9%→0%).
- **workbuddy/kimi**: cwd(workbuddy dir), title, SUBAGENT relations, USAGE tokens
  (deep providerData/message.usage), old-format timestamps (kimi 0→100%), model
  (last-wins), new kimi envelope format (tool pairing, turn bounds, subagent, title).
- **zcode**: title 100%, trace→TURN, parent→SUBAGENT, COMPACTED_RANGE, ended_at + cwd
  (directory column), usage normalized to input_tokens=.
- **pi**: toolResult/thinking/toolCall classification (unknown 42.5%→0%), model_change→model,
  usage canonical. **gemini**: model/title/USAGE.
- **grok**: cwd (info.cwd bug fixed), model (current_model_id), head_branch, USAGE,
  COMPACTED_RANGE. **copilot**: dotted event types (tool.execution_*), toolCallId pairing,
  subagent/compaction mapping (unknown 2,878→22).
- **mimo/opencode**: tool_call content=state.input, tool_result=state.output (cap 50k/100k),
  reasoning full content (cap 100k, was 2048), fidelity honest (partial+disposition),
  cwd from message.path.cwd, model from data.modelID.
- **antigravity**: N×M bug fixed; binary protobuf honestly unknown_native +
  content_availability=unavailable (no schema available).
- **cursor**: cwd from project dir, model extraction (native lacks it).

## 6. Audit loop (3 rounds, subagent-driven) — see
`docs/architecture/conversation-data-quality-audit.md` for the full log

R1 found: tool content missing, kimi timestamps NULL, 2048 truncation, cwd/ended_at
missing, model coarse, ordinal NULL.
R2 verified: all P0/P1 fixed (content verbatim, timestamps ms-exact, ended_at/cwd 345/345,
grok model/branch 62/62).
R3 verified: mimo reasoning full content, claude sub-agent model, 8192 cap removed,
ordinal 99.98%. Final per-family rating: all High.

## 7. Current data state (latest shadow generation)

```
generation  shadow-cohort-2c2ec59191bb (2026-08-16T09:38:24Z)
sessions    1,249
events      575,328   (unknown 1.6% — dominated by antigravity protobuf)
relations   200,658   (0 orphans)
gates       overall=true, detected_families_unblocked=true, uncovered_sources=true
```

## 8. How to verify (audit commands)

```powershell
python -m pytest -q tests/contract tests/unit tests/integration/test_conversation_client_discovery.py tests/integration/test_conversation_v2_sync.py
python -m personal_knowledge.application.sync conversations --v2-native-dry-run   # discovery only
python tools/verify_session_context.py                                             # field coverage
pk-ku doctor --skip-ports
```

## 9. Known limitations (honest, not bugs)

- **antigravity**: steps are binary protobuf without .proto schema — semantic decode impossible;
  `unknown_native` + `content_availability=unavailable` is the honest representation.
- **grok**: native dir contains only summary.json (no chat_history) — 2 events/session is a
  capture limitation, not an adapter bug.
- **kimi/workbuddy cwd**: capture layer passes only basenames; absolute workdir lives in
  `state.json.workDir` which never enters the artifact set — needs a capture-layer change
  (v2_sync/discovery), deliberately deferred.
- **kimi new-format model (7/102)**: native file has no model field at all.
- **codex non-standard tools** (web_search/mcp_tool_call_end): payload uses query/invocation
  fields without input/output — ~3-5% tool content unfilled by design.
- **JSON key-order / block-boundary normalization** in tool payloads (semantic equal, not byte-equal).

## 10. Deliberate engineering decisions

- Capture logic follows Phase 62 adapter architecture (explicitly NOT copied from AgentsView).
- Shadow is metadata-only and NEVER auto-activates (D-18/D-31; activation needs explicit
  `--v2-activate` + human approval phrase). Zero paid LLM calls.
- SQLite sources use WAL-safe online backup + allowlist (D-05/D-08), never loose .db copies.
- Unknown native records are preserved (not dropped) with dispositions, so nothing is lost.
- Fidelity claims were corrected to match actual content (complete only when content present).

## 11. Working tree status

53 files changed vs HEAD (11 adapters + discovery.py + 13 test files + tools + docs).
NOT committed — review before commit. `data/**`, `var/**` are gitignored (private).

