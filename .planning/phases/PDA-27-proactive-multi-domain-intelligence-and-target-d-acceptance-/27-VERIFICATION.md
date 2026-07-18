---
phase: 27
verified: 2026-07-18
status: failed
score: "3/4"
requirements:
  PRO-01: passed
  PRO-02: passed
  TRUST-01: failed
  TD-01: passed
technical_status: failed
release_status: release_blocked
verification_scope: independent_technical
---

# Phase 27 / Target D Independent Verification

## Verdict

**Phase 27 independent technical verification: FAILED (3/4 requirements).** PRO-01, PRO-02 and TD-01 have direct implementation and positive/negative execution evidence. TRUST-01 has one independently reproduced temporal-precedence defect: same-specificity control events are ordered by their raw ISO-8601 strings, so equivalent timestamps with different UTC offsets can select an older control as the current winner.

**Product release remains `release_blocked`.** Phase 24 still lacks genuine human Gold, groundedness, Judge calibration, reviewed lifecycle adoption and product UAT. This verification did not run any live migration/write/apply, change serving/pointer/watermark state, finalize reviews, dispatch an external action, or make network/paid calls.

## Requirement results

### PRO-01 — passed

- `a.proactive_intelligence` is an independent non-serving A-layer authority and is not a required serving role or a second KU/fact authority.
- The closed vocabulary contains exactly learning, career, project, health, finance, relationship, time and energy.
- Coordination requires exact Phase 25/26/snapshot binding and decisive source references. The bounded-resource conflict path now requires a stable `resource_id`, compatible units and overlapping horizons; mere coexistence, missing support, sensitive input and mixed snapshots abstain.
- Disposable publication tests prove atomic, immutable, idempotent and concurrency-safe run/coordination/candidate persistence with no protected-authority mutation.

### PRO-02 — passed

- Privacy, evidence and trust vetoes precede deterministic importance ranking and cannot be bypassed by criticality.
- Candidate identity, material novelty, deduplication, cooldown, quiet deferral and global/domain budgets are versioned and reason-coded.
- Exact candidate-support replay validates the complete support set and rejects missing, extra, payload-tampered or stale source records.
- Outputs remain metadata-only inbox/digest proposals; REST/MCP expose no notification sender, scheduler, connector, command or external executor.

### TRUST-01 — failed

Append-only user ownership, exact target binding, sequence/checksum chains, idempotency, restore history, current overlay and correction routing are implemented and their ordinary paths pass. However, temporal precedence is incorrect for valid offset-aware timestamps.

#### F-01 — raw timestamp string can select the wrong latest control

**Contract:** `27-RESEARCH.md` requires the most recent valid stream state in sequence order and says the latest valid event wins at equal specificity. `27-03-PLAN.md` also requires timezone-aware `as_of` behavior.

**Implementation evidence:** `src/personal_knowledge/intelligence/proactive/controls.py:258` selects the winner with:

```python
max(denials or top, key=lambda item: (item.created_at, item.sequence, item.event_id))
```

`created_at` is the unnormalized input string. Although eligibility and expiry parse timestamps to UTC, winner ordering does not.

**Independent disposable reproduction:** one exact candidate target received two valid same-specificity denial events:

1. sequence 1: `suppress`, `created_at=2026-07-18T12:00:00+08:00` (UTC 04:00);
2. sequence 2: `snooze`, `created_at=2026-07-18T05:00:00Z` (UTC 05:00), expiry UTC 08:00;
3. projection at `2026-07-18T06:00:00Z`.

The later event is the snooze, but the implementation returned `suppressed_by_user` and the sequence-1 suppress event as winner because the string `12:00...` sorts after `05:00...`.

**Impact:** current control reason, winning event and projected checksum can be wrong when callers use different valid timezone offsets. This weakens user trust lifecycle semantics and deterministic replay across equivalent timestamp representations.

