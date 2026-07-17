---
phase: 24
plan: 04
status: blocked_on_human_and_quality_gates
updated: 2026-07-17
---

# Phase 24-04 Final Evaluation Checkpoint

## Exact dry-run evidence

- Run ID: `5a59bbccc8af07586d686222a14bd4721f1441fd1b8c27ff884cfccd56b74484`
- Serving snapshot before/after: `ss_1590353394c948b908a5d675`
- Human-review binding checksum: `3a3cf55498d22c1dae3e9d6d4fdb850b4d77621ceae5f2e44d20d9935220b5fc`
- Gate verdict: `FAIL`
- Active authority unchanged: `true`
- Post-run `pk-sync status --json`: `ok=true`, `drift=[]`

The v2 policy now requires checksum-bound human-review evidence. The immutable run manifest contains the exact Gold, groundedness and judge evidence binding; absent evidence cannot be silently interpreted as PASS.

The run ID also binds seven executable evaluation/retrieval source files. Sandbox or test output directories no longer mutate the global latest-run pointer.

## Automated candidate safety gates now pass

- `l2_only` no-answer false-positive rate: 0.0.
- `l1_l2` no-answer false-positive rate: 0.0.
- `hybrid` no-answer false-positive rate: 0.0625 (threshold 0.10).
- Candidate privacy hits: 0 in `l2_only`, `l1_l2` and `hybrid`.
- Candidate secret hits: 0 in `l2_only`, `l1_l2` and `hybrid`.
- Sensitive identity, credential and payment-detail queries abstain.
- Resolved but ungrounded KU/Turn candidates are filtered; grounded product queries still return evidence-backed results.

## Open blocking evidence

- Private suite contains 22 real Gold cases; the minimum is 30.
- Private suite contains 0 real cross-turn Gold cases; the minimum is 30.
- Imported Gold, grounded L2 and judge calibration manifests are absent.
- The current unreviewed private suite cannot prove Recall@5 improvement; required minimum is +10pp with positive CI low.
- Cross-turn L2 and grounded human precision claims lack eligible reviewed evidence.

## Safety decision

No promotion, rollback or forward-restore UAT was performed because the candidate did not pass the gate. This is the required fail-closed behavior. Promotion/rollback UAT remains pending until genuine human review is imported and every v2 candidate gate passes.
