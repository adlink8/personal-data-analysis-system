---
phase: 32
slug: unified-agent-read-surfaces
status: verified
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: 2026-07-18
---

# Phase 32 — Security

> Per-phase security contract for the unified Agent read surfaces.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| SQLite authorities → shared service | Four immutable Phase 28-31 stores are opened in read-only/query-only mode | Verified metadata, checksums, stable IDs |
| Shared service → REST/stdio MCP | Thin adapters delegate to one normalized operation map | Versioned success/error envelopes |
| REST → ChatGPT HTTP MCP | Fixed loopback GET routes produce compact model-facing results | Bounded metadata, IDs, limitations |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-32-01 | Tampering | Authority readers | mitigate | Checksum/lineage verification fails closed; tamper unit test passes | closed |
| T-32-02 | Information disclosure | Service and model context | mitigate | Metadata-only privacy envelope, omitted list bodies, 48 KB drill-down cap, no provider bodies | closed |
| T-32-03 | Tampering / spoofing | REST, stdio MCP, Node proxy | mitigate | Shared dispatch parity, fixed route map, typed REST error propagation | closed |
| T-32-04 | Elevation / side effects | SQLite and transport handlers | mitigate | `mode=ro`, `query_only`, GET-only tools, pre/post live SHA-256 fingerprints | closed |
| T-32-05 | Repudiation / contract mismatch | MCP descriptors | mitigate | Strict inputs and tested read-only, non-destructive, idempotent, closed-world annotations | closed |

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 5 | 5 | 0 | Codex inline security auditor |

## Verification Evidence

- `tests/unit/test_agent_read_services.py`: corrupt analysis checksum fails closed.
- `tests/integration/test_agent_read_authority_integrity.py`: privacy, no-write, causal and no-promotion assertions.
- `tests/contract/test_agent_read_interfaces.py`: REST/stdio MCP semantic parity.
- `tests/contract/test_agent_read_end_to_end.py`: live four-database SHA-256 fingerprints unchanged.
- `apps/personal_data_chatgpt/test/agent-read-tools.test.mjs`: strict schemas, annotations, payload budget and typed errors.

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-18
