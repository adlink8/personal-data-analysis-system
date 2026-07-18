---
phase: 27
status: complete
researched: 2026-07-18
requirements: [PRO-01, PRO-02, TRUST-01, TD-01]
confidence: high
release_status: release_blocked
---

# Phase 27 Research: Proactive Multi-domain Intelligence and Target D Acceptance

## Research conclusion

Phase 27 should add one independent, append-only, non-serving **A-layer proactive intelligence authority** over the technically verified Phase 25 personal-state and Phase 26 decision-feedback authorities. It should coordinate typed goals and constraints across eight explicit domains, produce evidence-bound proactive suggestion candidates, deterministically suppress noise, and let a user add reversible trust controls. It must not create a second fact store, turn a suggestion into a KU, alter Phase 25/26 history, or dispatch any external action.

The correct acceptance model has two separate verdicts:

1. `technical_status=passed` may be proved with deterministic fixtures, a disposable SQLite sandbox and a live metadata-only inspection. This proves the Target D contracts without applying the currently unapplied live Phase 25/26/27 schemas.
2. `release_status=release_blocked` must remain until Phase 24 has genuine Gold/Judge/UAT evidence and a reviewed real lifecycle cohort. Phase 24 is therefore a hard blocker for **product-level Target D sign-off**, although it does not prevent Phase 27 code and sandbox contracts from being technically verified.

No automated agent may reinterpret a fixture loop as real personal intelligence adoption, fabricate a human correction, approve lifecycle changes, or declare full product Target D complete while those gates remain open.

## Current authority and implementation facts

### Verified foundations to reuse

- Phase 23 provides a validated composite serving snapshot, typed D/S/R/A registry, authoritative evidence resolution and fail-closed source-version checks. The live authority is snapshot `ss_1590353394c948b908a5d675` with manifest hash `a2ce76eb76c15ab8560718b03e94405538a54491c7b14c12f283d29e35c1a0fa`.
- Phase 24-01 provides evidence-aware abstention and snapshot-bound evaluation. Candidate privacy/no-answer safety is technically improved, but Phase 24-02/03/04 remain `awaiting_human`, `human_verification_required` and `blocked_on_human_and_quality_gates`.
- Phase 25 provides immutable `personal_state_runs`, typed goals/constraints/observations/states, bitemporal current/history projections, deterministic changes/conflicts/trends/risks and checksum-verifying CLI/REST/MCP reads. It is technically passed but not live-published.
- Phase 26 provides independent `a.decision_feedback` runs, typed recommendations, explicit user confirmations, action/outcome streams and observational non-causal effectiveness. Local writes use human actor checks, expected sequence and idempotency; REST/MCP remain read-only. It is technically passed but not live-published.
- `knowledge_lifecycle_*` already demonstrates reviewed manifests, correction/supersede/conflict/restore events, optimistic version checks and rollback links. It must remain the only route for changing canonical KU lifecycle or content.
- Existing acceptance commands fingerprint serving authority, KU/lifecycle tables, watermarks and Phase 24 checkpoints before and after, and explicitly allow a completely unapplied analysis schema while rejecting partial or corrupt schemas.

### Gaps Phase 27 must close

- There is no controlled vocabulary or coordination model spanning learning, career, project, health, finance, relationships, time and energy.
- Phase 25 changes and Phase 26 recommendations have no proactive candidate inbox, importance policy, deterministic deduplication, cooldown, quiet-period or global/domain noise budget.
- There is no user-owned control overlay for “do not use this”, “only in this scope”, “snooze”, “revoke”, “restore” or “this suggestion was not useful” across higher-level intelligence records.
- Current REST/MCP surfaces are read-only and pull-based. This is the correct permission boundary, but Phase 27 still needs a read-only proactive inbox/digest/explain surface; “proactive” must mean precomputed eligible suggestions, not an unreviewed external notification sender.
- Target D has no executable acceptance matrix that distinguishes technical fixture proof from real-data adoption and human product sign-off.