**Required fix:** normalize timestamps before ordering. Within one target stream, use the checksum-verified sequence as the authoritative order; across target streams, compare parsed UTC instants and use stable target/sequence/event-ID tie breakers. Add regression coverage for mixed offsets, equal instants, same-target sequence order and cross-target equal-specificity precedence. Re-run the complete Phase 27, adjacent, acceptance and preflight gates.

### TD-01 — passed

- The disposable sandbox actually executes capture, Phase 25 state/change/history, Phase 26 accepted/rejected recommendation histories, action/outcome/non-causal assessment, eight-domain coordination, ranking/noise, trust suppress/restore/stale append, future-run binding and shared get/explain.
- Every sandbox stage was independently fault-injected; the named stage became false and the overall technical sandbox failed.
- Applied schema validation passed for a complete disposable Phase 25→26→27 authority, rejected deleted candidate-support rows as `support_manifest_mismatch`, and rejected a partial Phase 27 schema as `phase27_schema_partial`.
- CLI guards require explicit local write authorization and exact confirmation. REST/MCP remain read-only and all external/network/paid counters are zero.

TD-01's end-to-end mechanism is technically demonstrated, but the phase-wide `technical_status` remains failed until F-01 is fixed because Target D includes trustworthy user correction/control semantics.

## Independent execution evidence

| Gate | Result |
|---|---|
| Phase 27 unit/contract/integration suite | PASS — 86 tests |
| Phase 25/26 adjacent regression | PASS — 78 tests |
| Apps SDK, knowledge search and serving snapshot regression | PASS — 33 tests |
| Governance preflight | PASS — 13/13 gates |
| Live metadata-only acceptance | Command passed its current gates; independent verification overrides technical verdict because F-01 is not covered |
| Complete-applied disposable authority | PASS — Phase 25/26/27 each `validated_committed_runs` |
| Corrupt candidate-support fixture | PASS fail-closed — `proactive_integrity_invalid:support_manifest_mismatch` |
| Partial Phase 27 schema fixture | PASS fail-closed — `technical_status=failed`, `phase27_schema_partial` |
| Mixed-offset trust precedence fixture | FAIL — reproduced F-01 |

The full repository suite was not rerun in this verifier pass because the current Phase 27 review already records a post-remediation repository PASS and the independent targeted, adjacent and interface suites cover the changed authority. This omission does not affect the failed verdict; it must be rerun after F-01 is repaired.

## Live metadata-only evidence

The independently rerun command was:

```powershell
python -m personal_knowledge.intelligence.proactive.cli acceptance --dry-run --metadata-only --json
```

It resolved active snapshot `ss_1590353394c948b908a5d675` with hash `a2ce76eb76c15ab8560718b03e94405538a54491c7b14c12f283d29e35c1a0fa`. Before/after fingerprints were identical at `4dd84122a832d593006f6f7107d96abe80fb6c77dfa7c2144cc06f0ec898476c`. Live Phase 25/26/27 schemas were all explicitly `unapplied`. `mutations`, `persisted_rows`, `private_bodies`, `external_actions`, `network_calls` and `paid_calls` were all zero.

The command reported its implemented sandbox as `technical_status=passed`, but that result does not cover F-01. The independent phase verdict is therefore `technical_status=failed` until the missing negative case is fixed and added to the acceptance/test matrix.

## Technical Target D vs product Target D

- **Technical Target D:** not yet signed off because TRUST-01 temporal precedence is wrong under valid mixed-offset timestamps. Fix and re-verification are required.
- **Product Target D:** remains blocked regardless of F-01. Fixture/sandbox identities, controls and outcomes are not real user adoption or usefulness evidence. Product sign-off additionally requires genuine Phase 24 human quality evidence, reviewed lifecycle adoption/rollback, authorized live analysis publication, real-user end-to-end UAT and explicit release authorization.

## Preserved Phase 24 blockers

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`
- Human review strict: false
- Lifecycle strict: false; applied manifests and lifecycle events remain zero
- Explicit product UAT: absent

No automated evidence in Phase 27 resolves these product blockers.

