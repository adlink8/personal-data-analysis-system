# Phase 28 UAT

**Status:** PASSED  
**Accepted:** 2026-07-18  
**User decision:** “验收通过”

## Real bounded cohort

| Source | Bounded facts | Official evidence |
|---|---|---|
| Python Software Foundation | Python `3.14.2`, final, released `2025-12-05` | https://www.python.org/downloads/release/python-3142/ |
| OpenJS Foundation / Node.js | Node.js `24.13.0`, LTS `Krypton`, released `2026-01-13` | https://nodejs.org/en/blog/release/v24.13.0 |

The cohort retained six structured facts and two bounded observations. No page,
article, changelog, or release-note body was persisted.

## Reversible authority sequence

| Step | Immutable evidence | Result |
|---|---|---|
| Python run | `eir_a3264b2a6038695c7166858a` | published |
| Node.js run | `eir_f6a617ec709aa5dca3c5a003` | published |
| Snapshot A | `exs_9b9c0fb0669fa2907d344757` / `59fd11c850a239b0239dde2c1b302aefaecf2ec6411dedc9e84922796711b72c` | validated and activated |
| Snapshot B | `exs_341722a70977ec446c62269f` / `33167fbda0c192595cb08b79779ed059133a945549f5ac01ed8cf3c1fa082a95` | validated and activated |
| Rollback | target Snapshot A | written |
| Forward restore | target Snapshot B | written |

Final authority sequence is `4`, the final active authority is Snapshot B, the
eight-event chain head is
`6eec7ce49d7bf5c4a14dc565ffd53733acae2b4c5828165296ee779df8a52ee5`,
and the external authority fingerprint is
`95244c16d0132d61510b7c4f3f9d4214ac426b2b1a628ff87354492f586958f6`.

## Acceptance observations

- Doctor: 10/10 critical checks passed on the healthy cohort.
- Transaction failure after the authority insert rolled back without changing
  Personal or External authority.
- Personal-authority sentinel checksum was identical before and after UAT.
- Metadata-only privacy counters: raw bodies `0`, personal writes `0`, external
  Doctor writes `0`.
- User explicitly accepted the evidence on 2026-07-18.

Open scenarios: **0**.
