# Phase 10 Plan: LLM Memory Relation Graph

## Objective

Add an auditable LLM-assisted relation layer for long-term memories, then expose those judged edges in the graph visualization.

## Scope

### In Scope

1. Add prompt/schema contract for memory-memory relation proposal.
2. Add a bounded candidate generator over `memory_items`.
3. Add a gate/evaluation layer for relation judgments.
4. Add reports under `integration/analysis/ai_context/`.
5. Add visualization option to include accepted/review LLM memory relation edges.
6. Add unit tests for schema, gate behavior, and no silent long-term memory writes.

### Out of Scope

- Automatic promotion into `memory_relations`.
- Changing existing memory item generation.
- Rebuilding vector stores.
- Running unbounded live LLM calls.

## Work Breakdown

### Wave 1: Contract and Candidate Layer

Owner: subagent A.

Files:

- `integration/prompts/memory_relation_proposal/v1_main.md`
- `integration/prompts/memory_relation_proposal/v1_schema.md`
- `integration/scripts/build_memory_relation_candidates.py`
- `tests/test_memory_relation_candidates.py`

Tasks:

1. Create tables:
   - `memory_relation_candidate_proposals`
   - `memory_relation_candidates`
2. Build deterministic memory pair recall from:
   - same or related subjects,
   - shared memory type/subtype,
   - existing `memory_relations`,
   - shared linked events/source refs when present.
3. Add optional live LLM proposal call using the existing `build_conversation_summary.make_llm_client()` pattern.
4. If no live LLM credentials are available, write only blocked/audit proposal records and do not fabricate accepted candidates.
5. Gate LLM proposals before writing candidates.

Verification:

```powershell
python integration\scripts\build_memory_relation_candidates.py --dry-run --limit 5
python integration\scripts\build_memory_relation_candidates.py --write --limit 5
python -m unittest tests.test_memory_relation_candidates
```

### Wave 2: Judgment/Evaluation Gate

Owner: subagent A.

Files:

- `integration/scripts/evaluate_memory_relation_candidates.py`
- `tests/test_memory_relation_candidates.py`

Tasks:

1. Create tables:
   - `memory_relation_judgments`
   - `memory_relation_review_queue`
2. Evaluate candidates with deterministic evidence/confidence rules.
3. Accept only supported, non-conflicting, high-confidence non-`no_relation` rows.
4. Reject self-loops, unknown relation types, unsupported evidence, and low-confidence rows.
5. Generate JSON and Markdown reports.

Verification:

```powershell
python integration\scripts\evaluate_memory_relation_candidates.py --write
python -m unittest tests.test_memory_relation_candidates
```

### Wave 3: Visualization Integration

Owner: subagent B.

Files:

- `integration/scripts/query_graph.py`
- `tests/test_memory_graph_visualization.py` if useful and low-risk.

Tasks:

1. Add a CLI option such as `--include-llm-relations`.
2. Load accepted/review `memory_relation_judgments` joined to `memory_relation_candidates`.
3. Add LLM edges with distinct labels/titles/colors.
4. Preserve current default behavior when the option is not passed.
5. Keep HTML generation UTF-8 safe on Windows.

Verification:

```powershell
python integration\scripts\query_graph.py visualize
python integration\scripts\query_graph.py visualize --include-llm-relations
```

### Wave 4: Integration Verification

Owner: main agent.

Tasks:

1. Merge subagent outputs.
2. Run targeted tests.
3. Run bounded pipeline commands.
4. Regenerate visualization artifacts.
5. Record actual counts in `VERIFICATION_2026-07-02.md`.

Verification:

```powershell
python -m unittest tests.test_memory_relation_candidates tests.test_memory_promotion_candidates tests.test_memory_candidate_extraction tests.test_memory_gate_repair_loop tests.test_memory_promotion_review
python integration\scripts\build_memory_relation_candidates.py --dry-run --limit 5
python integration\scripts\build_memory_relation_candidates.py --write --limit 5
python integration\scripts\evaluate_memory_relation_candidates.py --write
python integration\scripts\query_graph.py visualize --include-llm-relations
```

## Subagent Coordination

- Subagent A owns candidate and gate scripts plus prompt contract/tests.
- Subagent B owns visualization changes only.
- Main agent owns phase docs, final integration, live bounded verification, and any conflict resolution.
- No subagent should edit unrelated Phase 08/09 docs or revert existing dirty worktree changes.

## Success Definition

The phase is successful when the user can open the memory graph and see both:

- current long-term memory relations from `memory_relations`,
- LLM-audited memory-memory relationship edges with status/evidence visible,

while the persisted long-term memory tables remain unchanged unless a future explicit promotion command is introduced.
