# Phase 62: Multi-format conversation adapters, unified event authority, and replaceable extraction views - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-12
**Phase:** 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
**Areas discussed:** extraction granularity, unified fact boundary, adapter coverage, raw retention, canonical reuse, activation, semantic gating

---

## Adapter coverage

| Option | Description | Selected |
|--------|-------------|----------|
| Major families first | Cover the highest-volume/most-structured families and fail closed for the rest | |
| All observed families | Cover all 17 families in the live inventory with explicit capability/fidelity contracts | ✓ |
| Four-family pilot | Start with Codex, Qoder, Pi, and ZCode | |

**User's choice:** B — all observed families.
**Notes:** Coverage does not permit silent text fallback; partial native evidence must remain explicit.

---

## Raw evidence retention

| Option | Description | Selected |
|--------|-------------|----------|
| Immutable allowlisted snapshots | Content-addressed native snapshots; SQLite online backup; unmodeled safe data retained by source reference | ✓ |
| References and hashes only | Keep original paths/hashes and snapshot only mutable SQLite | |

**User's choice:** A — immutable allowlisted snapshots.
**Notes:** The no-loss guarantee is anchored in raw evidence plus resolvable provenance, not in forcing every native field into a flattened schema.

---

## Canonical reuse and activation

| Option | Description | Selected |
|--------|-------------|----------|
| Long-lived parallel authority | Build a separate event database and cut over after dual-run comparison | |
| Immediate replacement | Replace current canonical tables after tests | |
| Evolve canonical in place | Reuse canonical database/publication seams, add v2 event generations, retain old tables as compatibility projections, then atomically activate | ✓ |

**User's choice:** Asked why canonical could not be reused or adapted; this is captured as the in-place canonical evolution option.
**Notes:** Current message tables cannot themselves be the lossless semantic authority because they omit typed reasoning/tool/compaction/boundary/relationship semantics. Their consumer contract remains useful and is preserved as a projection.

---

## Extraction authority and priority

| Option | Description | Selected |
|--------|-------------|----------|
| Message/turn-first | Extract independently from each flattened message or turn | |
| Trace-first fixed model | Treat trace as the permanent extraction unit | |
| Replaceable views over events | Preserve canonical typed events; use versioned compaction/trace/session/cross-session views and a replaceable priority policy | ✓ |

**User's choice:** Compaction summaries first for scheduling, then trace/episode, session, and cross-session; trace must remain replaceable.
**Notes:** Summary and trace are navigation/synthesis layers, not fact authority.

---

## Semantic admission gate

| Option | Description | Selected |
|--------|-------------|----------|
| Regex/deterministic only | Admit based on structural rules and pattern filters | |
| LLM-only | Send all content to an LLM judge | |
| Deterministic then LLM | Privacy/structure/evidence gate first, semantic value judge second, with abstention | ✓ |

**User's choice:** Add an intelligent LLM decision rather than absorb everything or rely on regex alone.
**Notes:** No paid calls are authorized during Phase 62 planning or deterministic implementation/testing.

## the agent's Discretion

- Exact v2 type/table naming and internal module layout.
- Parser primitive sharing where family contracts remain explicit.
- Deterministic episode heuristics and fixture sampling details.

## Deferred Ideas

- Paid pilot/full extraction and activation of new KU data.
- Destructive removal of old canonical, raw, ledger, or vector artifacts.
