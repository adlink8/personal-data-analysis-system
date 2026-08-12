---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 01
subsystem: conversation event authority
tags: [typed-events, provenance, fidelity, snapshot, sqlite-online-backup, allowlist, generation, v2-schema, event-repository]

# Dependency graph
requires:
  - phase: 13.5
    provides: read-only AgentsView adapter + SQLite online-backup pattern, canonical store and legacy ConversationRepository seam
  - phase: 61
    provides: read-only AgentsView constraint and evidence-bound reflection context (D-03 supersedes 61 D-14 for ingestion authority)
provides:
  - typed EventKind/RelationKind/FidelityProfile/Provenance/FieldDisposition contract (core/conversation_events.py)
  - family adapter capability/result seam with deterministic dataset digest (adapters/conversation_sources/contracts.py)
  - allowlisted content-addressed immutable capture for file/directory/SQLite, WAL-safe, credential-excluding (adapters/conversation_sources/snapshots.py)
  - additive generation-bound v2 schema + event repository (application/conversation/event_schema.py, event_repository.py)
affects: [62-02, 62-03, 62-04, 62-05, 62-06, 62-07, 62-08, compatibility projection, extraction views]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Content-addressed immutable blob store (sha256 prefix ids) with atomic temp+rename publish"
    - "SQLite online backup + post-backup DROP of non-allowlisted tables for WAL-safe credential-safe capture"
    - "Generation-bound composite keys (generation_id, id) with in-generation FKs preventing cross-generation relations"
    - "Transactional stage-with-rollback: single BEGIN..COMMIT with INSERT OR IGNORE replay and integrity check"

key-files:
  created:
    - src/personal_knowledge/core/conversation_events.py
    - src/personal_knowledge/adapters/conversation_sources/__init__.py
    - src/personal_knowledge/adapters/conversation_sources/contracts.py
    - src/personal_knowledge/adapters/conversation_sources/snapshots.py
    - src/personal_knowledge/application/conversation/event_schema.py
    - src/personal_knowledge/application/conversation/event_repository.py
    - tests/unit/test_conversation_event_contracts.py
    - tests/integration/test_conversation_source_snapshots.py
    - tests/integration/test_conversation_event_repository.py
  modified: []

key-decisions:
  - "Event identity prefers native identity and always includes family/artifact/contract-version domains; ordinal is never an identity input (D-11)."
  - "Fidelity dimensions default to UNKNOWN in FidelityProfile.from_levels so absence is explicit; is_complete() requires every dimension COMPLETE (D-13)."
  - "Unprovenanced events (no artifact + no native locator) are rejected by the TypedEvent constructor and again by AdaptationResult validation (D-04)."
  - "SQLite capture = online backup then drop non-allowlisted tables; FORBIDDEN_TABLE_PATTERNS (account/credential/token/auth/secret/cookie/api_key) block allowlisting such tables by name (D-08)."
  - "v2 DDL is fully additive (CREATE TABLE IF NOT EXISTS, ce_* namespace); legacy canonical_* tables untouched (D-16/D-19)."
  - "ce_event_relations carries composite FKs to same-generation events + UNIQUE(source,target,kind), so a relation can never cross generations."
  - "EventRepository stages/validates/reads but never mutates ce_generation_authority (activation, projection, views belong to later plans)."

patterns-established:
  - "Pattern 1 (raw authority + semantic projection): immutable artifact first; events carry artifact_id + native_locator; unmodeled fields preserved by native_payload_ref/disposition."
  - "Pattern 2 (generation-bound canonical evolution): complete staged generation + validation; activation/authority is a separate state owner."

requirements-completed: [CONV-02, CONV-03, CONV-04, CONV-05]

# Metrics
duration: 95min
completed: 2026-08-12
---

# Phase 62 Plan 01: Multi-format conversation adapters, unified event authority — Summary

**Typed, loss-aware event/relation/provenance/fidelity contracts, allowlisted content-addressed immutable capture (file/directory/WAL-safe SQLite), and an additive generation-bound canonical v2 schema + repository with zero live-source writes**

## Performance

