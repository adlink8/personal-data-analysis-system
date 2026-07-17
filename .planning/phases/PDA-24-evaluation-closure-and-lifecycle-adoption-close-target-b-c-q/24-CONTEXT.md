---
phase: 24
name: evaluation-closure-and-lifecycle-adoption
created: 2026-07-17
mode: autonomous
depends_on: [23]
requirements: [QUAL-01, QUAL-02, LIFE-01, LIFE-02]
---

# Phase 24 Context

## Boundary

Close the evidence-backed quality and lifecycle gaps against the active Phase 23 serving snapshot. This phase may improve retrieval/evaluation, add auditable lifecycle operations, run private evaluations and perform reversible local UAT. It must not invent human labels, weaken thresholds, leak private cases, call paid judges without explicit approval, or promote a failing candidate.

## Current Evidence

- Active serving snapshot: `ss_1590353394c948b908a5d675`; Doctor critical failures 0; 10/10 roles bound.
- Authoritative evaluation run: `6d7233db5da0414c`, verdict FAIL.
- Real scoreable gold: 22; real cross-turn gold: 0 under scorer-v2 classification.
- Candidate no-answer FP: 90.625%; score-only abstention calibration cannot meet FP <=10% and positive retention >=80%.
- Grounded L2 review packet: 50 rows, 0 human labels.
- Lifecycle live counts: current 32,182; deprecated 2; no lifecycle/correction event table; 2,525 multi-current subject/type groups.
- A 100-subject dry-run proposed 13 conflicts but no supersedes, showing the existing token-Jaccard heuristic is too weak for blind mass adoption.

## Decisions

- **D-24-01:** Every evaluation run is bound to one active/candidate serving snapshot ID and manifest hash; mixed-version evaluation fails closed.
- **D-24-02:** Evidence-aware abstention must use typed evidence eligibility/resolution and query-support features. A single similarity threshold is insufficient and will not be deployed.
- **D-24-03:** Synthetic shells remain CI/safety fixtures. They never count as real Gold, cross-turn Gold, grounded-human labels or judge calibration.
- **D-24-04:** Human labels require reviewer identity/provenance and explicit import. The agent may prepare packets and validate labels but must not self-certify them as human.
- **D-24-05:** Paid judge calls remain blocked without separate explicit authorization. Cache replay and deterministic metrics are the default.
- **D-24-06:** Lifecycle writes require a reviewed action manifest, immutable before/after events and bounded scope. No mass write from heuristic output and no hard delete.
- **D-24-07:** Corrections are distinct from inferred conflicts/supersedes and record actor, reason, evidence, scope and rollback link.
- **D-24-08:** Product retrieval remains current-only. Growth-line/history is explicit and returns lifecycle events and evidence.
- **D-24-09:** Promotion requires a genuine policy PASS. Rollback UAT switches only validated snapshots and restores the original snapshot in the same controlled procedure.
- **D-24-10:** Phase completion is not allowed while required human Gold/grounded/judge/UAT evidence is absent, even if all code is complete.

## Implementation Direction

1. Make evaluation and relevance decisions snapshot/evidence aware and privacy fail-closed.
2. Productize private Gold, grounded review and judge calibration packets with explicit human import boundaries.
3. Add lifecycle/correction event governance and adopt a small reviewed real cohort before rebuilding a current-only candidate.
4. Run the full five-mode/answer/gate pipeline, then perform promote-refusal or reversible rollback UAT according to the genuine verdict.

## Out of Scope

- Target D state/change, decision feedback and proactive notification models (Phases 25–27).
- Changing v2 policy thresholds to force PASS.
- Publishing private queries, answers, evidence text or reviewer packets to Git.
- Remote deployment, paid evaluation or external account changes.
