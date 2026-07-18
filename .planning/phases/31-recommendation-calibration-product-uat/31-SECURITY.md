---
phase: 31
slug: recommendation-calibration-product-uat
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: false
created: 2026-07-18
---

# Phase 31 — Security

## Trust Boundaries

| Boundary | Data | Control |
|---|---|---|
| Pilot → Calibration | case/outcome IDs and checksums | read-only reconstruction |
| Personalized → Provider | bounded Personal context | exact allowlist and one-shot sandbox |
| Generic → Provider | external facts only | leakage scan and null Personal context |
| Provider → Calibration | structured response/receipt | strict schema and lineage checks |
| Verdict → Proposal | metrics and uncertainty | parent-bound candidate, no promotion |

## Threat Register

| ID | STRIDE | Threat | Mitigation | Status |
|---|---|---|---|---|
| T-31-01 | Information disclosure | Personal data leaks into generic arm | explicit forbidden fields, null context, canonical leakage tests | closed |
| T-31-02 | Tampering | protocol/results changed after observation | append-only SQLite, checksums, FK and immutable frozen protocol | closed |
| T-31-03 | Repudiation | provider call/receipt cannot be reconstructed | request/response/receipt checksums, blind labels and exact arm IDs | closed |
| T-31-04 | Denial of service/cost | replay causes another provider call | receipt lookup and checksum verification before provider invocation | closed |
| T-31-05 | Elevation | candidate proposal self-promotes | no promotion API, `auto_promote=false`, promotion counter 0 | closed |
| T-31-06 | Tampering | insufficient data becomes PASS | minimum evidence, missing/confounded/deviation rules and explicit FAIL thresholds | closed |
| T-31-07 | Information disclosure | credential or plugin access | ChatGPT login only, API keys removed, read-only sandbox, MCP/plugins/hooks disabled | closed |
| T-31-08 | Spoofing | arm identity biases scoring | frozen blind labels; arm mapping retained separately | closed |
| T-31-09 | Integrity | budget deviation hidden | provider-reported tokens preserved; deviation forces INCONCLUSIVE | closed |
| T-31-10 | Overclaim | correlation presented as causal gain | `causal_claim=false`; verdict remains INCONCLUSIVE | closed |

## Evidence

- 15 Phase 31 tests pass, including duplicate-call prevention, leakage, schema,
  small-sample, FAIL and proposal recovery paths.
- Two live GPT-5.4 calls: exactly one per arm, zero retries, zero cost.
- Governance secret/privacy/dependency/architecture gates PASS.
- Metadata acceptance reports no network, external action, source write or promotion.

## Accepted Risks

No accepted risks. The observed token-budget deviation is retained as verdict
evidence, not accepted as compliant behavior.

## Audit Trail

| Date | Total | Closed | Open | Reviewer |
|---|---:|---:|---:|---|
| 2026-07-18 | 10 | 10 | 0 | primary agent, inline retroactive STRIDE |

## Sign-Off

- [x] All threats have dispositions
- [x] `threats_open: 0`
- [x] Status verified

**Approval:** verified 2026-07-18
