---
phase: 26
status: complete
researched: 2026-07-18
requirements: [DEC-01, DEC-02]
confidence: high
---

# Phase 26 Research: Decision Action Feedback Loop

## Research conclusion

Phase 26 should add a separate, append-only **A-layer decision-feedback authority** over the technically verified Phase 25 personal-state runs. It must not extend `personal_state_assertions` with recommendations, copy facts into a new truth store, or treat user acceptance as evidence that a claim is true. The safe implementation is:

1. Phase 25 facts, observations and inferences remain immutable upstream references.
2. Recommendations are snapshot/run-bound proposals under a new `a.decision_feedback` authority.
3. User confirmation, action recording, outcome recording and effectiveness assessment are distinct append-only record types with explicit actors and transition rules.
4. Acceptance never executes an external action. An action row records intent or an attested event; it is not an executor job.
5. Phase 24 remains `release_blocked`, so Phase 26 can be implemented and verified with fixtures and metadata-only live inspection, but no live migration, publication, confirmation write or adoption is allowed.

Confidence is high for the local architecture and test strategy because it directly reuses verified repository patterns. Confidence is medium for effectiveness calibration because observational personal data cannot identify a counterfactual or causal effect without a designed comparison.

## Existing authority and constraints

### Reusable verified foundation

- Phase 23 provides the typed D/S/R/A registry, immutable composite serving snapshot and fail-closed evidence drill-down.
- Phase 25 publishes immutable `personal_state_runs` under `a.personal_change`, binds one snapshot ID/hash and complete member manifest, and orders publications with `personal_state_publications.publication_sequence`.
- `StateAssertion` and persisted assertion rows already separate `assertion_kind` from `provenance_class`; fact, observation and inference are schema constrained.
- Phase 25 current/history/recent/explain use one `IntelligenceService`, apply bitemporal valid/observed cutoffs, verify row-level checksums, and abstain on evidence/version drift.
- `knowledge_lifecycle_*` provides a useful pattern for reviewed manifests, exact checksums, actor/reviewer identity, optimistic versions, `BEGIN IMMEDIATE`, append-only events, rollback links and fault injection.
- REST and MCP already use thin adapters over a shared service and apply privacy guards at the transport boundary.

### Boundaries that Phase 26 must preserve

- `personal_state_assertions` permits only goal/constraint/observation/state; existing tests explicitly reject `recommendation` as an assertion kind. Preserve this contract.
- A recommendation is not a canonical KU, lifecycle transition, serving member, watermark input, source fact or evidence eligibility decision.
- A user confirmation expresses a decision about a recommendation. It does not promote the recommendation's premises from inference/observation to fact.
- Phase 25 risks are non-prescriptive inferences. Recommendation policy may consume them but must preserve the risk rule, uncertainty and evidence lineage.
- Phase 24 checkpoints remain exactly `awaiting_human`, `human_verification_required` and `blocked_on_human_and_quality_gates`. Phase 26 confirmations cannot satisfy Phase 24 Gold/Judge/lifecycle review.
- No network/paid provider, external command, calendar/email/task mutation, lifecycle apply, snapshot activation, pointer mutation or watermark advance belongs in this phase.

## Standard Stack

Use the repository's existing stack only:

| Concern | Prescribed implementation |
|---|---|
| Typed records | Frozen Python dataclasses and canonical JSON/checksum helpers, matching `intelligence/schema.py` |
| Storage | Additive SQLite tables, FK enforcement, immutable triggers and `BEGIN IMMEDIATE` transactions |
| Authority | New registry entry `a.decision_feedback`, layer A, evidence parent `a.personal_change`; do not add it to `required_serving_roles` |
| Upstream binding | Exact Phase 25 `run_id`, run checksum, publication sequence, snapshot ID/hash and assertion/change/risk refs |
| Read service | One shared decision service, with CLI/REST/MCP thin read adapters |
| Explicit writes | Local CLI only initially, with `--write`, exact record ID/checksum, expected sequence, actor and idempotency key |
| Privacy | Typed refs/checksums and minimum structured fields; existing `privacy_guard`; no source bodies or evidence quotes |
| Tests | pytest unit, contract and SQLite integration fixtures; no new dependency |