## Standard Stack

Use the current repository stack only.

| Concern | Prescribed implementation |
|---|---|
| Typed records | Frozen dataclasses plus existing canonical JSON/SHA-256 helpers |
| Storage | Additive SQLite tables, foreign keys, immutable triggers and `BEGIN IMMEDIATE` |
| Authority | New registry entry `a.proactive_intelligence`, layer A, evidence parent `a.decision_feedback`; do not add it to `required_serving_roles` |
| Source binding | Exact Phase 25 run/checksum/publication sequence and Phase 26 run/recommendation/event checksums, all on one snapshot ID/hash |
| Domain policy | Versioned tracked constants or metadata-only YAML with exactly eight canonical domains and explicit aliases |
| Ranking | Deterministic named components and thresholds; no opaque LLM score |
| Noise control | Stable dedup keys, cooldown windows, quiet-period deferral and rolling global/domain budgets |
| Trust control | Append-only user control events, expected sequence, idempotency and compensating restore/rollback events |
| Interfaces | One shared service; CLI/REST/MCP read parity; only guarded local CLI may append a user control |
| Acceptance | pytest fixtures, disposable sandbox, live metadata-only fingerprints and explicit technical/release verdicts |

Do not add a workflow engine, notification service, scheduler daemon, hosted event store, vector collection, agent framework, causal inference library or external connector.

## Recommended domain model

### Canonical domains

Use exactly these top-level domains in v1:

| Domain | Typical goals | Typical constraints and risks |
|---|---|---|
| `learning` | skill acquisition, study milestones | available study time, prerequisite gaps |
| `career` | role growth, job search, professional reputation | deadlines, market evidence, risk tolerance |
| `project` | deliverables, milestones, quality | blockers, dependencies, scope and capacity |
| `health` | routines and user-declared wellbeing goals | minimum privacy, no diagnosis, energy/time limits |
| `finance` | user-declared budget or savings goals | privacy, no credential/payment detail, uncertainty |
| `relationship` | user-declared commitments and follow-ups | consent, sensitivity, no inferred private diagnosis |
| `time` | scheduling capacity and deadline allocation | finite time windows and existing commitments |
| `energy` | user-declared or observed capacity patterns | uncertainty, health boundary and temporal validity |

`time` and `energy` are first-class resource domains, not loose metadata. A state assertion may retain its original domain, while coordination creates explicit cross-domain edges. Unknown domains fail closed or remain `unclassified`; they are never silently mapped by an LLM.

### Coordination records

Represent cross-domain reasoning as typed records, not one merged profile or vector:

- `goal_support`: one goal makes another easier.
- `goal_conflict`: two active goals compete under a named constraint.
- `dependency`: one goal or action must precede another.
- `resource_competition`: goals consume the same bounded time, energy or user-declared budget.
- `risk_propagation`: a Phase 25 risk or Phase 26 outcome affects another domain.
- `opportunity`: one bounded action can serve multiple compatible goals.

Every coordination item must bind exact source record IDs/checksums, domain/scope, valid and observed time, rule ID/version, confidence, uncertainty and snapshot/run lineage. Absence of data is not a conflict. Health, finance and relationship items require stricter abstraction and may abstain when evidence is sensitive or insufficient.

### Proactive suggestion candidate

A proactive candidate is an A-layer presentation proposal, never a fact or external action. It should contain:

- stable `candidate_id`, `run_id`, policy ID/version and canonical `dedup_key`;
- candidate class such as `important_change`, `goal_conflict`, `deadline_risk`, `stalled_project`, `cross_domain_opportunity`, `outcome_followup` or `trust_attention`;
- domain set, subject/scope, valid window and expiry;
- exact state/change/risk/recommendation/event support refs and checksums;
- explicit importance components, final importance, uncertainty and reason codes;
- presentation kind `inbox_item` or `digest_item` only;
- no command, connector, recipient, send target, credential, webhook or executable payload.

### Trust-control event