- **Duration:** ~95 min
- **Started:** 2026-08-12T07:10:00Z (approx)
- **Completed:** 2026-08-12T08:45:00Z (approx)
- **Tasks:** 3 (all TDD: RED → GREEN, plus REFACTOR for review thresholds)
- **Files modified:** 9 created (0 pre-existing files modified)

## Accomplishments

- **Task 1 — Loss-aware typed contract (RED→GREEN, 15 tests):** `core/conversation_events.py` defines 15 locked `EventKind`s, 9 `RelationKind`s, 7 `FidelityDimension`s with explicit `complete|partial|unknown|unavailable` levels, `Provenance`, `FieldDisposition*`, `TypedEvent`/`EventRelation`/`AdaptedSession` with constructor validation, and `make_event_id` (native identity preferred; family/artifact/contract-version collision domains; ordinal excluded). `adapters/conversation_sources/contracts.py` provides `SourceArtifact`, `SourceArtifactSet`, versioned `CapabilityDescriptor`, and `AdaptationResult` with a deterministic `dataset_digest` and endpoint validation. Events without an artifact/native locator are rejected by construction.
- **Task 2 — Immutable allowlisted snapshot seam (RED→GREEN, 12 tests):** `adapters/conversation_sources/snapshots.py` provides content-addressed deduplicated blob capture for files and allowlisted directories, symlink/reparse/junction escape rejection, exact relative-path allowlist validation, byte/count limits that fail closed before any artifact or manifest is published, manifest write/read/replay verification, and WAL-safe SQLite capture via online backup (never loose `.db/.db-wal/.db-shm`) filtered to declared tables/columns with credential/account/token/auth tables excluded by construction.
- **Task 3 — Generation-bound v2 schema + repository (RED→GREEN, 12 tests):** `application/conversation/event_schema.py` adds 8 `ce_*` v2 tables additively (compatibility tables untouched); `application/conversation/event_repository.py` stages generations transactionally with idempotent replay, generation isolation, native-locator lookup, event/relation ordering, unknown-native preservation, FK-enforced session/relation integrity with rollback on failure, and read-only authority queries — the repository never activates a generation.
- 39/39 focused tests green; `git diff --check` clean; no network/provider/paid calls; no live database or `var/` writes.

## Task Commits

Per ZCode execution protocol the coordinator reviews the diff and commits; no commits were made by this executor. All three tasks are TDD (RED → GREEN), each with REFACTOR where review thresholds required:

1. **Task 1: typed event/relation/provenance/fidelity contracts** — RED (import error) → GREEN (15 passed)
2. **Task 2: immutable allowlisted source snapshot seam** — RED (import error) → GREEN (12 passed; junction fallback for symlink test)
3. **Task 3: generation-bound v2 schema and repository** — RED (import error) → GREEN (12 passed)

## Files Created/Modified

- `src/personal_knowledge/core/conversation_events.py` — typed event/relation/fidelity/provenance/disposition contracts + `make_event_id` + `dataset_digest` (345 lines)
- `src/personal_knowledge/adapters/conversation_sources/__init__.py` — package re-exports
- `src/personal_knowledge/adapters/conversation_sources/contracts.py` — adapter capability/result seam (177 lines)
- `src/personal_knowledge/adapters/conversation_sources/snapshots.py` — allowlisted content-addressed capture (refactored to 520 lines, all functions ≤80)
- `src/personal_knowledge/application/conversation/event_schema.py` — additive v2 DDL + `SCHEMA_VERSION` (185 lines)
- `src/personal_knowledge/application/conversation/event_repository.py` — generation-bound repository (refactored to 413 lines, all functions ≤80)
- `tests/unit/test_conversation_event_contracts.py` — 15 RED/GREEN tests
- `tests/integration/test_conversation_source_snapshots.py` — 12 RED/GREEN tests
- `tests/integration/test_conversation_event_repository.py` — 12 RED/GREEN tests

## Decisions Made