Do not introduce an agent framework, workflow engine, hosted event store, vector index, external analytics service or causal-inference dependency.

## Recommended domain model

### Cognitive type envelope

Expose one discriminated read contract with exactly these types:

| Type | Storage authority | Meaning | May assert truth? | Who may create |
|---|---|---|---|---|
| `fact` | Phase 25 assertion ref | Reviewed/canonical factual premise | Only within existing Phase 25 provenance rules | Phase 25 pipeline |
| `observation` | Phase 25 assertion or recorded outcome ref | Time-bound observed occurrence | No timeless fact promotion | Phase 25 or explicit outcome recorder |
| `inference` | Phase 25 state/change/risk ref | Rule-derived interpretation | No | Versioned deterministic rule |
| `recommendation` | Phase 26 recommendation | Proposed option with rationale and trade-offs | No | Versioned recommendation policy |
| `user_confirmation` | Phase 26 confirmation event | User decision about one exact recommendation | No | Explicit user-authorized write only |

Facts/observations/inferences are referenced rather than copied. A `CognitionReference` should carry `cognitive_type`, authority ID, record ID, source run ID/checksum, snapshot ID/hash, provenance, evidence status and uncertainty. Serialization and API schemas must require the discriminator; no default-to-fact behavior is allowed.

### Additive tables

Use separate tables to make permissions and FKs enforceable:

1. `decision_runs`
   - immutable generation manifest;
   - registry ID `a.decision_feedback`;
   - FK to source `personal_state_runs` plus source run checksum/publication sequence;
   - exact snapshot ID/hash, policy ID/version, input/output manifest checksums and committed status.
2. `decision_recommendations`
   - immutable structured proposal: subject/domain/scope, recommendation kind, target, horizon, rationale codes, expected benefit, costs/constraints, assumptions, contraindications, confidence, uncertainty and expiry;
   - no `fact`, `knowledge_unit`, `approved` or `executed` authority field;
   - references one decision run and one or more typed support links.
3. `decision_support_refs`
   - typed FKs to Phase 25 assertions and, when persisted/available, change/risk records;
   - requires the same source run and snapshot; retains evidence checksums, never bodies.
4. `decision_confirmations`
   - append-only decisions `accept`, `reject`, `defer` or `revoke_before_action`;
   - exact recommendation checksum, actor identity hash, actor class `user`, recorded time, reason code, expected stream sequence, idempotency key and receipt checksum.
5. `decision_actions`
   - records `planned`, `started`, `completed`, `abandoned` or `not_taken` states;
   - records user attestation or an external reference supplied by the user; contains no executable command, connector credential or dispatch target.
6. `decision_outcomes`
   - append-only outcome observations: measurement definition, baseline, observed value, unit/window, source class (`user_reported` or `evidence_measured`), evidence refs, confidence and uncertainty.
7. `decision_effectiveness`
   - immutable assessment with rule ID/version and verdict `effective`, `ineffective`, `mixed` or `inconclusive`;
   - always inference provenance; includes adherence status, sample window, limitations and `causal_claim=false`.
8. `decision_events`
   - optional normalized event ledger for complete ordered audit (`recommendation_published`, confirmation, action, outcome and assessment events), each linked to the typed row and previous event checksum.

All committed rows need update/delete rejection triggers. Prefer normalized columns for constraints plus canonical payload JSON/checksum, matching the remediated Phase 25 hydration pattern.

## Architecture Patterns

### 1. Snapshot- and run-bound recommendation generation

Resolve one committed Phase 25 run using immutable publication sequence, then bind the recommendation run to:

```text
active/explicit serving snapshot
  -> exact personal_state_run + checksum + publication_sequence
  -> bitemporal projection as_of
  -> versioned deterministic recommendation policy
  -> immutable decision_run + recommendation checksum
```

