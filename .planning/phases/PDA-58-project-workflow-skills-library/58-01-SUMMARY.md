---
phase: 58
plan: 01
subsystem: skill-engine
tags: [skills, state-machine, receipts, checkpoint, deterministic-selection]
requires: [55-02, 57-02]
provides: [pi-project-skill-v1, skill-engine, personal-skill-manifests]
affects: [58-02, Phase 59, Phase 60]
tech-stack:
  added: []
  patterns: [declarative-step-graph, zero-or-one-selection, receipt-resume]
key-files:
  created:
    - apps/personal_intelligence_kernel/src/skills/engine.mjs
    - governance/schemas/pi-project-skill-v1.schema.json
    - apps/personal_intelligence_kernel/test/skill-engine.test.mjs
    - apps/personal_intelligence_kernel/skills/personal/daily-brief.md
    - apps/personal_intelligence_kernel/skills/personal/knowledge-research.md
    - apps/personal_intelligence_kernel/skills/personal/decision-support.md
    - apps/personal_intelligence_kernel/skills/personal/project-planning.md
    - apps/personal_intelligence_kernel/skills/personal/outcome-reflection.md
    - apps/personal_intelligence_kernel/skills/personal/system-diagnosis.md
    - tests/eval/test_pi_personal_skills.py
  modified:
    - apps/personal_intelligence_kernel/src/skills/registry.mjs
    - apps/personal_intelligence_kernel/test/skill-registry.test.mjs
    - governance/manifests/ai/pi-skills.json
requirements-completed: [PSKILL-01, PSKILL-02, PSKILL-03]
duration: 30 min
completed: 2026-08-05
---

# Phase 58 Plan 01: Skill engine and personal intelligence Skills

Replaced the thin selector with a strict `pi-project-skill-v1` registry and a
declarative Skill engine. Manifests carry version/checksum, profile/privacy,
allowed Tools, instruction checksum, bounded steps/rounds/budget/timeout, stop
conditions, recovery policy and expiry. The engine never executes manifest
text as code; every declared step receives a correlation ID, idempotency key
and receipt.

Execution states are `pending`, `running`, `waiting_confirmation`,
`completed`, `failed`, `cancelled` and `outcome_unknown`. Resume consumes the
last committed/reconciled receipt and does not repeat the side effect. L3
snapshot steps cannot run until explicit confirmation is present; after an L3
step commits, the engine pauses again before any subsequent step.

Six personal intelligence Skills and their instruction files are registered;
the manifest also carries the coordinated data Skill declarations that are
evaluated in Plan 02.

## Verification

- `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill` — 50 passed.
- Python personal/data/evidence Skill eval — 6 passed.
- Manifest load probe — 11/11 Skills loaded with exact checksums.

## Deviations from Plan

- [Rule 1 - Registry coordination] The single `pi-skills.json` SSOT contains all
  11 personal and data declarations in this commit so checksums and allowed
  Tools cannot drift between the two waves. Data instruction/evidence and
  recovery verification remain in Plan 02.

**Total deviations:** 1 coordination deviation. **Impact:** no additional
authority; data Skills remain bounded until their evaluation evidence passes.

## Self-Check: PASSED

- Implementation commit: pending (recorded after batch commit)
- Synthetic containment remains ambient-Skill-free.
- Ready for Phase 58 Plan 02.
