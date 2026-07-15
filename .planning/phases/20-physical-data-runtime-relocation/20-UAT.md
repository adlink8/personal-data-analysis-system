# Phase 20 UAT — Data / Runtime Relocation

## Status

**Apply complete 2026-07-13** after user **全部批准**.

## Approval table

| Cohort | Manifest | Checksum verified | Apply | Operator | Date |
|--------|----------|-------------------|-------|----------|------|
| agent-google-imports | `governance/manifests/data/agent-google-imports.apply.json` | yes | **PASS** | user 全部批准 | 2026-07-13 |
| var | `governance/manifests/data/var.apply.json` | yes | **PASS** | user 全部批准 | 2026-07-13 |
| archive | `governance/manifests/data/archive.apply.json` | yes | **PASS** | user 全部批准 | 2026-07-13 |

### Apply notes

- First var attempt failed because journal lived under `var/runtime` (recreated target). Fixed journal root → `var/phase20-journals/`, cleaned stage/bak, re-applied successfully.
- Apply manifests use **non-overlapping top-level roots** (not nested preview ops).

## Post-apply verification

| Check | Result |
|-------|--------|
| `post_apply_verify.py` | **PASS** |
| SQLite integrity | **ok** |
| KU current count | **30774** |
| Active pointer | `knowledge_units_205bff9560b9_20260712142938` unchanged |
| AgentsView external | unchanged home path |
| Migration unit tests | **PASS** |
| phase19 default path tests | **PASS** (after eval-dir prefer private suite) |

## Rollback drill

| Cohort | Status |
|--------|--------|
| Full reverse of `_recycle` (4.5GB) | **Deferred** — journals retained under `var/phase20-journals/`; backups `*.bak-phase20` retained for compatibility window |
| Executor unit rollback | Covered by sandbox tests |

## Alias / backup removal

Defer ≥30 days or one release with old-path consumers=0 (see 20-05).
