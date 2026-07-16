# Core
## Responsibility
Foundation contracts, paths, IDs and narrow shared utilities.
Includes **`llm.py`** (Phase 21): generic OpenAI-compatible client + retry,
extracted from conversation summary so graph/memory peers no longer import a
conversation domain hub.
## Boundaries
Cannot import domain, pipeline, service or evaluation modules.
## Entry points
Import from `personal_knowledge.core` (e.g. `project_paths`, `runtime_config`,
`llm.make_llm_client` / `llm._chat_with_retry`).
Legacy `integration.scripts.core` shims may re-export during compatibility.
## I/O and privacy
No direct raw/private content reads. Path resolution prefers Phase 20 trees
(`data/`, `var/`, `archive/`) via `project_paths`, with optional legacy fallback.
AgentsView live DB stays external and read-only.
`privacy_guard` is the shared exit sealer for MCP/REST retrieval payloads
(keys, tokens, PEM, assignment secrets → `[PRIVACY:…]`).
## Tests
Core contracts and path tests under `tests/` and `tests/governance/`.
## Ownership
Owner: platform. Status: supported. Last reviewed: 2026-07-16 (Phase 22 docs pass).

