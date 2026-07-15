# Repository Structure Map

**Mapped:** 2026-07-13  
**Scope:** repository root through deepest descendants; file names, metadata, code/config/docs inspected, but `.git`, cache bodies, runtime databases, imported raw data, session text, and private evaluation bodies were excluded from content inspection.

## Structural conclusion

The repository is not one homogeneous source tree. It contains six distinct classes of material that must be governed differently:

1. product source and tests;
2. immutable/private source data;
3. derived databases, indexes, reports, and runtime state;
4. planning and operational metadata;
5. vendored/external code;
6. quarantine/archive material.

The sustainable design is therefore **policy + generated manifest + automated validation**, not a README in every directory. Every file, including the deepest raw/import/archive file, must match exactly one manifest rule and inherit an owner, sensitivity, lifecycle, mutability, backup policy, and allowed dependency direction.

## Current root map

| Path | Current role | Governance class | Target treatment |
|---|---|---|---|
| `README.md`, requirements, `pytest.ini`, `.gitignore` | repository entry/config | tracked control plane | keep minimal and authoritative |
| `integration/` | production implementation plus runtime/data/report surfaces | mixed | retain, but enforce sub-surface boundaries |
| `tests/` | repository-level contract/regression tests | tracked test source | retain; mirror domains via markers/manifest rather than folders alone |
| `Agent/` | agent-derived structured data and DB | private data product | data surface, never imported as Python source |
| `Google/` | Google raw/structured data and legacy scripts | mixed private/legacy | raw immutable; migrate maintained scripts into adapters/pipeline |
| `imports/` | intake, batches, duplicate audit | private ingestion state | immutable batches with retention and lineage |
| `.planning/` | current GSD source of truth | tracked control plane | authoritative planning system |
| `.gsd/` | older GSD history | legacy planning | read-only historical compatibility; no new writes |
| `.github/` | CI automation | tracked control plane | enforce governance gates here |
| `.agents/`, `.codex/`, `.workbuddy/` | runtime-specific agent config | tool config | explicitly allowlisted; no project data |
| `.ai-bridge/` | external cloned project/reference | vendored/reference | pin provenance; exclude from product imports/tests unless promoted |
| `_recycle/` | quarantine from prior cleanup, including very deep copied environments | quarantine | retention manifest; never scan/import/test by default |
| `logs/` | operational output | ephemeral runtime | ignored, rotated, retention-bound |
| standalone HTML | generated visualization | generated artifact | move/declare under report artifact policy |

Observed scale illustrates why manual documentation cannot govern the tree: `_recycle/` alone contains roughly 9,210 files and reaches depth 17; the active non-private/non-runtime scan still includes roughly 985 files. Governance must operate on paths and metadata without opening private content.

## `integration/` current and target map

| Surface | Current responsibility | Target boundary |
|---|---|---|
| `scripts/core/` | paths, common utilities, repositories, embedding, Chroma, rules | dependency-free foundation except third-party libraries |
| `scripts/source_adapters/` | AgentView and Google source adapters | read-only source ports; emit canonical records only |
| `scripts/conversation/` | canonical conversation normalization and summaries | conversation domain; may depend on core/adapters |
| `scripts/knowledge/` | L1/L2 extraction, canonicalization, indexing lifecycle | knowledge-unit domain; no service/UI dependencies |
| `scripts/memory/` | memory candidates, promotion, lifecycle, profile outputs | memory domain; consume canonical knowledge/evidence contracts |
| `scripts/graph/` | relation candidates, judgments, triple graph | graph domain; consume stable IDs, never raw source paths |
| `scripts/vector/` | vector build/search and retrieval policy | retrieval infrastructure; adapters behind explicit interfaces |
| `scripts/evaluation/` | Phase 17 datasets, metrics, reports, gates | independent evaluation plane; read candidates, never promote except through gate command |
| `scripts/pipeline/` | orchestration and build steps | application layer; compose domains, contain no domain rules |
| `scripts/services/` | API, MCP, dashboard | delivery adapters; call application/domain APIs only |
| `scripts/examples/` | integration examples | non-production examples, tested for import/syntax |
| `scripts/_tools/` | one-off audit/migration/probe tools | developer tools with expiry/owner metadata |
| `scripts/*.py` | 86 compatibility shims | controlled compatibility layer; no new logic |
| `apps/personal_data_chatgpt/` | Node MCP/App UI | separate deployable adapter with its own package boundary |
| `prompts/` | versioned prompt/schema/rubric assets | immutable versioned AI contracts |
| `evals/` | public/synthetic evaluation assets | tracked evaluation inputs only; private cases remain runtime-only |
| `docs/` | focused operational/design docs | authoritative domain/runbook docs |
| `lib/` | vendored browser assets | pinned vendor assets with provenance/checksum |
| `db/` | production/backup DB files | private runtime state, ignored and retention-controlled |
| `runtime/` | private eval/runtime outputs | private ephemeral/stateful surface, never committed |
| `analysis/` | generated reports and historical analyses | generated artifacts with run IDs and retention |
| `structured/`, `raw_index/` | derived data | generated data product, traceable to run manifest |

## Entry points and compatibility layer

The canonical implementations now live in domain packages, but 86 files directly under `integration/scripts/` are compatibility shims. They preserve commands such as `python integration/scripts/run_pipeline.py` and legacy imports by forwarding to `pipeline.run_pipeline`, `knowledge.*`, `memory.*`, and other packages.

This is acceptable only as a temporary, governed API surface:

