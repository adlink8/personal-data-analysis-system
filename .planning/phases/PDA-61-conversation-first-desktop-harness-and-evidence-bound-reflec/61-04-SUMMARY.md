# 61-04 SUMMARY — Bounded governed SQLite evidence Tool

**Plan:** 61-04 (type=tdd, wave=1, autonomous=true)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | `tests/unit/test_evidence_sqlite_tool.py` (282 LOC) + `tests/integration/test_evidence_sqlite_tool.py` (336 LOC) created; RED state confirmed (module absent → collection error) (commit `2c3ba63`) |
| 2 | auto (tdd, GREEN) | ✅ PASS | `evidence_sqlite_tool.py` (441 LOC) + Gateway wiring + manifest registration; 63 tests green (commit `f7e9e5a`) |

## Verification

- `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py tests/contract/test_pi_domain_gateway.py` → **63 passed** (35 unit + 20 integration + 8 contract)
- `git diff --check` → 0

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-SQL-01 | Critical | CLOSED | descriptor allowlist, typed scope, Python-derived checksum-bound `statement_display`, RO URI + query_only, bounded execution, fingerprint tests — 55 passed |
| T-61-SQL-02 | Critical | CLOSED | explicit operation registration + capability/binding/idempotency validation; dynamic path/callable/capability bypass rejected — 63 passed |
| T-61-AUTH-01 | High | CLOSED | before/after fingerprints unchanged for success/reject/timeout — 20 passed |
| T-61-LEASE-01 | Critical | CLOSED | capability registered before checksummed `knowledge.research` lease; manifest drift/privacy-ceiling/lease double-denial — 63 passed |

## Deliverables

- `src/personal_knowledge/services/evidence_sqlite_tool.py` (new) — descriptor-only read-only SQLite authority; only query ID `conversation.evidence_messages.v1`; `file:...?mode=ro`, `PRAGMA query_only=ON`, single prepared query, 50-row/16KiB/3s ceilings; `statement_display` derived in Python from approved descriptor and checksum-bound to query ID/version + sorted parameter-name set
- `src/personal_knowledge/services/pi_domain_gateway.py` — `evidence.sqlite_query` operation map with capability/binding/idempotency, manifest checksum, privacy ceiling, lease validation
- `governance/manifests/capabilities/project-capabilities.json` — registered `evidence.sqlite_query` (versioned)
- `governance/manifests/ai/pi-skills.json` — `knowledge.research` allowlist lease updated (checksum recalculated)
- `tests/contract/test_pi_domain_gateway.py` — contract coverage for the new operation
- `pytest.ini` — `--import-mode=importlib` (needed because unit/ and integration/ both contain `test_evidence_sqlite_tool.py`)

## Deviations / risks

- **pytest.ini `--import-mode=importlib`** added (Rule 3 deviation): plan's own verification and threat-model commands failed with "import file mismatch" under default prepend mode because Task 1 committed same-named test files in `tests/unit/` and `tests/integration/`. Sampled regression (capability registry, warehouse containment, skill recovery, e2e/governance) confirms no new breakage.
- **`tests/e2e/test_pi_capability_os_uat.py` frozen evidence will break (expected, not fixed)**: registering the operation changes `project-capabilities.json` checksum + `pi-skills.json` sha256 and raises production op count 44→45. Direct consequence of plan's hard requirement (T-61-LEASE-01: capability before lease); e2e file is outside `files_modified` and Phase 61 regression gate list. **Deferred to Phase 61 close-out**: update frozen UAT evidence and op-count assertions.
- **Interface decision (recorded)**: missing DB path handling distinguishes by extension — `.sqlite/.db` missing → raise `database_unavailable` (integration test requirement); non-SQLite-extension missing path → bounded `database_unavailable` envelope without raising (unit test requirement). All policy validation precedes any DB open.
- Pre-existing unrelated failures (not fixed, out of scope): `tests/governance/test_governance_planning.py::test_phase17_remains_open_and_consistent` (ROADMAP content) and `test_knowledge_sqlite_policy.py::test_knowledge_write_paths_use_fk_connection_factory` (PDA-43). Identical before/after importlib mode.
- No plan deviation otherwise; only redacted temporary fixtures used; no live data/ or var/ databases touched.

## Self-Check: PASSED
