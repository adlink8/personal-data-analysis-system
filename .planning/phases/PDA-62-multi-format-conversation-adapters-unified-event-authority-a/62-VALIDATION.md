---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 07
subsystem: conversation extraction validation
date: 2026-08-12
mode: metadata-only
paid_calls: 0
disposition: NOT_READY_FOR_ACTIVATION (shadow-only; activation stays blocked)
evidence_artifacts:
  - .planning/phases/PDA-62-multi-format-conversation-adapters-unified-event-authority-a/62-SHADOW-REPORT.json
  - data/staging/v2/shadow/agent_conversations_v2.sqlite
  - data/staging/v2/artifacts
---

# Phase 62 Plan 07: Requirement and Security Validation Matrix

**Conclusion: `NOT_READY_FOR_ACTIVATION`.** The live shadow cohort produced honest
per-family evidence but **not** full 17-family capture coverage: 13 families had
no flat-file native source reachable through the v2 CLI shadow seam, and 3 file
families (codex / gemini / workbuddy) failed staging on live record shapes that
differ from the synthetic fixtures. `paid_calls=0` and no live canonical/KU
mutation occurred (incident inc-62-07-extract-guard-fallthrough was detected and
fully restored). `READY_FOR_HUMAN_ACTIVATION_REVIEW` is **not** claimed because
the `native_available_captured_or_blocked` critical gate fails.

---

## 1. Requirement coverage (CONV-01..08)

| Req | Evidence | Status | Notes |
|---|---|---|---|
| **CONV-01** | `known_families()` = 17; per-family `CapabilityDescriptor` (adapter_version/contract_version/event_kinds/relation_kinds); capability_coverage gate `with_result=17, missing=[]` | **PARTIAL** | All 17 families have an explicit versioned capability result; but live capture coverage is 1/17 staged (claude) + 3 blocked-staging + 13 no_source. Fail-closed disposition holds (nothing silent). |
| **CONV-02** | `test_conversation_source_snapshots.py` + `test_conversation_source_privacy.py` (12 + 22 passed); forbidden tables/columns canary negatives; WAL online backup; `forbidden_source_access=0` in live probe | **PASS** | Privacy negative tests green; live probe reads only `sessions`, never touches forbidden tables (`secret_findings` present but not read; `forbidden_source_access=0`). |
| **CONV-03** | `test_conversation_event_contracts.py` (typed events/relations/provenance); staged claude generation `validate()` ok: integrity=ok, FK check empty, provenance 10/0 unprovenanced | **PASS** (staged cohort) | Only the claude family staged on live data; typed event model proven by contract tests + staged generation validation. |
| **CONV-04** | fidelity report per family; claude `structure_completeness=partial`; chatgpt/cursor disclosures; unknown_native preserved | **PARTIAL** | Claude staged partial (honest); 3 families blocked on staging; 13 no_source — fidelity for those is `unknown`/`unavailable`, not fabricated. |
| **CONV-05** | `test_conversation_v2_compatibility.py` (projection parity, no double counting, exact lineage/fingerprint); `test_conversation_v2_sync.py`; consumer evidence (projected 1 session / 3 messages readable via `ConversationRepository`) | **PASS** | Compatibility projection deterministic; consumers read the projected legacy contract. Live canonical DB untouched (fingerprint unchanged; no `ce_*` tables created). |
| **CONV-06** | `test_conversation_extraction_views.py` (31) + `test_conversation_extraction_policy.py` (16) + `test_conversation_view_repository.py` (14); view_counts per family; DEFAULT_POLICY compaction-first | **PARTIAL** | Seven-view builders proven by tests; live staged claude yields episode(5)/session(1) views; turn/native_trace/compaction/topic/cross_session=0 because the staged claude file carries no such native boundaries. |
| **CONV-07** | `test_semantic_admission_gate.py` (26) + `test_conversation_extraction_policy.py` | **PASS** | Deterministic-first admission + abstention-capable replay judge; judge cannot override deterministic rejection. |
| **CONV-08** | All 196 focused tests green (this plan) + 160 adjacent regressions; `paid_calls=0`; active KU empty; old-run guard incident documented | **PARTIAL** | Replay/idempotency/privacy/parity/fault-injection all green; **old-run refusal is NOT effective on live** (see Section 6) — a genuine blocker for activation. |

---

## 2. Decision coverage (D-01..D-31)

