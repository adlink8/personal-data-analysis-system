# Technical Stack and File-Level Governance

**Scope:** repository-wide governance baseline for Phase 18  
**Evidence date:** 2026-07-13  
**Inspection rule:** configuration, source, schema references, paths, counts, and file metadata only; private record bodies were not read.

## Runtime stack

| Layer | Current implementation | Version / contract | Governance requirement |
|---|---|---|---|
| Primary runtime | Python | Python 3.14 is documented as verified | Pin the supported minor version in one machine-readable file; CI must test it. |
| Data processing | pandas, NumPy | `pandas>=3.0`, `numpy>=2.4` | Replace open-ended lower bounds with a lock/constraints file for reproducible rebuilds. |
| Visualization | Matplotlib, Plotly, Streamlit | `matplotlib>=3.10`, `plotly>=6.8`, `streamlit>=1.58` | Generated PNG/HTML is an artifact, not source; every report records input/run/config hashes. |
| Validation | Pydantic | `>=2,<3` | Treat schemas as public internal contracts and version breaking changes. |
| Test | pytest, pytest-asyncio | `>=8.0`, `>=0.24`; discovery restricted to `tests/` | Add dependency lock, governance tests, and artifact/privacy checks to the default suite. |
| Relational store | SQLite; one DuckDB graph artifact | Python stdlib SQLite; DuckDB used by analysis | All mutable builds use staging + integrity check + atomic publish; live source DBs are read-only. |
| Vector store | Chroma REST API v2 | local ports, KU currently uses 8001 | Persist collection manifests and active pointer; candidate must pass eval before promotion. |
| Embeddings | `BAAI/bge-small-zh-v1.5`, 512 dimensions | sentence-transformers + torch supplied outside requirements | Remove hard-coded `D:\\models`; configure model path, model digest, dimension, device, and offline mode. |
| Local services | stdlib HTTP REST, MCP SDK, Streamlit | REST 8000; Apps adapter 8789; KU Chroma 8001 | Bind loopback by default; external binding requires auth, TLS/reverse proxy, and explicit approval. |
| ChatGPT Apps adapter | Node.js ES modules | Node `>=20`; no npm runtime dependencies declared | Commit lockfile when dependencies appear; preserve read-only downstream contract. |
| LLM extraction/judging | Vertex Gemini and OpenAI-compatible endpoints | model names occur in scripts; API credentials via environment | Centralize provider/model/config; log provider/model/prompt/schema versions without logging secrets or private prompts. |

## Dependency findings

- `requirements.txt` does not declare every runtime import used by optional/live paths (`requests`, `openai`, `httpx`, `sentence-transformers`, `torch`, and DuckDB are examples). The comments say some are machine-provided, which is not reproducible enough for a sustainable architecture.
- Exact transitive dependency resolution is absent. Add `requirements.lock` or a chosen equivalent, generated from a reviewed input file. Separate `core`, `llm`, `vector`, `ui`, and `dev` extras if installation weight matters.
- Node currently has no third-party package dependencies. Keep `package.json` as the contract and add/commit `package-lock.json` whenever dependencies are introduced.
- Local embedding is privacy-preserving, but its model path is machine-specific. `PERSONAL_DATA_EMBED_MODEL_PATH` should replace the literal drive path; startup should fail with an actionable message when unavailable.

## Architectural boundaries

```text
private source snapshots (R4)
  -> normalized source stores (R4)
  -> integrated SQLite / canonical evidence (R4)
  -> knowledge units + vector generations (R3/R4)
  -> evaluation registry and reports (R2-R4)
  -> read-only CLI / REST / MCP / Apps surfaces (R2)
```

No downstream layer may write back into a live external source. Promotion, rollback, reconcile, and lifecycle mutation remain offline administrative commands and must not be exposed by REST/MCP tools.

## Repository data zones