- canonical entry point: `python -m <domain>.<module>` or installed console command;
- legacy shim: declares `target`, `introduced`, `owner`, `usage telemetry`, and `remove_after` in the repository manifest;
- shim must contain forwarding logic only and have parity tests;
- new modules must not receive root shims unless a documented compatibility requirement exists;
- pipeline orchestration must call canonical modules, not shims, after the migration window;
- removal requires zero observed consumers plus a deprecation release, not ad-hoc deletion.

Current `pipeline/run_pipeline.py` still locates root script names, so the shim layer is an active dependency rather than historical residue. Phase 18 should first change orchestration to canonical module invocation, then retire shims by cohort.

## Hard-coded path findings

Maintained code still contains machine-specific paths:

- four scripts under `Google/structured/scripts/` point at `C:\\Users\\li\\Desktop\\数据分析` and old Takeout/output locations;
- three knowledge LLM scripts hard-code `C:/Users/li/google-cloud-sdk`;
- the MCP server example embeds the local repository path.

Target rule: executable code may obtain paths only through `core.project_paths`, explicit CLI parameters, or named environment variables. Documentation may show placeholders, never a real username. A CI path audit must reject new drive-letter/user-profile literals outside fixtures specifically marked `allow_hardcoded_path`.

## File-level governance manifest

Create one machine-readable manifest, for example `governance/repository-manifest.yaml`, whose ordered glob rules cover the complete tree. It should not enumerate millions of private files individually in Git. Instead, a generated local inventory expands rules to every file and records only metadata/hash where allowed.

Minimum rule fields:

```yaml
version: 1
rules:
  - id: product-python
    include: ["integration/scripts/**/*.py"]
    exclude: ["integration/scripts/*.py"]
    class: source
    owner: product
    sensitivity: internal
    lifecycle: maintained
    tracked: required
    allowed_dependencies: [core, source_adapters, domain]

  - id: legacy-cli-shims
    include: ["integration/scripts/*.py"]
    class: compatibility
    owner: platform
    lifecycle: deprecating
    tracked: required
    content_policy: forwarding_only

  - id: private-raw
    include: ["Google/raw/**", "imports/**", "Agent/structured/db/**"]
    class: private_data
    sensitivity: restricted
    lifecycle: immutable_or_retention_bound
    tracked: forbidden
    content_scan: metadata_only
```

The local generated inventory should contain, for every file:

`relative_path`, `rule_id`, `class`, `owner`, `sensitivity`, `source/run_id`, `tracked`, `generated`, `mutable`, `retention`, `checksum policy`, `backup policy`, and `last validation result`.

Validation invariants:

1. every file matches exactly one rule;
2. no rule overlap and no unclassified file;
3. tracked/ignored status agrees with the rule;
4. private content is never opened by governance scans—metadata and optional locally computed hash only;
5. generated files have a producing command/run manifest and are not edited manually;
6. source files have an owner and tests or an explicit exemption;
7. compatibility files have a canonical target and retirement condition;
8. quarantine/vendor files cannot be imported, discovered by pytest, or used as production inputs;
9. symlinks/reparse points cannot escape approved roots;
10. case collisions and Windows-invalid/reserved path forms fail validation.

This mechanism reaches the last file at any depth without producing thousands of stale README files. README files remain useful only at human entry boundaries: root, major deployables, public data contracts, and operationally distinct modules.

## Target repository layout

The target can be reached incrementally without a big-bang move:

```text
/
├── src/ or integration/scripts/       # product code, one canonical module per behavior
│   ├── core/
│   ├── adapters/
│   ├── domains/{conversation,knowledge,memory,graph}/
│   ├── retrieval/
│   ├── evaluation/
│   ├── application/
│   └── services/
├── apps/                              # independently runnable UI/MCP app
├── tests/                             # unit, contract, integration, e2e
├── assets/{prompts,evals,vendor}/     # versioned immutable inputs
├── var/{db,runtime,reports,logs}/     # ignored mutable outputs
├── data/{raw,staging,canonical}/       # ignored/private data planes
├── governance/                        # policy, manifest, schema, generated summaries
├── docs/                              # architecture/runbooks/ADRs
├── .planning/                         # single GSD source of truth
└── archive/                           # indexed, retention-bound cold material
```

Physical renaming is secondary. The immediate requirement is that current paths map unambiguously to these logical zones and dependency rules.

## Migration order

1. Establish manifest schema, ordered rules, metadata-only scanner, and zero-unclassified baseline.
2. Mark `.planning/` authoritative and `.gsd/` historical; stop dual writes.
3. Separate `integration/` tracked source/assets from private/generated `db/runtime/analysis/structured` surfaces.
4. Replace hard-coded paths with `project_paths`/CLI/env and add CI audit.
5. Change orchestration/tests to canonical package imports; inventory all 86 shims and retire by cohorts.
6. Register vendor/reference/quarantine provenance and retention; exclude them from tests/import resolution.
7. Add ownership, architecture dependency, pytest discovery, secret, generated-drift, and manifest-coverage gates.

## Definition of structural governance complete

- 100% of files, including deepest descendants, have exactly one manifest classification.
- 0 private/runtime/generated files are accidentally tracked.
- 0 source files depend on quarantine, raw data paths, or vendored reference projects.
- 0 new hard-coded user/machine paths.
- all public/CLI entry points are registered; every shim has a target and retirement status.
- generated reports/databases identify producer, input lineage, schema version, and run ID.
- CI and a local preflight reproduce the same governance result.