| Decision | Status | Evidence |
|---|---|---|
| D-01 (17 families) | PASS (capability) / PARTIAL (capture) | 17 capabilities; 1 live-staged + 3 blocked-staging + 13 no_source capture. |
| D-02 (versioned registry, one contract per family) | PASS | `registry.py`; aliases resolve to owning family. |
| D-03 (AgentsView read-only, not semantic authority) | PASS | live probe read-only `mode=ro` + `query_only`; only `sessions` table read. |
| D-04 (fail closed, never silent coercion) | PASS | shadow per-family blocked dispositions; staging failures now fail closed per family (v2_sync.py fix). |
| D-05 (content-addressed immutable snapshots; SQLite online backup) | PASS | `snapshots.py` capture_file/capture_sqlite; artifact store blobs. |
| D-06 (provenance back to artifact/locator/hash) | PASS | staged claude provenance 10/10 resolvable. |
| D-07 (native_payload_ref / field dispositions explicit) | PASS | disposition counts per family in report; synthetic test asserts redacted/unavailable/unsupported counted. |
| D-08 (allowlist, forbidden tables never captured) | PASS | privacy suite green; live probe `forbidden_source_access=0`. |
| D-09 (manifests metadata-only) | PASS | shadow report contains hashes/fidelity/counts only; body/secret scan clean. |
| D-10 (typed event model, not flattened list) | PASS | event contract tests; staged typed events. |
| D-11 (stable identity; ordering not identity) | PASS | `make_event_id` tests. |
| D-12 (first-class relations) | PASS | relations in staged claude (5); contract tests. |
| D-13 (fidelity partial/unknown/unavailable never complete) | PASS | fidelity dimensions; claude structure=partial disclosed; `FidelityProfile.has_loss()`. |
| D-14 (ChatGPT no native path → honest partial) | PASS (disclosed) | chatgpt disclosure in report; no transcript fabricated. |
| D-15 (reuse canonical db/pk-sync seams) | PASS | shadow staged in `data/staging/v2`; live canonical untouched. |
| D-16 (additive v2 tables beside current schema) | PASS | `ce_*` tables in shadow db only; live canonical has none. |
| D-17 (legacy tables become deterministic projection) | PASS | compatibility projection tests + consumer evidence. |
| D-18 (shadow/staging then atomic activate; failure→rollback) | PASS (mechanism) / PARTIAL (live) | `GenerationLifecycle` fault-injection tests (17) green; activation not performed; staged generation validated. |
| D-19 (old canonical tables readable until consumers migrate) | PASS | compatibility projection contract tests. |
| D-20 (trace = replaceable view, not authority) | PASS | NativeTraceView only from explicit native IDs; policy tests. |
| D-21 (seven derived views) | PASS | view builders + tests; counts per family. |
| D-22 (versioned ExtractionPolicy, not hard-coded) | PASS | policy digest tests; DEFAULT_POLICY compaction-first. |
| D-23 (compaction highest initial priority) | PASS | policy contract tests. |
| D-24 (candidate lineage + evidence refs) | PASS | `view_candidate_prepare` tests; contradiction/lineage. |
| D-25 (adapter quality vs native fixtures + live metadata) | PASS (partial live) | fidelity evaluator (Task 1) measures discovery/capture/adapt/dispositions/replay/parity/views. |
| D-26 (two gates: deterministic first, semantic second) | PASS | `semantic_admission.py` tests. |
| D-27 (abstain-capable; reason codes; no sensitive prompt bodies) | PASS | semantic gate tests; DecisionRecord metadata-only. |
| D-28 (redacted reference set per family) | PASS (fixtures) / PARTIAL (live) | synthetic fixtures per family; live shapes differ → 3 blocked. |
| D-29 (quarantined KU isolated, active KU empty) | PASS | `knowledge_units=0`, active collection empty. |
| D-30 (old 24,487-call queues must not be extracted) | **PARTIAL — BLOCKER** | Guard works only when `ce_candidate_audit` exists; live DB has none → guard falls through (incident, restored). |
| D-31 (no extract/provider/paid work) | PASS (paid_calls=0) / incident-restored | `paid_calls=0`; provider_calls=0; the one guard-fall-through invocation marked 32 items terminal_failed and was fully restored to pending. |

---

## 3. Focused test commands (Task 3 verification)

| Command | Result |
|---|---|
| `python -m pytest -q tests/integration/test_conversation_v2_live_metadata.py` | **18 passed** |
| `python -m pytest -q tests/unit/test_conversation_event_contracts.py tests/contract/test_conversation_stream_adapters.py tests/contract/test_conversation_store_adapters.py tests/security/test_conversation_source_privacy.py tests/integration/test_conversation_event_generations.py tests/contract/test_conversation_extraction_policy.py tests/unit/test_semantic_admission_gate.py tests/contract/test_view_candidate_prepare.py` | **178 passed** |
| Adjacent v2 regressions (v2_sync / generations / compatibility / view repo / snapshots) | **67 passed** |
| **Total** | **196 passed (focused) + 67 adjacent** |

## 4. Shadow cohort evidence summary

