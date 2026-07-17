---
phase: 25
reviewed: 2026-07-18
depth: standard
status: clean
files_reviewed: 20
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
resolved_findings: 6
release_status: release_blocked
---

# Phase 25 Code Review

## Verdict

Clean after remediation. All six findings are resolved by commits `11c54d0`, `865b4b1` and compatibility hardening `58957b7`; the expanded Phase 25 suite, adjacent interface regressions, governance preflight and full repository suite pass. Phase 24 remains `release_blocked`; this review does not approve a migration, live publication, lifecycle apply, or serving change.

## Resolution Summary

- `11c54d0` makes hydration verify canonical assertion payloads, normalized columns, row checksums and snapshot/member-bound evidence; acceptance now allowlists only schema-unapplied/no-run empty states and blocks all integrity failures.
- `11c54d0` adds immutable `personal_state_publications.publication_sequence` ordering and uses it consistently for latest selection and explicit-run history cutoffs, including same-second, concurrent and VACUUM stability coverage.
- `58957b7` rejects partially upgraded databases where any committed run lacks an explicit publication sequence, including through the acceptance integrity gate.
- `865b4b1` applies one observed/valid bitemporal boundary to projection, history, lifecycle and explanation formation; future knowledge is excluded.
- `865b4b1` carries typed evidence metadata into explanations, passes expected artifact version/type to resolvers, requires `eligible is True`, and abstains on missing eligibility, missing binding or version drift.
- `865b4b1` unifies derived risk severity on `low|medium|high` (`medium` for the current rules) and proves direct schema persistence.

Validation after remediation:

- Phase 25 unit/contract/integration suite: **87 passed**.
- Apps SDK, knowledge search and serving snapshot regression: **33 passed**.
- Governance preflight: **13/13 PASS**.
- Full repository: **723 passed, 2 skipped**; two pre-existing `SyntaxWarning` messages only.
- Live metadata-only acceptance: `ok=true`, `status=release_blocked`, fingerprints unchanged, `mutations=0`, no network/paid calls.

## Findings

### CR-01 — RESOLVED: Read hydration verifies assertion and evidence integrity

- **Files:** `src/personal_knowledge/intelligence/service.py:307`, `src/personal_knowledge/intelligence/service.py:322`
- **Impact:** A committed run whose `value_json`, assertion metadata, evidence rows, or stored `payload_json` has drifted can still be returned as a successful current/history/explain response. The run manifest only binds assertion IDs and counts, so validating the input/output manifest checksums does not detect this row-level drift.
- **Evidence:** `_hydrate_run()` verifies the two run manifest checksums, then reconstructs assertions directly from normalized columns. It never recomputes `payload_checksum`, never compares normalized columns with `payload_json`, and never verifies evidence eligibility/snapshot/hash/checksum fields before returning the hydrated run. A temporary fixture that changed only `personal_state_assertions.value_json` produced `state.current.ok=true` and `status=success` with the tampered value checksum.
- **Required fix:** Reconstruct and validate every assertion payload against its stored checksum and canonical payload, validate every evidence row against the selected snapshot/member and eligibility contract, and fail closed before projection. Add a read-path tamper test covering value, assertion metadata, evidence version/privacy, and payload checksum drift.

### CR-02 — RESOLVED: Acceptance blocks arbitrary intelligence failures

- **Files:** `src/personal_knowledge/intelligence/cli.py:265`, `src/personal_knowledge/intelligence/cli.py:272`, `src/personal_knowledge/intelligence/cli.py:320`
- **Impact:** Checksum corruption, malformed committed rows, or another `invalid_intelligence_state` can be treated like an expected “no committed run/schema unapplied” condition. `ok` is based only on before/after fingerprint equality, and final `status` is based only on Phase 24 dependency state. Once Phase 24 gates are satisfied, acceptance could therefore report `pass` even though personal-state intelligence could not be validated.
- **Evidence:** Every unsuccessful `state.current` response enters the same fallback branch. The branch records the error as `candidate_reason` but still sets `candidate.computed=true`; the final result uses `ok=unchanged`. This also prevents acceptance from distinguishing a safely absent analysis schema from corrupt applied analysis state.
- **Required fix:** Allowlist only explicit expected empty states (for example schema absent or no committed run), make all integrity/validation errors set `ok=false` and a blocking status, and include that gate in release status. Add acceptance tests for corrupted manifests/assertions/evidence and for applied-schema/no-run versus unapplied-schema behavior.

