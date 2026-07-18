---
phase: 30-low-risk-project-decision-pilot
status: passed
verified: 2026-07-18
requirements: [PDI-07]
---

# Phase 30 Verification

## Verdict

PDI-07 is satisfied by one real complete project chain plus one real defer
control path. All records are append-only and checksum chained. Personal,
External, Analysis and Knowledge fingerprints are unchanged by acceptance
reads; provider, network and system external-action counters are zero.

## Exact real chain

| Item | Immutable evidence |
|---|---|
| Analysis run | `dar_77843392b266cd0a992cc274` |
| Analysis candidate | `dac_8abee23d30d7df2c9df47ab7` |
| Main case | `ppc_3c81da35094e5260d022f1ef` / `3c81da35094e5260d022f1efa545812b604f48f06080403f6f18e81313bf9957` |
| Recommendation | `ppr_bbbb25bdeb48c53ea416ad0c` / `opt_validate_then_adopt` |
| Preregistered protocol | `ppe_a3862801f8f8894687082299` |
| User-authorized accept | `ppe_f6775141cafed1cc61c842e1` |
| Codex local action start | `ppe_86a0d1546eb01a22a332d03e` |
| Codex local action complete | `ppe_d574b126204a5df1ae849116` |
| Outcome observation | `ppe_cb8d9c18e486785ca9a8fcfc` / checksum `4c0d592611219bf3606e99351e1f2eda29be5f92826457af254ea6b9425a05b1` |
| Assessment | non-causal `pass`; value `1.0`, target `1.0`, complete window, no confounders |

The protocol froze metric, unit, baseline, target, direction, window, source,
estimated time and cost before the action. The observation separately records
actual time/cost, completion, quality, satisfaction, side effects, regret and
confounders.

## Control and recovery proof

| Control | Immutable evidence |
|---|---|
| Direct-adoption control case | `ppc_b62f0f3506ca07a074c9ed54` |
| Explicit defer | `ppe_01e1bd75910bb130dffb125e` |
| Correction | `ppe_c2b1f4277dc883408ce508f6` |
| Decision revoke | `ppe_3814de5b6cb9d0f0fee09487` |
| Decision restore | `ppe_b5484b02c66cbe7bd386b233` |
| Pilot snapshot rollback | `ppe_93747ed90dd1f66f6ddfd5ef` |
| Exact forward restore | `ppe_7a97d56230c687d21cb12e6f` |

The rollback changes only the pilot projection to `UNBOUND`; it does not switch
the External or Personal source authority. Forward restore revalidates both
active source pointers and restores the exact frozen binding. Final projection
is `BOUND`, the revoked decision is restored and prior history is unchanged.

## Side-effect acceptance

Live metadata-only acceptance returned:

- schema state `applied`, integrity `ok`, FK violations `0`, append-only triggers `8`;
- main case events `11`, control case events `2`;
- Knowledge, Personal, External, Analysis and Pilot fingerprints identical before/after;
- provider calls `0`, network calls `0`, system external actions `0`;
- unauthorized Knowledge writes `0`.

## Automated verification

- Phase 30 focused suite: `13 passed`.
- Governance preflight: `13/13 PASS`.
- Runtime receipts: Python `3.14.2`, Node.js `v24.13.0`.
- Dependency gate: no dependency install performed.
- `git diff --check`: PASS.

## Open findings

None.
