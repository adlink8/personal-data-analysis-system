# Conversation Data-Quality Audit & Fidelity Fix Log

**Scope:** Phase 62 v2 native conversation pipeline — fidelity comparison against
original client artifacts, three audit rounds (subagent-driven random sampling)
and the fixes each round uncovered. All numbers are measured on the shadow DB
(`data/staging/v2/agent_conversations_v2.sqlite`) against the staged originals in
`data/staging/v2/native/<family>/`.

## Method

- Randomly sample sessions per family (proportional to session counts).
- Resolve each sampled event's `native_locator` to the original artifact line and
  compare kind / content / occurred_at / usage values / relation endpoints.
- Compare session-level fields (cwd / model / title / git_branch / started_at /
  ended_at) with the original artifact fields.
- Report only truncated (≤80 char) fragments; full message bodies never leave the DB.

## Round 1 — Findings (severity-ranked)

| Severity | Finding | Family |
|---|---|---|
| 🔴 High | tool_call/tool_result content entirely missing (inputs/outputs not stored) | codex / opencode / mimo |
| 🔴 High | old-format events have no occurred_at (56,832 events) | kimi |
| 🔴 High | tool_result hard-truncated at 2048 chars (content=None) | claude / mimo reasoning |
| 🟡 Medium | fidelity_json claims complete while content is missing | codex / opencode / mimo |
| 🟡 Medium | cwd missing (native has it) | kimi / workbuddy / zcode / opencode / mimo |
| 🟡 Medium | ended_at missing | zcode |
| 🟡 Medium | model coarse/alias (`openai` vs `gpt-5.6-luna`) | codex / claude |
| 🟢 Low | ordinal NULL while fidelity claims ordering=complete | codex |

## Round 2 — Fix verification

| Fix | Verified result |
|---|---|
| codex tool content | tool_call 96.9%, tool_result 94.7% (remaining = non-standard tool types without input/output) |
| claude tool content + 2048 cap | 100% / 99.9%; 25,192-char tool_result preserved verbatim |
| kimi occurred_at | 100% (82,956 events), millisecond-exact vs native `time` |
| zcode ended_at / cwd | 345/345, exact vs `time_updated` / `directory` |
| grok model / branch | 62/62 (`current_model_id` / `head_branch`) |
| opencode/mimo tool content + cwd | 100%; cwd from `message.path.cwd` |
| mimo reasoning | still truncated at 2048 (missed by first fix batch) |

## Round 3 — Residual fixes & final verification

| Residual fix | Verified result |
|---|---|
| mimo reasoning full content | 352/352 with content (cap 100,000; 159,098-char original stored to cap, verbatim head) |
| claude sub-agent model | concrete names (fable-5/sonnet-5/opus-5), only 3 None |
| claude tool_call 8192 cap | capped@8192 = 0; 16,827-char input preserved fully |
| codex ordinal | 209,510/209,561 (99.98%), monotonic line numbers |

## Final per-family fidelity rating (round 3)

| Family | Rating | Notes |
|---|---|---|
| codex / claude / kimi / workbuddy / zcode | 🟢 High | content/timestamps/usage/relations all faithful |
| grok / opencode / mimo / copilot / pi | 🟢 High | after fixes; grok 2-events-per-session is a capture limitation (no chat_history in native dir) |
| cursor / antigravity | 🟢 High (source-limited) | antigravity steps are binary protobuf without schema — unknown_native is honest; cursor native lacks model/title/cwd |

## Round 4 — post-activation audit of the formal projection (2026-08-16)

**Scope:** after purging failed live-cohort residues and activating
`shadow-cohort-b9abd482b46c` (1,250 sessions) as the formal projection in the
canonical DB, a fresh stratified random sample was drawn and compared against
the staged native mirrors. Sample: 209/1,250 sessions (~17%, seed=20260816,
small families fully covered; manifest: `var/audit/round4-manifest.json`,
per-group reports: `var/audit/round4-*.json`). Subagent-driven, same method as
R1–R3; all counts below cross-verified independently by the orchestrator.

### What passed

- **Projection layer (v2 → legacy canonical) is lossless at checked dimensions**:
  40 sampled sessions × (started_at/ended_at/cwd/model/agent) all match; 112
  sampled canonical_messages content/timestamp/role all match ce_events source.
- **Timestamps: 0 mismatches anywhere** (codex 333/333, zcode 323/323,
  claude 55/55, kimi 96/96, workbuddy 168/168, grok 20/20, mimo 27/27,
  opencode 46/46, pi 18/18 — all millisecond-exact).
- **Session fields largely faithful**: grok 60/60 (incl. model/branch/cwd),
  codex cwd/model/started/ended 56/56, zcode started/title/cwd 55/55,
  workbuddy started/ended/model 28/28, pi and cursor fully as-expected,
  antigravity honest (all not_in_native).
