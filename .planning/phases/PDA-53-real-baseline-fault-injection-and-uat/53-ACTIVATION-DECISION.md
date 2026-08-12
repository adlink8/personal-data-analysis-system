# Phase 53 Activation Decision

**Decision: proceed_shadow (candidate)**

The real authorized paired baseline was re-executed against a newly frozen protocol aligned with the actually-used provider (`openai-compatible` / `deepseek-v4-flash`). Both arms of both cohort members produced schema-valid 7-key responses (verified by the frozen response contract in `calibration/paired.py`), so the previous `arm_response_schema_invalid` blocker is resolved and the executed sample meets the protocol minimum (`member_count=2 >= minimum_evidence=2`). Evidence is recorded in [`ops/reports/evidence/pi-phase53-real-paired-baseline.json`](../../../ops/reports/evidence/pi-phase53-real-paired-baseline.json) and passes `evaluate_pi_kernel.py --check-real-receipts` with `status=PASS`.

Facts recorded before execution: preregistration `governance/manifests/ai/pi-baseline-preregistration.json` (evidence_class=`real_authorized_paired_baseline`, model=`deepseek-v4-flash`, timeout=120s, max_output_tokens=2048, cost_ceiling=30 CNY, 2 authorized real cases, preregistration_checksum=`1872180191f8882264f93660aed6a25ce6d712d67cc8e9eb03829598ccef501a`).

Execution facts: 4 provider calls (2 members x 2 arms, one call per arm, no retry), total `0.010219 CNY` (under the 30 CNY ceiling), raw response bodies not committed, authority mutations `0`. The `calibration_measurements` rows are checksum-protected and schema validation was enforced at insert time by `execute_frozen_arm`.

No canary or primary switch is authorized in this phase (D-06). The decision is a `proceed_shadow` **candidate** for the Phase 54 activation step; `governance/manifests/ai/pi-runtime-policy.json` still records `phase53_decision: "revise"` and must be updated by the operator before any shadow activation is prepared.
