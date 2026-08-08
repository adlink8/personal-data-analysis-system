# Phase 50 Research — Task, Tool Bridge and Isolation

## Findings

- Existing `GuardedOrchestrationInterface` already owns confirmation semantics; Pi Tool wrappers should delegate, not reproduce tokens/HMAC in Node.
- Spike 002 validates exact replay, concurrent claim, cancel and outcome_unknown in synthetic SQLite. Production needs migrations, lease recovery and cross-process HTTP failure injection.
- Candidate and Session separation is an authority invariant, not merely different tables. Separate files permit fingerprint and permission tests.
- Domain Gateway should expose operation IDs and JSON schemas; dynamic import/SQL/path parameters are unnecessary and unsafe.

## Validation Architecture

- Python unit: gateway operation registry, safe errors, read/write guard.
- Node unit: task transition graph, lease, cancel, idempotency, session/candidate repositories.
- Cross-process: kill before/after Domain response, duplicate claim, dropped response, restart, exact replay.
- Fingerprint: all live authority DBs and pointers unchanged under every failure fixture.