- **Historical fixes held**: no 2048 cap on claude tool_result (max 61,314
  chars), no 8192 cap on claude tool_call (54 inputs >8192 preserved verbatim),
  mimo reasoning full content, codex tool content 94–97% (only non-standard
  tools unfilled, by design).

### New findings (systemic, full-DB verified)

| Severity | Finding | Scale |
|---|---|---|
| 🔴 High | kimi: every non-message kind has NULL content/summary/payload_ref — native wire.jsonl has tool args/outputs/thinking | tool_call 13,369 + tool_result 13,370 + reasoning 6,193 + unknown_native 7,433 |
| 🔴 High | workbuddy: tool/reasoning/usage content not projected (native function_call.arguments / result.output.text / rawContent exist) | tool_call 18,108 + tool_result 17,664 + reasoning 13,547 + usage 14,712 |
| 🔴 High | zcode: tool part state.input never extracted; no tool_result kind at all (state.output lost) | tool_call 29,332/29,332 NULL content; 0 tool_result events |
| 🟡 Medium | codex: `event_msg/agent_message` content hard-truncated at 2048 via `_payload_text`, no disposition recorded | 416/26,156 assistant messages (46+ with no response_item twin → tail lost) |
| 🟡 Medium | mimo/opencode: session `time_updated` never mapped → ended_at NULL | 15/15 + 57/57 sessions |
| 🟡 Medium | copilot: model only from session.info, no fallback to tool.execution_complete.data.model; tool arguments/results not stored | 5/12 sessions model recoverable; tool_call 1,391 + tool_result 1,340 empty |
| 🟡 Medium | claude: placeholder duplicate sessions — same subagent jsonl yields a full session + a 1-event `#agent:` stub; attachment content unprojected | 54/116 sessions are stubs; 2,427 attachment messages empty |
| 🟢 Low | kimi ended_at NULL 7/102 (native has last timestamp); bare model alias `k3` 6/102; whitespace strip on 4 mimo/opencode tool_results; zcode ended_at snapshot skew 3/55 (source DB kept writing after capture) | small |

### Interpretation

R1's "tool content missing" fix covered codex/claude/opencode/mimo only;
kimi/workbuddy/zcode/copilot tool-content projection and the codex
agent_message 2048 cap were **outside the verified scope of R1–R3** and are
newly measured here — not regressions of previously verified claims. The v2
event store and canonical_tool_events (name-only for these families) are
affected; canonical_messages (user/assistant text) is unaffected and remains
verbatim-faithful.

## Round 4 fixes — applied and re-verified (2026-08-16, generation `shadow-cohort-5429d7e2194b`)

All seven systemic findings were fixed in the adapters (version bumps:
codex 1.3.0 · claude_qoder 1.3.0 · workbuddy_kimi 1.3.0 · zcode 1.3.0 ·
mimo_opencode 1.2.0 · copilot 1.1.0), full test suite green (contract+unit+
integration, exit 0), generation rebuilt, activated (prior
`shadow-cohort-68b53b7e1d84` retained as rollback) and the serving snapshot
rotated; `pk-ku doctor --skip-ports` OK.

| Fix | Verified result (new generation, cross-checked by orchestrator) |
|---|---|
| zcode tool state extraction | tool_call content 29,708/29,708; NEW tool_result 29,119/29,119 with CALL_RESULT relations; reasoning full content 15,470/15,470 |
| kimi/workbuddy tool+reasoning+unknown content | kimi tool_call 13,499/13,499, tool_result 13,500/13,500; workbuddy tool_call 18,108/18,108, tool_result 17,664/17,664, reasoning 13,547/13,547; unknown_native bounded-payload preservation |
| codex agent_message 2048 cap removed | 0 events at exactly 2048 (was 416); max length 10,908; truncation dispositioned at 100k |
| mimo/opencode ended_at mapping | 15/15 and 57/57 sessions (was 0) |
| copilot model fallback + tool payloads | model 9/12 (5 recovered, 3 natively absent); tool_call 1,391/1,391; tool_result 1,260/1,340 (80 are failed calls with native `error` and no result payload) |
| claude placeholder stub sessions | 0 single-event stub sessions (was 54); SUBAGENT_BOUNDARY fallback for no-main files preserved |
| claude attachment content | 338/338 attachment system_messages carry bounded payload content (was 0) |

Honest-empty normalization verified against staged originals: kimi reasoning
without content (2,188/6,248) all have native `think: ""`; remaining empty
contents match natively absent payloads. Integrity: 0 orphan relations,
gates overall=true. Residual known-good: claude title placeholders and
codex non-standard tools remain by design (unchanged from R3).

## Round 5 — post-fix verification audit (2026-08-16/17, generation `shadow-cohort-5429d7e2194b`)

**Scope:** fresh stratified random sample (209/1,258 sessions, seed=20260817,
`var/audit/round5-manifest.json`), subagent-driven, same method as R4 with
artifact-id content-addressed source resolution (no basename collisions) and
dual-side `generation_id` filtering. Focus: verbatim correctness of the newly
projected content (R4 fixes), not just presence. Reports:
`var/audit/round5-*.json`.