Revalidate all bindings immediately before publication. Same snapshot, source run, policy version and canonical input must replay to the same run/recommendation IDs. A changed source run or policy produces a new immutable version; it never overwrites an earlier recommendation.

Start with a small rule registry, not free-form LLM generation. Each rule must declare eligible input types, minimum evidence, contraindications, output domain/kind, uncertainty behavior and version. Insufficient, conflicting, stale or abstained Phase 25 input yields no recommendation or an explicit `insufficient_evidence` result.

### 2. Append-only state machine

Project current status from events; do not update a mutable recommendation status column.

```text
proposed
  -> accepted -> planned -> started -> completed -> outcome_recorded -> assessed
  -> rejected (terminal for this recommendation version)
  -> deferred (no action; later reconsideration creates a new confirmation/event)

accepted -> revoke_before_action -> no action
planned/started -> abandoned -> optional outcome -> assessed/inconclusive
```

Acceptance and execution are separate. `accept` authorizes only recording the user's decision; it does not authorize an external side effect. Completion is an attestation until eligible outcome evidence is attached.

### 3. Idempotency and concurrency

- Every write supplies `expected_sequence` for one recommendation stream.
- In `BEGIN IMMEDIATE`, compare expected sequence, validate transition, insert the typed row and event, then commit once.
- Assign one immutable monotonic sequence per recommendation stream and order by it, never timestamp/hash alone.
- Require a caller-provided `idempotency_key` scoped to actor + operation. Retry with the same canonical payload returns the existing receipt; different payload returns `idempotency_conflict`.
- Stable reason codes distinguish stale sequence, illegal transition, duplicate receipt, recommendation expired, cross-snapshot input and insufficient authority.
- Fault injection after every insert boundary must roll back all rows.

### 4. Permission and confirmation boundary

The current REST/MCP services are localhost but do not establish a verified user identity or authorization capability. Therefore:

- Phase 26 REST/MCP should expose read operations only: list/get recommendation, history, outcome and effectiveness.
- The first write surface should be a local CLI requiring `--write`, `--i-confirm <recommendation-id>`, actor ID, expected sequence and idempotency key.
- Do not accept agent/synthetic actor IDs as `user_confirmation`; reuse the repository's non-human identity rejection pattern.
- Do not expose `execute`, `send`, `schedule`, `purchase`, `publish` or connector mutation tools.
- If authenticated REST/MCP writes are desired later, they require a separate capability/identity design and explicit authorization, not a boolean request field.

### 5. Outcome and effectiveness semantics

Separate three questions:

- **Adoption:** did the user accept or reject the recommendation?
- **Execution/adherence:** was the accepted action started/completed?
- **Observed outcome:** did a predefined measurement change during the declared window?

Effectiveness rules may compare a recorded baseline/target with the observed value only when metric, unit, direction and window match. Missing outcome is `unknown`, not ineffective. Rejection calibrates feasibility/acceptability, not efficacy. User-reported and evidence-measured outcomes remain distinct.

Future recommendation ranking may use bounded cohort statistics by policy version, domain and recommendation kind only after a declared minimum sample. Store counts and confidence intervals, not a self-modifying opaque score. Historical records and rule versions never change.

### 6. Counterfactual limitation

A single-person observational loop normally lacks a no-action counterfactual. Phase 26 must therefore:

- set `causal_claim=false` on every effectiveness assessment;
- label results as observed association or goal attainment, not causal impact;
- report confounding, selection bias, regression to the mean, concurrent actions and measurement uncertainty;
- return `inconclusive` when baseline, comparator, window or adherence is missing;
- never claim that an accepted recommendation caused an outcome merely because it preceded it.

## Don't Hand-Roll

