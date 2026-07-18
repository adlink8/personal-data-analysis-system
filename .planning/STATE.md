---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Agent Productization
status: verifying
last_updated: "2026-07-19T02:20:00Z"
last_activity: 2026-07-19
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# Project State

## Milestone

**v1.3 Agent Productization:** implementation complete; milestone verification in progress. Phases 32–35 expose v1.2 authorities to real REST/MCP/ChatGPT-compatible reads, add guarded decision orchestration, standardize Agent-readable UX, and prove live tunnel-backed MCP E2E while retaining zero automatic external execution and zero automatic promotion.

## Authoritative surfaces

| Layer | Path / surface |
|-------|----------------|
| Dialogue SSOT | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Knowledge SSOT | `canonical_knowledge_units` + **active** Chroma collection |
| Active KU (live) | **`knowledge_units_ir_4cd8af4ad_20260718054940`** — 32,181 vectors, exact collection checksum verified |
| Active serving snapshot | **`ss_5d816a6bf3ebd0bce9463236`** — 10/10 typed roles, Doctor critical_fail=0 |
| Watermark | matches current source checksum |
| Product CLI | `pk-sync`, `pk-ku` (inspect…promote, watermark, **reconcile**, **history**, **doctor**) |

## Phase 22 plan status

| Plan | Title | Status |
|------|-------|--------|
| **22-01** | Lifecycle reconcile dry-run + CLI (zero DELETE) | **done** — `pk-ku reconcile` |
| **22-02** | Growth-line history read | **done** — `pk-ku history` |
| **22-03** | Canary critical triage / label path | **done** (CLI + ops: strict PASS + promote) |
| **22-04** | Facade inventory + doctor + readiness gates | **done** — `pk-ku doctor`, `22-FACADE-INVENTORY.md` |

## Done (latest, 2026-07-17 Target A)

- pk-sync / pk-ku product packaging; incremental extract; publish additive; vector candidate
- LLM canary labeling; promote default require-eval; full inventory `--start` soft-ban
- **22-01/02:** lifecycle reconcile + growth-line history (never DELETE)
- **22-04:** `pk-ku doctor` read-only health; facade inventory (16 import lines / 10 files)
- Safe cleanup: bak-phase20 quarantined; readiness scorecard updated (~81 weighted)
- **Phase 23:** typed D/S/R/A registry, immutable composite snapshot, evidence drilldown, source versions/watermarks, fail-closed Doctor/Preflight
- Live Target A: snapshot `ss_5d816a6bf3ebd0bce9463236`; 10/10 roles; pointer parity clean; Doctor 10/10 critical
- **Phase 24-01:** evidence-aware support/abstain and snapshot-bound evaluation complete; private dev FP=0, eligible-positive retention=100%, 26 invalid legacy positives routed to human Gold review
- **Phase 24-02 review re-baseline:** explicit LLM provenance accepted without human impersonation; 45 cross-turn Gold, 50 grounded labels and independent 30x5 judge ratings pass strict evidence checks
- **Phase 24-03/04 closure:** evidence-aware final run `3a4b7f7b85e864b86031a79a0c017fa74c80e5b9908aa7fd73e765343fcc5d99` passes unchanged quality gates (+10.4478pp overall, +13.3333pp cross-turn); lifecycle has 6 append-only events and 2 applied manifests; activation/rollback/forward-restore UAT passes
- **Phase 25-01/02/03/04:** immutable snapshot-bound personal-state runs, typed current-state projection, deterministic changes/trends/risks, metadata-safe explanations, shared CLI/REST/MCP reads and zero-mutation metadata-only acceptance complete
- **Phase 26-01/02/03/04:** independent non-serving decision authority, deterministic abstaining recommendations, genesis-rooted confirmation/action streams, typed outcomes, non-causal effectiveness, shared read-only interfaces, guarded local writes and metadata-only acceptance complete
- **Phase 27-01:** independent non-serving proactive authority, seven immutable tables, exact Phase 25/26/frontier binding and deterministic eight-domain resource coordination complete
- **Phase 27-02:** deterministic evidence-bound importance/novelty, stable dedup/cooldown, quiet deferral and global/domain noise-budget evaluation complete
- **Phase 27-03:** user-owned append-only trust controls, deterministic scope/expiry projection, compensating restore and future-run control-frontier binding complete
- **Phase 27-04:** checksum-verifying proactive inbox/digest/explain/control-history reads, guarded local user writes, read-only REST/MCP and zero-mutation Target D technical acceptance complete; Product UAT passed
- **Phase 25–27 live adoption:** committed runs `psr_3a28363b9d1c6d9ab656fde5` → `dfr_e367f7689d64ad96a10311bd` → `pir_065c80888c81723abd43fc4a`; exact seven-event decision history, conservative insufficient-window assessment and proactive suppress/restore all verified

## Current Position

Phase: 35 (Runtime and Live E2E) — COMPLETE
Plan: 3 of 3
Status: Verified; milestone audit pending
Last activity: 2026-07-19

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-18)

**Core value:** Local, evidence-bound and uncertainty-aware personal decision support.
**Current focus:** v1.3 milestone audit and archive

