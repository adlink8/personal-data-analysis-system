---
phase: 25
status: complete
researched: 2026-07-17
requirements: [INTEL-01, INTEL-02]
---

# Phase 25 Research: Personal State and Change Intelligence

## Scope and existing authority

Phase 25 must add an analysis layer, not another memory or knowledge authority. The current system already provides:

- An immutable serving snapshot that binds canonical conversation/message, Turn, Google, KU and retrieval versions.
- Typed D/S/R/A registry entries, including the reserved `a.personal_change` analysis authority.
- EvidenceResolver contracts for KU, canonical message, Turn and Google signal.
- Versioned KU lifecycle/history code and an append-only event model; live lifecycle adoption remains human-gated.
- Snapshot-bound evaluation and fail-closed retrieval safety.

The new subsystem should consume one serving snapshot and publish an immutable analysis run. It must not mutate KU, lifecycle, watermarks, serving authority or source data while computing state.

## Recommended domain model

Use explicit typed records rather than free-form summaries:

1. `goal` — desired future condition, scope, horizon and evidence.
2. `constraint` — hard/soft limit, scope, validity interval and evidence.
3. `observation` — time-bound evidence-backed occurrence; never silently promoted to fact.
4. `state` — a versioned projection derived from accepted evidence as of a serving snapshot.
5. `change` — comparison between two state projections, with before/after refs and change type.

Every assertion should include stable ID, subject/domain, type, predicate/value, valid time, observed time, confidence, uncertainty reason, provenance class (`fact`, `observation`, `inference`), evidence refs, source snapshot ID/hash, producer version and lifecycle. Facts, observations and inferences remain distinguishable in storage and output.

## Storage and lineage

Use additive SQLite tables with foreign keys and immutable JSON manifests:

- `personal_state_runs`: snapshot-bound input/output manifest, algorithm version, status and checksum.
- `personal_state_assertions`: typed evidence-backed goals/constraints/observations/state claims.
- `personal_state_evidence`: assertion-to-typed-evidence mapping.
- `personal_state_changes`: before/after assertion refs, change type, magnitude, confidence and uncertainty.
- `personal_state_risks`: optional derived risk records with rule ID, evidence and non-prescriptive severity.

Materialized “current state” is a deterministic projection over immutable records, not a separately edited truth table. Re-running the same snapshot and algorithm must return the same checksum. Different snapshots or implementation versions produce new runs and never overwrite old runs.

## Deterministic change semantics

Start with explainable rules:

- `created`, `updated`, `reaffirmed`, `stale`, `conflict`, `resolved`, `trend_up`, `trend_down`, `risk`.
- A change requires comparable typed predicates and a valid before/after ordering.
- Conflict requires incompatible current claims in the same scope; absence of evidence is not conflict.
- Trend requires at least three ordered observations and reports sample count/window.
- Risk requires an explicit rule and evidence; it is an inference, never a fact KU.
- Uncertain or insufficient evidence remains visible and must not be collapsed into a confident current state.

## Privacy and trust boundaries

- Resolve only snapshot-bound, eligible evidence; retain refs/checksums, not unrestricted source bodies.
- Secret/ineligible evidence vetoes the assertion.
- Sensitive domains may be modeled only at the minimum useful abstraction; no credentials, identity numbers or payment details.
- Phase 25 produces explanations and change summaries, not recommendations. Recommendation/confirmation/action semantics belong to Phase 26.
- Human correction must be representable as a later immutable assertion/event, never destructive editing.

## Product surface

Provide read-first interfaces:

- `state current`: typed current goals, constraints and observations with evidence and uncertainty.
- `state history`: versioned projection history for a subject/domain.
- `changes recent`: bounded changes with before/after evidence.
- `state explain`: why a current state exists, including conflict/trend/risk derivation.

CLI/shared backend should return snapshot ID, run ID, manifest checksum and evidence status. REST/MCP can wrap the same backend after contracts pass.

## Validation strategy

- Unit fixtures for temporal ordering, conflict, trend, risk and uncertainty rules.
- Contract tests that prevent inference-as-fact, cross-snapshot mixing and secret evidence.
- Idempotence and checksum tests for same-snapshot replay.
- Fault injection proving failed runs publish nothing.
- Live read-only dry-run against the active snapshot, with aggregate counts and metadata-only samples.
- Golden explanation tests showing each current state can be reconstructed from immutable evidence.

Phase 24 human review remains a release dependency, but Phase 25 code can be built and validated read-only against the current snapshot. No Phase 25 acceptance claim should depend on fabricating Phase 24 approvals.

## Recommended plan split

1. **25-01 — State schema and snapshot-bound run contract:** typed tables, manifests, evidence validation, idempotent dry-run/write separation.
2. **25-02 — Deterministic state projection:** goal/constraint/observation extraction inputs, temporal current-state reconstruction and uncertainty.
3. **25-03 — Change intelligence:** before/after comparison, conflict/trend/risk rules and evidence-backed recent-change summaries.
4. **25-04 — Product interfaces and acceptance:** shared read backend, CLI/REST/MCP parity, live dry-run, replay/fault/privacy gates and verification.

## RESEARCH COMPLETE