Higher-level intelligence needs its own immutable user overlay. A control event should support:

- `limit_scope`: restrict one cognition, recommendation or policy rule to a named domain/project/scope;
- `suppress`: do not present the referenced candidate/rule in the matched scope;
- `snooze`: suppress until an explicit timestamp;
- `revoke`: make a previously accepted higher-level cognition/recommendation ineligible for future coordination;
- `correct`: record a user correction request or corrected interpretation at the A layer;
- `mark_not_useful` / `mark_wrong_timing`: feedback for noise metrics, not truth evidence;
- `restore`: compensating event that reverses a prior limit/suppress/snooze/revoke/correct overlay.

Controls must declare target authority/type/ID/checksum, scope, actor class `user`, actor identity hash, expected stream sequence, idempotency key, reason code, created time, optional expiry and `rollback_of_event_id`. They never UPDATE or DELETE Phase 25/26 rows.

Important boundary: if a correction changes canonical KU content or lifecycle, Phase 27 may only create a `canonical_correction_requested` control outcome and link to the Phase 24 reviewed lifecycle workflow. It must not bypass `knowledge_lifecycle_*`, invent a reviewer, or mutate KU itself.

## Recommended additive schema

Add the following tables to the existing schema migration, with immutable UPDATE/DELETE triggers and canonical payload checksums:

1. `proactive_runs`
   - exact snapshot ID/hash;
   - Phase 25 source run/checksum/publication sequence;
   - optional exact Phase 26 decision run checksum and policy version;
   - coordination/ranking/noise-policy versions;
   - immutable input/output manifest checksums and committed status.
2. `proactive_coordination_items`
   - typed cross-domain relation, source refs/checksums, domains, scope, rule version, confidence and uncertainty.
3. `proactive_candidates`
   - typed suggestion metadata, importance components, dedup key, expiry, support manifest and payload checksum.
4. `proactive_candidate_support`
   - typed links to Phase 25 assertions/changes/risks and Phase 26 recommendations/events/effectiveness; exact run/snapshot binding.
5. `proactive_evaluations`
   - one deterministic evaluation per candidate/policy/evaluation window, result `eligible|suppressed|deferred|expired|abstained`, reason codes and budget/cooldown/quiet state checksum.
6. `proactive_control_events`
   - append-only user limit/suppress/snooze/revoke/correct/feedback/restore events with per-target sequence, idempotency and rollback link.
7. `proactive_surface_events`
   - optional explicit local records such as `presented`, `acknowledged` or `dismissed`; never an external delivery receipt and never written implicitly by a REST/MCP read.

Do not add a mutable `current_notification_status` truth table. Current eligibility and control state are pure projections over immutable run, evaluation and user-event sequences.

## Architecture Patterns

### 1. Bind one immutable upstream state

The run graph must be:

```text
serving snapshot
  -> exact committed Phase 25 personal-state run
  -> optional exact committed Phase 26 decision run/event frontier
  -> active user-control frontier
  -> versioned coordination/ranking/noise policies
  -> immutable proactive run and candidates
```

Revalidate every binding inside the publication transaction, as Phase 26 now does for every append. A changed source run, event frontier, control frontier or policy version produces a new run; it never edits a historical candidate.

### 2. Deterministic multi-domain coordination

Use explicit rule registries. A rule declares eligible source types, involved domains, required goal/constraint/resource inputs, temporal compatibility, privacy class, minimum confidence, contraindications and output coordination type. Rules abstain on cross-snapshot input, future observations, unresolved conflict, expired state, sensitive evidence or missing resource units.

Coordinates must compare compatible units and horizons. “Two goals exist” is not sufficient evidence of conflict. A conflict requires a shared bounded resource or incompatible state; an opportunity requires an explicit compatible action/target.

### 3. Importance ranking without an opaque score

Calculate a bounded, explainable importance vector rather than a learned scalar alone:

