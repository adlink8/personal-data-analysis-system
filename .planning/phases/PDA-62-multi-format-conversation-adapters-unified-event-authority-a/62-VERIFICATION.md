---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
verified_at: 2026-08-15T11:37:45Z
status: passed
generation_id: live-cohort-39a8813cb95d1d77
serving_snapshot_id: ss_a0cfb34277a809e3d85a8196
paid_calls: 0
---

# Phase 62 Verification

## Verdict

**PASSED — CONV-01..08 verified against the current live AgentsView inventory,
immutable captured artifacts, the activated canonical database, serving
snapshot, real consumers and the full Phase 62 test matrix.**

This does not claim that every source has complete native fidelity. All 17
registered family names are honestly reported `partial`; unsupported or absent
native structure remains explicit. It does claim that every currently observed
source family is covered by a versioned adapter, all available files are
captured, no adapted rows were silently lost, and the resulting cohort is the
active canonical conversation authority.

## Live authority and data proof

- Active conversation generation: `live-cohort-39a8813cb95d1d77` (prior:
  `live-cohort-3ca0d9721bed2fde`).
- Active serving snapshot: `ss_a0cfb34277a809e3d85a8196`; snapshot and legacy
  pointer agree.
- Cohort: 16 owner-family runs / 17 registered names (the
  `vscode-copilot` alias resolves to `copilot`), 1,678 sessions, 988,690 typed
  events, 240,039 relations, 1,224 immutable artifacts.
- SQLite: `quick_check=ok`, `foreign_key_check=0`, unresolved provenance=0,
  invalid session fidelity=0.
- Compatibility projection: 1,678 sessions, 83,080 messages, 211,458 tool
  rows. `ConversationRepository` reads 1,678 projected sessions and 83,080
  projected messages.
- Old canonical data remains readable and unchanged in place: 1,159 non-v2
  sessions and 95,428 non-v2 messages retained.
- Live inventory count after activation exactly matches the captured cutoff for
  every owner family (including 662 Codex, 345 ZCode, 183 WorkBuddy, 158 Grok,
  104 ChatGPT observations and all smaller families). Grok combines 83 native
  snapshots with 75 explicitly unavailable-locator compatibility observations.
- Pre-activation SQLite online backups are under
  `archive/phase62/content-fix-20260815T183753/`; the canonical backup is
  1,369,755,648 bytes with SHA-256
  `5a4dafb98feb3edded4c558492890123148c5cafbfd511ad8b23f76fa4483d01`.

## Exact message-content repair

- `TypedEvent.content` now carries exact message text independently from
  `summary`; persistence, dataset digests, replay and compatibility projection
  all preserve it. Projection falls back to `summary` only for old events that
  have no `content` field.
- ChatGPT is converted from a row/column-allowlisted, read-only AgentsView
  observation: 104 sessions and 3,929 messages. The filtered artifact excludes
  auth, token, thinking and unrelated-agent rows.
- Grok stale locators are not silently dropped: all 158 sessions are present,
  with unavailable native provenance remaining explicit for the 75 missing
  source files.
- Claude/Qoder multi-block envelopes are decomposed into message, reasoning,
  tool-call and tool-result events with relations instead of becoming empty
  message rows.
- The active projection has 3,655 null-or-exact-empty messages and 4,476 after
  trimming, including 821 whitespace-only source values. These are retained as
  source facts rather than deleted or fabricated. Before this repair the active
  projection had 57,623 empty message bodies.
- The AgentsView source database remained byte-identical across capture:
  SHA-256 `823707bc2be2520f529c1f076032d49c6fd864bc1edaa7b58ff93f3a853852c6`.
- Runtime capture, probe and fidelity scratch space is rooted under project
  `var/tmp`; retained diagnostic replays are archived under
  `archive/phase62/diagnostic-replays`. No Phase 62 replay directory remains
  under the system drive temporary directory.

## Requirement verification

