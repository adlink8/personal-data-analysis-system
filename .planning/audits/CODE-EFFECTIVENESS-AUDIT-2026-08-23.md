# Code effectiveness audit — 2026-08-23

## Verdict

The active product path is the current `src/` package plus the REST, Pi Kernel,
Node MCP and optional Tunnel stack. The repository also contains supported
compatibility surfaces, frozen-but-retained source, historical planning and
private quarantine; those categories must not be deleted as one undifferentiated
"old content" cohort.

## Runtime evidence

| Surface | Live result | Disposition |
|---|---|---|
| `pk-sync`, `pk-ku`, `rag-search` | Console entry points resolve to this checkout's `src/personal_knowledge/cli.py`; help succeeds | KEEP |
| `rag-pipeline` | Exits 2 with the canonical `pk-sync` / `pk-ku` redirect | KEEP retired guard only |
| REST :8000, Pi Kernel :8790, MCP :8789 | Bounded no-Tunnel stack start returned 200 readiness for all three | KEEP |
| Tunnel :8081 | Not exercised because the required control-plane credential was absent | UNVERIFIED external boundary |
| `/app/knowledge`, `/ui/overview` | Live REST returned 404 | FROZEN |
| `/ui/topics` | Live REST returned 200 | KEEP |
| KU/Chroma | Doctor exit 1: collection listing unavailable and source watermark drift; inspect reports 34,941 new refs | BLOCKED data-health repair |

## Repository cohorts

| Cohort | Evidence | Decision |
|---|---|---|
| `integration/scripts/governance` | CI/preflight imports and executes it | KEEP |
| `src/personal_knowledge/domains` | 66 Python files, all re-export-only; no application imports, but external consumers are unknown | RETAIN compatibility until explicit external retirement |
| Internal `domains` imports | 162 references across evaluation/tests/forensics before cleanup | RETIRE by direct canonical imports |
| `tools/compat/v1_1` | 78 valid shims; consumer telemetry explicitly unknown; review date 2026-10-01 | KEEP |
| `apps/personal_decision_cockpit` | Production route frozen; source, tests and build remain intentionally retained | KEEP frozen source |
| `archive/legacy-pipeline` | No import, test-root or runtime dependency; exact bytes preserved on history branch | RETIRE from active branch |
| `.planning` | Governance preflight treats it as authoritative and many current docs cross-reference verification records | KEEP; repair stale current-state pages |
| `.migration-backup*`, `tmp` | Ignored local recovery/diagnostic artifacts, not runtime dependencies | QUARANTINE intact |
| `archive/phase62` and other private archive | 8+ GB ignored retention evidence; Git branches do not preserve it | KEEP pending retention review |

## Recovery points

- Tracked pre-cleanup snapshot: `codex/archive-pre-cleanup-20260823` at
  `a52e30b779a0ac35d26f76c2660c31c9f26f241e`.
- Active cleanup branch: `codex/cleanup-effective-main`.
- Ignored local files moved intact to
  `archive/quarantine/pre-main-cleanup-20260823/` with a local manifest.

No private archive body, active database, canonical data, KU row, collection,
watermark or remote branch was deleted or modified by this cleanup.