- `severity`: explicit risk/change severity;
- `urgency`: time remaining relative to a declared horizon;
- `goal_impact`: number and priority of user-declared goals affected;
- `cross_domain_impact`: bounded count of materially affected domains;
- `novelty`: whether the exact dedup group has materially changed since its last eligible evaluation;
- `evidence_strength`: eligible source count, confidence and uncertainty penalties;
- `user_relevance`: explicit user priority/control only, never inferred from private data;
- `outcome_signal`: bounded observational Phase 26 usefulness data only after minimum sample, never causal.

Store every component and reason code. Apply a versioned threshold only after privacy, evidence and trust-control vetoes. A high score never bypasses an explicit suppress/quiet/privacy control.

### 4. Deduplication, cooldown, quiet periods and noise budgets

- **Dedup key:** canonical hash of candidate class, normalized target authority/record group, domain set, scope, material change signature and policy version. Avoid fuzzy semantic deduplication in v1.
- **Material update:** only a changed severity/urgency band, new eligible evidence, changed goal/constraint relation or expired prior candidate opens a new candidate version.
- **Cooldown:** key by `(candidate_class, subject, scope, domain_set)` and project the last explicit surfaced/acknowledged event. Repeated candidates become `suppressed:cooldown_active` unless a versioned critical escalation rule applies.
- **Quiet period:** use an explicit timezone and user-declared windows. The result is `deferred_until`, not sent later by a daemon. Missing/invalid timezone fails closed to inbox-only.
- **Noise budget:** deterministic rolling global and per-domain limits for eligible items. Select by importance vector, urgency and stable candidate ID; excess becomes `suppressed:noise_budget_exhausted`. Critical escalation may exceed the numeric budget only if the policy declares it, but never overrides privacy or explicit suppression.
- **Digesting:** group compatible low-urgency candidates into a metadata-only digest proposal. Grouping never drops evidence refs or merges contradictory items.

### 5. Permission and external-action boundary

“Proactive” in Phase 27 means the system can prepare an eligible inbox/digest before a user asks a question. It does **not** authorize sending email, calendar/task creation, push notification, messaging, purchasing, publishing, command execution or connector calls.

- REST and MCP expose read-only `inbox`, `digest`, `candidate.get`, `explain` and `controls.status` operations.
- A local CLI may append user controls or explicit presented/acknowledged feedback only with `--write`, exact target/checksum, human identity hash, expected sequence, idempotency key and exact `--i-confirm` token.
- No REST POST or MCP mutation tool is added until a separate authenticated capability design exists.
- Acceptance must assert `external_actions=0`, `network_calls=0`, `paid_calls=0` and static absence of executor/dispatch surfaces.

### 6. Trust projection and rollback

Project the most recent valid control stream in sequence order. Exact-target controls outrank policy/domain/global controls; at the same specificity, the latest valid event wins, while explicit deny/suppress remains fail-closed when state is ambiguous. Expiry is evaluated at the acceptance `as_of`, not wall-clock time hidden inside tests.

Rollback is a new `restore` event that references one prior event and records before/after projected state. It cannot erase the prior event. Same-key retries return the original receipt; changed payloads return `idempotency_conflict`; stale expected sequences return `stale_sequence`. Fault injection after every insert boundary must leave typed row counts and event sequence unchanged.

### 7. Observability and bounded learning

Expose metadata-only metrics by policy version, domain and candidate class:

- generated, eligible, deferred, suppressed and abstained counts;
- suppression counts by privacy, evidence, dedup, cooldown, quiet and budget reason;
- dedup rate, repeat-within-cooldown rate, budget utilization and age-to-expiry;
- acknowledged, dismissed, `not_useful`, `wrong_timing` and correction rates from explicit user events;
- evidence-resolution, checksum and cross-snapshot failure counts;
- zero external/network/paid action counters.

Do not call a candidate “accurate” or “useful” from synthetic fixtures. Fixture labels prove deterministic behavior only. Real usefulness and noise precision require explicit user feedback and sufficient real sample sizes. Phase 26 effectiveness remains observational with `causal_claim=false`; it may inform a later bounded policy version but must never self-modify historical scores.

