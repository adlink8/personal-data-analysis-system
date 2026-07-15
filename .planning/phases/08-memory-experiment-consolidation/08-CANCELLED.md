---
phase: 08
status: cancelled
cancelled: 2026-07-12
reason: superseded_by_knowledge_unit_architecture
requirement: MEMX-01
---

# Phase 08 Cancelled

## Decision

**Do not execute Phase 08** (Memory Experiment Consolidation). The project’s authoritative personal-knowledge path is now:

- **Dialogue SSOT:** AgentsView → canonical conversations  
- **Knowledge SSOT:** `canonical_knowledge_units` + active KU index (Phase 14–15)  
- **Non-dialogue / Google:** raw events + light assertions (Phase 16), not memory_items  

Merging first-gen `memory_items` rules with Phase 07 graph experiments into a third long-term memory pipeline would recreate complexity the KU layer already replaced.

## What remains of Phase 08 artifacts

| Artifact | Treatment |
|---|---|
| `08-CONTEXT.md`, `08-NOTES-deferred-plan.md` | Historical only |
| `memory_items` / graph experiment tables | May remain for archaeology; **not** consumption SSOT |
| MEMX-01 | **Cancelled / wontfix** |

## Explicit non-actions

- No inventory→delete purge wave from Phase 08 plans  
- No automatic promotion of graph edges into memory_items  
- No new parallel memory store  

If experimental graph edges are ever needed again, they should attach as **evidence-adjacent analytics**, not as a competing SSOT to knowledge units.
