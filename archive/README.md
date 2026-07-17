# archive/ — Phase 20 archival roots

## Responsibility

Quarantined historical material retained for audit and recovery.

## Boundaries

Archive content is not an import source, test root, or runtime dependency. Moving
or deleting it requires an exact manifest, retention review, and approval.

## Entry points

Use governance inventory and disposition tooling for metadata inspection;
restore only through an approved recovery procedure.

## I/O and privacy

Archived private bodies remain private. Governance scans are metadata-only and
must not copy archive contents into reports or logs.

## Tests

Archive classification, retention, and migration safety are covered under
`tests/governance/`.

## Ownership

Owner: platform. Status: quarantined.

| Path | Content |
|------|---------|
| `quarantine/_recycle/` | Soft-deleted project history (was root `_recycle/`) |
| `planning/.gsd/` | Historical GSD planning (read-only) |
| `vendor-reference/.ai-bridge/` | Vendored bridge reference material |

Not an import source, not a test root, not a runtime dependency.

## Quarantine (2026-07-16)

Phase 20 recovery backups that previously lived as sibling `*.bak-phase20` trees
(repo root + `integration/*`) were **moved** (not deleted) to:

`archive/quarantine/bak-phase20-20260716/`

Tracked summary: `.planning/cleanup/2026-07-16-safe-cleanup.md`.  
Physical delete of quarantine still requires owner + retention journal.

## Quarantine notes

- 2026-07-16: Phase 20 `*.bak-phase20` trees moved to `quarantine/bak-phase20-20260716/` (see tracked log `.planning/cleanup/2026-07-16-safe-cleanup.md`).