### WR-01 — RESOLVED: Point-in-time projection excludes future knowledge

- **Files:** `src/personal_knowledge/intelligence/state_projection.py:312`, `src/personal_knowledge/intelligence/service.py:135`, `src/personal_knowledge/intelligence/explanations.py:323`
- **Impact:** Historical reconstruction can claim that a goal/constraint/observation was current before the system learned it, and history/explain responses can include future formation records relative to `as_of`.
- **Evidence:** `_assertion_status()` gates only on `valid_from`/`valid_to`, not `observed_at`. A fixture with `valid_from=2026-01-01`, `observed_at=2026-08-01`, and `as_of=2026-07-01` returned `status=current`. Separately, `state_history()` emits every formation step, including steps marked `future`, and `explain_state()` resolves evidence for the entire unbounded formation path.
- **Required fix:** Define the bitemporal rule explicitly and exclude assertions/events not yet observed at `as_of`; filter history and explanation formation/evidence to the same temporal boundary. Add before-observation and future-formation contract tests.

### WR-02 — RESOLVED: Latest committed run uses immutable publication sequence

- **Files:** `src/personal_knowledge/intelligence/runs.py:57`, `src/personal_knowledge/intelligence/runs.py:586`, `src/personal_knowledge/intelligence/service.py:276`
- **Impact:** Two valid publications in one second can cause the older run to be selected as latest. Explicitly selecting the newer run can also omit an earlier same-second run from its reconstruction history because the cutoff uses `run_id <= selected_run_id`.
- **Evidence:** Run timestamps have only second precision. The service orders ties by deterministic hash-derived `run_id`. A temporary fixture published `psr_1dc...` then `psr_131...` at the same timestamp; the default service selected the first run because its hash sorted later.
- **Required fix:** Persist a total commit order (microsecond timestamp plus monotonic sequence, or an immutable integer publication sequence) and use it for both latest selection and historical cutoff. Add same-second and concurrent publication tests.

### WR-03 — RESOLVED: Explanation evidence is typed and version bound

- **Files:** `src/personal_knowledge/intelligence/explanations.py:133`, `src/personal_knowledge/intelligence/explanations.py:140`, `src/personal_knowledge/intelligence/explanations.py:340`
- **Impact:** Explain/recent responses may mark a reference eligible using a different source version than the committed run, and a resolver response with `status=ok` but no explicit eligibility flag is accepted. This is weaker than the strict evidence validation used when planning a run.
- **Evidence:** `_resolve_evidence()` receives only string refs, calls `resolver.resolve(ref, include_content=False)` without expected artifact type or source version, and computes eligibility with `result.get("eligible", status == "ok")`. Returned `source_version` is displayed but never compared with the run-bound version.
- **Required fix:** Carry typed evidence references (artifact type, serving role, artifact version, privacy class/checksum) into explanation resolution, pass the expected version to the resolver, require `eligible is True`, and abstain on any mismatch or omitted eligibility field. Add version-drift and missing-eligibility tests.

### WR-04 — RESOLVED: Derived risk severity matches persistence schema

- **Files:** `src/personal_knowledge/intelligence/changes.py:592`, `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py:514`
- **Impact:** A derived risk uses severity `elevated`, while `personal_state_risks.severity` permits only `low`, `medium`, or `high`. Any later atomic publication of the Phase 25 risk record will fail its database constraint or require an undocumented translation.
- **Evidence:** The unit contract explicitly asserts `risk.severity == "elevated"`; no adapter maps that value to the storage enum.
- **Required fix:** Define one severity vocabulary across typed records, API contracts, tests, and schema, then add a schema-level persistence contract for a derived risk.

## Original Review Evidence

- Reviewed the 20 requested source/test files and traced run publication, hydration, projection, explanation, CLI, REST, MCP, and acceptance call chains.
- Ran the reviewed Phase 25 suite: **74 passed**.
- Ran isolated temporary fixtures only; no live migration or project data write occurred.
- Reproduced same-second latest-run inversion, pre-observation projection, and successful serving/acceptance of tampered assertion data.

## Boundary Conditions

- Remediation is limited to Phase 25 implementation, tests and this review record.
- No live analysis schema was applied and no project data was written.
- No Phase 24 checkpoint, label, review decision, lifecycle manifest, serving pointer, or watermark was modified.
