---
phase: quick
plan: 260812-dug
subsystem: personal-knowledge
tags: [sqlite, chroma, serving-snapshot, rollback, quarantine, knowledge-units]

requires:
  - phase: 23
    provides: immutable composite serving snapshots and version-bound watermarks
  - phase: 14
    provides: knowledge-unit inventory, extraction ledger, canonical units, and Chroma index lifecycle
provides:
  - checksummed online SQLite backup and exact manifest-constrained restore
  - fail-closed legacy KU isolation with automatic restoration on any projection failure
  - active zero-entry knowledge generation with preserved canonical/normalized/Google sources
  - user/assistant rebuild queues and a cost-approval boundary with zero paid calls
affects: [knowledge-rebuild, pk-ku, serving-snapshots, disaster-recovery]

tech-stack:
  added: []
  patterns: [allowlisted derived-state mutation, online SQLite backup, immutable publication watermark binding, explicit paid-call checkpoint]

key-files:
  created:
    - src/personal_knowledge/application/knowledge/quarantine_manifest.py
    - src/personal_knowledge/application/knowledge/legacy_isolation.py
    - src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py
    - tests/integration/test_isolate_legacy_knowledge.py
  modified: []

key-decisions:
  - "Treat activate_snapshot ok=true with projection_ok=false as failure and restore the entire SQLite authority plus pointer."
  - "Never delete legacy Chroma collections; activate a separately named, checksummed empty collection."
  - "Publish fresh artifact versions and source watermarks for all three replacement knowledge roles."
  - "Stop at blocked_pending_user_cost_approval after local prepare; no extract or provider generation is authorized."

patterns-established:
  - "Quarantine manifest restore accepts only the exact producer, generation path, target paths, schema fingerprint, logical fingerprint, and backup checksum."
  - "Live mutation requires 8000/8789/8790 consumers stopped while Chroma 8001 remains available."

requirements-completed: []

duration: 31min
completed: 2026-08-12
---

# Quick 260812-dug: Reversible Legacy Knowledge Isolation Summary

**All legacy derived KU state was quarantined behind a checksummed SQLite backup, serving moved to a zero-entry Chroma generation, and two-track rebuild preparation stopped before any paid call.**

## Performance

- **Duration:** 31 min
- **Started:** 2026-08-12T02:28:56Z
- **Completed:** 2026-08-12T02:59:31Z
- **Tasks:** 3/3
- **Code/test files created:** 4
- **Paid provider calls:** 0

## Accomplishments

- Added a fail-closed `plan` / guarded `apply` / exact `rollback` CLI whose state machine owns all SQLite, Chroma, snapshot, pointer, and restoration transitions.
- Created final live generation `kg_20260812T025401Z_live`, snapshot `ss_916f80a497db56ccab23b0fc`, and active collection `knowledge_units_empty_kg_20260812T025401Z_live` with zero entries.
- Cleared every allowlisted legacy KU, inventory, ledger, cache, lifecycle, and index row; after isolation only the empty build/index existed. Later no-cost prepare added two pending rebuild runs and 24,487 pending work items while KU/cache/lifecycle rows stayed zero.
- Preserved all original AgentView, normalized, canonical conversation, and Google fingerprints and retained every pre-existing knowledge Chroma collection as inactive rollback evidence.
- Generated privacy-safe user and assistant prepare artifacts with a combined estimate of 24,487 calls, 48,974,000 tokens, and USD 24.487; extraction remains blocked pending user cost approval.

## Task Commits

1. **Task 1: Reversible isolation boundary** — `02756ca` (feature), `1ead42e` and `cc9f21c` (live-found correctness fixes)
2. **Task 2: Live isolation and empty serving generation** — runtime artifacts only; intentionally not committed
3. **Task 3: No-cost two-track prepare and budget** — private runtime artifacts only; intentionally not committed

## Files Created

- `src/personal_knowledge/application/knowledge/quarantine_manifest.py` — online SQLite backup, privacy-safe logical fingerprints, manifest checksum validation, and constrained restore.
- `src/personal_knowledge/application/knowledge/legacy_isolation.py` — allowlisted derived-table transaction, empty collection/snapshot activation, consumer gate, and automatic rollback.
- `src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py` — thin CLI with explicit write confirmations.
- `tests/integration/test_isolate_legacy_knowledge.py` — dry-run, source preservation, projection rollback, manifest drift, consumer, unknown-table/FK, and watermark publication coverage.
- `archive/quarantine/knowledge_generations/kg_20260812T025401Z_live/manifest.json` — final applied before/after manifest.
- `archive/quarantine/knowledge_generations/kg_20260812T025401Z_live/personal_system.sqlite` — final exact pre-isolation backup.
- `var/reports/analysis/ai_context/knowledge_rebuild_prepare_kg_20260812T025401Z_live_user.json` — user-only prepare statistics.
- `var/reports/analysis/ai_context/knowledge_rebuild_prepare_kg_20260812T025401Z_live_assistant.json` — assistant-only prepare statistics.
- `var/reports/analysis/ai_context/knowledge_rebuild_prepare_kg_20260812T025401Z_live.json` — combined budget and blocked paid-call checkpoint.

Rollback evidence is retained at `kg_20260812T024335Z_live` (`rolled_back_after_failure`) and `kg_20260812T024812Z_live` (`rolled_back_explicitly`). Neither generation is active.

## Decisions Made

