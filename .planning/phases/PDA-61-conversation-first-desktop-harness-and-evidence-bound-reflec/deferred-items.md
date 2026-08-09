# Deferred Items (Phase 61)

Out-of-scope discoveries logged during Plan 61-06 Task 2 execution (2026-08-09).
These are pre-existing failures NOT caused by Plan 61-06 changes and are left untouched.

| Item | Where observed | Why out of scope | Action |
|------|----------------|------------------|--------|
| `capability-registry.test.mjs` "production capability registry loads the approved project surface" fails: expects 44 operations, `governance/manifests/capabilities/project-capabilities.json` contains 45 | `node --test test/capability-registry.test.mjs` (also fails at HEAD f710926) | Manifest count drifted outside Plan 61-06 (events/reflection seam). No event/delta source was added to the capability registry. | Deferred to a governance/wave owner; do not fix inside 61-06. |
| `skill-warehouse-e2e.test.mjs` "real Pi Skill -> domain tool -> isolated SQLite write -> verification" fails with `domain_test_server_unavailable:fetch failed` | `node --test test/skill-warehouse-e2e.test.mjs` | Requires a live Python domain test authority on the loopback; not available in this environment. Pre-existing, environmental. | Re-run when the Python domain fixture server is present. |
