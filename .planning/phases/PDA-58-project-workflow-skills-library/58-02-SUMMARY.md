---
phase: 58
plan: 02
subsystem: skill-library
tags: [skills, data-workflows, recovery, replay, l3-checkpoint, evaluation]
requires: [58-01, 56-02, 57-02]
provides: [data-skill-manifests, skill-evaluation-evidence, recovery-matrix]
affects: [59, 60]
tech-stack:
  added: []
  patterns: [exact-tool-sequence, metadata-only-evidence, receipt-replay]
key-files:
  created:
    - apps/personal_intelligence_kernel/skills/data/knowledge-maintenance.md
    - apps/personal_intelligence_kernel/skills/data/warehouse-health.md
    - apps/personal_intelligence_kernel/skills/data/failed-batch-recovery.md
    - apps/personal_intelligence_kernel/skills/data/retrieval-rebuild.md
    - apps/personal_intelligence_kernel/skills/data/snapshot-release.md
    - tests/eval/test_pi_data_skills.py
    - tests/integration/test_pi_skill_recovery.py
    - ops/reports/evidence/pi-skill-evaluation.json
  modified:
    - governance/manifests/ai/pi-skills.json
requirements-completed: [PSKILL-01, PSKILL-02, PSKILL-03]
duration: 20 min
completed: 2026-08-05
---

# Phase 58 Plan 02: Data maintenance Skills and evaluation matrix

Registered five bounded data Skills for knowledge maintenance, warehouse
health, failed-batch recovery, retrieval rebuild and guarded snapshot release.
The manifests expose only the Phase 55–57 project capability IDs and encode
fixed inspect/preview/execute/verify sequences, stop conditions and recovery.

The evaluation matrix covers successful selection, no-match, collision,
denied-tool, timeout, cancel, crash-after-receipt and outcome-unknown resume
fixtures. Evidence is metadata-only and records exact sequences, side-effect
counts, authority fingerprints and honest checkpoint outcomes. Snapshot
release stops at the human confirmation boundary; no model output is accepted
as confirmation and no live pointer drill was performed.

## Verification

- `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill` — 50 passed.
- `python -m pytest tests/eval/test_pi_personal_skills.py tests/eval/test_pi_data_skills.py tests/integration/test_pi_skill_recovery.py -q` — 6 passed.
- Manifest load probe — 11/11 Skills loaded with exact instruction/checksum validation.

## Self-Check: PASSED

- Implementation commit: f0ec121
- Forbidden tool count: 0.
- Skipped L3 checkpoint count: 0.
- Ambient/provider/production pointer access: 0.