- Do not create a second fact/KU store or copy Phase 25 assertions into recommendation rows.
- Do not encode the workflow in ad-hoc mutable status fields; use constrained append-only events and a pure projector.
- Do not infer human identity from a REST/MCP caller or auto-fill reviewer/actor fields.
- Do not build an external action runner, scheduler, retry daemon or connector abstraction.
- Do not use an LLM to decide whether a confirmation is valid, whether evidence is eligible, or whether a transition is legal.
- Do not implement causal inference from before/after coincidence. Use explicit observational limitations.
- Do not introduce a new serving pointer or add decision feedback to the composite serving snapshot in Phase 26.

## Common Pitfalls and required controls

| Pitfall | Required control |
|---|---|
| Recommendation serialized as fact/KU | Discriminated cognitive type, separate table/registry, forbidden-field contract tests |
| Confirmation treated as premise validation | Confirmation references recommendation only; never changes provenance/evidence status |
| Accept triggers action | No executor import/callback; action requires a later explicit record operation |
| Duplicate click/retry creates duplicate events | Idempotency key + canonical payload checksum + unique constraint |
| Concurrent clients create impossible order | Expected stream sequence + `BEGIN IMMEDIATE` + monotonic event sequence |
| Recommendation generated from newer/mixed evidence | Exact Phase 25 run/snapshot/checksum binding and revalidation |
| Missing outcome counted as failure | Explicit unknown/inconclusive state |
| Outcome leaks private source content | Typed refs/checksums, allowlisted structured metrics, privacy guard |
| Rejection lowers estimated efficacy | Calibrate acceptability separately from outcome effectiveness |
| Same-second order is unstable | Immutable integer sequence, following Phase 25 remediation |
| REST/MCP write impersonates user | Keep transports read-only until authenticated capability exists |
| Phase 26 appears complete despite Phase 24 | Separate `technical_status=passed` from `release_status=release_blocked` |

## File touchpoints

### New implementation

- `src/personal_knowledge/intelligence/decision/__init__.py`
- `src/personal_knowledge/intelligence/decision/schema.py`
- `src/personal_knowledge/intelligence/decision/runs.py`
- `src/personal_knowledge/intelligence/decision/state_machine.py`
- `src/personal_knowledge/intelligence/decision/effectiveness.py`
- `src/personal_knowledge/intelligence/decision/service.py`
- `src/personal_knowledge/intelligence/decision/cli.py`
- `docs/runbooks/decision-feedback.md`

### Existing files to extend narrowly

- `governance/policies/artifact_layers.yaml` — add `a.decision_feedback`; do not add a serving role.
- `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py` — additive tables, FKs, indexes and immutable triggers only.
- `src/personal_knowledge/services/api_server.py` — thin read routes only.
- `src/personal_knowledge/services/mcp_server.py` — thin read tools only; no execution tool.
- `src/personal_knowledge/intelligence/service.py` — consume existing read contracts; avoid changing Phase 25 semantics.

### Tests

- `tests/unit/test_decision_schema.py`
- `tests/unit/test_decision_state_machine.py`
- `tests/unit/test_decision_effectiveness.py`
- `tests/contract/test_decision_cognition_boundaries.py`
- `tests/contract/test_decision_interfaces.py`
- `tests/integration/test_decision_feedback_runs.py`
- `tests/integration/test_decision_feedback_concurrency.py`
- `tests/integration/test_decision_feedback_privacy.py`
- `tests/integration/test_decision_feedback_acceptance.py`

## Recommended plan split

### 26-01 — Cognitive boundary and immutable decision authority

- Register `a.decision_feedback` without a serving role.
- Add typed cognition envelopes and additive run/recommendation/support schema.
- Bind exact Phase 25 run, publication sequence, snapshot and checksums.
- Prove recommendation cannot be persisted as fact, observation, inference or KU.

### 26-02 — Recommendation rules, confirmation and permission state machine

- Add versioned deterministic recommendation rules and abstention/contraindication behavior.
- Add append-only confirmations/actions and pure current-state projection.
- Implement expected-sequence, idempotency, actor and expiry validation.
- Provide explicit local CLI confirmation/action recording only; no external execution.