## Don't Hand-Roll

- Do not create a unified personal-profile blob, second KU store or cross-domain vector authority.
- Do not copy Phase 25 facts into proactive candidates or treat candidate importance as truth confidence.
- Do not use an LLM to decide evidence eligibility, user identity, control precedence, sequence validity or lifecycle mutation.
- Do not implement fuzzy deduplication before deterministic keys and reason-coded suppression are proven.
- Do not add an external notification sender, scheduler, retry daemon, connector abstraction or background executor.
- Do not auto-confirm recommendations, auto-apply corrections or infer consent from a read request.
- Do not let Phase 27 corrections bypass the reviewed Phase 24 canonical lifecycle path.
- Do not claim causal recommendation effectiveness or train an opaque ranking model on small personal samples.
- Do not run the live migration merely to make acceptance non-empty.
- Do not count fixture/sandbox identities, controls, outcomes or feedback as real user evidence.

## Common pitfalls and required controls

| Pitfall | Required control |
|---|---|
| Domain labels drift or overlap | Closed eight-domain vocabulary, explicit aliases and unknown-domain abstention |
| Two goals are called a conflict without a bounded resource | Rule requires compatible resource/unit/horizon evidence |
| Importance hides uncertainty | Persist every component, confidence penalty and reason code |
| Repeated changes spam the inbox | Stable dedup key, material-change rule, cooldown and global/domain budgets |
| Quiet hours become a hidden scheduler | Record `deferred_until`; no daemon or automatic dispatch |
| Critical score bypasses user suppression | Privacy and explicit trust controls are unconditional vetoes |
| Correction silently edits history | Append control/correction request; canonical changes stay in Phase 24 lifecycle |
| Read endpoint records “presented” | Reads remain side-effect free; surfacing is a separate explicit local event |
| Concurrent controls reorder state | `BEGIN IMMEDIATE`, expected sequence, event checksum chain and idempotency key |
| Partial Phase 27 schema treated as unapplied | Three-state schema check: complete-unapplied allowlisted, complete-applied verified, partial blocked |
| Synthetic acceptance becomes product proof | Separate technical and release verdicts and evidence classes |
| Phase 24 blocker disappears from Target D report | Bind exact checkpoint checksums/status and require all quality/lifecycle gates for product sign-off |

## File touchpoints

### New implementation

- `src/personal_knowledge/intelligence/proactive/__init__.py`
- `src/personal_knowledge/intelligence/proactive/schema.py`
- `src/personal_knowledge/intelligence/proactive/runs.py`
- `src/personal_knowledge/intelligence/proactive/coordination.py`
- `src/personal_knowledge/intelligence/proactive/ranking.py`
- `src/personal_knowledge/intelligence/proactive/controls.py`
- `src/personal_knowledge/intelligence/proactive/service.py`
- `src/personal_knowledge/intelligence/proactive/cli.py`
- `docs/runbooks/proactive-intelligence.md`

### Narrow extensions

- `governance/policies/artifact_layers.yaml` — add non-serving `a.proactive_intelligence`.
- `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py` — additive tables, indexes, FKs and immutable triggers only.
- `src/personal_knowledge/services/api_server.py` — thin read-only routes.
- `src/personal_knowledge/services/mcp_server.py` — thin read-only tools; no send/execute/control-write tool.
- `src/personal_knowledge/intelligence/cli.py` and `src/personal_knowledge/intelligence/decision/cli.py` — reuse checkpoint/fingerprint helpers where practical; do not alter Phase 25/26 semantics.
- `src/personal_knowledge/governance/preflight.py` — registry/interface/static no-executor contracts if needed.

### Tests

- `tests/unit/test_proactive_schema.py`
- `tests/unit/test_proactive_coordination.py`
- `tests/unit/test_proactive_ranking.py`
- `tests/unit/test_proactive_controls.py`
- `tests/contract/test_proactive_boundaries.py`
- `tests/contract/test_proactive_interfaces.py`
- `tests/integration/test_proactive_runs.py`
- `tests/integration/test_proactive_concurrency.py`
- `tests/integration/test_proactive_privacy.py`
- `tests/integration/test_target_d_acceptance.py`

