---
phase: 26
verified: 2026-07-18
status: failed
score: "1/2"
requirements:
  DEC-01: passed
  DEC-02: failed
release_status: release_blocked
verification_scope: independent_technical
---

# Phase 26 Verification

## Verdict

**Phase 26 independent technical verification: FAILED (1/2 requirements).** DEC-01 passes: the implementation keeps fact, observation, inference, recommendation and user confirmation in separate typed and authority boundaries. DEC-02 is not yet complete because the local append path can extend a recommendation stream after its bound Phase 25 source run has failed checksum validation.

**Release status remains `release_blocked`.** Phase 24 human Gold/Judge/UAT and lifecycle quality gates remain unresolved. This verification performed no live schema migration, live decision write, lifecycle apply, serving/pointer/watermark change, network/paid call or external action.

## Requirement verification

### DEC-01 — passed

- `a.decision_feedback` is an independent immutable R4 A-layer authority with evidence parent `a.personal_change`; it is not a required serving role.
- The schema exposes exactly `fact`, `observation`, `inference`, `recommendation` and `user_confirmation`. Only the first three can be Phase 25 support references.
- Recommendations have no fact, KU, approved, executed, command, credential or dispatch authority. Confirmation records a human decision and does not change Phase 25 assertions or evidence.
- Decision runs and supports bind one Phase 25 run checksum/publication sequence and one serving snapshot ID/hash. Recommendation publication atomically commits the recommendation and its unique sequence-1 `recommendation_published` genesis.
- Outcome rows are typed observations; effectiveness rows are immutable inferences with `causal_claim=false`. The persistence boundary reloads outcome/action rows, resolves a registered rule and recomputes the assessment before accepting it.

### DEC-02 — failed

The append-only loop, sequence, idempotency, concurrency and assessment derivation tests pass for valid fixtures, but the local write boundary does not revalidate the bound Phase 25 source before appending.

#### F-01 — source-version drift is read-blocking but not write-blocking

**Severity:** blocking integrity gap  
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

**Observed:**

```text
read_ok=False
read_error=source_analysis_invalid
write.accepted=True
write.sequence=2
```

The read service correctly fails closed because `_context()` hydrates `IntelligenceService` and validates the Phase 25 run. The local writers call `_project()` directly; `_project()` validates the decision run manifests, recommendation genesis and decision event chain but does not validate the current Phase 25 run manifest/checksum/publication/snapshot binding. Therefore a user-facing local write can extend a stream that every read surface considers invalid.

This violates the Phase 26 contract that a stream remains bound to an exact valid Phase 25 run and that source-version/tamper drift fails closed. Existing automated tests cover drift on reads and acceptance, but not the same drift at each local append boundary.

#### Required fix and regression proof

Before Phase 26 can pass:

1. Add one shared, read-only source-binding validator that recomputes and verifies the Phase 25 run/output manifest checksum, publication sequence, snapshot ID/hash and the decision run/support binding in the same `BEGIN IMMEDIATE` transaction used by each append.
2. Invoke it before idempotent replay or insertion in `record_confirmation`, `record_action`, `record_outcome` and `record_assessment`; failure must roll back and return a stable source-drift reason code.
3. Do not route through a separate connection whose validation can race the append transaction.
4. Add negative tests for all four append operations after Phase 25 manifest/checksum/publication/snapshot tampering. Assert zero new typed rows/events and unchanged last sequence.
5. Retain the current read-service validation, CLI five guards, REST/MCP read-only boundary and Phase 24 release block.

## Independent passing evidence

| Gate | Result |
|---|---|
| Phase 26 unit/contract/integration suite | PASS — 65 tests |
| Apps SDK, Phase 25 interface, knowledge-search and serving-snapshot regression | PASS — 45 tests |
| Governance preflight | PASS — 13/13 gates |
| Full repository regression | PASS — 788 passed, 2 skipped; two pre-existing SyntaxWarnings |
| Live metadata-only acceptance | PASS for the currently encoded read-only gate; technical result in this verification remains failed because F-01 is outside that gate |

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

Phase 26 must not be marked technically complete or used as a verified dependency for Phase 27 until F-01 is fixed and independently reverified. This failure does not authorize live migration/publication, lifecycle apply, serving changes, external action or REST/MCP writes.
