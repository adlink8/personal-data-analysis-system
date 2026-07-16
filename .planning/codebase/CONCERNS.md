---
mapped_at: 2026-07-16
last_mapped_commit: ce6dfde1f6d759368077e47288dcfc811f2960b9
focus: concerns
scope: risks-and-cleanup-candidates
branch: codex/llm-memory-mcp-integration
---

# Concerns — risks & cleanup candidates

Severity legend (disposal class):

| Class | Meaning |
|-------|---------|
| **safe-delete** | No runtime import path; regenerable or pure cache; delete after one dry-run inventory check |
| **quarantine-first** | Large / private / unclear consumers — move under `archive/quarantine/` with manifest, hold, then cohort-delete |
| **keep-facade** | Temporary re-export or CLI shim; retain until stated window + consumer zero + gate pass |
| **never-delete** | Product SSOT, schema DDL, active pointer contracts, or operational evidence still needed for forensics |

Automatic delete is **prohibited** (`governance/policies/retention.yaml`, `governance/baselines/storage_budgets.yaml`). Any physical delete needs owner approval + journal.

---

## 1. `tools/compat/v1_1` (shims)

| | |
|--|--|
| **Paths** | `D:\ADLINK\数据分析\tools\compat\v1_1\` (~87 `*.py` + README) |
| **Severity** | **keep-facade** (budget-gated); individual members → **quarantine-first** only after cohort approval |
| **Role** | v1.1 compatibility entrypoints that `import_module` into `personal_knowledge.domains.*` (themselves often facades → `application`/`evaluation`) |
| **Gate** | `python integration/scripts/governance/check_shim_budget.py --check` discovers **this** tree (`SCRIPTS = …/tools/compat/v1_1`) |
| **Manifest drift** | `governance/manifests/entrypoints.yaml` still claims `"root": "integration/scripts"` and `expected_count: 86` — **stale vs live discoverer**; fix manifest before any retirement |

**Risks**

- Double hop: `tools/compat/v1_1/X.py` → `domains.X` facade → `application`/`evaluation` (extra identity surface; `sys.modules` rebind).
- Shims still teach callers the **old** domain path; new code should use `personal_knowledge.application.*` / `evaluation.*` (`docs/architecture/repository-zones.md`).
- Retirement preview deferred: `.planning/phases/18-full-repository-governance/18-03-SHIM-RETIREMENT-PREVIEW.md` — **no shim delete authorized** (2026-07-13 DEFERRED).
- Baseline-only-down: additions must fail `check_shim_budget`; count drift is a governance fail, not a delete trigger.

**Actions**

1. Align `governance/manifests/entrypoints.yaml` `shim_registry.root` → `tools/compat/v1_1` and re-count expected.
2. Keep product surface on console scripts (`pk-sync`, `pk-ku`, `rag-search`, … in `pyproject.toml`); do not document shim paths for daily ops.
3. After **2026-08-13** domain-facade cleanup: re-point shims to **canonical** modules (skip domains hop), then retire leaf-library cohort only with consumer=0 + rollback manifest.
4. **Do not** bulk-delete this directory.

---

## 2. `integration/scripts` (mostly pyc + governance)

| | |
|--|--|
| **Paths** | `D:\ADLINK\数据分析\integration\scripts\` |
| **Live source** | `governance/*.py` (preflight, shim budget, inventory, path/docs/planning checks, migration apply/plan) |
| **Residue** | Domain package trees (`knowledge/`, `memory/`, …) populated almost entirely by `__pycache__/*.pyc`; root-level shims **moved** to `tools/compat/v1_1` |
| **Severity** | **safe-delete** for orphan `*.pyc` / empty package shells after import-smoke; **keep-facade** for `governance/`; **quarantine-first** for any remaining real `.py` that is not governance |

**Risks**

- Stale bytecode: import if someone still puts `integration/scripts` on `sys.path` can load **wrong generation** vs `src/personal_knowledge`.
- README still describes root shims + `python integration/scripts/build_*.py` (`integration/scripts/README.md`) — **docs lie** post Phase 19/20/21; operators follow dead paths.
- `cli.py` legacy fallback still probes `…/integration/scripts` when package import fails (`src/personal_knowledge/cli.py`).
- Manifest / tools.json still reference `integration/scripts/_tools/*` while live tools live under `tools/forensics/`, `tools/migrations/`.

**Actions**

1. Delete only `__pycache__` under `integration/scripts/**` after confirming no `.py` body remains in those domain subpackages (governance **excluded**).
2. Rewrite `integration/scripts/README.md` to: “governance + historical cache only; product code = `src/personal_knowledge`; shims = `tools/compat/v1_1`”.
3. Update `governance/manifests/source/tools.json` inverse paths if `_tools` no longer exists under integration.
4. Keep `integration/scripts/governance/` until preflight CI entry is moved under `src/personal_knowledge/governance` or `tools/supported`.

---

## 3. `integration/analysis.bak-phase20` (~65MB)

| | |
|--|--|
| **Paths** | `D:\ADLINK\数据分析\integration\analysis.bak-phase20\` |
| **Live reports** | `var/reports/analysis/` (Phase 20 target); thin live stub `integration/analysis/ai_context/` |
| **Severity** | **quarantine-first** (not safe-delete while recovery window open) |
| **Contents** | Historical `ai_context/`, `evaluations/`, `stage1_profile/`, `refactoring/` reports, charts, canary supersets |

**Risks**

- Disk / IDE index noise; privacy class inherits embedded personal analysis labels.
- Operators may open **bak** paths thinking they are SSOT; live writes should go to `var/reports/analysis/`.
- Sibling bak surfaces amplify confusion: `integration/db.bak-phase20/`, `integration/runtime.bak-phase20/`, `integration/raw_index.bak-phase20/`, root `Agent.bak-phase20/`, `Google.bak-phase20/`, `imports.bak-phase20/`, `logs.bak-phase20/`, `_recycle.bak-phase20/`.

**Actions**

1. Confirm live regeneration: canary/eval reports currently written under `var/reports/analysis/ai_context/` (see `docs/runbooks/ku-incremental.md`).
2. After recovery window close: move entire `*.bak-phase20` cohort into `archive/quarantine/bak-phase20-<date>/` with MANIFEST; hold per `retention.yaml` `archive-quarantine`.
3. Never import bak trees as Python packages; exclude from tests/inventory default scan.
4. **never-delete** any bak tree that is the **only** copy of a needed eval evidence until rebuildability proven.

---

## 4. `archive/` (~4GB quarantine)

| | |
|--|--|
| **Paths** | `D:\ADLINK\数据分析\archive\` |
| **Budget** | `governance/baselines/storage_budgets.yaml` → archive budget 6 GiB (`6442450944`) |
| **Severity** | **quarantine-first** hold; physical delete = **never** without cohort review |

| Subpath | Content | Note |
|---------|---------|------|
| `archive/quarantine/_recycle/2026-07-12_structure_cleanup/` | Soft-deleted Agent/Google/GPT trees, raw agent exports, SQLite, empty stubs | ~9k files; depth high; **private** |
| `archive/quarantine/desktop-strays-20260713/` | Hash-named `.py` strays + `quarantine-manifest.json` | Already manifested |
| `archive/planning/` | Historical GSD (`.gsd`) | read-only |
| `archive/vendor-reference/` | Vendored bridge refs | not product import |

**Risks**

- Accidental scan/import/test of quarantine (policy: not an import source — `archive/README.md`, `docs/architecture/repository-zones.md`).
- Private conversation dumps under recycle Agent raw trees if tools walk repo root.
- Storage pressure vs budget (report_only overage, not auto-delete).

**Actions**

1. Keep gitignore + inventory exclude on `archive/**` private bodies.
2. Cohort-review `_recycle` only with lineage journal; prefer cold offline storage over in-repo forever.
3. Do not “clean by deleting” to free space without owner approval.
4. **safe-delete** only: empty `root_empty_stubs/` style zero-byte noise **inside** quarantine after MANIFEST update (still requires approval).

---

## 5. `domains/*` facades (cleanup window **2026-08-13**)

| | |
|--|--|
| **Paths** | `src/personal_knowledge/domains/{conversation,graph,knowledge,memory}/*.py` |
| **Also** | `src/personal_knowledge/retrieval/evaluate_vector_*.py`, `compare_*_generations.py` → `evaluation/vector/` |
| **Severity** | **keep-facade** until 2026-08-13; then remove after import migration |
| **Canonical** | `application/{conversation,graph,knowledge,memory}/`, `evaluation/{…,vector}/`, `core/llm.py` |
| **Sole non-facade domain logic** | `domains/knowledge/migrate_add_knowledge_unit_tables.py` (`SCHEMA_SQL`) — **never-delete** without schema migration plan |

**Pattern** (example `domains/knowledge/refresh_knowledge_units.py`):

```text
_canonical = import_module("personal_knowledge.application.knowledge.refresh_knowledge_units")
sys.modules[__name__] = _canonical
```

**Risks**

- New code still imports `domains.*` → cleanup breakage after 2026-08-13.
- `tools/compat/v1_1` targets `domains.*` today — facade removal **breaks shims** unless retargeted first.
- Residual: `retrieval/memory.py` lazy-imports `domains.graph.query_graph` (Phase 21 deferred, `21-VERIFICATION.md`).
- ~63 facades counted at Phase 21 complete.

**Actions (ordered)**

1. Grep/CI: ban new `from personal_knowledge.domains…` outside tests/shims (new code → application/evaluation/core).
2. Before window end: retarget `tools/compat/v1_1` → application/evaluation canonical.
3. Fix `retrieval/memory.py` to import `application.graph.query_graph` (or retrieval-local API).
4. On/after 2026-08-13: delete facade modules only; **keep** `migrate_add_knowledge_unit_tables.py` + domain `__init__`/README stating rules-only.
5. Re-run architecture-boundary + import smoke + REST/MCP health.

---

## 6. `rag-pipeline` / memory experimental path

| | |
|--|--|
| **CLI** | `rag-pipeline` → `personal_knowledge.cli:pipeline` (`pyproject.toml`) |
| **Impl** | `src/personal_knowledge/application/run_pipeline.py` (steps 1–12: integrated system, PE enrich, memory store/graph, vectors, context docs) |
| **Severity** | **keep-facade** (retired redirect + forensics); underlying modules **never-delete** until experimental data lifecycle closed |

**Behavior**

- Default: print redirect to `pk-sync` / `pk-ku`, **exit 2**.
- Forensics only: `PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated`.
- Memory / `personal_events` vectors are **not** knowledge SSOT (`AGENTS.md`, `docs/runbooks/product-sync.md`).

**Risks**

- Agents/docs outside repo still teach `rag-pipeline` or `run_pipeline` for “daily sync”.
- Accidental legacy run **rebuilds** `personal_system.sqlite` / memory layers (paid + destructive relative to PE rebuild step 1).
- Experimental memory tables/collections can be mistaken for KU active index.

**Actions**

1. Product path only: `pk-sync conversations [--write]` then optional `pk-ku …`.
2. Leave CLI stub forever or until all external docs updated; do not remove env gate.
3. Treat memory promotion/apply scripts as experimental: no auto-chain from `pk-sync`.
4. Docs that still say “run integration/scripts/run_pipeline.py” (e.g. stale root snippets) must point to `pk-sync`.

---

## 7. CLI gaps: canary, watermark advance, Google sync (not on `pk-ku` yet)

Product KU CLI: `src/personal_knowledge/application/ku.py` + entry `pk-ku`.

| Capability | Exists in code? | On `pk-ku`? | Operator today |
|------------|-----------------|-------------|----------------|
| inspect / prepare / extract / status / extract-gate / canonical / publish / vector / promote / workflow | Yes | **Yes** | `pk-ku …` |
| Watermark **floor** on prepare (`--extract-since-watermark`) | Yes | **Yes** (policy flag only) | prepare flags |
| Watermark **advance** / journal commit (`advance_watermark`, journal commit in `refresh_knowledge_units.py`) | Yes | **No** dedicated subcommand | module / promote-adjacent journal APIs — easy to skip or call wrong |
| Canary eval | Yes — `evaluation/knowledge/evaluate_knowledge_canary.py` (also domain facade) | **No** | `python -m personal_knowledge.evaluation.knowledge.evaluate_knowledge_canary …` then `pk-ku promote --require-eval-pass` |
| Google activity sync / light assertions / normalized events | Yes — `application/build_google_*`, `application/google_structure_lifecycle.py`, adapters | **No** on `pk-ku` or `pk-sync` | manual `python -m personal_knowledge.application.…` |
| Full inventory backfill | Yes | **Intentionally absent** | see §8 |

**Risks**

- Operators finish extract/publish/vector but **never advance watermark** → prepare floors / baselines drift; inspect vs prepare conflicts (known defect note in `ku-incremental.md`).
- Canary stays at `gate.status=pending_labels` while humans promote without labels if they skip `--require-eval-pass`.
- Google pipeline remains tribal knowledge; easy to re-run wrong generation or mix with KU path.

**Actions**

1. Add (when productizing): `pk-ku canary …` wrapping evaluate_knowledge_canary; `pk-ku watermark show|advance` bound to journal preconditions.
2. Add `pk-sync google` (or `pk-google`) only after runbook parity with conversation sync.
3. Until then: document exact module commands in runbooks (already partially in `ku-incremental.md` Step E) — **do not** paper over by editing application code for daily ops.

---

## 8. Full inventory backfill still via modules (not `pk-ku`)

| | |
|--|--|
| **Modules** | `application/knowledge/build_knowledge_inventory.py`, `build_knowledge_units_prod.py` |
| **Intent** | Phase 14 **KU-05** rare production backfill — freeze **all** eligible evidence |
| **Severity** | Capability **never-delete**; daily invocation **forbidden** (process, not code delete) |

**Hard product rule** (`docs/runbooks/ku-incremental.md`, `docs/AGENTS.md`):

- Daily: delta only via `pk-ku`.
- Full freeze + `prod --start` **not** exposed on `pk-ku` by design.
- `pk-ku extract` rejects non-`ir_*` / non-incremental runs unless `PK_KU_ALLOW_NON_INCREMENTAL_RUN=1`.

**Risks**

- Agents treat “prepare no_op” as permission to full-inventory (see §9).
- Direct module CLI still fully available — guard is social/docs + env flags, not hard removal.

**Actions**

1. Keep full inventory **off** `pk-ku`.
2. Optional: require second env flag for `build_knowledge_inventory --write` in production DBs.
3. Planned backfill only with written inventory_id, cost estimate, human approval.

---

## 9. Mistaken full KU runs still in DB (data not code)

| | |
|--|--|
| **Severity** | **never-delete** blind rows; **quarantine-first** operational handling |
| **Evidence** | `docs/runbooks/ku-incremental.md` §4 **Incident 2026-07-16** |

**Incident facts (documented)**

- Agent ran **full inventory** after prepare `no_op` while inspect showed ~4k `new_refs`.
- Process stopped; **active pointer left unchanged** (`var/db/knowledge_index_active.txt`).
- Forbidden: resume mistaken full-inventory run “until pending=0”.

**Later successful delta cycle (same doc, reference)**

- Run `ir_4cd8af4ad31ccdc2` / delta `di_9e002cdac7af1460` — extract/canonical/publish/vector path; canary pending_labels; active still `knowledge_units_205bff9560b9_20260712142938`.

**Where residue lives (data plane)**

- KU run / item ledgers inside project SQLite under `var/db/` (and any canonical KU tables) — not in git.
- May include full-inventory `run_id`s with pending/failed items, partial staging, or orphan candidate Chroma collections.
- Active pointer and knowledge SSOT must **not** be rewritten to “finish” those runs.

**Actions**

1. Inventory mistaken runs: list run_ids with full-inventory lineage; mark status abandoned in ops notes (no mass SQL delete without journal).
2. Do **not** `--resume` those run_ids for daily work.
3. Orphan Chroma candidates: report via vector generation compare tools; delete collections only after rebuildability + approval (retention derived-artifact policy).
4. Fix prepare/delta defect (inspect≠prepare) so agents are not tempted; treat as product bug not operator inventiveness.
5. Code changes do not erase ledger rows — cleanup is **data ops**, tracked outside this file’s code disposal classes.

---

## Cross-cutting risk matrix

| Concern | Primary severity | Blocks product? | Next concrete step |
|---------|------------------|-----------------|--------------------|
| Shim path + entrypoints.yaml drift | keep-facade | No (governance fail) | Fix `entrypoints.yaml` root/count |
| integration/scripts pyc husks | safe-delete (cache) | No | Purge `__pycache__`; rewrite README |
| analysis.bak-phase20 + root `*.bak-phase20` | quarantine-first | No | Cohort archive after recovery window |
| archive/ ~4GB | quarantine-first | No | Hold; optional offline cold storage |
| domains facades → 2026-08-13 | keep-facade | Yes after window if unmigrated | Retarget shims; grep ban domains imports |
| rag-pipeline / memory batch | keep-facade (retired) | Yes if misused | Keep exit-2; never document as daily |
| CLI gaps (canary/watermark/google) | process gap | Partial | Module runbook until CLI exists |
| Full inventory modules | never-delete capability | Yes if misused | Env/process gates; no pk-ku expose |
| Mistaken full KU DB rows | data quarantine | Cost/quota risk | Abandon runs; never resume to zero |

---

## Explicit never-delete (code/control plane)

- `src/personal_knowledge/application/ku.py`, `sync.py`, `cli.py` product entries  
- `src/personal_knowledge/application/knowledge/refresh_knowledge_units.py` and KU ledger writers  
- `domains/knowledge/migrate_add_knowledge_unit_tables.py` (`SCHEMA_SQL`)  
- `data/canonical/**` dialogue + knowledge SSOT (private data)  
- `var/db/knowledge_index_active.txt` + active Chroma generation contracts  
- `governance/policies/*`, evaluation public contracts under `assets/evals/`  
- AgentsView live DB path (external) — never relocate/write  

---

## Mapping notes

- Supersedes prior `.planning/codebase/CONCERNS.md` body focused on Phase 18 general governance; that content is partially absorbed into P0/P1 themes above where still true (shim budget, private data, promote-without-eval).
- Physical sizes (~65MB bak analysis, ~4GB archive) are operator-scale estimates from zone layout + prior planning; re-measure with metadata-only inventory before disposal approvals.
- `automatic_delete: prohibited` remains global default.