- Used `INSERT OR IGNORE` for idempotent replay within a generation (same generation re-staged without duplicate rows) while foreign keys still enforce endpoint/session existence and block cross-generation relations.
- `ce_event_relations` adds a `UNIQUE(generation_id, source_event_id, target_event_id, relation_kind)` so replayed relations cannot duplicate.
- `FidelityProfile.from_levels` defaults unset dimensions to `UNKNOWN` — an omission can never masquerade as complete.
- `capture_sqlite` validates declared table/column capability against the live schema (integrity + column check) before any backup; only the backup, then drop non-allowlisted tables; a schema-digest and metadata-only `privacy_dispositions` (e.g., `excluded_table:accounts`) are recorded.
- Symlink test uses Windows junction fallback (reparse point, no privilege required) so the escape negative path runs on this host instead of skipping.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite index drop failed on PRIMARY KEY/UNIQUE-backed indexes**
- **Found during:** Task 2 GREEN
- **Issue:** Dropping every `sqlite_master` index in the filtered backup raised `sqlite3.OperationalError: index associated with UNIQUE or PRIMARY KEY constraint cannot be dropped` for tables whose PK/UNIQUE was still present.
- **Fix:** Only drop indexes whose `sql` is non-NULL (explicit `CREATE INDEX` statements); auto-created PK/UNIQUE indexes are dropped implicitly with their table.
- **Files modified:** `src/personal_knowledge/adapters/conversation_sources/snapshots.py`
- **Verification:** `tests/integration/test_conversation_source_snapshots.py` 12/12 pass.
- **Committed in:** coordinator commit (part of Task 2).

**2. [Rule 3 - Blocking] Missing `sqlite3.Row` row factory on repository reads**
- **Found during:** Task 3 GREEN
- **Issue:** `iter_events`/`iter_relations`/`iter_dispositions`/`lookup_by_native_locator` failed with `ValueError: dictionary update sequence element ... has length 64; 2 is required` because the connection had no row factory.
- **Fix:** Set `con.row_factory = sqlite3.Row` in `EventRepository._connect`.
- **Files modified:** `src/personal_knowledge/application/conversation/event_repository.py`
- **Verification:** `tests/integration/test_conversation_event_repository.py` 12/12 pass.
- **Committed in:** coordinator commit (part of Task 3).

**3. [Rule 1 - Bug] Event-level field dispositions were not persisted**
- **Found during:** Task 3 GREEN
- **Issue:** `TypedEvent.field_dispositions` (e.g., UNKNOWN_NATIVE preserved-by-reference) were never written to `ce_field_dispositions`; only top-level `GenerationInput.dispositions` were.
- **Fix:** Persist each event's `field_dispositions` in the event insert loop.
- **Files modified:** `src/personal_knowledge/application/conversation/event_repository.py`
- **Verification:** `test_unknown_native_preserved_by_reference` passes.
- **Committed in:** coordinator commit (part of Task 3).

**4. [Rule 1 - Bug] Windows symlink test skipped on this host**
- **Found during:** Task 2 GREEN
- **Issue:** `Path.symlink_to` requires Developer Mode on Windows; the escape test skipped (`WinError 1314`), leaving the reparse-escape negative path unexecuted.
- **Fix:** Fall back to `_winapi.CreateJunction` (a reparse point creatable without privilege) before skipping; verified `is_junction()` detection on this host.
- **Files modified:** `tests/integration/test_conversation_source_snapshots.py`
- **Verification:** 12/12 pass, no skip.
- **Committed in:** coordinator commit (part of Task 2).

### REFACTOR (threshold compliance, not a deviation)

Two functions exceeded the 80-line review threshold from `docs/architecture/engineering-and-testing-contract.md`:
- `capture_sqlite` (116 lines) split into `_validate_sqlite_capability` + `_filtered_backup`.
- `write_generation` (143 lines) split into `_insert_artifacts/_insert_sessions/_insert_events/_insert_relations/_insert_dispositions`.

Behavior unchanged; all 39 tests still green after refactor. No production file outside the plan's `files_modified` was touched.

---

**Total deviations:** 4 auto-fixed (2 bug, 1 blocking, 1 bug/test-hardening) + 1 threshold refactor
**Impact on plan:** All auto-fixes were necessary for correct local behavior or test execution on Windows; no scope creep, no architecture changes.

## Issues Encountered

