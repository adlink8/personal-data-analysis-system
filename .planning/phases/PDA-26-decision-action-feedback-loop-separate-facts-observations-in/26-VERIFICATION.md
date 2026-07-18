---
phase: 26
verified: 2026-07-18
status: passed
score: "2/2"
requirements:
  DEC-01: passed
  DEC-02: passed
release_status: release_blocked
verification_scope: independent_technical
---

# Phase 26 Verification

## Verdict

**Phase 26 independent technical verification: PASSED (2/2 requirements).** DEC-01 keeps fact, observation, inference, recommendation and user confirmation in separate typed and authority boundaries. DEC-02 now validates the exact Phase 25 source and Phase 26 decision/support binding inside every append transaction before idempotent replay or insertion.

**Release status remains `release_blocked`.** Phase 24 human Gold/Judge/UAT and lifecycle quality gates remain unresolved. This verification performed no live schema migration, live decision write, lifecycle apply, serving/pointer/watermark change, network/paid call or external action.

## Requirement verification

### DEC-01 — passed

- `a.decision_feedback` is an independent immutable R4 A-layer authority with evidence parent `a.personal_change`; it is not a required serving role.
- The schema exposes exactly `fact`, `observation`, `inference`, `recommendation` and `user_confirmation`. Only the first three can be Phase 25 support references.
- Recommendations have no fact, KU, approved, executed, command, credential or dispatch authority. Confirmation records a human decision and does not change Phase 25 assertions or evidence.
- Decision runs and supports bind one Phase 25 run checksum/publication sequence and one serving snapshot ID/hash. Recommendation publication atomically commits the recommendation and its unique sequence-1 `recommendation_published` genesis.
- Outcome rows are typed observations; effectiveness rows are immutable inferences with `causal_claim=false`. The persistence boundary reloads outcome/action rows, resolves a registered rule and recomputes the assessment before accepting it.

### DEC-02 — passed

The append-only loop, sequence, idempotency, concurrency and assessment derivation tests pass for valid fixtures. The local write boundary now also fails closed on upstream source-version or tamper drift.

#### F-01 — source-version drift is read-blocking but not write-blocking

**Severity:** blocking integrity gap — resolved
**Affected entry points:**

- `record_confirmation()` and CLI `confirm`
- `record_action()` and CLI `action`
- `record_outcome()` and CLI `outcome`
- `record_assessment()` is transitively affected because it also uses `_project()` before appending and does not call the checksum-verifying shared service/source validator

**Independent reproduction (temporary SQLite only):**

1. Build and publish a valid Phase 25 run and Phase 26 recommendation using the repository fixture.
2. Simulate persisted upstream corruption by disabling the temporary fixture's immutable update trigger and changing `personal_state_runs.output_manifest_json` without changing its checksum.
3. Read the recommendation through `DecisionFeedbackService.recommendations_get()`.
4. Append an `accept` confirmation with the exact recommendation checksum, human actor, expected sequence and idempotency key.

**Original observation:**

```text
read_ok=False
read_error=source_analysis_invalid
write.accepted=True
write.sequence=2
```

The original read service correctly failed closed while local writers could append. This mismatch is now closed by one shared `_validate_source_binding()` boundary in `state_machine.py`.

This violates the Phase 26 contract that a stream remains bound to an exact valid Phase 25 run and that source-version/tamper drift fails closed. Existing automated tests cover drift on reads and acceptance, but not the same drift at each local append boundary.

#### Implemented fix and regression proof

1. `_validate_source_binding(con, recommendation_id)` recomputes both Phase 25 input/output manifest checksums and validates publication sequence, serving snapshot ID/hash, decision run manifests/checksum and recommendation/support bindings.
2. `record_confirmation`, `record_action`, `record_outcome` and `record_assessment` call it on the same connection immediately after `BEGIN IMMEDIATE`, before projection, idempotent replay or insertion. It opens no second connection.
3. All source drift failures use stable reason code `source_binding_invalid`; the surrounding transaction rolls back.
4. Four negative entry-point tests cover output-manifest, input-checksum, publication-sequence and snapshot tampering. The confirmation case exercises the guarded CLI write path. Every case asserts unchanged typed-row counts and event sequence/count.
5. Existing read-service validation, CLI five guards, REST/MCP read-only boundary and the Phase 24 release block remain intact.

## Independent passing evidence

| Gate | Result |
|---|---|
| Phase 26 unit/contract/integration suite | PASS — 69 tests |
| Phase 25, Apps SDK, knowledge-search and serving-snapshot regression | PASS — 120 tests |
| Governance preflight | PASS — 13/13 gates |
| Full repository regression | PASS — 792 passed, 2 skipped; two pre-existing SyntaxWarnings |
| Live metadata-only acceptance | PASS — `technical_status=passed`, `release_status=release_blocked`, zero mutations |

The live acceptance resolved a complete-unapplied decision schema, returned `technical_status=passed` for its existing checks and retained `release_status=release_blocked`. Before/after authority fingerprint was identical at `99b5dacbb9e3ba3ed6c67512d01bae3d2988ffce47e70a2d5da05154e198324c`. `persisted_rows`, `mutations`, `private_bodies`, `external_actions`, `network_calls` and `paid_calls` were all zero. The sandbox reconstructed one seven-event accepted history and one two-event rejected history; its effectiveness result remained observational with `causal_claim=false`.

## Other verified boundaries

- Complete-unapplied decision schema is allowlisted; every partial-schema case is technically blocked.
- Recommendation/run/support/genesis publication is deterministic and atomic; exact replay is idempotent and publication fault injection rolls back all rows.
- Valid decision streams enforce monotonic sequence, previous-event checksums, caller expected sequence, same-payload replay and changed-payload idempotency conflict. Concurrent stale writers fail closed.
- Missing, reordered or tampered genesis/events fail closed on projection and all read interfaces.
- REST and MCP expose only five read operations. They expose no confirm, action, outcome-write, execute, send, schedule, purchase, publish or dispatch capability.
- Local CLI writes require `--write`, exact `--i-confirm <recommendation-id>`, a user actor identity hash, expected sequence and idempotency key. These guards do not replace F-01's missing source validation.
- Privacy checks reject source bodies, unrestricted notes, secrets and untyped/cross-snapshot outcome evidence; shared reads are metadata-only.

## Release blockers preserved

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`
- Human review strict: false
- Lifecycle strict: false; applied manifests and lifecycle events remain zero

F-01 is fixed and reverified, so Phase 26 is technically complete and may be used as the verified technical dependency for Phase 27. This pass does not authorize live migration/publication, lifecycle apply, serving changes, external action or REST/MCP writes, and it does not resolve the Phase 24 release blockers.
