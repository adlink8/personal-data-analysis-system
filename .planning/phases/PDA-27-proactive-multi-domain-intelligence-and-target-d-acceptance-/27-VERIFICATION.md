---
phase: 27
verified: 2026-07-18
status: passed
score: "4/4"
requirements:
  PRO-01: passed
  PRO-02: passed
  TRUST-01: passed
  TD-01: passed
technical_status: passed
release_status: awaiting_product_uat
verification_scope: independent_technical
---

# Phase 27 / Target D Independent Verification

## Verdict

**Phase 27 independent technical verification: PASSED (4/4 requirements).** PRO-01, PRO-02, TRUST-01 and TD-01 have direct implementation and positive/negative execution evidence. The independently reproduced TRUST-01 temporal-precedence defect is fixed and covered by mixed-offset, equal-instant, same-target sequence and cross-target regression cases.

**Current product status: `awaiting_product_uat`.** The historical verification below remains the independent technical record; the live-adoption addendum supersedes its earlier Phase 24 blocker snapshot.

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

### TRUST-01 — passed

Append-only user ownership, exact target binding, sequence/checksum chains, idempotency, restore history, current overlay and correction routing are implemented and pass. Temporal precedence now also passes valid offset-aware, equal-instant and out-of-time-order sequence cases.

#### F-01 — RESOLVED: normalized cross-stream time with authoritative stream sequence

**Contract:** `27-RESEARCH.md` requires the most recent valid stream state in sequence order and says the latest valid event wins at equal specificity. `27-03-PLAN.md` also requires timezone-aware `as_of` behavior.

**Original independent reproduction:** one exact candidate target received two valid same-specificity denial events:

1. sequence 1: `suppress`, `created_at=2026-07-18T12:00:00+08:00` (UTC 04:00);
2. sequence 2: `snooze`, `created_at=2026-07-18T05:00:00Z` (UTC 05:00), expiry UTC 08:00;
3. projection at `2026-07-18T06:00:00Z`.

The old implementation returned the sequence-1 suppress event because it compared the raw strings. The repaired implementation first selects the latest event within each checksum-verified target stream by sequence, then compares different target streams by parsed UTC instant with stable target/sequence/event-ID tie breakers. Target specificity remains the primary order, scope specificity remains secondary and denial semantics remain fail closed.

**Regression evidence:** the old implementation failed three new cases covering same-stream sequence, mixed-offset cross-stream order and equal-instant stable target precedence. After the repair, all four added cases pass, including cross-stream selection after per-stream sequence reduction. The complete control suite and all wider gates also pass.

**Repair commits:** `0e01c40` adds the RED regression matrix; `a526f3a` implements the minimal normalized precedence repair.

### TD-01 — passed

- The disposable sandbox actually executes capture, Phase 25 state/change/history, Phase 26 accepted/rejected recommendation histories, action/outcome/non-causal assessment, eight-domain coordination, ranking/noise, trust suppress/restore/stale append, future-run binding and shared get/explain.
- Every sandbox stage was independently fault-injected; the named stage became false and the overall technical sandbox failed.
- Applied schema validation passed for a complete disposable Phase 25→26→27 authority, rejected deleted candidate-support rows as `support_manifest_mismatch`, and rejected a partial Phase 27 schema as `phase27_schema_partial`.
- CLI guards require explicit local write authorization and exact confirmation. REST/MCP remain read-only and all external/network/paid counters are zero.

TD-01's end-to-end mechanism and the repaired TRUST-01 control semantics are technically demonstrated. The phase-wide `technical_status` is therefore `passed`.

## Independent execution evidence

| Gate | Result |
|---|---|
| Phase 27 unit/contract/integration suite | PASS — 90 tests |
| Phase 25/26 adjacent regression | PASS — 156 tests |
| Apps SDK, knowledge search and serving snapshot regression | PASS — 33 tests |
| Governance preflight | PASS — 13/13 gates |
| Live metadata-only acceptance | PASS — `technical_status=passed`, unchanged fingerprint and zero side effects |
| Complete-applied disposable authority | PASS — Phase 25/26/27 each `validated_committed_runs` |
| Corrupt candidate-support fixture | PASS fail-closed — `proactive_integrity_invalid:support_manifest_mismatch` |
| Partial Phase 27 schema fixture | PASS fail-closed — `technical_status=failed`, `phase27_schema_partial` |
| Mixed-offset/equal-instant/stream-sequence fixtures | PASS — F-01 repaired |
| Full repository suite | PASS — 2 skipped; only 2 pre-existing `SyntaxWarning` messages |

The full repository suite was rerun after the repair and passed. `git diff --check` also passed.

## Live metadata-only evidence

The independently rerun command was:

```powershell
python -m personal_knowledge.intelligence.proactive.cli acceptance --dry-run --metadata-only --json
```

It resolved active snapshot `ss_1590353394c948b908a5d675` with hash `a2ce76eb76c15ab8560718b03e94405538a54491c7b14c12f283d29e35c1a0fa`. Before/after fingerprints were identical at `4dd84122a832d593006f6f7107d96abe80fb6c77dfa7c2144cc06f0ec898476c`. Live Phase 25/26/27 schemas were all explicitly `unapplied`. `mutations`, `persisted_rows`, `private_bodies`, `external_actions`, `network_calls` and `paid_calls` were all zero.

The command reported `technical_status=passed`, and independent regression now covers F-01. The live command remained metadata-only: before/after fingerprints were identical, with zero persisted rows, mutations, private bodies, external actions, network calls and paid calls.

## Technical Target D vs product Target D

- **Technical Target D:** passed independent verification across PRO-01, PRO-02, TRUST-01 and TD-01.
- **Product Target D:** remains blocked regardless of F-01. Fixture/sandbox identities, controls and outcomes are not real user adoption or usefulness evidence. Product sign-off additionally requires genuine Phase 24 human quality evidence, reviewed lifecycle adoption/rollback, authorized live analysis publication, real-user end-to-end UAT and explicit release authorization.

## Preserved Phase 24 blockers

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`
- Human review strict: false
- Lifecycle strict: false; applied manifests and lifecycle events remain zero
- Explicit product UAT: absent

No automated evidence in Phase 27 resolves these product blockers.

## Live-adoption and product-UAT addendum — 2026-07-18

The Phase 27 schema is applied and a real proactive run is committed:

- run `pir_065c80888c81723abd43fc4a`, candidate
  `pcd_d19e768ac127dc5a841a0eea`;
- importance score `0.7215`, evidence strength `0.95`, evaluation `eligible`;
- the candidate explains that effectiveness is observational and the window is
  insufficient, with checksum-verified recommendation and assessment support;
- one presentation event was recorded; suppress and explicit restore were
  executed locally, and current eligibility is restored to `true` with full
  history retained;
- live acceptance validates committed Phase 25/26/27 runs, unchanged
  before/after fingerprints, and zero external, network or paid actions.

Phase 24 now reports all three checkpoints passed, strict review passed and
strict lifecycle passed. Technical blockers are empty. The only remaining
release blocker is `product_uat:missing`, which deliberately requires the
user's explicit acceptance after reviewing the live demonstration.
