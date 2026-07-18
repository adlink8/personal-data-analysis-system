# Phase 32: Unified Agent Read Surfaces - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-18
**Phase:** 32-unified-agent-read-surfaces
**Areas discussed:** Tool granularity and transport parity, Read integrity and privacy boundary, Analysis authority read model, Compatibility and response bounds

---

## Tool granularity and transport parity

| Option | Description | Selected |
|---|---|---|
| One intent per tool | Separate list/get/explain tools backed by shared services | ✓ |
| Broad operation tool | One tool dispatches multiple authority operations | |

**Choice:** One intent per tool.  
**Notes:** Auto-selected recommended Apps SDK pattern; all transports must remain semantically equivalent.

## Read integrity and privacy boundary

| Option | Description | Selected |
|---|---|---|
| Fail closed plus bounded metadata | Validate checksum/lineage and require explicit evidence drill-down | ✓ |
| Best-effort partial reads | Return available fields despite drift or incomplete records | |

**Choice:** Fail closed plus bounded metadata.  
**Notes:** Preserves existing authority and privacy invariants.

## Analysis authority read model

| Option | Description | Selected |
|---|---|---|
| First-class shared service | Centralize read/checksum semantics for all transports | ✓ |
| Transport-local SQL | Implement queries independently in REST and MCP | |

**Choice:** First-class shared service.  
**Notes:** Avoids contract drift and mirrors External/Pilot/Calibration patterns.

## Compatibility and response bounds

| Option | Description | Selected |
|---|---|---|
| Additive versioned contracts | Preserve existing tools and add bounded deterministic reads | ✓ |
| Replace legacy tools | Rename or remove old surfaces during Phase 32 | |

**Choice:** Additive versioned contracts.  
**Notes:** Phase 25–27 consumers remain compatible.

## the agent's Discretion

- Exact route path spelling and internal envelope helper location.
- Test fixture decomposition within the fixed zero-mutation and parity gates.

## Deferred Ideas

- Rich ChatGPT widget/dashboard.
