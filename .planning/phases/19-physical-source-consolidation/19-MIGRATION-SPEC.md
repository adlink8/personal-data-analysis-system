# Phase 19 Source Migration Safety Contract

Every tracked-source cohort uses `governance/manifests/source/<cohort>.json` and `var/runtime/migration/source-<cohort>.journal.jsonl`.

Preflight freezes `git status --porcelain=v1`, source bytes hash, target absence/hash, Unicode NFC/case-folded path key, path length, volume, capacity and reparse status. Untracked files/directories at source or target are first-class conflicts. Manifest drift after approval aborts apply. Symlink/junction/reparse nodes are never followed.

Windows sequence: resolve workspace-contained absolute paths → reject reparse/case/Unicode collision → verify same volume/capacity → stage copy → byte hash → old→backup atomic rename → stage→target atomic rename → rewrite imports/docs as one journaled transaction → smoke. Any rewrite/test failure reverses journal to the exact pre-run bytes, never to HEAD. Backup remains until final phase verification.

Checkpoint tasks only approve an immutable manifest checksum. Separate auto apply tasks run `python -m personal_knowledge.governance.apply_source_migration --manifest <file> --apply`; rollback uses `--rollback --journal <file>`.

Phase19 transitional tree is generated from the 19-05 final inventory, not a closed handwritten root list. Every residual node must have an explicit `phase20-pending`, `retained-tooling`, or `approved-root-config` disposition; this includes `integration,Agent,Google,imports,_recycle,logs,.gsd,.ai-bridge,.pytest_cache`, root HTML and registered cache/generated remnants. `integration/` may retain only `db,runtime,analysis,raw_index,structured` and registered generated remnants; it contains no source/apps/assets/docs. Phase20 owns the final allowlist without legacy data roots. `integration/scripts/*.py=0`; legacy runtime refs=0. Phase17 eval paths are rewritten and its automated suite rerun while human status remains open.