## Recommended plan split

### 27-01 — Multi-domain coordination authority

- Register non-serving `a.proactive_intelligence` and add immutable run/coordination/candidate schema.
- Define the eight domains, typed resource/horizon model and cross-domain relation rules.
- Bind exact Phase 25/26 run, snapshot, source checksum and event frontier.
- Prove cross-snapshot, sensitive, incompatible-unit, future/stale and insufficient inputs abstain.
- Primary requirement: PRO-01.

### 27-02 — Important-change ranking and noise governance

- Add versioned importance components and deterministic candidate ranking.
- Add dedup, material-update, cooldown, quiet-period, digest and global/domain noise-budget policies.
- Publish immutable evaluations with explicit suppression/defer reason codes.
- Prove repeated/noisy candidates cannot bypass privacy, trust or budget gates.
- Primary requirement: PRO-02.

### 27-03 — User trust controls and reversible scope lifecycle

- Add append-only limit/suppress/snooze/revoke/correct/feedback/restore events.
- Implement exact-target/domain/global precedence, expiry, expected sequence, idempotency and rollback projection.
- Keep canonical corrections linked to, but outside, Phase 27; Phase 24 review remains mandatory.
- Add guarded local CLI writes only and read-only REST/MCP status/explain contracts.
- Primary requirement: TRUST-01.

### 27-04 — Shared proactive interfaces and Target D acceptance

- Add shared inbox/digest/get/explain/observability reads and thin CLI/REST/MCP adapters.
- Run a full Target D disposable sandbox from source state through change, recommendation, confirmation, action, outcome, feedback, proactive suppression and trust rollback.
- Run live metadata-only acceptance with schema three-state checks and before/after fingerprints.
- Emit separate `technical_status` and `release_status`; preserve exact Phase 24 blockers.
- Primary requirement: TD-01.

Wave structure: 27-01 first; 27-02 and 27-03 may execute in parallel after the shared schema/binding contract; 27-04 depends on both.

## Target D end-to-end acceptance matrix

| Stage | Required technical proof | Fixture/sandbox evidence | Live-safe evidence | Product sign-off requirement |
|---|---|---|---|---|
| Capture and authority | One immutable serving snapshot and eligible typed evidence | Temporary Phase 23 snapshot fixture | Resolve active snapshot/hash metadata only | Phase 24 current quality evidence is genuine PASS |
| State modeling | Goals, constraints and observations remain distinct | Publish deterministic Phase 25 run | Report applied/unapplied/partial schema state | Authorized real run, not required for technical pass |
| Change/history | Created/updated/conflict/trend/risk and bitemporal history reconstruct | Multi-version Phase 25 fixture | Zero-mutation read or explicit unavailable reason | Real user interpretation/UAT if claimed as product behavior |
| Recommendation | Recommendation remains A-layer and evidence-bound | Phase 26 eligible + abstain rules | No live publication | Genuine quality/lifecycle prerequisites satisfied |
| Confirmation/correction | User confirmation differs from truth; correction is append-only | Human-class sandbox actor and control stream | No fabricated live write | Genuine user/operator confirmation; canonical correction follows Phase 24 review |
| Action/outcome/effectiveness | Explicit action and observation; assessment non-causal | Accepted and rejected event histories | `external_actions=0` | Real outcome only if separately authorized and observed |
| Multi-domain coordination | Eight domains, resource conflicts/opportunities and explicit uncertainty | At least one support, conflict, abstain and sensitive-domain case | Candidate counts/reasons only | User validates domain/scope usefulness |
| Proactive filtering | Threshold, dedup, cooldown, quiet and budgets are deterministic | Repeated candidate suppression and critical/privacy veto cases | No dispatch, network or paid calls | Real noise/usefulness sample before tuning claims |
| Trust lifecycle | Limit/revoke/snooze/correct/restore are ordered, idempotent and rollbackable | Concurrent/stale/tamper/fault tests | No live control mutation | Genuine user controls for product adoption |
| Interfaces | CLI/REST/MCP share checksum-verifying reads | Contract parity and side-effect tests | Metadata-only invocation if schema absent | Services/UAT operational if release is claimed |
| Privacy/evidence | No source body, secret, PII or version drift leaks | Privacy and cross-snapshot negative tests | `private_bodies=0` | Phase 24 privacy/quality gate PASS |
| Release | Technical and release states cannot be conflated | Sandbox `technical_status=passed` | Phase 24 exact statuses/checksums preserved | Human Gold/Judge/UAT + reviewed lifecycle cohort + explicit release authorization |