| Zone | Examples | Class | Source controlled? | Lifecycle |
|---|---|---:|---|---|
| Product source | `integration/scripts/**`, `integration/apps/**`, `tests/**`, prompts | R1/R2 | Yes | Review, test, version, deprecate through compatibility shims only when needed. |
| Public eval fixtures | `integration/evals/knowledge_units/*.synthetic.jsonl`, policies/rubrics | R1/R2 | Yes | Version with schema and dataset card; prohibit private excerpts. |
| Raw/private intake | `Google/raw`, `imports/**`, AgentsView live DB | R4 | No | Read-only intake/snapshot; record origin, consent, retention, and deletion lineage. |
| Normalized private stores | `Agent/structured/db`, `Google/structured`, `integration/structured` | R4 | No except scripts/README | Rebuildable where possible; manifest source snapshot and transformation version. |
| Integrated databases | `integration/db` | R4 | No | Staging, integrity gate, atomic publish, backup/rollback, retention cap. |
| Vector generations | Chroma collections and pointers | R3/R4 | No | Immutable candidate generations; promote by pointer; delete only after retention window and approval. |
| Analysis/reports | `integration/analysis` | R2-R4 | No by default | Separate sanitized shareable reports from private reports; TTL and input hashes required. |
| Runtime/private eval | `integration/runtime`, private gold JSONL | R4 | No | Ephemeral or explicitly retained; never included in packages or screenshots. |
| Logs/process state | `logs`, `*.log`, `*.pid`, service stdout/stderr | R2-R4 | No | Redact identifiers/content; rotate; short TTL; PID files removed on clean shutdown. |
| Soft archive | `_recycle` | inherits source class | No | Inventory and expiry review; archive is not a backup and must not bypass privacy deletion. |

Privacy classes: **R1 public**, **R2 internal metadata/code**, **R3 derived personal inference**, **R4 raw or linkable personal evidence/secrets**. When uncertain, use the higher class.

## Observed footprint requiring lifecycle controls

Metadata-only scan found approximately: `integration/db` 216 MB, `Agent` 580 MB, `Google` 156 MB, `imports` 578 MB, `integration/analysis` 68 MB, and `integration/structured` 19 MB. These are local operational datasets, not Git assets. Size budgets, retention limits, backup ownership, and rebuild/run manifests are therefore required.

## File-level governance record

Every file, including files at the deepest directory level, must be represented by a generated inventory row. Do not hand-maintain one row per file. The scanner should emit a private machine-readable manifest and a sanitized summary with these fields:

| Field | Meaning |
|---|---|
| `path` | Project-relative canonical path; reject traversal and external paths unless declared integration inputs. |
| `kind` | source, config, test, prompt, fixture, raw, normalized, database, vector, report, runtime, log, archive, documentation. |
| `owner_module` / `maintainer` | Owning subsystem and responsible role. |
| `privacy_class` | R1-R4; inherited from parent unless explicitly raised. |
| `git_policy` | track, ignore, generated-ignore, private-ignore, archive-ignore. |
| `source_of_truth` | Whether authoritative; if derived, name upstream artifact/run. |
| `producer` / `consumers` | Script/job that creates it and code paths that consume it. |
| `schema_version` / `format` | Contract version, encoding, database migrations, vector dimension where relevant. |
| `content_hash` / `size` / `mtime` | Integrity and drift metadata; hashes of R4 stay private. |
| `run_id` / `input_hashes` / `config_hash` | Reproducibility lineage for generated files. |
| `retention` / `disposal` | TTL or keep count; approval and secure deletion policy. |
| `backup` / `restore_tested_at` | Backup tier and last restore proof for authoritative data. |
| `validation` | Tests, schema checks, secret scan, privacy scan, or visual QA required. |
| `status` | active, candidate, deprecated, quarantined, archived, orphaned. |
| `last_reviewed` | Governance review date and decision reference. |

## Required automated gates

1. Inventory completeness: every non-Git-internal file has exactly one effective governance policy through explicit row or deterministic parent inheritance.
2. Privacy: R3/R4 cannot be tracked, packaged, or rendered into public reports; secret scan checks source and staged files.
3. Reproducibility: every generated DB/vector/report has producer, run ID, inputs, config, schema, and content hash.
4. Drift: documentation paths, requirements, planning status, schemas, and active pointers are checked against runtime facts.
5. Orphans: files with no owner/producer/consumer are reported; deletion remains a separate approved operation.
6. Portability: reject user-name, Desktop, and fixed-drive paths in production code; allow documented external defaults only through configuration.
7. Storage: report per-zone growth, retention violations, stale WAL/SHM, abandoned candidates, and unrotated logs.

## Immediate stack risks

- Machine-specific embedding path blocks reproducible installation.
- Optional runtime dependencies are used but not fully declared or locked.
- Broad `*.json`, `*.html`, and image ignores protect privacy but can silently hide legitimate source/config; allowlists must be narrow and governance-tested.
- Some scripts remain compatibility shims beside modular implementations. Inventory must mark canonical implementation vs shim to prevent duplicated maintenance.
- Current worktree contains many modified/untracked planning and source files; Phase 18 must classify them without deleting or overwriting user work.
