---
phase: 33
slug: guarded-decision-orchestration
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-19
---

# Phase 33 — Security

## Threat Register

| Threat ID | Category | Component | Mitigation | Status |
|---|---|---|---|---|
| T-33-01 | Spoofing | Actor identity | Exact 64-character lowercase SHA-256 actor identity is bound into session, preview, capability and event | closed |
| T-33-02 | Tampering | Preview/capability | HMAC binds session, operation, checksum, actor, sequence and expiry | closed |
| T-33-03 | Replay | Provider and writes | Reservation-before-call, single-use confirmation digest and idempotent immutable replay | closed |
| T-33-04 | Elevation | Domain/risk | Only project/low-risk requests pass; forbidden action domains fail before mutation | closed |
| T-33-05 | External side effect | Pilot bridge | Actions are user-reported only; URLs, deployment, messaging and purchasing are rejected | closed |
| T-33-06 | Information disclosure | Transports/logs | Capabilities remain server-side; legacy token fields are redacted from stdio logs | closed |
| T-33-07 | Integrity | Authority bridges | Binding, sequence, state and confirmation are authorized before every downstream write | closed |
| T-33-08 | Misrepresentation | Calibration | `causal_claim=false`, `promotion_available=false`; no automatic promotion path | closed |

## Accepted Risks

None.

## Evidence

- Append-only schema triggers and checksum-chain corruption tests.
- Expired, drifted, consumed, stale and illegal requests fail closed.
- Provider replay count remains one; reserved unknown outcome is never retried.
- Authority fingerprints remain unchanged on rejected high-risk and expired requests.
- ChatGPT annotations are non-destructive/idempotent/closed-world and mutations are not marked read-only.

**Approval:** verified 2026-07-19; `threats_open: 0`.