The sandbox should include at least:

1. one Phase 25 goal and constraint in different domains sharing a bounded time/energy resource;
2. one compatible cross-domain opportunity and one real rule-based conflict;
3. one Phase 26 recommendation accepted through action/outcome/assessment and one rejected recommendation;
4. duplicate proactive candidates evaluated across fixed time windows, proving dedup, cooldown, quiet and budget behavior;
5. one sensitive/private candidate that remains abstained regardless of importance;
6. one user suppression or scope limit, one rollback/restore and one stale concurrent append;
7. a complete checksum chain and identical live before/after fingerprints.

## Target D acceptance command semantics

The Phase 27 acceptance command should require `--dry-run --metadata-only` for live inspection and return at least:

```text
technical_status
release_status
release_ready
release_blockers.technical
release_blockers.phase24
snapshot_id / snapshot_hash
phase25_binding / phase26_binding / phase27_schema_state
sandbox.stage_results
candidate_counts / suppression_reason_counts / domain_counts
control_and_rollback_results
before_fingerprint / after_fingerprint / unchanged
mutations / persisted_rows / private_bodies
external_actions / network_calls / paid_calls
phase24 checkpoint statuses and checksums
```

Rules:

- completely unapplied Phase 25/26/27 analysis schemas may be allowlisted as explicit unavailable states for live metadata-only acceptance;
- any partial schema, corrupt checksum, mixed snapshot, stale source binding or malformed event chain makes `technical_status=failed`;
- `release_ready = technical_ok AND phase24_human_review_strict_ok AND phase24_lifecycle_strict_ok AND phase24_final_gate_passed AND explicit_product_uat_signed`;
- fixture/sandbox rows never contribute to those release conditions;
- the command must not migrate, persist, publish, activate, advance watermarks, finalize review, apply lifecycle, dispatch, call network or call a paid provider.

## Target D completion definition

### Technically complete

Phase 27 and Target D are **technically complete** only when:

1. PRO-01, PRO-02, TRUST-01 and TD-01 each have direct positive and negative automated evidence.
2. All eight domains and time/energy resource conflicts are covered by deterministic rules and abstention tests.
3. Every proactive output is snapshot/run/evidence bound and never serialized as fact or KU.
4. Importance, dedup, cooldown, quiet and budget decisions expose reproducible components and reason codes.
5. User controls are append-only, scoped, idempotent, concurrency safe and rollbackable.
6. REST/MCP are read-only and no external executor/dispatch surface exists.
7. Disposable sandbox completes the full Target D loop and live metadata-only acceptance proves zero mutation and zero external/network/paid action.
8. Targeted suites, adjacent Phase 25/26 regressions, governance preflight and the full repository suite pass.
9. Verification explicitly reports `release_blocked` while Phase 24 remains open.

### Product complete / signed off

Target D is **not product complete** until all technical conditions above plus all of the following are true:

