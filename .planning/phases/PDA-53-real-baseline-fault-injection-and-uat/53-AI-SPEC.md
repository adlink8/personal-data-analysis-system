# AI-SPEC — Phase 53: Real Baseline, Fault Injection and UAT

## Evaluation Contract

- Compare Pi and legacy on identical authorized cases, model, input checksum and budget.
- Dimensions: schema correctness, evidence grounding, task completion, Tool selection, latency, tokens/cost, recovery and user-rated usefulness.
- No aggregate claim when sample, budget or parity preconditions fail.
- LLM judge is optional and separately labeled; deterministic/human evidence cannot be impersonated.
- Personal outputs remain local; external tracing SaaS is prohibited.

## Activation Thresholds

Security/privacy/authority/replay are zero-tolerance. Quality and latency thresholds are preregistered. `proceed_canary` requires no critical regression, successful rollback drill and explicit user acceptance; otherwise revise/reject.
