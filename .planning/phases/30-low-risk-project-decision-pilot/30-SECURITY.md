---
phase: 30
slug: low-risk-project-decision-pilot
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: false
created: 2026-07-18
---

# Phase 30 — Security

> Retroactive STRIDE review of the independent low-risk project pilot authority.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|---|---|---|
| Analysis → Pilot | Read-only admission of one committed candidate | IDs, checksums, bounded options and evidence lineage |
| User → Pilot | Explicit decision/control authorization | hashed actor reference, exact case checksum, reason code |
| Codex operator → Pilot | Local compatibility action observation | bounded description and receipts; no command executor |
| Pilot → Personal/External | Active snapshot revalidation | snapshot IDs/hashes and policy reads only |
| Pilot → Product CLI | Metadata-only reconstruction | typed case/event/outcome/control JSON |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|---|---|---|---|---|---|
| T-30-01 | Spoofing | user decision/action attribution | mitigate | exact case checksum, actor class/hash, separate `codex_operator`, no raw identity claim | closed |
| T-30-02 | Tampering | SQLite authority and replay | mitigate | append-only triggers, FK constraints, canonical checksums, chain/sequence validation and full child replay checks | closed |
| T-30-03 | Repudiation | decisions and compensating controls | mitigate | stable event IDs, UTC time, expected sequence, idempotency key and target checksum | closed |
| T-30-04 | Information disclosure | case/event payloads and CLI | mitigate | typed bounded metadata, forbidden credential/command fields, metadata-only CLI and repository secret scan | closed |
| T-30-05 | Denial of service | payloads and fingerprint reads | mitigate | bounded field/list sizes, streaming file hashes, SQLite timeout and deterministic single-pass reads | closed |
| T-30-06 | Elevation of privilege | model candidate becoming decision/action | mitigate | recommendation remains non-authoritative; user decision is distinct; no connector/network/deployment surface | closed |
| T-30-07 | Source authority drift | Personal/External/Analysis lineage | mitigate | read-only SQLite access, complete Analysis envelope recomputation, active dual-snapshot validation and before/after fingerprints | closed |
| T-30-08 | Supply-chain change | runtime compatibility action | mitigate | no dependency install; existing Python/Node runtimes and lock/governance gates only | closed |

## Verification Evidence

- Offline Analysis run checksum and Pilot child deletion tamper tests fail closed.
- Cross-snapshot drift and acceptance-time active pointer drift fail closed.
- External-action-like descriptions are rejected before event publication.
- Phase 30 focused suite: 16 passed after review hardening.
- Governance preflight: secret scan, privacy, dependency and architecture gates PASS.
- Live acceptance: provider `0`, network `0`, system external actions `0`, unauthorized Knowledge writes `0`.

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|---|---:|---:|---:|---|
| 2026-07-18 | 8 | 8 | 0 | primary agent, inline retroactive STRIDE |

The audit ran inline because the available collaboration call cannot independently
prove a spawned agent's model identity; project policy restricts subagents to
`gpt-5.6-luna`. The configured security-auditor resolution was confirmed as
`gpt-5.6-luna`, but no unverifiable spawn was used.

## Sign-Off

- [x] All threats have a disposition
- [x] Accepted risks log reviewed
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set

**Approval:** verified 2026-07-18