### Fix verification — all seven R4 fixes PASS at sample and full-DB scale

- codex long messages: 34/34 sampled verbatim; full-DB 885 messages >2048
  (max 10,908), zero at exactly 2048.
- zcode new projections full-DB verbatim: tool_call 29,705/29,708 semantic-equal
  (3 truncated at 50k WITH disposition), tool_result 29,119/29,119, reasoning
  15,470/15,470.
- kimi/workbuddy new projections: 324/327 sampled content match (3 unsure =
  known design), 0 mismatch; empty reasoning/think all natively empty.
- mimo/opencode ended_at: 15/15 + 57/57 = native session.time_updated.
- copilot: model 9/12 with fallback values verbatim from
  tool.execution_complete.data.model; tool contents verbatim; 80 failed calls
  honestly empty (native error, no result).
- claude: 0 single-event stub sessions; 54 remaining single-event sessions are
  all genuine subagent_boundary fallbacks (R4's 8 stop_reason mis-derivations
  eliminated); attachment payloads 338/338 verbatim.
- Projection layer (v2→canonical): 40 sessions × 5 fields + 101 messages
  content/timestamp/role — 0 deviations.
- Timestamps: 0 mismatches anywhere (all families, millisecond-exact).

### New residual findings (minor, pre-existing behaviors)

| Severity | Finding | Scale |
|---|---|---|
| 🟡 Medium | mimo/opencode `_payload()` strips whitespace from tool payloads and caps at 50k without a truncation disposition | 791 stripped (688 opencode + 103 mimo); 16 truncated at exactly 50k, 0 dispositioned |
| 🟢 Low | zcode ended_at derives MAX(message/part time) instead of session.time_updated | 17/353 (16 exactly equal, 1 off by 3ms) |
| 🟢 Low | codex title quality: CLI-injected `# Files mentioned by the user` not in placeholder-skip list; GSD template tasks skipped → NULL title | 27/356 titles |
| 🟢 Low | copilot one session could recover model from session.model_change (not in fallback chain) | 1/12 |
| 🟢 Low | mimo title 256-char truncation unrecorded (2); opencode empty-string reasoning → NULL representation (732, zero content diff) | small |
| Note | pi tool_call 512-char / reasoning 2048 truncations are 100% dispositioned (honest by design); copilot 9f586e57 native file has a corrupted NUL tail line (source-side, no loss) | — |

**Verdict:** zero real fidelity mismatches in Round 5; all Round-4 fixes hold.
The pipeline's conversation data is verbatim-faithful at every audited
dimension modulo the documented minor residuals above.

## Round 5 fixes — applied and re-verified (2026-08-17, generation `shadow-cohort-74c3020369b2`)

All Round-5 residuals fixed in the adapters (mimo_opencode 1.3.0 · zcode 1.4.0
· codex 1.4.0 · copilot 1.2.0), full test suite green (exit 0), generation
rebuilt + activated (prior `shadow-cohort-5429d7e2194b` retained), serving
snapshot rotated, `pk-ku doctor` OK.

| Fix | Verified result (new generation) |
|---|---|
| mimo/opencode `_payload` no longer strips whitespace; 50k truncation now dispositioned | leading whitespace preserved 40/270 (mimo) + 181/2,353 (opencode); 16 truncated-at-50k outputs all carry disposition |
| zcode ended_at folds in session.time_updated | 358/358 sessions non-null (was 17/353 under-reported); contract test updated to the new semantics |
| codex `# Files mentioned by the user` injected message skipped as title source | titles equal to that injection 6 → 0; NULL-title count unchanged (77/356, pre-existing GSD-template skipping by design) |
| copilot `session.model_change.data.newModel` joins the model fallback chain | copilot model 9/12 → 10/12 (remaining 2 natively model-less) |

Integrity: 1,263 sessions / 612,805 events / 233,115 relations, 0 orphans,
gates overall=true.

## Known residual limitations (not extraction bugs)

- kimi/workbuddy `cwd`: capture layer only passes basenames (`capture_file(relative_path=path.name)`);
  absolute workdir lives in `state.json.workDir` which never enters the artifact set — needs a capture-layer change.
- kimi new-format sessions (7/102): native file has no `model` field at all.
- antigravity protobuf: no `.proto` schema available; semantic decode impossible (declared in capability).
- codex non-standard tools (web_search/mcp_tool_call_end): payload uses query/invocation fields without input/output.
- JSON key-order / block-boundary newline normalization in tool payloads (semantic equal, not byte-equal).

## Regression status

- `tests/contract` + `tests/unit` + conversation integration suites: all green (~1,000+ tests).
- Shadow rebuild: gate `overall=true`, 0 blocked.
- Relationship graph: 0 orphan endpoints across all families (195k+ relations).

