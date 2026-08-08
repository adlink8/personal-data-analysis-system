# AI-SPEC — Phase 49: Pi Kernel Host and Event Lifecycle

**Selected Framework:** `@earendil-works/pi-coding-agent` 0.83.0 accepted baseline from Phase 48.  
**System Type:** event-driven Agent runtime host.  
**Provider budget:** 0 real calls in Phase 49.

## Contract

- One Host owns AgentSession construction and event projection; no second control loop.
- `pi_kernel_event_v1` is deterministic metadata, never model prose or personal body.
- Readiness requires accepted package decision, exact resource registry and healthy event journal.
- Unknown event/tool/resource/schema is blocking; no best-effort coercion.
- Session/model/tool events are normalized to project-owned types so later Pi upgrades do not leak SDK-private shapes into Python/UI contracts.

## Evaluation

| Dimension | Pass condition |
|---|---|
| Determinism | same input → same event_id/idempotency result |
| Durability | restart and cursor replay preserve exact sequence |
| Privacy | no inline body/credential/path in journal/SSE/error |
| Isolation | authority fingerprints unchanged |
| Lifecycle | loopback-only, bounded shutdown, no orphan process |

## Guardrails

- No Provider adapter or real prompt in this phase.
- Event payload inline objects are rejected; only typed refs/checksums allowed.
- Journal corruption, schema drift or package decision expiry makes `/ready` fail.
- Every SDK upgrade re-runs Phase 48 and event compatibility tests.