| Requirement | Result | Live evidence |
|---|---|---|
| CONV-01 | PASS | 17/17 versioned capability results; 16 explicit owner adapters; current inventory contains no uncovered family. |
| CONV-02 | PASS | 1,224 content-addressed artifacts; filtered SQLite capture uses family/session row filters plus explicit column allowlists; undeclared columns and forbidden credential/auth/token tables excluded; forbidden-source access count 0. |
| CONV-03 | PASS | Typed event authority contains sessions, messages, reasoning, tools, usage, compaction, boundaries, context and unknown-native records plus 234,791 first-class relations; all rows resolve to artifact/native locator. |
| CONV-04 | PASS | Per-session/event and family roll-up fidelity is explicit; 17/17 are honestly partial and never presented as complete. |
| CONV-05 | PASS | Verified cohort transactionally imported and activated in existing canonical DB; projection/version/watermark/fingerprint bound atomically; publication registry and serving snapshot both current; old rows preserved. |
| CONV-06 | PASS | Seven replaceable views rebuild from canonical events. Full Codex proof: turn 77,396; native trace 8,367; episode 667,131; compaction window 1,576; session 662; topic 4,619; cross-session 1. Priority is a versioned policy, not adapter code. |
| CONV-07 | PASS | Deterministic privacy/secret/injection/structure/evidence checks precede the abstention-capable semantic-value gate; missing evidence and low-fidelity compaction cannot pass by priority alone. |
| CONV-08 | PASS | 17/17 immutable-artifact replay digests stable; conversation matrix 344 passed / 20 skipped; active KU remains empty; no provider generation was run; Kernel provider_calls=0. |

## Fidelity and gate proof

The final metadata-only fidelity report is
`62-FIDELITY-EVAL-LIVE-FULL-LOSSLESS.json` (ignored JSON audit artifact):

- capability coverage: 17/17, missing=[]
- native available captured or explicitly unavailable: pass, violations=[]
- unresolved provenance: 0
- forbidden source access: 0
- replay digest stable: 17/17, drifted=[]
- consumer parity: projected sessions 1,678 = consumer sessions 1,678;
  consumer messages 83,080
- ChatGPT/Cursor limitations disclosed: pass
- paid calls: 0
- overall: true

The shadow report and staged DB were also independently count-reconciled before
promotion. This caught and fixed an earlier silent `INSERT OR IGNORE` loss:
event IDs now include immutable record locators when native IDs are reused,
`AdaptationResult` rejects duplicate event/session/relation identities, and the
semantic dataset digest includes event kind, fidelity, provenance, disposition,
summary and relation meaning rather than IDs alone.

## Tests and runtime

- Current conversation matrix: **344 passed / 20 skipped**; security matrix:
  **20 passed**.
- `git diff --check`: passed (only existing Windows LF/CRLF notices).
- `pk-ku doctor --json`: exit 0, 10/10 critical checks pass.
- `rag-search stats --json`: exit 0; knowledge collection remains
  `knowledge_units_empty_kg_20260812T025401Z_live`, count 0; turn retrieval
  remains available (3,601).
- REST `:8000/health`: HTTP 200.
- MCP `:8789/health`: HTTP 200.
- Pi Kernel `:8790/ready`: HTTP 200, `provider_calls=0`.
- Chroma `:8001`: HTTP 200; active empty knowledge collection count 0 and
  `conversation_turns` count 3,601.
- `pk-ku extract --run ir_6d1c610127139045 --max-items 1`: exit 2,
  `legacy message-level prepare run ... non-executable`; provider calls remain 0.

## Explicit boundary

Phase 62 completes the conversation fact authority, multi-format normalization,
replaceable extraction views, admission contract and activation. It does **not**
perform paid semantic extraction. Active KU is intentionally empty after the
old-data quarantine; `pk-sync status --json` therefore still reports
`s.knowledge_unit` drift until a separately approved view-policy prepare/extract/
evaluate/promote workflow produces a new knowledge generation. This is an
expected downstream state, not a Phase 62 authority failure.