1. Phase 24 genuine human Gold, groundedness, judge calibration and UAT evidence passes the unchanged policy.
2. A genuinely reviewed lifecycle cohort is applied and rollback evidence exists; canonical corrections do not bypass that workflow.
3. Any live Phase 25/26/27 schema migration and publication has separate explicit authorization and a verified rollback path.
4. A real user/operator validates at least one end-to-end state/change/recommendation/control path without fabricated identity or labels.
5. Real usefulness/noise feedback is reported as observational evidence with adequate sample disclosure, not inferred from fixtures.
6. An explicit product UAT signs the no-external-action boundary and release status.

Therefore, **Phase 24's real human review gate is a hard Target D product blocker**. It is not a blocker to Phase 27 implementation or technical sandbox verification. The agent can autonomously complete the technical phase but cannot autonomously produce the missing human evidence or truthfully declare full product Target D release.

## Validation strategy

### Unit and contract gates

- Domain vocabulary, alias, unit/horizon and coordination rule tests.
- Importance component, threshold, dedup, cooldown, quiet, budget and deterministic ordering tests.
- Trust-control precedence, expiry, correction boundary, restore and idempotency tests.
- Contracts rejecting candidate-as-fact/KU, private source bodies, command/connector fields and REST/MCP writes.
- Static tests proving no executor, dispatch, email, calendar, purchase, publish or connector mutation tool.

### Integration and fault gates

- Cross-snapshot, stale Phase 25/26 binding, partial schema and row-checksum tamper failures.
- Exact replay, changed-input new run, concurrent control append and same-key payload conflict.
- Fault injection after run, candidate, support, evaluation and control/event inserts with total rollback.
- Complete sandbox Target D loop with fixed `as_of` and no wall-clock nondeterminism.
- Privacy/secret/sensitive-domain candidate remains abstained even under maximum importance.

### Repository and live-safe gates

- Phase 27 targeted pytest suite.
- Phase 25 and Phase 26 full adjacent regression suites.
- Existing Apps SDK, knowledge search and serving snapshot contracts.
- `python -m personal_knowledge.governance.preflight --ci`.
- Full `python -m pytest -x -q --tb=short`.
- Live acceptance only with metadata-only dry-run and exact before/after fingerprints.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Phase 27 appears to finish Target D while source quality is unsigned | Two verdicts, immutable Phase 24 checkpoint binding and explicit release formula |
| Cross-domain model overreaches into health/finance/relationship advice | Minimum abstraction, sensitivity veto, deterministic abstention and no external action |
| Ranking becomes an opaque personal manipulation loop | Named components, versioned thresholds, reason codes and no self-modification |
| Notification noise is measured only on synthetic data | Label fixture results as technical; real usefulness requires explicit user events |
| Controls mutate historical truth | Overlay events only; canonical changes route through Phase 24 lifecycle |
| Read interface accidentally becomes stateful | No implicit surfaced event; explicit guarded local event only |
| Analysis schema absence is treated as success after corruption | Complete-unapplied allowlist, complete-applied validation, partial/corrupt fail closed |
| Time-dependent tests flake | Fixed `as_of`, explicit timezone and deterministic evaluation windows |
| Concurrent retries duplicate prompts or controls | Unique idempotency scope, expected sequence and transactional append |
| “Proactive” expands into unauthorized delivery | Inbox/digest only; static and dynamic zero-external-action gates |

## Planning decisions to lock

1. Create `a.proactive_intelligence` as a non-serving A-layer authority.
2. Use exactly eight canonical domains; time and energy are explicit bounded resources.
3. Reference Phase 25/26 records by exact checksum; never duplicate/reclassify them as facts.
4. Use deterministic coordination and importance policies before any model-based ranking.
5. Treat dedup, cooldown, quiet and budgets as immutable reason-coded evaluations.
6. Keep REST/MCP read-only and provide no notification sender or external executor.
7. Implement user corrections/limits/revocations as reversible overlays; canonical corrections stay behind Phase 24 human review.
8. Separate technical Target D acceptance from product release sign-off.
9. Preserve Phase 24 blockers verbatim and do no live migration/write/apply/serving/external action in Phase 27 acceptance.

## RESEARCH COMPLETE