- The source watermark value for replacement roles includes the unique isolation generation, preventing mutable watermark reuse from invalidating older snapshot evidence.
- The empty generation has a `not_applicable_empty_generation` evaluation publication rather than claiming an evaluation pass over zero KU.
- `legacy_isolation.py` is 666 lines, above the 500-line review threshold. It remains one file because this task's ownership and PLAN fix the three-module boundary and require the CLI to stay thin. Split the Windows/Chroma/snapshot adapters from the state machine before adding another platform adapter or a second isolation lifecycle.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rejected regressing role watermarks**
- **Found during:** Task 2, first live apply
- **Issue:** Reusing the canonical-message watermark for retrieval/evaluation caused snapshot validation to reject two watermark regressions.
- **Fix:** Initially retained each role's current watermark; the failed apply automatically restored the exact pre-migration DB and pointer and deleted its new empty collection.
- **Files modified:** `legacy_isolation.py`, integration test
- **Verification:** focused regression plus full isolation test passed; rollback manifest status is `rolled_back_after_failure`.
- **Committed in:** `1ead42e`

**2. [Rule 1 - Bug] Doctor required artifact-version-bound fresh watermarks**
- **Found during:** Task 2, post-activation Doctor
- **Issue:** Snapshot validation passed, but Doctor correctly reported `watermark_version_mismatch` for the new retrieval and evaluation artifacts.
- **Fix:** Recorded fresh publications and fresh source watermarks for canonical knowledge, knowledge retrieval, and knowledge evaluation; explicitly rolled back the intermediate successful generation, then re-applied from the original state.
- **Files modified:** `legacy_isolation.py`, integration test
- **Verification:** 42 focused tests passed; final Doctor exit 0 with 10/10 critical checks and no watermark errors.
- **Committed in:** `cc9f21c`

**3. [Rule 3 - Blocking] Explicit prepare provider metadata**
- **Found during:** Task 3, first user-track prepare command
- **Issue:** The local CLI has no default provider and rejected the plan's abbreviated command with `unknown provider` before writing or calling anything.
- **Fix:** Added the project-runbook metadata flags `--provider vertex_google --endpoint https://aiplatform.googleapis.com --auth-mode gcloud` to both prepare calls.
- **Verification:** Both prepare artifacts report `validation_passed=true` and `production_llm_calls=0`.
- **Committed in:** runtime-only; no code change

---

**Total deviations:** 3 auto-fixed (2 correctness bugs, 1 blocking invocation issue)
**Impact on plan:** All changes tightened rollback and serving-authority correctness. No source data, old collection, or paid-call scope was added.

## Verification

- `python -m pytest -q tests/integration/test_isolate_legacy_knowledge.py` — 7 passed.
- Snapshot/promotion/Doctor focused regression — 42 passed.
- Broader snapshot consumer selection — 72 passed before the live run.
- `pk-ku doctor --json` — exit 0, 10 critical checks passed, FK clean, snapshot/pointer parity clean, watermark binding clean.
- `rag-search stats --json` — active final empty collection, KU DB/vector counts both 0.
- `rag-search semantic "PPT 排版" --top-k 3 --json` — KU layer hits 0; first contributing layer `canonical_messages`; legacy pad not used.
- Manifest self-check — backup checksum and logical fingerprint valid; source fingerprints unchanged; every old collection name still exists.
- Services after cutover — REST 8000, MCP 8789, and Kernel 8790 all healthy; Chroma remained running throughout mutation windows.

## Prepare Cost Boundary

| Track | Roles | Prompt | Queued | Estimated tokens | Estimated cost |
|---|---|---|---:|---:|---:|
| user | user | v1 | 3,224 | 6,448,000 | USD 3.224 |
| assistant | assistant | v1_assistant | 21,263 | 42,526,000 | USD 21.263 |
| **total** | — | — | **24,487** | **48,974,000** | **USD 24.487** |

Recommended pilot, blocked until explicit cost approval:

```powershell
pk-ku extract --run ir_b0099928a0ad7f5e --max-items 25
pk-ku extract --run ir_6d1c610127139045 --max-items 25
```

Estimated two-track pilot: 50 calls / USD 0.05. These commands were **not** executed.

## Auth Gates

None.

## Known Stubs

None. No placeholder, TODO, mock-data, or empty UI flow is present in the created code.

## Threat Flags

| Flag | File | Description |
|---|---|---|
| threat_flag: constrained_database_restore | `quarantine_manifest.py` | Restores a live SQLite authority only after exact producer, path, schema, logical fingerprint, and backup checksum verification. |
| threat_flag: destructive_allowlist | `legacy_isolation.py` | Deletes rows only from the fixed derived-knowledge allowlist and fails closed on unknown knowledge tables or external foreign keys. |
| threat_flag: local_service_cutover | `legacy_isolation.py` | Requires exact local consumers to be stopped, preserves Chroma, and treats pointer projection drift as rollback-worthy failure. |

## User Setup Required

None. Paid extraction remains intentionally blocked pending an explicit budget decision.

## Next Phase Readiness

- Canonical conversation data is preserved and ready for a controlled user/assistant rebuild.
- Live knowledge serving is intentionally empty, consistent, and queryable through canonical dialogue fallback.
- No further action is authorized until the user approves a pilot or full extraction budget.

## Self-Check: PASSED

- All four code/test files, the final manifest/backup, all three prepare reports, and this summary exist.
- Commits `02756ca`, `1ead42e`, and `cc9f21c` are present.
- Runtime artifacts are intentionally ignored by repository privacy rules; PLAN/SUMMARY/STATE were not committed.
- Stub scan returned no TODO, FIXME, placeholder, or unavailable markers in created code/tests.

---
*Phase: quick 260812-dug*
*Completed: 2026-08-12*