### 26-03 — Outcome, effectiveness and bounded calibration

- Add typed outcomes and effectiveness assessments.
- Separate adoption, adherence and observed result.
- Add rule-versioned, non-causal assessment and minimum-sample cohort summaries.
- Prove missing/confounded data remains inconclusive and never becomes a fact.

### 26-04 — Read interfaces and metadata-only acceptance

- Add one read service and CLI/REST/MCP parity for recommendation/history/outcome/effectiveness.
- Keep REST/MCP mutation and all executor actions absent.
- Run sandbox full-loop fixtures plus live metadata-only zero-mutation inspection.
- Report Phase 24 statuses verbatim and retain `release_blocked`.

## Validation matrix

| Requirement / invariant | Automated proof | Live-safe proof |
|---|---|---|
| DEC-01 five types remain distinct | Schema/contract tests reject discriminator omission, recommendation-as-fact/KU and confirmation-as-evidence | Metadata-only output includes authority/type/provenance; no private bodies |
| Snapshot/run lineage | Cross-snapshot, stale sequence, tampered checksum and unpublished-run fixtures fail closed | Resolve active snapshot and Phase 25 availability without applying schema |
| Recommendation quality boundary | Rule fixtures cover evidence minimum, stale/conflict/uncertainty/contraindication and deterministic replay | Candidate count/reason codes only; no publication |
| Confirmation authority | Agent/synthetic actor rejection, exact recommendation binding, expiry and illegal transition tests | No live confirmation write |
| Idempotency/concurrency | Same-key replay, changed-payload conflict, concurrent expected-sequence and fault-injection rollback | Fingerprints unchanged |
| No external action | Static import/tool contract and monkeypatched network/subprocess/connector counters remain zero | `external_actions=0`, `network_calls=0`, `paid_calls=0` |
| DEC-02 complete audit loop | Sandbox proposed→accepted/rejected→action→outcome→assessment histories reconstruct checksums | Read-only interface demonstration only |
| Effectiveness honesty | Missing baseline/outcome, unit mismatch, confounding and no-adherence return inconclusive; causal flag always false | No causal/product claim |
| Privacy | Secret/private payload veto across plan, write, service and transports | `private_bodies=0` and metadata samples only |
| Phase 24 preserved | Tests fixture all unresolved statuses and forbid them from becoming confirmation evidence | Checkpoint checksums/status, lifecycle counts, authority, KU and watermarks identical before/after |
| Regression | Phase 25 87-test suite, adjacent interface tests, governance preflight and full pytest | No migration/live write/apply/serving change |

## Acceptance and release semantics

Phase 26 can be declared **technically verified** when DEC-01/02 pass in deterministic fixtures, sandbox SQLite and read-only interfaces. It must still report:

```text
technical_status = passed
release_status = release_blocked
release_blockers = Phase 24 human Gold/Judge/UAT and lifecycle quality gates
```

The live acceptance command should fingerprint serving authority, active snapshot, KU/lifecycle tables, source watermarks and all Phase 24 checkpoint files before/after. With the live Phase 25 analysis schema intentionally unapplied, an empty decision result such as `source_analysis_unavailable` is correct. It must not run the migration merely to make a demo non-empty.

## Planning decisions to lock

1. Create `a.decision_feedback` as a non-serving A-layer authority; do not overload `a.personal_change` or KU.
2. Reference Phase 25 facts/observations/inferences; never duplicate or reclassify them.
3. Use separate recommendation, confirmation, action, outcome and effectiveness records plus an append-only event order.
4. Keep recommendation generation deterministic and versioned in Phase 26; LLM generation is staging-only future scope.
5. Make local CLI the only explicit write surface until authenticated REST/MCP capabilities exist.
6. Define acceptance as recording a decision only, never external action authorization.
7. Treat effectiveness as observational and non-causal; missing evidence is inconclusive.
8. Preserve Phase 24 release blockers and perform no live migration/write/apply/serving change.

## RESEARCH COMPLETE
