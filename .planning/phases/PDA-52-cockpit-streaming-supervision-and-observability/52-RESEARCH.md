# Phase 52 Research — Cockpit, Supervisor and Observability

## Findings

- Existing Cockpit already uses same-origin API, React Query, Zod and truthful degraded states; Pi UI should be an additive runtime surface, not a new app.
- Browser `EventSource` cannot set arbitrary auth headers. Same-origin Python endpoint should own authorization/proxy and emit sanitized events.
- Current supervisor has proven child ownership, bounded readiness and safe status projection. Kernel should be another explicit spec with port 8790 and `/ready`.
- Historical supervisor state is intentionally marked stale; Pi live task status must not falsely upgrade that section to current service ownership.

## Validation Architecture

- Python contract: SSE headers, origin policy, schema, safe errors and no-write on cross-origin.
- React component: reconnect/de-dup, cancel states, offline/stale/partial and keyboard/Esc/reduced-motion.
- Ops: Check/DryRun zero-write, owned child stop, unknown port preservation, restart budget.
- Privacy scan: DOM/console/API/log excludes seeded prompt/provider/credential/path literals.