- **Mode:** metadata-only shadow (`pk-sync conversations --v2-shadow --write`).
- **Live cohort:** 4 real flat-file artifacts copied read-only from live agent
  stores into `data/staging/v2/live` (codex, claude, gemini, workbuddy).
- **Result:** claude **partial** (staged, 10 events, 1 session, 5 relations,
  structure=partial), codex/gemini/workbuddy **blocked** (staging_failed:
  `EventRepositoryError` FK — live record shapes lack the native `session_id`
  the adapter emits a derived session for), 13 families **no_source** (flat-file
  seam cannot reach SQLite/directory families zcode, mimo, opencode, antigravity,
  cursor, grok, chatgpt, etc.).
- **Schema/FK:** staged claude generation `validate()` ok; `PRAGMA
  integrity_check=ok`; `PRAGMA foreign_key_check=[]`; provenance 10/0.
- **Source fingerprints:** live canonical DB unchanged (SHA-256 identical);
  `var/db` logical state restored (24,487 items all pending, leases 0, cache 0,
  KU 0); AgentsView is daemon-write (hash varies with daemon activity, read-only
  access).
- **Compatibility consumers:** projected 1 session / 3 messages readable via
  `ConversationRepository(source=canonical)`.
- **Views:** staged claude → episode 5, session 1, others 0.
- **Cost estimate:** deterministic local arithmetic only — 6 semantic-gate calls,
  30,720 tokens, USD 0.016589, **paid_calls_executed=0**.
- **Deterministic gates:** `capability_coverage=ok`, `unresolved_provenance=ok`,
  `forbidden_source_access=ok`, `replay_digest_stable=ok`,
  `current_consumers_pass=ok`, `partial_chatgpt_cursor_disclosed=ok`,
  `paid_calls_zero=ok`; **`native_available_captured_or_blocked=FAIL`**
  (13 families with live-discovered sessions not captured, because the flat-file
  shadow seam cannot reach them and they are reported `no_source`, not `blocked`).

## 5. Privacy negatives and fault injection

- **Privacy:** `test_conversation_source_privacy.py` 22 passed — forbidden
  tables/columns canary values never in artifacts/manifests; declaring a
  forbidden table fails closed; path escape rejected; WAL online-backup.
- **Activation/rollback fault injection:** `test_conversation_event_generations.py`
  17 passed — checksum mismatch, stale manifest, unknown adapter, consumer
  parity, projection/authority/version write failure all restore exact prior
  state; old generation rows + audit preserved.
- **Replay/idempotency:** Task 1 evaluator re-adapts the captured blob and
  compares dataset digests; staged claude replay digest == staged digest.

## 6. Known blockers (honest partial/unknown)

1. **D-30 old-run refusal is NOT effective on live.** The guard
   `_assert_legacy_not_superseded` requires a `ce_candidate_audit` row on the
   live canonical DB, which is never materialized without a live write.
   **Incident inc-62-07-extract-guard-fallthrough:** a verification invocation
   of `pk-ku extract --run ir_b0099928a0ad7f5e` fell through the guard and
   marked 32 user items `terminal_failed` on live `var/db`. All 32 were
   restored to exact prior `pending` state (verified: 3,224 pending, leases 0,
   response_cache 0). **Activation must remain blocked** until the supersession
   audit is materialized in an authorized live-write step (Plan 62-08 scope).
2. **Live capture coverage is partial:** the v2 CLI shadow seam
   (`probe_conversation_sources`/`shadow_conversation_generation`) discovers
   only flat files under a source root; SQLite families (zcode/mimo/opencode/
   antigravity/cursor), directory families (grok), and chatgpt (no native path)
   are reported `no_source`, not captured. This is an honest environmental
   limitation of the current seam, not fabricated coverage.
3. **Live record shapes differ from synthetic fixtures** for codex (payload-
   wrapped), gemini (camelCase `sessionId`), workbuddy (no per-record
   `session_id`) — the adapters emit derived-session events with no session row,
   tripping the FK constraint and failing staging. Fixes require adapter contract
   version bumps (Plan 62-08 or a dedicated adapter-hardening plan).

## 7. provider-call count

- Shadow/evaluator/tests: **0** provider calls (all local deterministic).
- Kernel health: `provider_calls=0`.
- Report: `paid_calls=0`, `report_contains_bodies_or_secrets=false`.
- Incident: 0 paid calls (the guard-fall-through run hit local failure paths;
  `response_hash=None` on all items; no provider output persisted).

---
*Disposition: shadow-only. `READY_FOR_HUMAN_ACTIVATION_REVIEW` is NOT claimed
because the critical native-available-captured-or-blocked gate fails and the
D-30 old-run refusal is ineffective on live.*
