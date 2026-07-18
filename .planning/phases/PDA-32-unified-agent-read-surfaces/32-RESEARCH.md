# Phase 32 Research: Unified Agent Read Surfaces

**Researched:** 2026-07-18
**Status:** Complete

## Current implementation

- `ExternalContextService` already supplies a schema-versioned metadata-only envelope for active snapshot and fact list/get, including lifecycle and checksum drift rejection.
- Pilot reads already verify payload checksums and event chains through `get_case`, `list_cases`, `history`, `controls` and `explain`, but return raw domain dictionaries rather than the shared transport envelope.
- Calibration `explain` already reads all protocol tables and preserves `causal_claim=false`, `promotion_available=false` and `external_action_available=false`; it needs bounded list/get semantics and typed errors.
- Analysis is the only v1.2 authority without a public read service. `analysis/doctor.py` already traverses runs, candidates, claims, evidence refs, receipts and events and validates most integrity rules.
- Existing Phase 25–27 interfaces establish the preferred pattern: shared service contract → thin REST adapter → thin stdio MCP adapter with contract parity and zero-mutation tests.
- ChatGPT reaches the Node HTTP MCP adapter, which currently proxies local REST and accurately annotates its existing tools as read-only.

## Recommended implementation

1. Add a common bounded read envelope/helper and a first-class `AnalysisReadService`; extend or wrap External/Pilot/Calibration reads to expose list/get/explain with stable error codes.
2. Add additive `/agent/...` REST routes and matching stdio MCP tools. Both transports invoke exactly the same Python service dispatch.
3. Add matching Node HTTP MCP descriptors/handlers that proxy REST. Keep one intent per tool and accurate read-only annotations.
4. Verify semantic parity, hard limits, deterministic ordering, checksum/lineage tamper failure, privacy filtering and byte-for-byte authority fingerprints before/after reads.

## Test strategy

- Unit tests: each authority service happy path, bounds, not-found, malformed JSON and checksum drift.
- Contract tests: REST helper and stdio MCP helper return equivalent schema-versioned payloads for the same fixture.
- Node tests: tool descriptors, annotations, schemas, REST path/query mapping and response forwarding.
- Integration acceptance: fingerprint all four authority DBs, execute all public list/get/explain reads, assert unchanged and provider/network/action/promotion counters remain zero.

## Validation Architecture

- Existing `pytest` and Node `node:test` infrastructure is sufficient; no dependency or Wave 0 framework setup is needed.
- Each task has a targeted automated command with expected feedback below 60 seconds on fixtures.
- Each wave ends with its complete targeted suite; Phase completion runs Python service/integration/contract tests plus Node descriptor tests.
- Security-critical assertions are checksum fail-closed behavior, privacy-field exclusion, truthful MCP annotations and unchanged authority fingerprints.
- No behavior in Phase 32 requires manual-only verification; real ChatGPT connectivity is deliberately Phase 35.

## Risks and mitigations

- **Context bloat:** enforce item and evidence limits; return receipt/request/response checksums rather than bodies.
- **Transport drift:** one Python dispatch contract plus fixed Node route mapping snapshots.
- **Legacy regression:** only additive names/routes and targeted existing contract suites.
- **False success on corruption:** service reads fail closed before constructing success envelopes.

## Official guidance applied

OpenAI Apps SDK guidance favors clear single-purpose tools, accurate safety annotations, concise structured data and a server-owned authorization/data boundary. Phase 32 therefore stays tool-only and read-only; orchestration writes remain Phase 33.

## RESEARCH COMPLETE
