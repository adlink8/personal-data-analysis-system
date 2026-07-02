# Phase 10 Context: LLM Memory Relation Graph

## Current Facts

- Current long-term memory tables live in `integration/db/personal_system.sqlite`.
- `memory_items` is the persisted long-term memory node table.
- `memory_relations` already stores first-generation rule-based memory-to-memory edges.
- Latest observed rule graph size: `memory_items=194`, `memory_relations=27`.
- Existing relation generator: `integration/scripts/build_memory_graph.py`.
- Existing memory graph viewer: `integration/scripts/query_graph.py visualize`, outputting `integration/analysis/memory_graph.html`.
- Phase 09 added LLM-assisted conversation relation candidate flow:
  - `graph_relation_candidate_proposals`
  - `graph_relation_candidates`
  - `graph_relation_judgments`
  - `graph_relation_review_queue`
  - `memory_promotion_candidates`

## Problem

The current memory graph has memory-to-memory links, but those links are rule-based. The system does not yet have an auditable LLM judgment layer for long-term memory relationships themselves.

This means the visualization can show existing long-term memory edges, but cannot distinguish:

- rule-generated memory edges,
- LLM-proposed memory-memory relation candidates,
- LLM-judged accepted/rejected/review edges,
- evidence or risk flags behind those judgments.

## Goal

Add an auditable LLM-assisted long-term memory relation layer without silently mutating the persisted memory graph.

The phase should produce:

1. A bounded candidate generator for memory-to-memory relation proposals.
2. A deterministic gate/review layer for LLM memory relation judgments.
3. Reports showing exact counts and example judgments.
4. Visualization support so the user can inspect rule edges and LLM-judged memory edges separately.

## Non-Goals

- Do not overwrite or rebuild `memory_items`.
- Do not silently write accepted LLM judgments into `memory_relations`.
- Do not require live LLM credentials for unit tests.
- Do not pass API keys, tokens, cookies, or other secrets to subagents.
- Do not remove the existing rule-based `build_memory_graph.py` path.

## Design Boundary

Use a candidate/audit layer parallel to existing Phase 09 patterns:

- `memory_relation_candidate_proposals`: raw LLM proposal/audit output.
- `memory_relation_candidates`: schema/evidence-gated memory-memory candidates.
- `memory_relation_judgments`: deterministic or LLM judgment result for each candidate.
- `memory_relation_review_queue`: edges that need human review.

Only a future explicit promotion step may write reviewed edges into `memory_relations`.

## Relation Types

Initial allowed relation vocabulary:

- `same_subject`
- `related_topic`
- `enables`
- `uses_tool`
- `embodies`
- `conflicts_with`
- `refines`
- `supports`
- `no_relation`

The gate must reject unknown relation types.

## Evidence Rules

Every non-`no_relation` judgment must reference evidence from the two memory records only:

- memory ids,
- memory subjects/descriptions,
- memory metadata,
- linked event ids or source refs when available.

The gate should reject or mark review for:

- unsupported evidence,
- low confidence,
- pair conflicts,
- unknown relation type,
- self-loop relation,
- missing source/target memory id.

## Visualization Requirement

The memory visualization must make source clear:

- existing rule edge: current `memory_relations`.
- LLM candidate/judgment edge: new memory relation judgment layer.
- rejected/no-relation edges should not clutter the default view.
- review/accepted status should be visible in edge title or label.

## Acceptance Criteria

- Candidate generation runs in dry-run and write mode with a small `--limit`.
- Tests cover schema creation, relation validation, evidence gating, and no direct `memory_relations` mutation.
- Visualization command can include LLM memory relation edges while still supporting the old default graph.
- Reports include total candidates, accepted, rejected, review, relation type distribution, and examples.
- Existing Phase 09 tests still pass after integration.
