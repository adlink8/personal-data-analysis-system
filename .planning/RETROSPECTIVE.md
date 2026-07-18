# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.2 — External Context & Low-risk Decision Intelligence Pilot

**Shipped:** 2026-07-18
**Phases:** 4 | **Plans:** 14 | **Tasks:** 10

### What Was Built

- An independent append-only External Context Authority with reversible snapshots and exact dual-context binding.
- A strict evidence-bound LLM analysis candidate path with deterministic privacy, conflict, injection and risk gates.
- A real low-risk project decision/action/outcome chain plus a defer control path and compensating recovery.
- A preregistered personalized/generic comparison with immutable receipts, honest INCONCLUSIVE semantics and no auto-promotion.

### What Worked

- Exact IDs, checksums and source fingerprints made Phase 28→31 lineage independently reconstructable.
- One-shot provider budgets, deterministic gates and explicit zero-side-effect acceptance kept LLM work bounded.
- Deep code review caught duplicate-call, schema-validation and FAIL-path defects before closeout.
- Treating INCONCLUSIVE as a successful scientific boundary prevented an unsupported product claim.

### What Was Inefficient

- Historical UAT status vocabularies caused false open-artifact findings and required metadata normalization.
- The Phase 28 rehearsal UAT and later live cross-phase snapshot were not clearly distinguished until milestone audit.
- Initial Phase 31 token budgets were lower than the provider-reported context usage, forcing a protocol deviation.

### Patterns Established

- Preregister before provider invocation or action observation.
- Keep model output non-authoritative; publish only after deterministic evidence and safety gates.
- Store compensating events instead of mutating historical decisions, outcomes or proposals.
- Bind every downstream artifact to exact upstream IDs and checksums, then fingerprint sources before and after acceptance.

### Key Lessons

1. A minimum-evidence rule is useful only if insufficient evidence mechanically forces INCONCLUSIVE.
2. Generic-arm privacy requires an explicit null Personal context plus leakage tests, not prompt wording alone.
3. Provider-reported token accounting belongs in the frozen protocol when local estimates can diverge.
4. Rehearsal and live evidence need distinct labels even when both are valid UAT artifacts.

### Cost Observations

- Provider usage: three bounded real `gpt-5.4` tasks across Phases 29 and 31; Phase 31 used exactly two calls, zero retries and zero billed cost.
- Subagents: only configured `gpt-5.6-luna` routing was used for cross-phase integration audit.
- Notable: deterministic replay and focused test suites avoided repeat provider calls during review.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Key Change |
|---|---:|---|
| v1.1 | 27 | Established composite SSOT, lifecycle and internal intelligence authorities |
| v1.2 | 4 | Added external authority, bounded LLM decisions and honest paired calibration |

### Cumulative Quality

| Milestone | Audit | Requirements | Key verification |
|---|---|---:|---|
| v1.1 | passed | 17/17 | 70 focused integration tests |
| v1.2 | passed | 8/8 | 52 cross-phase tests plus per-phase suites |

### Top Lessons (Verified Across Milestones)

1. Immutable lineage and reversible events are more reliable than in-place state correction.
2. User authority and deterministic gates must remain outside model output.