## Cross-cutting architecture/data governance audit

- **2026-07-18 live closure:** Phase 24 strict review, final retrieval gate and lifecycle adoption pass; Active snapshot is `ss_5d816a6bf3ebd0bce9463236`. Phase 25–27 schemas are applied with one validated committed real run per phase. Technical blockers are empty and explicit Product UAT passed.

- **Corrected product vision and current status:** [`PERSONAL-DECISION-INTELLIGENCE-VISION-STATUS-2026-07-18.md`](./PERSONAL-DECISION-INTELLIGENCE-VISION-STATUS-2026-07-18.md) — final target is decision intelligence based on long-term personal data plus external environment, not a project-status Agent.
- **Authoritative issue inventory:** [`ARCHITECTURE-LAYERING-DATA-GOVERNANCE-AUDIT-2026-07-17.md`](./ARCHITECTURE-LAYERING-DATA-GOVERNANCE-AUDIT-2026-07-17.md)
- **Current expected-target gap:** [`TARGET-GAP-ANALYSIS-2026-07-18.md`](./TARGET-GAP-ANALYSIS-2026-07-18.md) — current authoritative distance analysis for PDI-T0..T4, Phase 24 blockers, External Context, LLM decision analysis and real outcome calibration.
- **Historical target-gap snapshot:** [`TARGET-GAP-ANALYSIS-2026-07-17.md`](./TARGET-GAP-ANALYSIS-2026-07-17.md) — retained for historical comparison only.
- Scope: D/S/R/A layer separation, SQLite/Chroma composite SSOT, inventory/watermark/lifecycle integrity, evaluation evidence, repository and runtime drift.
- Initial verdict: **gaps_found**. The audit found disabled SQLite FK enforcement, 18,859 FK violations, Delta Inventory FK mismatch, and unsafe incremental inspection/execution boundaries.
- **2026-07-17 remediation:** unified Full/Delta Inventory registry migrated with verified backup; FK violations are 0; knowledge write connections enforce FK; doctor and publish/promote gates fail closed; inspect defaults to committed watermark; execution lists are no longer preview-truncated; governance preflight is 12/12 PASS.
- No reconcile write, KU collection promotion, source-watermark advance, data delete, or compat/archive retirement was performed during remediation. Phase 23 registered the unchanged live collection as one validated composite serving authority.

## Completed product checkpoints

1. **Product UAT** — **PASSED 2026-07-18** by explicit user acceptance
2. ~~Phase 24 retrieval quality~~ **DONE** — +10.4478pp, positive CI lower bound
3. ~~Lifecycle adoption~~ **DONE** — 6 events, 2 applied manifests, reversible history
4. 2026-08-13: domains facade removal (optional follow-up; outside current release gate)

## Deferred Items

Items acknowledged at the v1.1 close audit on 2026-07-18. The GSD scanner
reported six historical UAT files because their status vocabulary predates the
current scanner; every file has zero open scenarios. Phase 17 and Phase 27 are
explicitly passed, and the remaining records are retained as historical
decision/compatibility evidence rather than active product blockers.

| Category | Item | Status |
|---|---|---|
| uat | Phase 14 `14-UAT.md` | acknowledged; zero open scenarios |
| uat | Phase 17 `17-UAT.md` | passed; zero open scenarios |
| uat | Phase 18 `18-ARCHIVE-UAT.md` | decisions recorded; zero open scenarios |
| uat | Phase 18 `18-MIGRATION-UAT.md` | approved empty manifest; zero open scenarios |
| uat | Phase 20 `20-UAT.md` | acknowledged compatibility record; zero open scenarios |
| uat | Phase 27 `27-UAT.md` | passed; zero open scenarios |

Phase 17 code complete; historical human checkpoints remain open and are
preserved as a separate governance record. Phase 24's authorized LLM review
does not rewrite or impersonate those Phase 17 human checkpoints.

Latest Phase 24 evidence: run `3a4b7f7b85e864b86031a79a0c017fa74c80e5b9908aa7fd73e765343fcc5d99` has 67 real scoreable Gold and 45 real cross-turn Gold. Review, safety, citation, reconcile, latency, grounded precision and both retrieval-improvement confidence gates pass.

## Verification snapshot

```powershell
$env:PYTHONPATH="D:\ADLINK\数据分析\src"
python -m personal_knowledge.application.knowledge.doctor_ku --json
python -m personal_knowledge.intelligence.proactive.cli acceptance --dry-run --metadata-only --json
python -m pytest -q
python -m personal_knowledge.governance.preflight
```

## Accumulated Context

### Roadmap Evolution

- Phase 23 added: Target A composite SSOT snapshot integrity
- Phase 24 added: Target B/C evaluation closure and lifecycle adoption
- Phase 25 added: Target D personal state and change intelligence
- Phase 26 added: Target D decision/action feedback loop
- Phase 27 added: Target D proactive multi-domain acceptance

## Operator Next Steps

- Audit and archive v1.3 Agent Productization.
- Define a fresh requirements set only when a next milestone is authorized.