- The plan's `files_modified` list included `src/personal_knowledge/application/conversation/event_schema.py`, but the plan artifact `must_haves` map labeled it as provided by `conversation_events.py`; the actual v2-schema module (`event_schema.py`) was created as the plan's files list specifies, and `conversation_events.py` was deliberately kept as the pure typed-contract module. This keeps "one module, one authority owner" (deterministic core vs persistence) intact.
- `FidelityProfile` carries `dimensions`+`levels` parallel tuples (both serializable) rather than a dict mapping; `FidelityProfile.from_dict` is provided for repository round-tripping.

## User Setup Required

None - no external services, credentials, or manual configuration required. All tests are deterministic local tests on temporary fixtures.

## Next Phase Readiness

- Ready for 62-02..62-08: family adapters consume `SourceArtifactSet`/`CapabilityDescriptor` from the capture seam; event generation staging is the persistence path (`EventRepository.write_generation`), and the compatibility-projection/activation plan will own the `ce_generation_authority` pointer (deliberately not activated here).
- Known deliberate seam boundary: `EventRepository` exposes read-only authority queries only; authority activation, compatibility projection, views and extraction policy are later plans.

## Self-Check: PASSED

- [x] Task 1 RED: `ModuleNotFoundError: No module named 'personal_knowledge.core.conversation_events'` → Task 1 GREEN: 15 passed
- [x] Task 2 RED: `ModuleNotFoundError: ... snapshots` → Task 2 GREEN: 12 passed
- [x] Task 3 RED: `ModuleNotFoundError: ... event_schema` → Task 3 GREEN: 12 passed
- [x] All three focused suites together: `python -m pytest -q tests/unit/test_conversation_event_contracts.py tests/integration/test_conversation_source_snapshots.py tests/integration/test_conversation_event_repository.py` → 39 passed
- [x] Each plan `<verify>` command green (see Verification table below)
- [x] `git diff --check` on all new files → clean
- [x] `python -m compileall` on all new modules → OK
- [x] Adjacent regression: `tests/integration/test_agentsview_source_adapter.py` + `tests/unit/test_conversation_repository.py` → 15 passed (legacy seam untouched)
- [x] No functions over 80 lines in new production modules
- [x] Fixtures/failures contain only synthetic/redacted content; no user paths beyond explicit `tmp_path` roots (grep verified)
- [x] No network/provider/paid-call code in new modules (grep verified); no `var/` or live database writes

## Verification Command Results

| Command | Status | Result |
|---|---|---|
| `python -m pytest -q tests/unit/test_conversation_event_contracts.py` | PASSED | 15 passed in 0.05s |
| `python -m pytest -q tests/integration/test_conversation_source_snapshots.py` | PASSED | 12 passed in ~1.5s |
| `python -m pytest -q tests/integration/test_conversation_event_repository.py` | PASSED | 12 passed in ~0.4s |
| All three suites together | PASSED | 39 passed in ~2s |
| `git diff --check` (new files) | PASSED | clean |
| Adjacent regression (agentsview adapter + conversation repository) | PASSED | 15 passed |

## Security Closure Gate

| Check | Status | Evidence |
|---|---|---|
| No `pk-ku extract` / provider generation / paid semantic labeling / paid LLM call (D-31) | PASSED | No network/provider/paid code in new modules (grep); tests are deterministic local only |
| No live-source mutation; SQLite capture WAL-safe; no loose `.db/.db-wal/.db-shm` copies (D-05) | PASSED | `capture_sqlite` uses `sqlite3.Connection.backup`; concurrent-WAL writer test proves consistency |
| Allowlist-only capture; credential/account/token/auth tables excluded by construction (D-08) | PASSED | `FORBIDDEN_TABLE_PATTERNS` blocks allowlisting; post-backup DROP removes non-allowlisted tables; negative tests prove absence |
| Manifest metadata-only; no bodies/credentials logged (D-09) | PASSED | manifests carry hashes/capture method/schema digest/dispositions only |
| Failure before publication leaves no artifact/manifest (fail closed) | PASSED | byte/count/column/escape tests assert empty blob store after failure |
| No touch of `.planning/spikes/`, `tmp/`, `var/`, `data/`; no git state changes | PASSED | only the 9 planned files created; `git status` shows no other modifications |

---
*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Completed: 2026-08-12*
