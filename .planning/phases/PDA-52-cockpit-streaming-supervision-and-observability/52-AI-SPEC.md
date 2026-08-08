# AI-SPEC — Phase 52: Cockpit Streaming, Supervision and Observability

The UI displays AI runtime truth; it does not evaluate or modify AI output. Pi events are projected through project-owned `pi_cockpit_event_v1`, never exposed as raw SDK events.

## Guardrails

- Same-origin Python gateway only; Kernel port is loopback internal.
- Raw prompts, completions, Tool arguments/results and provider bodies are excluded by schema.
- Cancel/resume preserves task version/idempotency and cannot bypass confirmation.
- UI status distinguishes queued/running/cancel_requested/cancelled/succeeded/failed/outcome_unknown/stale/offline.
- Supervisor readiness and UI runtime readiness are independently truthful.

## Evaluation

Schema parity, replay de-dup, accessibility, degraded states, privacy, no unauthorized writes and process ownership are blocking.
