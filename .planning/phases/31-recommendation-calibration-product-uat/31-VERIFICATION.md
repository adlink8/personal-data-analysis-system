---
phase: 31-recommendation-calibration-product-uat
status: passed
milestone_verdict: INCONCLUSIVE
verified: 2026-07-18
requirements: [PDI-08]
---

# Phase 31 Verification

## Verdict

PDI-08 is technically complete and reconstructable. Product-boundary acceptance
passes, while comparative effectiveness remains **INCONCLUSIVE** by the frozen
rules. No personalized gain or causal benefit is claimed.

## Immutable evidence

| Layer | ID / checksum |
|---|---|
| Protocol | `calp_2dc7078cfc7fec88a75826b0` / `2dc7078cfc7fec88a75826b0ceb593bb99d62fdecc8fed96edbdbb22d3ec44e0` |
| Cohort member | `calm_0978e9a606257316254bb2ad`, exact Phase 30 case/outcome |
| Personalized arm | `cala_49fce560acbd91a3421e7501` / response `fd871ae48b3fc8f8977976def88a3c562c5bda9454f182f64ceef69d22660fde` |
| Generic arm | `cala_eec33f90bf2c602f9e46c185` / response `8d15d48e4c2ecd49047f9974e41446c7101fde28b58c024cef0c342a137d2eb4` |
| Verdict | `calv_3aab06de0c879656707f55f7` / `3aab06de0c879656707f55f74080e44329a26d4a73e737768b5dfa84b7afa5ef` |
| Proposal | `calpr_8951a15495de0d5075d78e78` / `8951a15495de0d5075d78e78dfcf291b0def7fe6169defc3f6a5c9ccd7cc7b44` |

## Paired result

- Personalized: candidate to adopt the validated local runtime; confidence 0.91.
- Generic: abstain because no project compatibility evidence was available; confidence 0.94.
- Same provider/model/schema/temperature and frozen external context; only Personal context differs.
- Actual input tokens were 18,567 versus 18,515, exceeding the frozen 12,000 budget.
- Cohort size is 1 versus minimum evidence 2; generic real action/outcome metrics are missing.

Reason codes: `sample_below_minimum`, `missing_measurements`,
`protocol_deviation`. `causal_claim=false`.

## Proposal controls

Candidate proposes cohort size 4, provider-reported budget accounting and a
40,000-token per-arm ceiling against parent `calibration-paired-v1`. It was not
promoted. Reject `calpr_11f689605880bd510c3753c4`, rollback
`calpr_333a823a87935ae48e690d13` and forward restore
`calpr_2e17871c7f275a7805e85b1b` all target the exact proposal checksum.

## Acceptance

- Calibration schema: integrity `ok`, FK violations 0, append-only triggers 14.
- Phase 31 suite: 15 passed after deep-review hardening.
- Metadata-only acceptance: unchanged source/calibration fingerprints.
- Provider/network/external-action/source-write/promotion counters during acceptance: 0.
- Governance preflight and `git diff --check`: PASS.

## Open technical findings

None. The `INCONCLUSIVE` verdict is an intended scientific result, not an open
implementation defect.
