---
phase: 24
plan: 03
status: human_verification_required
updated: 2026-07-17
---

# Phase 24-03 Lifecycle Adoption Checkpoint

## Automated evidence complete

- Lifecycle manifests, actions, events and corrections use FK-backed additive tables.
- Proposal, exact human review finalization, registration, apply and rollback are separate operations.
- Tampered, stale, unreviewed and fault-injected paths fail without materialized lifecycle changes.
- Candidate vector construction requires both `status=current` and `lifecycle=current`.
- History exposes ordered metadata-only lifecycle events and never deletes prior units.
- Direct heuristic `reconcile --write` is retired.
- Targeted verification: 62 tests passed on 2026-07-17.
- Serving registry check: `pk-sync status --json` returned `ok=true` and `drift=[]`.

## Bounded private review cohort

- Proposal: `var/runtime/private_evals/lifecycle_review_v1.private.json`
- Review template: `var/runtime/private_evals/lifecycle_review_v1.private.review.json`
- Proposal manifest: `klm_e8ced73cbe5a0aec47406f64`
- Proposal checksum: `e8ced73cbe5a0aec47406f64d94313607776fb9730b55f9006c84827aaf42159`
- Actions: 13 `conflict` proposals; every decision is `pending`.
- Content fields: none; only unit IDs, versions, reasons and evidence references are included.

## Blocking human verification

A genuine human reviewer must approve or reject every proposal and provide a non-agent reviewer identity and review timestamp. Do not fabricate approvals and do not apply the proposal itself.

After review, use the exact workflow below:

```powershell
pk-ku lifecycle-finalize --proposal var/runtime/private_evals/lifecycle_review_v1.private.json --review var/runtime/private_evals/lifecycle_review_v1.private.review.json --artifact var/runtime/private_evals/lifecycle_reviewed_v1.private.json
pk-ku lifecycle-register --manifest var/runtime/private_evals/lifecycle_reviewed_v1.private.json --write --i-know
pk-ku lifecycle-apply --manifest var/runtime/private_evals/lifecycle_reviewed_v1.private.json --actor <human-operator-id> --write --i-know
pk-ku lifecycle-status --strict
```

Applying any accepted action is a live data transition. It requires explicit review and authorization, followed by candidate rebuild, snapshot-bound evaluation and PASS-gated publication. Until then, `lifecycle-status --strict` is expected to fail with zero applied manifests and zero events.

